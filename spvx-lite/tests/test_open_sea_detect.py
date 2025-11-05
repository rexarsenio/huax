import datetime as dt
import json

import duckdb

from spvx.open_sea.detect import (
    RouteDeviationConfig,
    detect_floating_storage,
    detect_route_deviation,
    detect_transit_anomalies,
)


def _setup_connection(tmp_path):
    db_path = tmp_path / "detect.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE polygon_events(
            mmsi BIGINT,
            polygon_id TEXT,
            event TEXT,
            ts TIMESTAMP,
            lat DOUBLE,
            lon DOUBLE,
            sog DOUBLE,
            cog DOUBLE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE gate_flux_daily(
            ds DATE,
            gate_id TEXT,
            direction TEXT,
            crossings INTEGER
        )
        """
    )
    con.execute(
        """
        CREATE TABLE tanker_presence(
            mmsi BIGINT,
            polygon_id TEXT,
            enter_ts TIMESTAMP,
            exit_ts TIMESTAMP,
            last_seen_ts TIMESTAMP,
            inside BOOLEAN,
            samples_inside INTEGER,
            sog_min DOUBLE,
            sog_max DOUBLE,
            sog_avg DOUBLE
        )
        """
    )
    return con


def test_detect_transit_anomalies_flags_long_transit(tmp_path):
    con = _setup_connection(tmp_path)
    try:
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        baseline_pairs = [
            (1, "AG", "exit", now - dt.timedelta(days=3, hours=13)),
            (1, "HORMUZ", "enter", now - dt.timedelta(days=3, hours=1)),
            (2, "AG", "exit", now - dt.timedelta(days=2, hours=14)),
            (2, "HORMUZ", "enter", now - dt.timedelta(days=2, hours=1)),
        ]
        anomaly_pairs = [
            (3, "AG", "exit", now - dt.timedelta(hours=26)),
            (3, "HORMUZ", "enter", now - dt.timedelta(hours=1)),
        ]
        rows = baseline_pairs + anomaly_pairs
        con.executemany(
            "INSERT INTO polygon_events VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL)",
            rows,
        )

        inserted = detect_transit_anomalies(con, corridor="AG->HORMUZ", lookback_days=10, recent_hours=48)
        assert inserted == 1
        payload_raw = con.execute(
            "SELECT payload FROM open_sea_alerts WHERE kind = 'TRANSIT_ANOMALY'"
        ).fetchone()[0]
        payload = json.loads(payload_raw)
        assert payload["mmsi"] == 3
        assert payload["transit_hours"] > payload["threshold_hours"] - 1e-6
    finally:
        con.close()


def test_detect_route_deviation_emits_when_share_spikes(tmp_path):
    con = _setup_connection(tmp_path)
    try:
        today = dt.date.today()
        # Baseline: strong Suez share
        baseline_days = [today - dt.timedelta(days=14), today - dt.timedelta(days=13)]
        for d in baseline_days:
            con.execute(
                "INSERT INTO gate_flux_daily VALUES (?, 'CAPE', 'AtoB', 5)", [d]
            )
            con.execute(
                "INSERT INTO gate_flux_daily VALUES (?, 'SUEZ', 'AtoB', 25)",
                [d],
            )
        # Recent window: Cape dominates
        recent_days = [today - dt.timedelta(days=i) for i in range(3)]
        for d in recent_days:
            con.execute(
                "INSERT INTO gate_flux_daily VALUES (?, 'CAPE', 'AtoB', 20)", [d]
            )
            con.execute(
                "INSERT INTO gate_flux_daily VALUES (?, 'SUEZ', 'AtoB', 10)", [d]
            )

        cfg = RouteDeviationConfig(recent_days=3, baseline_days=15, share_threshold=0.2, corridor_id="INDIAN->NATL")
        inserted = detect_route_deviation(con, cape_gate="CAPE", suez_gate="SUEZ", cfg=cfg)
        assert inserted == 1
        payload_raw = con.execute(
            "SELECT payload FROM open_sea_alerts WHERE kind = 'ROUTE_DEVIATION'"
        ).fetchone()[0]
        payload = json.loads(payload_raw)
        assert payload["cape_share_recent"] > payload["cape_share_baseline"]
    finally:
        con.close()


def test_detect_floating_storage_counts_threshold(tmp_path):
    con = _setup_connection(tmp_path)
    try:
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        con.executemany(
            """
            INSERT INTO tanker_presence VALUES
            (?, ?, ?, ?, ?, FALSE, 10, 0.2, 1.5, 0.8)
            """,
            [
                (
                    111,
                    "POLY",
                    now - dt.timedelta(hours=72),
                    now - dt.timedelta(hours=24),
                    now - dt.timedelta(hours=24),
                ),
                (
                    222,
                    "POLY",
                    now - dt.timedelta(hours=30),
                    now - dt.timedelta(hours=2),
                    now - dt.timedelta(hours=2),
                ),
            ],
        )
        inserted = detect_floating_storage(con, polygon_id="POLY", vlcc_h=48, other_h=24)
        assert inserted == 1
        payload_raw = con.execute(
            "SELECT payload FROM open_sea_alerts WHERE kind = 'FLOATING_STORAGE'"
        ).fetchone()[0]
        payload = json.loads(payload_raw)
        assert payload["count_vlcc"] == 1
        assert payload["count_other"] == 2
    finally:
        con.close()

