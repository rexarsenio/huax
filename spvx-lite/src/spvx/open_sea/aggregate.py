"""SQL aggregation helpers for open-sea analytics."""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from pathlib import Path
from typing import Sequence

import duckdb
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from spvx.open_sea.config import OpenSeaConfig
from spvx.open_sea.corridors import CorridorDefinition, iter_corridors

LOG = logging.getLogger(__name__)


def _sql_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _update_gate_flux_hits(
    con: duckdb.DuckDBPyConnection,
    start_date: dt.date,
    config: OpenSeaConfig,
) -> None:
    flux_cfg = config.flux

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS gate_flux_daily_deduplicated (
            ds DATE,
            gate_id VARCHAR,
            direction VARCHAR,
            crossings INTEGER,
            unique_vessels INTEGER
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS gate_flux_daily (
            ds DATE,
            gate_id VARCHAR,
            direction VARCHAR,
            crossings INTEGER
        )
        """
    )

    con.execute("DELETE FROM gate_flux_daily WHERE ds >= ?", [start_date])
    con.execute("DELETE FROM gate_flux_daily_deduplicated WHERE ds >= ?", [start_date])

    con.execute("DROP TABLE IF EXISTS tmp_flux_rehit")
    con.execute("CREATE TEMP TABLE tmp_flux_rehit (group_id VARCHAR, rehit_hours DOUBLE)")
    if flux_cfg.rehit_hours_by_group:
        con.executemany(
            "INSERT INTO tmp_flux_rehit VALUES (?, ?)",
            [(group, hours) for group, hours in flux_cfg.rehit_hours_by_group.items()],
        )

    tanker_only_flag = flux_cfg.tanker_only
    sog_min = flux_cfg.sog_min_kn
    rehit_default = flux_cfg.rehit_hours_default

    con.execute("DROP TABLE IF EXISTS tmp_gate_hits")
    con.execute(
        """
        CREATE TEMP TABLE tmp_gate_hits AS
        WITH recent AS (
            SELECT
                gc.mmsi,
                gc.gate_id,
                gc.ts,
                COALESCE(f.sog, gc.sog, 0.0) AS sog,
                COALESCE(f.is_tanker, CASE WHEN f.shiptype_num BETWEEN 80 AND 89 THEN TRUE ELSE FALSE END) AS is_tanker
            FROM gate_crossings gc
            LEFT JOIN open_sea_fixes f USING (mmsi, ts)
            WHERE DATE(gc.ts) >= ?
        ),
        filtered AS (
            SELECT
                *,
                COALESCE(NULLIF(REGEXP_EXTRACT(gate_id, '(.*)_\\d+NM', 1), ''), gate_id) AS group_id,
                CAST(NULLIF(REGEXP_EXTRACT(gate_id, '_(\\d+)NM', 1), '') AS INTEGER) AS band_nm
            FROM recent
            WHERE (? = FALSE OR is_tanker)
              AND sog >= ?
        ),
        canon AS (
            SELECT gate_id
            FROM (
                SELECT
                    gate_id,
                    group_id,
                    COALESCE(band_nm, 0) AS band_nm,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_id
                        ORDER BY COALESCE(band_nm, 0) DESC
                    ) AS rn
                FROM filtered
            )
            WHERE rn = 1
        ),
        base AS (
            SELECT
                DATE(f.ts) AS ds,
                f.gate_id,
                f.group_id,
                f.mmsi,
                f.ts,
                COALESCE(tr.rehit_hours, ?) AS rehit_hours
            FROM filtered AS f
            LEFT JOIN tmp_flux_rehit tr
              ON tr.group_id = f.group_id
            WHERE f.gate_id IN (SELECT gate_id FROM canon)
        ),
        buckets AS (
            SELECT
                ds,
                gate_id,
                mmsi,
                MIN(ts) AS first_ts
            FROM base
            GROUP BY
                ds,
                gate_id,
                mmsi,
                CAST(FLOOR(EXTRACT(epoch FROM ts) / (COALESCE(rehit_hours, ?) * 3600.0)) AS BIGINT)
        )
        SELECT
            ds,
            gate_id,
            COUNT(*) AS crossings,
            COUNT(DISTINCT mmsi) AS unique_vessels
        FROM buckets
        GROUP BY ds, gate_id
        """,
        [start_date, tanker_only_flag, sog_min, rehit_default, rehit_default],
    )

    con.execute(
        """
        INSERT INTO gate_flux_daily
        SELECT ds, gate_id, 'all' AS direction, crossings
        FROM tmp_gate_hits
        """
    )

    con.execute(
        """
        INSERT INTO gate_flux_daily_deduplicated
        SELECT ds, gate_id, 'all' AS direction, crossings, unique_vessels
        FROM tmp_gate_hits
        """
    )

    con.execute("DROP TABLE IF EXISTS tmp_gate_hits")
    con.execute("DROP TABLE IF EXISTS tmp_flux_rehit")


def _update_gate_paired_transits(con: duckdb.DuckDBPyConnection, start_date: dt.date) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS gate_paired_transits_daily (
            ds DATE,
            corridor_id VARCHAR,
            paired_transits INTEGER,
            mean_transit_h DOUBLE,
            median_transit_h DOUBLE,
            p90_transit_h DOUBLE
        )
        """
    )
    con.execute("DELETE FROM gate_paired_transits_daily WHERE ds >= ?", [start_date])
    con.execute(
        """
        INSERT INTO gate_paired_transits_daily
        SELECT
            ds,
            corridor_id,
            SUM(n) AS paired_transits,
            CASE WHEN SUM(n) > 0 THEN SUM(mean_h * n) / SUM(n) ELSE NULL END AS mean_transit_h,
            CASE WHEN SUM(n) > 0 THEN SUM(median_h * n) / SUM(n) ELSE NULL END AS median_transit_h,
            MAX(p90_h) AS p90_transit_h
        FROM transit_times_daily
        WHERE ds >= ?
        GROUP BY ds, corridor_id
        ORDER BY ds, corridor_id
        """,
        [start_date],
    )


def compute_aggregates(config: OpenSeaConfig, duckdb_path: Path | str) -> None:
    start = time.perf_counter()
    now = dt.datetime.now(dt.timezone.utc)
    window_30m = now - dt.timedelta(minutes=30)
    start_daily = now.date() - dt.timedelta(days=7)
    start_hourly = now - dt.timedelta(hours=48)

    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute("DELETE FROM tanker_occupancy_intraday")
        con.execute(
            """
            INSERT INTO tanker_occupancy_intraday
            SELECT ?, polygon_id, COUNT(*)
            FROM tanker_presence
            WHERE inside = TRUE AND last_seen_ts >= ?
            GROUP BY polygon_id
            """,
            [now, window_30m],
        )

        con.execute("DELETE FROM tanker_entries_daily WHERE ds >= ?", [start_daily])
        con.execute(
            """
            INSERT INTO tanker_entries_daily
            SELECT DATE(ts) AS ds, polygon_id, COUNT(*) AS entries
            FROM polygon_events
            WHERE event = 'enter' AND DATE(ts) >= ?
            GROUP BY ds, polygon_id
            """,
            [start_daily],
        )

        con.execute("DELETE FROM tanker_dwell_daily WHERE ds >= ?", [start_daily])
        con.execute(
            """
            INSERT INTO tanker_dwell_daily
            SELECT
                DATE(exit_ts) AS ds,
                polygon_id,
                median(datediff('minute', enter_ts, exit_ts)) AS dwell_p50_min,
                quantile(datediff('minute', enter_ts, exit_ts), 0.9) AS dwell_p90_min,
                COUNT(*) AS n
            FROM tanker_presence
            WHERE inside = FALSE
              AND exit_ts IS NOT NULL
              AND enter_ts IS NOT NULL
              AND DATE(exit_ts) >= ?
              AND coalesce(sog_avg, sog_max, sog_min, 0) <= ?
            GROUP BY ds, polygon_id
            """,
            [start_daily, config.sog_thresholds.dwell_max_kn],
        )

        con.execute("DELETE FROM gate_flux_hourly WHERE ts >= ?", [start_hourly])
        con.execute(
            """
            INSERT INTO gate_flux_hourly
            SELECT date_trunc('hour', ts) AS ts_hour, gate_id, direction, COUNT(*)
            FROM gate_crossings
            WHERE ts >= ?
            GROUP BY ts_hour, gate_id, direction
            """,
            [start_hourly],
        )

        modes = {mode.lower() for mode in config.flux.count_modes}
        if "gate_hits" in modes:
            _update_gate_flux_hits(con, start_daily, config)
        _update_gate_flux_rolling(con, now)
        _update_transit_times(con, start_daily)
        if "paired_transits" in modes:
            _update_gate_paired_transits(con, start_daily)

        duration = time.perf_counter() - start
        _emit_metrics(con, now, duration)
    finally:
        con.close()


def _update_gate_flux_rolling(con: duckdb.DuckDBPyConnection, now: dt.datetime) -> None:
    cutoff = now - dt.timedelta(days=14)
    con.execute("DELETE FROM gate_flux_rolling WHERE end_ts < ?", [cutoff])
    con.execute("DELETE FROM gate_flux_rolling WHERE end_ts = ?", [now])
    con.execute(
        """
        INSERT INTO gate_flux_rolling
        SELECT '24h' AS window_label, gate_id, direction, ? AS end_ts, COUNT(*) AS crossings
        FROM gate_crossings
        WHERE ts >= ?
        GROUP BY gate_id, direction
        UNION ALL
        SELECT '7d' AS window_label, gate_id, direction, ? AS end_ts, COUNT(*) AS crossings
        FROM gate_crossings
        WHERE ts >= ?
        GROUP BY gate_id, direction
        """,
        [now, now - dt.timedelta(hours=24), now, now - dt.timedelta(days=7)],
    )


def _update_transit_times(con: duckdb.DuckDBPyConnection, start_date: dt.date) -> None:
    con.execute("DELETE FROM transit_times_daily WHERE ds >= ?", [start_date])
    for definition in iter_corridors():
        _insert_corridor_transits(con, definition, start_date)


def _insert_corridor_transits(
    con: duckdb.DuckDBPyConnection,
    definition: CorridorDefinition,
    start_date: dt.date,
) -> None:
    corridor_id = definition.corridor_id
    entry_gates = list(definition.entry_gates)
    exit_gates = list(definition.exit_gates)
    if not entry_gates or not exit_gates:
        LOG.debug("Skipping corridor %s due to missing gate definitions", corridor_id)
        return

    min_hours = float(definition.min_hours)
    max_hours = float(definition.max_hours)
    entry_sql = _sql_list(entry_gates)
    exit_sql = _sql_list(exit_gates)

    query = f"""
        WITH entry_events AS (
            SELECT mmsi, ts, gate_id
            FROM gate_crossings
            WHERE gate_id IN ({entry_sql})
              AND ts >= ?
        )
        INSERT INTO transit_times_daily (ds, corridor_id, from_id, to_id, median_h, mean_h, p90_h, n)
        SELECT
            DATE(e.ts) AS ds,
            '{corridor_id}' AS corridor_id,
            e.gate_id AS from_id,
            exit_evt.gate_id AS to_id,
            median(exit_evt.transit_h) AS median_h,
            avg(exit_evt.transit_h) AS mean_h,
            quantile(exit_evt.transit_h, 0.9) AS p90_h,
            COUNT(*) AS n
        FROM entry_events e
        JOIN LATERAL (
            SELECT
                gx.gate_id,
                datediff('minute', e.ts, gx.ts) / 60.0 AS transit_h
            FROM gate_crossings gx
            WHERE gx.mmsi = e.mmsi
              AND gx.ts > e.ts
              AND gx.ts <= e.ts + INTERVAL '{max_hours} hours'
              AND gx.gate_id IN ({exit_sql})
            ORDER BY gx.ts
            LIMIT 1
        ) AS exit_evt ON TRUE
        WHERE exit_evt.transit_h BETWEEN {min_hours} AND {max_hours}
        GROUP BY ds, from_id, to_id
    """
    con.execute(query, [start_date])


def _emit_metrics(con: duckdb.DuckDBPyConnection, as_of: dt.datetime, duration: float) -> None:
    gateway = os.getenv("OPEN_SEA_PUSHGATEWAY")
    if not gateway:
        return

    registry = CollectorRegistry()
    occupancy_gauge = Gauge(
        "open_sea_tanker_occupancy_now",
        "Current tanker count inside polygon based on hysteresis rules.",
        ["polygon"],
        registry=registry,
    )
    gate_flux_gauge = Gauge(
        "open_sea_gate_flux_24h",
        "Gate crossings observed in the last 24 hours.",
        ["gate", "direction"],
        registry=registry,
    )
    aggregate_runtime = Gauge(
        "open_sea_aggregate_runtime_seconds",
        "Wall-clock runtime of the latest open-sea aggregate job.",
        registry=registry,
    )
    aggregate_as_of = Gauge(
        "open_sea_aggregate_as_of_timestamp",
        "Unix timestamp of the aggregation evaluation time.",
        registry=registry,
    )

    occupancy_rows = con.execute("SELECT polygon_id, count_now FROM tanker_occupancy_intraday").fetchall()
    for polygon_id, count_now in occupancy_rows:
        occupancy_gauge.labels(polygon=polygon_id).set(float(count_now))

    flux_rows = con.execute(
        """
        SELECT gate_id, direction, COUNT(*) AS crossings
        FROM gate_crossings
        WHERE ts >= ?
        GROUP BY gate_id, direction
        """,
        [as_of - dt.timedelta(hours=24)],
    ).fetchall()
    for gate_id, direction, crossings in flux_rows:
        gate_flux_gauge.labels(gate=gate_id, direction=direction or "unknown").set(float(crossings))

    aggregate_runtime.set(duration)
    aggregate_as_of.set(as_of.timestamp())

    try:
        push_to_gateway(gateway, job="open_sea_aggregate", registry=registry)
    except Exception as exc:  # pragma: no cover - network/IO
        LOG.warning("Failed to push open-sea metrics to %s: %s", gateway, exc)
