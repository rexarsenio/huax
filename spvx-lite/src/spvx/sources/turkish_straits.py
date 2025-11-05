"""
Derive Bosporus congestion metrics from AIS dwell windows.

The AIS websocket ingest (`ingest_aisstream.py`) maintains a `dwell_10m` table with
10-minute buckets per chokepoint. We reuse those windows to estimate daily closures
and waiting times and persist them into `turkish_events`, which downstream components
already consume.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from spvx.config import AppSettings
from spvx.db import ensure_core_tables

LOG = logging.getLogger(__name__)

CLOSURE_THRESHOLD = int(os.getenv("TURKISH_CLOSURE_THRESHOLD", "5"))
WAIT_HOURS_PER_SLOW = float(os.getenv("TURKISH_WAIT_HOURS_PER_SLOW", "0.45"))
DEFAULT_REGION = "bosporus"


def _connect() -> duckdb.DuckDBPyConnection:
    settings = AppSettings()
    db_path = Path(settings.duckdb_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    ensure_core_tables(con)
    return con


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND lower(table_name) = ?
        """,
        [table.lower()],
    ).fetchone()
    return bool(row)


def _prepare_target_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS turkish_events (
            ts TIMESTAMP PRIMARY KEY,
            closure_minutes DOUBLE,
            wait_hours DOUBLE
        )
        """
    )


def _chunked(rows: Iterable[tuple], size: int = 500) -> Iterable[list[tuple]]:
    chunk: list[tuple] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def run(*, days: int = 400, region: str = DEFAULT_REGION) -> None:
    con = _connect()
    try:
        if not _table_exists(con, "dwell_10m"):
            LOG.warning("dwell_10m table not found; skipping Turkish straits ingestion.")
            return

        latest_row = con.execute(
            """
            SELECT max(window_start) FROM dwell_10m WHERE region = ?
            """,
            [region],
        ).fetchone()
        if not latest_row or latest_row[0] is None:
            LOG.warning("No dwell windows available for region '%s'; skipping Turkish straits ingestion.", region)
            return
        latest_ts = latest_row[0]
        start_ts = latest_ts - dt.timedelta(days=days)
        df = con.execute(
            """
            SELECT
                date(window_start) AS day,
                SUM(CASE WHEN slow_count >= ? THEN 10 ELSE 0 END) AS closure_minutes,
                AVG(slow_count) AS avg_slow,
                COUNT(*) AS window_count,
                MAX(window_start) AS last_ts
            FROM dwell_10m
            WHERE region = ?
              AND window_start >= ?
            GROUP BY 1
            ORDER BY 1
            """,
            [CLOSURE_THRESHOLD, region, start_ts],
        ).df()

        if df.empty:
            LOG.warning("No dwell windows available for region '%s'; skipping Turkish straits ingestion.", region)
            return

        df["closure_minutes"] = df["closure_minutes"].fillna(0.0)
        df["avg_slow"] = df["avg_slow"].fillna(0.0)
        df["wait_hours"] = (df["avg_slow"] * WAIT_HOURS_PER_SLOW).clip(lower=0)
        df["ts"] = pd.to_datetime(df["day"]) + pd.Timedelta(hours=12)

        rows = [
            (
                row.ts.to_pydatetime(),
                float(row.closure_minutes),
                float(row.wait_hours),
            )
            for row in df.itertuples()
            if pd.notna(row.ts)
        ]
        if not rows:
            LOG.warning("Derived Turkish events set is empty after transformation.")
            return

        _prepare_target_table(con)
        con.execute("BEGIN")
        try:
            for chunk in _chunked(rows):
                con.executemany(
                    """
                    INSERT INTO turkish_events (ts, closure_minutes, wait_hours)
                    VALUES (?, ?, ?)
                    ON CONFLICT (ts) DO UPDATE SET
                        closure_minutes = excluded.closure_minutes,
                        wait_hours = excluded.wait_hours
                    """,
                    chunk,
                )

            # Drop historical rows beyond requested horizon to keep the table bounded.
            cutoff_ts = min(row[0] for row in rows)
            con.execute("DELETE FROM turkish_events WHERE ts < ?", [cutoff_ts - dt.timedelta(days=5)])

            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

        LOG.info(
            "Upserted %s Turkish straits rows (region=%s, threshold=%s, wait_factor=%.2f).",
            len(rows),
            region,
            CLOSURE_THRESHOLD,
            WAIT_HOURS_PER_SLOW,
        )
    finally:
        con.close()
