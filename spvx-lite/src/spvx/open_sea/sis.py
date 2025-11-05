"""
Sea-state join helpers for SIS (Sea Impact Score) computations.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

import duckdb
import numpy as np
import pandas as pd


@dataclass
class SISConfig:
    """Configuration for SIS weighting and normalization windows."""

    weights_wave: float = 0.50
    weights_head_current: float = 0.35
    weights_head_wind: float = 0.15
    pct_low: float = 0.05
    pct_high: float = 0.95
    history_days: int = 730
    sis_threshold: float = 0.70

    def weights(self) -> Iterable[float]:
        return (self.weights_wave, self.weights_head_current, self.weights_head_wind)


def _proj_head(val_u: pd.Series, val_v: pd.Series, cog_rad: pd.Series) -> pd.Series:
    """
    Project a vector (u, v) onto the opposite course direction.

    Parameters are pandas Series to allow vectorised operations.
    """
    cos_cog = np.cos(cog_rad)
    sin_cog = np.sin(cog_rad)
    return -(val_u * cos_cog + val_v * sin_cog)


def compute_samples(df_tracklets: pd.DataFrame, df_cmems: pd.DataFrame) -> pd.DataFrame:
    """
    Merge tracklet-level metadata with CMEMS samples to derive head components and wave metrics.

    Both frames must contain `tracklet_id` and `ts` and be pre-aligned in time/space.
    """
    df = df_tracklets.merge(df_cmems, on=["tracklet_id", "ts"], how="inner")
    if df.empty:
        return df

    if "lat" not in df.columns:
        if "lat_y" in df.columns:
            df["lat"] = df["lat_y"]
        elif "lat_x" in df.columns:
            df["lat"] = df["lat_x"]
    if "lon" not in df.columns:
        if "lon_y" in df.columns:
            df["lon"] = df["lon_y"]
        elif "lon_x" in df.columns:
            df["lon"] = df["lon_x"]

    df["head_current_kn"] = _proj_head(df["uo"], df["vo"], df["mean_cog"]) * 1.94384
    df["head_wind_ms"] = _proj_head(df["u10"], df["v10"], df["mean_cog"])
    df["wave_encounter_m"] = df["hs"]

    columns = [
        "tracklet_id",
        "ts",
        "lat",
        "lon",
        "hs",
        "u10",
        "v10",
        "uo",
        "vo",
        "sst_anom",
        "head_current_kn",
        "head_wind_ms",
        "wave_encounter_m",
    ]
    return df[columns]


def compute_sis_daily(con: duckdb.DuckDBPyConnection, cfg: SISConfig | None = None) -> int:
    """
    Aggregate SIS metrics for the latest sample date and persist them to `sea_state_daily`.

    Returns the number of corridor-day rows inserted (0 if prerequisites are missing).
    """
    cfg = cfg or SISConfig()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sea_state_daily(
            ds DATE,
            corridor_id TEXT,
            sis_mean DOUBLE,
            sis_p90 DOUBLE,
            pct_sis_gt_0_7 DOUBLE,
            hc_p90_kn DOUBLE,
            hw_p90_ms DOUBLE,
            we_p90_m DOUBLE,
            n_samples BIGINT,
            PRIMARY KEY (ds, corridor_id)
        )
        """
    )

    required_tables = {"sea_state_samples", "tracklets"}
    existing_tables = {
        row[0].lower()
        for row in con.execute("SELECT lower(table_name) FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    }
    if not required_tables.issubset(existing_tables):
        return 0

    target_row = con.execute("SELECT max(date(ts)) FROM sea_state_samples").fetchone()
    if not target_row or target_row[0] is None:
        return 0

    max_ds = target_row[0]
    recent_start = max_ds - dt.timedelta(days=6)

    date_rows = con.execute(
        """
        SELECT DISTINCT DATE(t.start_ts) AS ds
        FROM sea_state_samples s
        JOIN tracklets t USING (tracklet_id)
        WHERE DATE(t.start_ts) BETWEEN ? AND ?
        ORDER BY ds
        """,
        [recent_start, max_ds],
    ).fetchall()

    if not date_rows:
        return 0

    inserted_total = 0

    weights_wave, weights_current, weights_wind = cfg.weights()

    for (target_ds,) in date_rows:
        history_start = target_ds - dt.timedelta(days=cfg.history_days)

        con.execute("DELETE FROM sea_state_daily WHERE ds = ?", [target_ds])

        params = [
            target_ds,  # samples.ds filter
            history_start,
            target_ds,
            cfg.pct_low,
            cfg.pct_high,
            cfg.pct_low,
            cfg.pct_high,
            cfg.pct_low,
            cfg.pct_high,
            weights_wave,
            weights_current,
            weights_wind,
            cfg.sis_threshold,
        ]

        con.execute(
            """
        WITH samples AS (
            SELECT
                DATE(t.start_ts) AS ds,
                COALESCE(t.poly_from_id, 'UNK') || '->' || COALESCE(t.poly_to_id, 'UNK') AS corridor_id,
                s.head_current_kn,
                s.head_wind_ms,
                s.wave_encounter_m
            FROM sea_state_samples s
            JOIN tracklets t USING (tracklet_id)
            WHERE DATE(t.start_ts) = ?
              AND isfinite(s.head_current_kn)
              AND isfinite(s.head_wind_ms)
              AND isfinite(s.wave_encounter_m)
        ),
        history AS (
            SELECT
                DATE(t.start_ts) AS ds,
                COALESCE(t.poly_from_id, 'UNK') || '->' || COALESCE(t.poly_to_id, 'UNK') AS corridor_id,
                s.head_current_kn,
                s.head_wind_ms,
                s.wave_encounter_m
            FROM sea_state_samples s
            JOIN tracklets t USING (tracklet_id)
            WHERE DATE(t.start_ts) BETWEEN ? AND ?
              AND isfinite(s.head_current_kn)
              AND isfinite(s.head_wind_ms)
              AND isfinite(s.wave_encounter_m)
        ),
        stats AS (
            SELECT
                corridor_id,
                quantile_cont(wave_encounter_m, ?) AS we_lo,
                quantile_cont(wave_encounter_m, ?) AS we_hi,
                quantile_cont(head_current_kn, ?) AS hc_lo,
                quantile_cont(head_current_kn, ?) AS hc_hi,
                quantile_cont(head_wind_ms, ?) AS hw_lo,
                quantile_cont(head_wind_ms, ?) AS hw_hi
            FROM history
            GROUP BY corridor_id
        ),
        normalized AS (
            SELECT
                s.ds,
                s.corridor_id,
                CASE
                    WHEN stats.we_hi > stats.we_lo THEN
                        (least(greatest(s.wave_encounter_m, stats.we_lo), stats.we_hi) - stats.we_lo)
                        / NULLIF(stats.we_hi - stats.we_lo, 0)
                    ELSE 0 END AS we_n,
                CASE
                    WHEN stats.hc_hi > stats.hc_lo THEN
                        (least(greatest(s.head_current_kn, stats.hc_lo), stats.hc_hi) - stats.hc_lo)
                        / NULLIF(stats.hc_hi - stats.hc_lo, 0)
                    ELSE 0 END AS hc_n,
                CASE
                    WHEN stats.hw_hi > stats.hw_lo THEN
                        (least(greatest(s.head_wind_ms, stats.hw_lo), stats.hw_hi) - stats.hw_lo)
                        / NULLIF(stats.hw_hi - stats.hw_lo, 0)
                    ELSE 0 END AS hw_n,
                s.head_current_kn,
                s.head_wind_ms,
                s.wave_encounter_m
            FROM samples s
            JOIN stats USING (corridor_id)
        ),
        sis AS (
            SELECT
                ds,
                corridor_id,
                1.0 / (1.0 + exp(-(? * we_n + ? * hc_n + ? * hw_n))) AS sis,
                head_current_kn,
                head_wind_ms,
                wave_encounter_m
            FROM normalized
        )
        INSERT INTO sea_state_daily
        SELECT
            ds,
            corridor_id,
            avg(sis) AS sis_mean,
            quantile_cont(sis, 0.90) AS sis_p90,
            avg(CASE WHEN sis >= ? THEN 1 ELSE 0 END) AS pct_sis_gt_0_7,
            quantile_cont(head_current_kn, 0.90) AS hc_p90_kn,
            quantile_cont(head_wind_ms, 0.90) AS hw_p90_ms,
            quantile_cont(wave_encounter_m, 0.90) AS we_p90_m,
            COUNT(*) AS n_samples
        FROM sis
        GROUP BY ds, corridor_id
        """
        ,
            params,
        )

        inserted = con.execute("SELECT COUNT(*) FROM sea_state_daily WHERE ds = ?", [target_ds]).fetchone()[0]
        inserted_total += int(inserted or 0)

    return inserted_total
