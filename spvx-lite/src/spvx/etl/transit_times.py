"""
Transit Time Calculation for SPVX v1.5 DelayScore.

Computes median transit times through corridors based on polygon entry/exit events.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

import duckdb
import pandas as pd

LOG = logging.getLogger(__name__)


def compute_transit_times_daily(
    con: duckdb.DuckDBPyConnection,
    target_date: Optional[dt.date] = None,
) -> pd.DataFrame:
    """
    Compute daily transit time statistics for all corridors.

    Transit time = time between entry and exit of a corridor polygon.

    Args:
        con: DuckDB connection
        target_date: Date to compute (defaults to yesterday)

    Returns:
        DataFrame with columns:
            - ds: date
            - corridor_id: corridor identifier
            - median_h: median transit time in hours
            - p50_h: 50th percentile (same as median)
            - p90_h: 90th percentile
            - num_transits: number of complete transits observed
    """
    if target_date is None:
        target_date = dt.date.today() - dt.timedelta(days=1)

    LOG.info(f"Computing transit times for {target_date}")

    # Query to match entry/exit events for each vessel
    query = """
    WITH entry_exit AS (
        SELECT
            polygon_id,
            mmsi,
            ts,
            UPPER(event) as event,
            LAG(UPPER(event)) OVER (PARTITION BY polygon_id, mmsi ORDER BY ts) as prev_event,
            LAG(ts) OVER (PARTITION BY polygon_id, mmsi ORDER BY ts) as prev_ts
        FROM polygon_events
        WHERE
            CAST(ts AS DATE) = ?
            AND UPPER(event) IN ('ENTER', 'EXIT')
            AND polygon_id LIKE 'CHOKEPOINT_%'
    ),
    transits AS (
        SELECT
            polygon_id,
            mmsi,
            prev_ts as entry_ts,
            ts as exit_ts,
            EXTRACT(EPOCH FROM (ts - prev_ts)) / 3600.0 as transit_h
        FROM entry_exit
        WHERE
            prev_event = 'ENTER'
            AND event = 'EXIT'
            AND transit_h > 0
            AND transit_h < 72  -- Filter unrealistic transits (max 3 days)
    )
    SELECT
        ? as ds,
        polygon_id || '->UNK' as corridor_id,
        MEDIAN(transit_h) as median_h,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY transit_h) as p50_h,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY transit_h) as p90_h,
        COUNT(*) as num_transits
    FROM transits
    GROUP BY polygon_id
    HAVING COUNT(*) >= 3  -- Minimum 3 transits for statistical validity
    ORDER BY corridor_id
    """

    try:
        df = con.execute(query, [target_date, target_date]).df()
        LOG.info(f"Computed transit times for {len(df)} corridors on {target_date}")
        return df
    except Exception as e:
        LOG.error(f"Failed to compute transit times: {e}")
        return pd.DataFrame(columns=['ds', 'corridor_id', 'median_h', 'p50_h', 'p90_h', 'num_transits'])


def persist_transit_times_daily(
    con: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
) -> None:
    """
    Persist transit time statistics to transit_times_daily table.

    Args:
        con: DuckDB connection
        df: DataFrame from compute_transit_times_daily()
    """
    if df.empty:
        LOG.warning("No transit times to persist")
        return

    # Ensure transit_times_daily table exists
    con.execute("""
        CREATE TABLE IF NOT EXISTS transit_times_daily (
            ds DATE NOT NULL,
            corridor_id VARCHAR NOT NULL,
            median_h DOUBLE,
            p50_h DOUBLE,
            p90_h DOUBLE,
            num_transits INTEGER,
            PRIMARY KEY (ds, corridor_id)
        )
    """)

    # Insert or update
    con.execute("""
        INSERT OR REPLACE INTO transit_times_daily
        SELECT * FROM df
    """)

    con.commit()
    LOG.info(f"Persisted {len(df)} transit time records to transit_times_daily")


def compute_and_persist_transit_times(
    duckdb_path: str,
    target_date: Optional[dt.date] = None,
) -> pd.DataFrame:
    """
    Compute and persist transit times for a given date.

    Args:
        duckdb_path: Path to DuckDB database
        target_date: Date to compute (defaults to yesterday)

    Returns:
        DataFrame with transit time statistics
    """
    con = duckdb.connect(str(duckdb_path))

    try:
        df = compute_transit_times_daily(con, target_date)

        if not df.empty:
            persist_transit_times_daily(con, df)

        return df
    finally:
        con.close()


def get_baseline_transit_time(
    con: duckdb.DuckDBPyConnection,
    corridor_id: str,
    reference_date: dt.date,
    lookback_days: int = 30,
) -> Optional[float]:
    """
    Get baseline transit time for a corridor (30-day median).

    Args:
        con: DuckDB connection
        corridor_id: Corridor identifier
        reference_date: Reference date
        lookback_days: Days to look back for baseline

    Returns:
        Baseline median transit time in hours, or None if insufficient data
    """
    start_date = reference_date - dt.timedelta(days=lookback_days)

    query = """
    SELECT MEDIAN(median_h) as baseline_median_h
    FROM transit_times_daily
    WHERE
        corridor_id = ?
        AND ds >= ?
        AND ds < ?
        AND num_transits >= 3
    """

    result = con.execute(query, [corridor_id, start_date, reference_date]).fetchone()

    if result and result[0] is not None:
        return float(result[0])
    return None
