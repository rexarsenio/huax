"""
Detection utilities for open-sea chokepoint analytics.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Iterable

import duckdb

try:  # Prometheus metrics are optional
    from prometheus_client import Counter
except Exception:  # pragma: no cover - optional dependency
    Counter = None  # type: ignore[assignment]

OPEN_SEA_ALERTS_TOTAL = (
    Counter("open_sea_alerts_total", "Alerts emitted by open-sea detection", ["kind"]) if Counter else None
)


def _ensure_alert_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS open_sea_alerts(
            ts TIMESTAMP,
            kind TEXT,
            corridor_id TEXT,
            payload JSON
        )
        """
    )


def _insert_alerts(
    con: duckdb.DuckDBPyConnection,
    kind: str,
    corridor_id: str,
    rows: Iterable[tuple[dt.datetime, dict]],
) -> int:
    payloads = [(row_ts, kind, corridor_id, json.dumps(payload)) for row_ts, payload in rows]
    if not payloads:
        return 0
    con.executemany(
        "INSERT INTO open_sea_alerts(ts, kind, corridor_id, payload) VALUES (?, ?, ?, ?)",
        payloads,
    )
    if OPEN_SEA_ALERTS_TOTAL is not None:
        OPEN_SEA_ALERTS_TOTAL.labels(kind=kind).inc(len(payloads))
    return len(payloads)


def detect_transit_anomalies(
    con: duckdb.DuckDBPyConnection,
    corridor: str,
    lookback_days: int = 60,
    recent_hours: int = 24,
) -> int:
    """
    Flag transits whose duration exceeds the corridor median by >3 MAD within the recent window.
    """
    if "->" not in corridor:
        raise ValueError("corridor must be in form 'FROM->TO'")
    from_id, to_id = corridor.split("->", 1)
    _ensure_alert_table(con)

    now = dt.datetime.now(dt.timezone.utc)
    baseline_start = now - dt.timedelta(days=lookback_days)
    recent_start = now - dt.timedelta(hours=recent_hours)

    con.execute(
        "DELETE FROM open_sea_alerts WHERE kind = 'TRANSIT_ANOMALY' AND corridor_id = ? AND ts >= ?",
        [corridor, recent_start],
    )

    query = """
        WITH ordered AS (
            SELECT
                mmsi,
                ts,
                polygon_id,
                event,
                lead(polygon_id) OVER (PARTITION BY mmsi ORDER BY ts) AS next_polygon,
                lead(event) OVER (PARTITION BY mmsi ORDER BY ts) AS next_event,
                lead(ts) OVER (PARTITION BY mmsi ORDER BY ts) AS next_ts
            FROM polygon_events
            WHERE ts >= ?
        ),
        pairs AS (
            SELECT
                mmsi,
                ts AS depart_ts,
                next_ts AS arrive_ts,
                datediff('minute', ts, next_ts) / 60.0 AS transit_h
            FROM ordered
            WHERE event = 'exit'
              AND next_event = 'enter'
              AND polygon_id = ?
              AND next_polygon = ?
              AND next_ts IS NOT NULL
              AND datediff('minute', ts, next_ts) BETWEEN 0 AND 2400
        ),
        baseline AS (
            SELECT transit_h
            FROM pairs
            WHERE depart_ts >= ? AND depart_ts < ?
        ),
        stats AS (
            SELECT median(transit_h) AS med FROM baseline
        ),
        mad_calc AS (
            SELECT 1.4826 * median(abs(b.transit_h - stats.med)) AS mad
            FROM baseline b
            CROSS JOIN stats
        ),
        recent AS (
            SELECT p.*, stats.med, mad_calc.mad
            FROM pairs p
            CROSS JOIN stats
            CROSS JOIN mad_calc
            WHERE p.depart_ts >= ?
        ),
        flagged AS (
            SELECT *
            FROM recent
            WHERE mad > 0 AND transit_h > med + 3 * mad
        )
        SELECT mmsi, arrive_ts, depart_ts, transit_h, med, mad
        FROM flagged
        ORDER BY arrive_ts
    """
    rows = con.execute(query, [baseline_start, from_id, to_id, baseline_start, recent_start, recent_start]).fetchall()
    alerts = []
    for mmsi, arrive_ts, depart_ts, transit_h, med, mad in rows:
        if arrive_ts is None:
            continue
        payload = {
            "mmsi": int(mmsi),
            "depart_ts": depart_ts.isoformat() if depart_ts else None,
            "arrive_ts": arrive_ts.isoformat(),
            "transit_hours": float(transit_h),
            "median_hours": float(med),
            "mad_hours": float(mad),
            "threshold_hours": float(med + 3 * mad),
        }
        alerts.append((arrive_ts, payload))

    return _insert_alerts(con, "TRANSIT_ANOMALY", corridor, alerts)


@dataclass(slots=True)
class RouteDeviationConfig:
    recent_days: int = 7
    baseline_days: int = 180
    min_cape_crossings: int = 10
    share_threshold: float = 0.25
    corridor_id: str = "INDIAN->NATL"


def detect_route_deviation(
    con: duckdb.DuckDBPyConnection,
    cape_gate: str,
    suez_gate: str,
    cfg: RouteDeviationConfig | None = None,
) -> int:
    """
    Compare Cape vs. Suez gate flux share to a long-run baseline and emit alerts on large swings.
    """
    cfg = cfg or RouteDeviationConfig()
    _ensure_alert_table(con)

    today = dt.date.today()
    recent_start = today - dt.timedelta(days=cfg.recent_days - 1)
    baseline_start = today - dt.timedelta(days=cfg.baseline_days)
    baseline_end = recent_start

    recent_rows = con.execute(
        """
        SELECT gate_id, SUM(crossings) AS total
        FROM gate_flux_daily
        WHERE gate_id IN (?, ?)
          AND ds >= ?
        GROUP BY gate_id
        """,
        [cape_gate, suez_gate, recent_start],
    ).fetchall()
    cape_recent = sum(row[1] for row in recent_rows if row[0] == cape_gate)
    suez_recent = sum(row[1] for row in recent_rows if row[0] == suez_gate)
    total_recent = cape_recent + suez_recent
    if total_recent == 0 or cape_recent < cfg.min_cape_crossings:
        con.execute(
            "DELETE FROM open_sea_alerts WHERE kind = 'ROUTE_DEVIATION' AND corridor_id = ?",
            [cfg.corridor_id],
        )
        return 0

    baseline_rows = con.execute(
        """
        SELECT gate_id, SUM(crossings) AS total
        FROM gate_flux_daily
        WHERE gate_id IN (?, ?)
          AND ds >= ?
          AND ds < ?
        GROUP BY gate_id
        """,
        [cape_gate, suez_gate, baseline_start, baseline_end],
    ).fetchall()
    cape_baseline = sum(row[1] for row in baseline_rows if row[0] == cape_gate)
    suez_baseline = sum(row[1] for row in baseline_rows if row[0] == suez_gate)
    total_baseline = cape_baseline + suez_baseline
    if total_baseline == 0:
        con.execute(
            "DELETE FROM open_sea_alerts WHERE kind = 'ROUTE_DEVIATION' AND corridor_id = ?",
            [cfg.corridor_id],
        )
        return 0

    share_recent = cape_recent / total_recent
    share_baseline = cape_baseline / total_baseline
    if share_recent - share_baseline < cfg.share_threshold:
        con.execute(
            "DELETE FROM open_sea_alerts WHERE kind = 'ROUTE_DEVIATION' AND corridor_id = ?",
            [cfg.corridor_id],
        )
        return 0

    con.execute(
        "DELETE FROM open_sea_alerts WHERE kind = 'ROUTE_DEVIATION' AND corridor_id = ?",
        [cfg.corridor_id],
    )
    payload = {
        "cape_share_recent": share_recent,
        "cape_share_baseline": share_baseline,
        "cape_crossings_recent": cape_recent,
        "suez_crossings_recent": suez_recent,
        "recent_days": cfg.recent_days,
        "baseline_days": cfg.baseline_days,
    }
    alert_ts = dt.datetime.now(dt.timezone.utc)
    return _insert_alerts(con, "ROUTE_DEVIATION", cfg.corridor_id, [(alert_ts, payload)])


def detect_floating_storage(
    con: duckdb.DuckDBPyConnection,
    polygon_id: str,
    vlcc_h: int = 48,
    other_h: int = 24,
) -> int:
    """
    Flag long-duration tanker presence as potential floating storage.
    """
    _ensure_alert_table(con)

    result = con.execute(
        """
        WITH durations AS (
            SELECT datediff('minute', enter_ts, exit_ts) / 60.0 AS duration_h
            FROM tanker_presence
            WHERE polygon_id = ?
              AND enter_ts IS NOT NULL
              AND exit_ts IS NOT NULL
        )
        SELECT
            SUM(CASE WHEN duration_h >= ? THEN 1 ELSE 0 END) AS cnt_vlcc,
            SUM(CASE WHEN duration_h >= ? THEN 1 ELSE 0 END) AS cnt_other
        FROM durations
        """,
        [polygon_id, vlcc_h, other_h],
    ).fetchone()
    if not result:
        return 0

    cnt_vlcc = int(result[0] or 0)
    cnt_other = int(result[1] or 0)
    if cnt_vlcc == 0 and cnt_other == 0:
        return 0

    con.execute(
        "DELETE FROM open_sea_alerts WHERE kind = 'FLOATING_STORAGE' AND corridor_id = ?",
        [polygon_id],
    )
    payload = {
        "count_vlcc": cnt_vlcc,
        "count_other": cnt_other,
        "vlcc_threshold_h": vlcc_h,
        "other_threshold_h": other_h,
    }
    alert_ts = dt.datetime.now(dt.timezone.utc)
    return _insert_alerts(con, "FLOATING_STORAGE", polygon_id, [(alert_ts, payload)])
