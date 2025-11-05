#!/usr/bin/env python3
"""
Process regional CMEMS currents/wind data and write to sea_state_daily table.

This script processes the small regional NetCDF files downloaded by the technician
instead of the large global files.
"""

import datetime as dt
from pathlib import Path

import pandas as pd

from spvx.sea_state.cmems import extract_region_features

# Regional files mapping
REGIONAL_FILES = {
    "CHOKEPOINT_MALACCA->UNK": {
        "currents": "data/external/cmems/currents/malacca/currents_malacca_2025-10-31_to_2025-11-02.nc",
        "waves": [],  # Use global waves (already working)
        "bbox": {"lat_min": 1.0, "lat_max": 4.0, "lon_min": 100.0, "lon_max": 104.0},
        "bearing_deg": 300,
    },
    "CHOKEPOINT_SINGAPORE_STRAIT->UNK": {
        "currents": "data/external/cmems/currents/singapore/currents_singapore_2025-10-31_to_2025-11-02.nc",
        "waves": [],
        "bbox": {"lat_min": 0.5, "lat_max": 2.0, "lon_min": 103.3, "lon_max": 104.3},
        "bearing_deg": 300,
    },
    "CHOKEPOINT_SUEZ_NORTH->UNK": {
        "currents": "data/external/cmems/currents/suez/currents_suez_2025-10-31_to_2025-11-02.nc",
        "waves": [],
        "bbox": {"lat_min": 29.8, "lat_max": 31.3, "lon_min": 32.2, "lon_max": 32.6},
        "bearing_deg": 180,
    },
    "CHOKEPOINT_GIBRALTAR->UNK": {
        "currents": "data/external/cmems/currents/gibraltar/currents_gibraltar_2025-10-31_to_2025-11-02.nc",
        "waves": [],
        "bbox": {"lat_min": 35.8, "lat_max": 36.2, "lon_min": -5.5, "lon_max": -5.2},
        "bearing_deg": 90,
    },
    "CHOKEPOINT_BOSPORUS->UNK": {
        "currents": "data/external/cmems/currents/bosporus/currents_bosporus_2025-10-31_to_2025-11-02.nc",
        "waves": [],
        "bbox": {"lat_min": 40.9, "lat_max": 41.4, "lon_min": 28.6, "lon_max": 29.3},
        "bearing_deg": 20,
    },
}

# Features to extract
FEATURES_CFG = [
    {
        "id": "current_speed",
        "dataset": "currents",
        "type": "vector_magnitude",
        "variables": ["uo", "vo"],
        "stats": ["p90"],
    },
    {
        "id": "opp_current",
        "dataset": "currents",
        "type": "opposing",
        "variables": ["uo", "vo"],
        "stats": ["mean"],
    },
]


def process_regional_currents(db_path: str = "db/spvx.duckdb", output_csv: str = "data/processed/regional_currents.csv"):
    """
    Process regional currents files and write to CSV (for later DB import).

    This reads the small regional NetCDF files, extracts current statistics,
    and writes them to CSV file that can be imported when DB is available.
    """

    # Don't connect to DB yet - just process NetCDF files
    con = None

    print("📊 Processing regional CMEMS currents data...\n")

    all_rows = []

    for corridor_id, config in REGIONAL_FILES.items():
        currents_file = config["currents"]

        # Check if file exists
        if not Path(currents_file).exists():
            print(f"⚠️  {corridor_id}: File not found: {currents_file}")
            continue

        print(f"Processing {corridor_id}...")
        print(f"  File: {currents_file}")

        # Extract features from regional NetCDF
        df = extract_region_features(
            waves_files=[],  # No waves (already in DB from global files)
            currents_files=[currents_file],
            features_cfg=FEATURES_CFG,
            bbox=config["bbox"],
            bearing_deg=config["bearing_deg"],
            buffer_km=0.0,  # No buffer needed for regional files
        )

        if df.empty:
            print(f"  ⚠️  No data extracted")
            continue

        # Convert to daily aggregates
        df["ds"] = pd.to_datetime(df["time"]).dt.date
        daily = df.groupby("ds").agg({
            "current_speed_p90": "mean",  # Average of 90th percentiles across time
            "opp_current_mean": "mean",   # Average of opposing currents
        }).reset_index()

        # Add corridor_id
        daily["corridor_id"] = corridor_id

        # Rename columns to match sea_state_daily schema
        daily = daily.rename(columns={
            "current_speed_p90": "hc_p90_kn",  # Current speed 90th percentile (m/s -> kn conversion below)
            "opp_current_mean": "opp_current_mean_ms",  # Opposing current mean (m/s)
        })

        # Convert m/s to knots (1 m/s = 1.94384 knots)
        daily["hc_p90_kn"] = daily["hc_p90_kn"] * 1.94384
        daily["opp_current_mean_ms"] = daily["opp_current_mean_ms"] * 1.94384  # Also convert for consistency

        print(f"  ✅ Extracted {len(daily)} daily records")
        print(f"     Date range: {daily['ds'].min()} to {daily['ds'].max()}")
        print(f"     Current speed (hc_p90_kn): {daily['hc_p90_kn'].mean():.2f} kn (mean)")

        all_rows.append(daily)

    if not all_rows:
        print("\n⚠️  No data to update!")
        return

    # Combine all corridors
    combined = pd.concat(all_rows, ignore_index=True)

    print(f"\n📦 Total records extracted: {len(combined)}")
    print(f"   Corridors: {combined['corridor_id'].nunique()}")
    print(f"   Date range: {combined['ds'].min()} to {combined['ds'].max()}")
    print(f"   Avg current speed: {combined['hc_p90_kn'].mean():.2f} kn")

    # Write to CSV
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_csv, index=False)
    print(f"\n💾 Wrote data to {output_csv}")

    print("\n📋 Summary by corridor:")
    summary = combined.groupby("corridor_id").agg({
        "hc_p90_kn": "mean",
        "ds": "count"
    }).round(2)
    summary.columns = ["Avg Current (kn)", "Days"]
    print(summary.to_string())

    print("\n✅ Done!")
    print(f"\n💡 To import into database when ready:")
    print(f"   duckdb db/spvx.duckdb")
    print(f"   >> CREATE TEMP TABLE currents_temp AS SELECT * FROM read_csv_auto('{output_csv}');")
    print(f"   >> UPDATE sea_state_daily SET hc_p90_kn = t.hc_p90_kn")
    print(f"   >> FROM currents_temp t WHERE sea_state_daily.ds = t.ds AND sea_state_daily.corridor_id = t.corridor_id;")


if __name__ == "__main__":
    process_regional_currents()
