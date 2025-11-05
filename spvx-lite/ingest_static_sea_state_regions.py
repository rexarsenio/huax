#!/usr/bin/env python
"""
Ingest static CMEMS sea-state metrics for predefined regions.

This script samples CMEMS wave/wind/current grids for target bounding boxes
and stores region-level aggregates in DuckDB. Unlike the tracklet-based
pipeline, this runs independently of vessel movement so the dashboard can
surface weather conditions even when no ships crossed a chokepoint recently.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import duckdb
import numpy as np
import pandas as pd
import xarray as xr

from spvx.api_open_sea import WEST_AFRICA_REGIONS
from spvx.sea_state.cmems import extract_region_features, _sort_dataset

LOG = logging.getLogger("spvx.ingest_static_sea_state_regions")

WAVES_DIR = Path("data/sea_state/waves")
CURRENTS_DIR = Path("data/sea_state/currents")
DEFAULT_LOOKBACK_HOURS = 24

MAX_FILES_PER_DATASET = 1


REGION_FEATURES: List[dict[str, object]] = [
    {
        "id": "hs",
        "dataset": "waves",
        "type": "scalar",
        "variables": ["VHM0", "hs", "swh", "significant_wave_height"],
        "stats": ["mean", "p90"],
    },
    {
        "id": "wind_head",
        "dataset": "waves",
        "type": "opposing",
        "variables": ["u10", "v10"],
        "stats": ["mean", "p90"],
    },
    {
        "id": "wind_speed",
        "dataset": "waves",
        "type": "vector_magnitude",
        "variables": ["u10", "v10"],
        "stats": ["p90"],
    },
    {
        "id": "current_head",
        "dataset": "currents",
        "type": "opposing",
        "variables": ["uo", "vo"],
        "stats": ["mean", "p90"],
    },
    {
        "id": "current_speed",
        "dataset": "currents",
        "type": "vector_magnitude",
        "variables": ["uo", "vo"],
        "stats": ["p90"],
    },
]


@dataclass
class RegionConfig:
    region_id: str
    label: str
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    bearing_deg: float


def _latest_files(directory: Path, limit: int = 6) -> List[str]:
    files = sorted(directory.glob("*.nc"), key=lambda p: p.stat().st_mtime)
    if not files:
        return []
    return [str(path) for path in files[-limit:]]


def _compute_initial_bearing(path: List[List[float]]) -> float:
    if len(path) < 2:
        return 0.0
    lon1, lat1 = path[0]
    lon2, lat2 = path[-1]
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_lon = np.radians(lon2 - lon1)
    x = np.sin(delta_lon) * np.cos(phi2)
    y = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(delta_lon)
    bearing = np.degrees(np.arctan2(x, y))
    return (bearing + 360.0) % 360.0


def _load_region_configs() -> List[RegionConfig]:
    configs: List[RegionConfig] = []
    for region_id, cfg in WEST_AFRICA_REGIONS.items():
        lon_min, lat_min, lon_max, lat_max = cfg["bbox"]
        bearing = _compute_initial_bearing(cfg.get("corridor_path", []))
        configs.append(
            RegionConfig(
                region_id=region_id,
                label=cfg.get("label", region_id),
                lon_min=float(lon_min),
                lat_min=float(lat_min),
                lon_max=float(lon_max),
                lat_max=float(lat_max),
                bearing_deg=float(bearing),
            )
        )
    return configs


def _grid_cell_count(wave_files: List[str], config: RegionConfig) -> Optional[int]:
    if not wave_files:
        return None
    ds = None
    try:
        ds = xr.open_mfdataset(
            wave_files,
            combine="by_coords",
            engine="netcdf4",
            join="override",
            preprocess=_sort_dataset,
            chunks={},
        )
        clipped = ds.sel(
            latitude=slice(config.lat_min, config.lat_max),
            longitude=slice(config.lon_min, config.lon_max),
        )
        lat_count = int(clipped.dims.get("latitude", 0))
        lon_count = int(clipped.dims.get("longitude", 0))
        return lat_count * lon_count if lat_count and lon_count else None
    except Exception as exc:  # pragma: no cover - IO guard
        LOG.warning("Failed to compute grid size for %s: %s", config.region_id, exc)
        with contextlib.suppress(Exception):
            if ds is not None:
                ds.close()
        try:
            ds = xr.open_dataset(wave_files[-1], engine="netcdf4", chunks={})
            ds = _sort_dataset(ds)
            clipped = ds.sel(
                latitude=slice(config.lat_min, config.lat_max),
                longitude=slice(config.lon_min, config.lon_max),
            )
            lat_count = int(clipped.dims.get("latitude", 0))
            lon_count = int(clipped.dims.get("longitude", 0))
            return lat_count * lon_count if lat_count and lon_count else None
        except Exception as inner_exc:
            LOG.warning("Single-file grid computation failed for %s: %s", config.region_id, inner_exc)
        return None
    finally:
        with contextlib.suppress(Exception):
            if ds is not None:
                ds.close()


def _prepare_dataframe(
    region: RegionConfig,
    df: pd.DataFrame,
    grid_points: Optional[int],
    min_time: datetime,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df = df.rename(
        columns={
            "hs_mean": "wave_mean",
            "hs_p90": "wave_p90",
            "wind_head_mean": "head_wind_mean",
            "wind_head_p90": "head_wind_p90",
            "current_head_mean": "head_current_mean",
            "current_head_p90": "head_current_p90",
            "wind_speed_p90": "wind_speed_p90",
            "current_speed_p90": "current_speed_p90",
        }
    )

    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df[df["time"] >= min_time]

    df["region_id"] = region.region_id
    df["samples"] = grid_points if grid_points is not None else 0

    desired_columns = [
        "region_id",
        "time",
        "wave_mean",
        "wave_p90",
        "head_current_mean",
        "head_current_p90",
        "head_wind_mean",
        "head_wind_p90",
        "wind_speed_p90",
        "current_speed_p90",
        "samples",
    ]

    for column in desired_columns:
        if column not in df.columns:
            if column == "samples":
                df[column] = grid_points if grid_points is not None else 0
            else:
                df[column] = np.nan

    return df[desired_columns].drop_duplicates(subset=["region_id", "time"]).sort_values("time")


def _collect_region_metrics(
    region: RegionConfig,
    waves_files: List[str],
    currents_files: List[str],
    lookback_hours: int,
) -> pd.DataFrame:
    waves_subset = waves_files[-MAX_FILES_PER_DATASET:] if waves_files else []
    currents_subset = currents_files[-MAX_FILES_PER_DATASET:] if currents_files else []

    bbox = {
        "lat_min": region.lat_min,
        "lat_max": region.lat_max,
        "lon_min": region.lon_min,
        "lon_max": region.lon_max,
    }

    df = extract_region_features(
        waves_files=waves_subset,
        currents_files=currents_subset,
        features_cfg=REGION_FEATURES,
        bbox=bbox,
        bearing_deg=region.bearing_deg,
        buffer_km=30.0,
    )

    min_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    grid_points = _grid_cell_count(waves_subset, region)
    return _prepare_dataframe(region, df, grid_points, min_time)


def _ensure_table(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sea_state_region_metrics (
            region_id VARCHAR,
            ts TIMESTAMP,
            wave_mean DOUBLE,
            wave_p90 DOUBLE,
            head_current_mean DOUBLE,
            head_current_p90 DOUBLE,
            head_wind_mean DOUBLE,
            head_wind_p90 DOUBLE,
            wind_speed_p90 DOUBLE,
            current_speed_p90 DOUBLE,
            samples INTEGER,
            PRIMARY KEY (region_id, ts)
        )
        """
    )


def _write_region_metrics(connection: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0

    region_id = frame["region_id"].iloc[0]
    start_ts = frame["time"].min().to_pydatetime()
    end_ts = frame["time"].max().to_pydatetime()

    connection.execute(
        "DELETE FROM sea_state_region_metrics WHERE region_id = ? AND ts BETWEEN ? AND ?",
        [region_id, start_ts, end_ts],
    )

    rows = [
        (
            row.region_id,
            row.time.to_pydatetime(),
            _maybe_float(row.wave_mean),
            _maybe_float(row.wave_p90),
            _maybe_float(row.head_current_mean),
            _maybe_float(row.head_current_p90),
            _maybe_float(row.head_wind_mean),
            _maybe_float(row.head_wind_p90),
            _maybe_float(row.wind_speed_p90),
            _maybe_float(row.current_speed_p90),
            int(row.samples) if not pd.isna(row.samples) else 0,
        )
        for row in frame.itertuples(index=False)
    ]

    connection.executemany(
        """
        INSERT INTO sea_state_region_metrics
        (region_id, ts, wave_mean, wave_p90, head_current_mean, head_current_p90,
         head_wind_mean, head_wind_p90, wind_speed_p90, current_speed_p90, samples)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    return len(rows)


def _maybe_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_ingest(lookback_hours: int) -> None:
    configs = _load_region_configs()
    if not configs:
        LOG.warning("No region configurations found.")
        return

    waves_files = _latest_files(WAVES_DIR)
    currents_files = _latest_files(CURRENTS_DIR)

    LOG.info("Using %d wave files, %d current files", len(waves_files), len(currents_files))
    if not waves_files:
        LOG.error("No CMEMS wave NetCDF files available in %s", WAVES_DIR)
        return

    con = duckdb.connect("db/spvx.duckdb")
    try:
        _ensure_table(con)
        total_rows = 0

        for region in configs:
            LOG.info("Processing region %s (%s)", region.region_id, region.label)
            frame = _collect_region_metrics(region, waves_files, currents_files, lookback_hours)
            if frame.empty:
                LOG.warning("  No CMEMS samples within lookback window.")
                continue
            written = _write_region_metrics(con, frame)
            total_rows += written
            LOG.info("  ✓ Stored %d rows (time span %s → %s)", written, frame['time'].min(), frame['time'].max())

        LOG.info("Finished ingest. Total rows written: %d", total_rows)
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest static CMEMS metrics for chokepoint regions.")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Limit data to the most recent N hours (default: {DEFAULT_LOOKBACK_HOURS}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    run_ingest(lookback_hours=args.lookback_hours)


if __name__ == "__main__":
    main()
