"""
Anchorage Baseline Computation and Z-Score Enrichment (TH-3)

Computes historical baselines using DoW × WoY buckets and enriches
daily metrics with Z-scores for anomaly detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def compute_daily_metrics(
    con: duckdb.DuckDBPyConnection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """
    Aggregate episodes into daily metrics per anchorage.

    Args:
        con: DuckDB connection
        start_date: Start date for aggregation
        end_date: End date for aggregation
    """
    if start_date is None:
        # Get earliest episode
        result = con.execute("SELECT MIN(ts_entry) FROM anchorage_episodes").fetchone()
        start_date = result[0] if result[0] else datetime.now() - timedelta(days=30)

    if end_date is None:
        end_date = datetime.now()

    LOG.info(f"Computing daily metrics from {start_date} to {end_date}")

    # Aggregate episodes by day and anchorage
    query = """
        INSERT OR REPLACE INTO anchorage_daily_dwell
        (ds, anchorage_id, episode_count, median_dwell_h, p90_dwell_h, coverage_ratio)
        SELECT
            DATE(ts_entry) as ds,
            anchorage_id,
            COUNT(*) as episode_count,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dwell_hours) as median_dwell_h,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY dwell_hours) as p90_dwell_h,
            COUNT(*) / 24.0 as coverage_ratio  -- Rough estimate: episodes per hour
        FROM anchorage_episodes
        WHERE ts_entry >= ? AND ts_entry < ?
          AND ts_exit IS NOT NULL
          AND dwell_hours >= 1.0  -- Minimum 1 hour dwell
        GROUP BY DATE(ts_entry), anchorage_id
    """

    con.execute(query, [start_date, end_date])
    con.commit()

    rows = con.execute("SELECT COUNT(*) FROM anchorage_daily_dwell").fetchone()[0]
    LOG.info(f"Created/updated {rows} daily metric rows")


def compute_baselines(
    con: duckdb.DuckDBPyConnection,
    lookback_days: int = 90,
    min_samples: int = 20
):
    """
    Compute baselines using DoW × WoY buckets.

    For each anchorage and (day_of_week, week_of_year) combination,
    computes median and std of dwell time from historical data.

    Args:
        con: DuckDB connection
        lookback_days: Days of history to use for baseline
        min_samples: Minimum samples required for valid baseline
    """
    LOG.info(f"Computing baselines with {lookback_days} day lookback, min {min_samples} samples")

    # Get all daily data
    query = """
        SELECT
            ds,
            anchorage_id,
            episode_count,
            median_dwell_h,
            DAYOFWEEK(ds) as dow,
            WEEKOFYEAR(ds) as woy
        FROM anchorage_daily_dwell
        WHERE ds >= CURRENT_DATE - INTERVAL '{lookback_days} days'
          AND median_dwell_h IS NOT NULL
    """.format(lookback_days=lookback_days)

    df = con.execute(query).df()

    if df.empty:
        LOG.warning("No daily data available for baseline computation")
        return

    LOG.info(f"Computing baselines from {len(df)} daily records")

    # Compute baselines by (anchorage_id, dow, woy)
    baselines = df.groupby(['anchorage_id', 'dow', 'woy'])['median_dwell_h'].agg([
        ('median', 'median'),
        ('std', 'std'),
        ('count', 'count')
    ]).reset_index()

    # Filter by minimum samples
    baselines = baselines[baselines['count'] >= min_samples]

    LOG.info(f"Created {len(baselines)} baseline buckets (DoW × WoY)")

    # For each daily record, find matching baseline and compute Z-score
    results = []

    for _, row in df.iterrows():
        ds = row['ds']
        anch_id = row['anchorage_id']
        dow = row['dow']
        woy = row['woy']
        dwell = row['median_dwell_h']

        # Find baseline for this (anchorage, dow, woy)
        baseline = baselines[
            (baselines['anchorage_id'] == anch_id) &
            (baselines['dow'] == dow) &
            (baselines['woy'] == woy)
        ]

        if baseline.empty:
            # No baseline available
            z_dwell = None
            baseline_median = None
            baseline_std = None
            baseline_insufficient = True
        else:
            baseline_median = baseline.iloc[0]['median']
            baseline_std = baseline.iloc[0]['std']

            if baseline_std > 0:
                z_dwell = (dwell - baseline_median) / baseline_std
            else:
                z_dwell = 0.0

            baseline_insufficient = False

        # Detect anomaly (|Z| > 2.0)
        anomaly_detected = z_dwell is not None and abs(z_dwell) > 2.0

        results.append({
            'ds': ds,
            'anchorage_id': anch_id,
            'baseline_median_h': baseline_median,
            'baseline_std_h': baseline_std,
            'z_dwell': z_dwell,
            'anomaly_detected': anomaly_detected
        })

    # Update database with Z-scores
    results_df = pd.DataFrame(results)

    con.execute("DROP TABLE IF EXISTS _temp_baselines")
    con.execute("CREATE TEMP TABLE _temp_baselines AS SELECT * FROM results_df")

    con.execute("""
        UPDATE anchorage_daily_dwell
        SET
            baseline_median_h = t.baseline_median_h,
            baseline_std_h = t.baseline_std_h,
            z_dwell = t.z_dwell,
            anomaly_detected = t.anomaly_detected
        FROM _temp_baselines t
        WHERE anchorage_daily_dwell.ds = t.ds
          AND anchorage_daily_dwell.anchorage_id = t.anchorage_id
    """)

    con.commit()

    # Summary
    enriched = len(results_df[results_df['z_dwell'].notna()])
    anomalies = len(results_df[results_df['anomaly_detected'] == True])

    LOG.info(f"Enriched {enriched} records with Z-scores")
    LOG.info(f"Detected {anomalies} anomalies (|Z| > 2.0)")

    # Show recent anomalies
    recent_anomalies = con.execute("""
        SELECT
            ds,
            anchorage_id,
            episode_count,
            median_dwell_h,
            z_dwell
        FROM anchorage_daily_dwell
        WHERE anomaly_detected = true
          AND ds >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY ABS(z_dwell) DESC
        LIMIT 5
    """).fetchall()

    if recent_anomalies:
        LOG.info("Recent anomalies (last 7 days):")
        for ds, anch, eps, dwell, z in recent_anomalies:
            LOG.info(f"  {ds} | {anch:20s} | {eps:3d} eps | {dwell:5.1f}h | Z={z:+5.2f}")


def backfill_all(
    con: duckdb.DuckDBPyConnection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    lookback_days: int = 90,
    min_samples: int = 20
):
    """
    Full backfill: compute daily metrics + baselines + Z-scores.

    This is the TH-3 main function.

    Args:
        con: DuckDB connection
        start_date: Start date for daily aggregation
        end_date: End date for daily aggregation
        lookback_days: Days to use for baseline computation
        min_samples: Minimum samples per baseline bucket
    """
    LOG.info("Starting TH-3 backfill (daily metrics + baselines + Z-scores)")

    # Step 1: Compute daily metrics from episodes
    compute_daily_metrics(con, start_date, end_date)

    # Step 2: Compute baselines and enrich with Z-scores
    compute_baselines(con, lookback_days, min_samples)

    LOG.info("TH-3 backfill complete")
