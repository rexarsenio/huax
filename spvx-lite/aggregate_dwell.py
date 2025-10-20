"""
Aggregate AIS raw data into the chokepoint_dwell materialisation.

The aggregation can run inside the long-lived ingest process by reusing the
same DuckDB connection. A job_state watermark ensures we only process new
time windows while still re-evaluating the most recent bucket to catch any
late-arriving messages.

Usage (stand‑alone):
    python aggregate_dwell.py
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb
from dotenv import load_dotenv

from spvx.db import ensure_core_tables

load_dotenv()

DEFAULT_DUCKDB = Path(__file__).resolve().parent / "db" / "spvx.duckdb"
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", str(DEFAULT_DUCKDB)))
DEFAULT_INTERVAL_SECONDS = int(os.getenv("AGGREGATION_INTERVAL_SECONDS", "600"))

EPOCH_UTC = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

LOG = logging.getLogger("spvx.aggregate")


@dataclass
class AggregationResult:
    raw_record_count: int
    window_count: int
    last_window: dt.datetime | None


def _ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    ensure_core_tables(con)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS chokepoint_dwell (
            ts TIMESTAMP,
            region TEXT,
            slow_count BIGINT,
            PRIMARY KEY (ts, region)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS job_state (
            key TEXT PRIMARY KEY,
            value TIMESTAMP
        )
        """
    )


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'main' AND lower(table_name) = ?
            """,
            [table.lower()],
        ).fetchone()
    )


def _get_watermark(con: duckdb.DuckDBPyConnection) -> dt.datetime:
    row = con.execute(
        "SELECT value FROM job_state WHERE key = 'dwell_watermark'"
    ).fetchone()
    if row and row[0] is not None:
        value = row[0]
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=dt.timezone.utc)
            return value.astimezone(dt.timezone.utc)
    return EPOCH_UTC


def _set_watermark(con: duckdb.DuckDBPyConnection, value: dt.datetime) -> None:
    con.execute(
        """
        INSERT INTO job_state (key, value)
        VALUES ('dwell_watermark', ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value
        """,
        [value],
    )


def _log_lines(lines: Iterable[str]) -> None:
    for line in lines:
        LOG.info(line)


def run_aggregation(
    con: duckdb.DuckDBPyConnection,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> AggregationResult:
    """
    Execute the chokepoint dwell aggregation using an existing connection.
    Returns an AggregationResult describing the operation.
    """
    if interval_seconds <= 0:
        interval_seconds = DEFAULT_INTERVAL_SECONDS

    if not _table_exists(con, "ais_canon"):
        LOG.info("[DWELL] Table 'ais_canon' not found; skipping aggregation run.")
        return AggregationResult(raw_record_count=0, window_count=0, last_window=None)

    raw_count = con.execute("SELECT COUNT(*) FROM ais_canon").fetchone()[0]
    if raw_count == 0:
        LOG.info("[DWELL] No canonical AIS records available; skipping aggregation run.")
        return AggregationResult(raw_record_count=0, window_count=0, last_window=None)

    _ensure_tables(con)

    watermark = _get_watermark(con)
    window_interval = dt.timedelta(seconds=interval_seconds)
    lower_bound = max(EPOCH_UTC, watermark - window_interval)
    upper_bound = dt.datetime.now(dt.timezone.utc)

    if lower_bound >= upper_bound:
        LOG.info("[DWELL] No new time window to process (lower_bound >= upper_bound).")
        return AggregationResult(raw_record_count=raw_count, window_count=0, last_window=watermark)

    bucket_expr = f"time_bucket(INTERVAL '{interval_seconds} seconds', msg_time)"

    con.execute("BEGIN")
    try:
        inserted = con.execute(
            f"""
            INSERT INTO chokepoint_dwell AS target
            WITH new_rows AS (
                SELECT *
                FROM ais_canon
                WHERE msg_time > ? AND msg_time <= ?
            ),
            deduped AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY mmsi, date_trunc('minute', msg_time)
                        ORDER BY msg_time DESC, rx_time DESC
                    ) AS rn
                FROM new_rows
            )
            SELECT
                {bucket_expr} AS ts,
                region,
                COUNT(DISTINCT mmsi) FILTER (WHERE is_tanker AND sog < 0.5) AS slow_count
            FROM deduped
            WHERE rn = 1
            GROUP BY ts, region
            ON CONFLICT (ts, region)
            DO UPDATE SET slow_count = excluded.slow_count
            RETURNING ts
            """,
            [lower_bound, upper_bound],
        ).fetchall()

        window_count = len(inserted)
        last_window = max((row[0] for row in inserted), default=watermark)

        if inserted:
            lower_ts = min(row[0] for row in inserted)
            upper_ts = max(row[0] for row in inserted)
            con.execute(
                """
                INSERT INTO dwell_10m AS target
                SELECT
                    ts AS window_start,
                    region,
                    slow_count
                FROM chokepoint_dwell
                WHERE ts BETWEEN ? AND ?
                ON CONFLICT (window_start, region)
                DO UPDATE SET slow_count = excluded.slow_count
                """,
                [lower_ts, upper_ts],
            )
        if last_window is not None:
            _set_watermark(con, last_window)

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    if window_count == 0:
        LOG.info("[DWELL] Aggregation executed, but no new windows were produced.")
    else:
        LOG.info("[DWELL] Upserted %d window(s); latest window start %s", window_count, last_window)

    result_overview = con.execute(
        """
        SELECT
            region,
            COUNT(*) AS total_windows,
            SUM(slow_count) AS total_slow_vessels
        FROM chokepoint_dwell
        GROUP BY region
        ORDER BY region
        """
    ).fetchall()

    lines = ["[DWELL] Aggregation overview:"]
    for region, windows, slow in result_overview:
        lines.append(f"  {region}: {windows} windows, {slow} slow vessel observations")

    latest = con.execute(
        """
        SELECT ts, region, slow_count
        FROM chokepoint_dwell
        ORDER BY ts DESC
        LIMIT 5
        """
    ).fetchall()

    if latest:
        lines.append("[DWELL] Latest 5 observations:")
        for ts_val, region, count in latest:
            lines.append(f"  {ts_val} | {region:20s} | {count:3d} slow vessels")

    _log_lines(lines)

    return AggregationResult(
        raw_record_count=raw_count,
        window_count=window_count,
        last_window=last_window,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if not DUCKDB_PATH.exists():
        LOG.error("[DWELL] Database not found at %s", DUCKDB_PATH)
        return 1

    try:
        con = duckdb.connect(str(DUCKDB_PATH))
    except duckdb.duckdb.IOException as exc:
        LOG.error("[DWELL] Could not open DuckDB at %s: %s", DUCKDB_PATH, exc)
        LOG.error("[DWELL] Hint: stop the launchd service before running the manual aggregation.")
        return 2

    try:
        run_aggregation(con)
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
