#!/usr/bin/env python
"""
Spatial-temporal join of CMEMS NetCDF data with real vessel tracklets.

This script:
1. Reads real tracklets from database
2. Gets actual AIS fix positions for each tracklet
3. Loads CMEMS NetCDF files for relevant regions
4. Performs nearest-neighbor spatial-temporal join
5. Computes head components (wind, current, wave)
6. Writes to sea_state_samples table
"""

import numpy as np
import pandas as pd
import xarray as xr
import duckdb
from pathlib import Path
from datetime import datetime, timedelta, timezone
from scipy.spatial import cKDTree
import logging

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def load_tracklets_from_db(db_path="db/spvx.duckdb", only_real=True):
    """Load real tracklets from database."""
    con = duckdb.connect(db_path, read_only=True)

    try:
        # Only real tracklets (not mock)
        where_clause = "WHERE tracklet_id < 1000000" if only_real else ""

        tracklets = con.execute(f"""
            SELECT tracklet_id, mmsi, poly_from_id, poly_to_id,
                   start_ts, end_ts, mean_sog, mean_cog, n_fixes
            FROM tracklets
            {where_clause}
            ORDER BY start_ts DESC
        """).fetchdf()

        LOG.info(f"Loaded {len(tracklets)} tracklets from database")
        return tracklets

    finally:
        con.close()


def get_tracklet_fixes(tracklet_id, mmsi, start_ts, end_ts, db_path="db/spvx.duckdb"):
    """Get actual AIS fixes for a tracklet."""
    con = duckdb.connect(db_path, read_only=True)

    try:
        fixes = con.execute("""
            SELECT ts, lat, lon, sog, cog
            FROM open_sea_fixes
            WHERE mmsi = ?
              AND ts BETWEEN ? AND ?
            ORDER BY ts
        """, [mmsi, start_ts, end_ts]).fetchall()

        return fixes

    finally:
        con.close()


def load_cmems_netcdf(netcdf_path):
    """Load CMEMS NetCDF file and extract grid data."""
    LOG.info(f"Loading CMEMS NetCDF: {netcdf_path}")

    ds = xr.open_dataset(netcdf_path)

    # Extract variables
    time = ds['time'].values
    lat = ds['latitude'].values
    lon = ds['longitude'].values

    # Create a flat grid of all points
    records = []

    for t_idx, t in enumerate(time):
        for lat_idx, lat_val in enumerate(lat):
            for lon_idx, lon_val in enumerate(lon):
                record = {
                    'time': pd.Timestamp(t),
                    'lat': float(lat_val),
                    'lon': float(lon_val),
                }

                # Extract wave data
                if 'VHM0' in ds:
                    record['hs'] = float(ds['VHM0'].values[t_idx, lat_idx, lon_idx])
                elif 'hs' in ds:
                    record['hs'] = float(ds['hs'].values[t_idx, lat_idx, lon_idx])
                else:
                    record['hs'] = 0.0

                # Extract wind data
                if 'u10' in ds:
                    record['u10'] = float(ds['u10'].values[t_idx, lat_idx, lon_idx])
                else:
                    record['u10'] = 0.0

                if 'v10' in ds:
                    record['v10'] = float(ds['v10'].values[t_idx, lat_idx, lon_idx])
                else:
                    record['v10'] = 0.0

                # Extract current data
                if 'uo' in ds:
                    record['uo'] = float(ds['uo'].values[t_idx, lat_idx, lon_idx])
                else:
                    record['uo'] = 0.0

                if 'vo' in ds:
                    record['vo'] = float(ds['vo'].values[t_idx, lat_idx, lon_idx])
                else:
                    record['vo'] = 0.0

                # SST anomaly
                record['sst_anom'] = 0.0  # Not in all datasets

                records.append(record)

    df = pd.DataFrame(records)
    df['time'] = pd.to_datetime(df['time'], utc=True)

    LOG.info(f"  Loaded {len(df)} grid points from NetCDF")

    ds.close()
    return df


def spatial_temporal_join_single(tracklet_fixes, cmems_df, mean_cog, max_distance_km=100, max_time_hours=12):
    """
    Perform nearest-neighbor spatial-temporal join for a single tracklet.

    Args:
        tracklet_fixes: List of (ts, lat, lon, sog, cog) tuples
        cmems_df: DataFrame with columns [time, lat, lon, hs, u10, v10, uo, vo, sst_anom]
        mean_cog: Mean course over ground in radians
        max_distance_km: Maximum spatial distance for match
        max_time_hours: Maximum temporal distance for match

    Returns:
        List of matched samples
    """
    if cmems_df is None or cmems_df.empty or not tracklet_fixes:
        return []

    results = []

    # Build spatial index for CMEMS points
    cmems_coords = cmems_df[['lat', 'lon']].values
    tree = cKDTree(cmems_coords)

    for ts, lat, lon, sog, cog in tracklet_fixes:
        # Find nearest CMEMS points spatially
        distances, indices = tree.query([lat, lon], k=10)

        # Check temporal distance
        fix_time = pd.Timestamp(ts, tz='UTC')

        best_match = None
        best_score = float('inf')

        for dist_deg, idx in zip(distances, indices):
            dist_km = dist_deg * 111  # Convert degrees to km

            if dist_km > max_distance_km:
                continue

            cmems_time = cmems_df.iloc[idx]['time']
            time_diff_hours = abs((fix_time - cmems_time).total_seconds()) / 3600

            if time_diff_hours > max_time_hours:
                continue

            # Combined score: spatial + temporal
            score = dist_km + time_diff_hours * 10  # Weight temporal by 10 km/hour

            if score < best_score:
                best_score = score
                best_match = idx

        if best_match is not None:
            cmems_row = cmems_df.iloc[best_match]

            # Compute head components
            cos_cog = np.cos(mean_cog)
            sin_cog = np.sin(mean_cog)

            # Head current (opposing flow)
            head_current_ms = -(cmems_row['uo'] * cos_cog + cmems_row['vo'] * sin_cog)
            head_current_kn = head_current_ms * 1.94384  # m/s to knots

            # Head wind (opposing)
            head_wind_ms = -(cmems_row['u10'] * cos_cog + cmems_row['v10'] * sin_cog)

            # Wave encounter (simplified - just wave height)
            wave_encounter_m = cmems_row['hs']

            result = {
                'ts': ts,
                'lat': lat,
                'lon': lon,
                'hs': cmems_row['hs'],
                'u10': cmems_row['u10'],
                'v10': cmems_row['v10'],
                'uo': cmems_row['uo'],
                'vo': cmems_row['vo'],
                'sst_anom': cmems_row['sst_anom'],
                'head_current_kn': head_current_kn,
                'head_wind_ms': head_wind_ms,
                'wave_encounter_m': wave_encounter_m,
            }
            results.append(result)

    return results


def write_samples_to_db(samples, db_path="db/spvx.duckdb"):
    """Write sea state samples to database."""
    if not samples:
        LOG.warning("No samples to write")
        return 0

    con = duckdb.connect(db_path)

    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sea_state_samples (
                tracklet_id TEXT,
                ts TIMESTAMP,
                lat DOUBLE,
                lon DOUBLE,
                hs DOUBLE,
                u10 DOUBLE,
                v10 DOUBLE,
                uo DOUBLE,
                vo DOUBLE,
                sst_anom DOUBLE,
                head_current_kn DOUBLE,
                head_wind_ms DOUBLE,
                wave_encounter_m DOUBLE
            )
            """
        )

        times = pd.to_datetime([s["ts"] for s in samples], utc=True)
        min_ts = times.min()
        max_ts = times.max()
        LOG.info(
            "Deleting existing sea_state_samples between %s and %s",
            min_ts.isoformat(),
            max_ts.isoformat(),
        )
        con.execute(
            "DELETE FROM sea_state_samples WHERE ts BETWEEN ? AND ?",
            [min_ts.to_pydatetime(), max_ts.to_pydatetime()],
        )

        rows = [
            (
                str(sample["tracklet_id"]),
                sample["ts"],
                sample["lat"],
                sample["lon"],
                sample["hs"],
                sample["u10"],
                sample["v10"],
                sample["uo"],
                sample["vo"],
                sample["sst_anom"],
                sample["head_current_kn"],
                sample["head_wind_ms"],
                sample["wave_encounter_m"],
            )
            for sample in samples
        ]
        con.executemany(
            """
            INSERT INTO sea_state_samples
            (tracklet_id, ts, lat, lon, hs, u10, v10, uo, vo, sst_anom,
             head_current_kn, head_wind_ms, wave_encounter_m)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.commit()
        count = len(rows)
        LOG.info("✓ Wrote %s samples to sea_state_samples", count)
        return count
    finally:
        con.close()


def main():
    LOG.info("=== CMEMS-Tracklet Join (Real Data) ===\n")

    # Step 1: Load real tracklets
    LOG.info("Step 1: Loading real tracklets from database...")
    tracklets = load_tracklets_from_db(only_real=True)

    if tracklets.empty:
        LOG.error("No real tracklets found! Run: python generate_tracklets_from_events.py")
        return

    # Limit to recent tracklets for demo (last 24 hours)
    cutoff = pd.Timestamp(datetime.now(timezone.utc) - timedelta(hours=24))
    tracklets['start_ts'] = pd.to_datetime(tracklets['start_ts'], utc=True)
    recent_tracklets = tracklets[tracklets['start_ts'] >= cutoff]
    LOG.info(f"✓ Found {len(recent_tracklets)} tracklets from last 24 hours")

    # Step 2: Check for available CMEMS NetCDF files
    LOG.info("\nStep 2: Checking for CMEMS NetCDF files...")
    netcdf_dir = Path("data/sea_state/waves")

    if not netcdf_dir.exists():
        LOG.error(f"No CMEMS data directory found at {netcdf_dir}")
        return

    netcdf_files = list(netcdf_dir.glob("*.nc"))

    if not netcdf_files:
        LOG.error(f"No NetCDF files found in {netcdf_dir}")
        return

    LOG.info(f"✓ Found {len(netcdf_files)} NetCDF files")

    # Step 3: Load CMEMS data (use first file for demo)
    LOG.info("\nStep 3: Loading CMEMS NetCDF data...")
    netcdf_file = netcdf_files[0]
    cmems_df = load_cmems_netcdf(netcdf_file)

    # Step 4: Join tracklets with CMEMS data
    LOG.info("\nStep 4: Performing spatial-temporal join...")

    all_samples = []
    processed = 0

    for _, tracklet in recent_tracklets.head(100).iterrows():  # Limit to first 100 for demo
        # Get AIS fixes for this tracklet
        fixes = get_tracklet_fixes(
            tracklet['tracklet_id'],
            tracklet['mmsi'],
            tracklet['start_ts'],
            tracklet['end_ts']
        )

        if not fixes:
            continue

        # Perform join
        samples = spatial_temporal_join_single(
            fixes,
            cmems_df,
            tracklet['mean_cog'],
            max_distance_km=100,
            max_time_hours=12
        )

        # Add tracklet_id to each sample
        for sample in samples:
            sample['tracklet_id'] = tracklet['tracklet_id']

        all_samples.extend(samples)
        processed += 1

        if processed % 10 == 0:
            LOG.info(f"  Processed {processed} tracklets, {len(all_samples)} samples so far...")

    LOG.info(f"✓ Matched {len(all_samples)} samples from {processed} tracklets")

    # Step 5: Write to database
    if all_samples:
        LOG.info("\nStep 5: Writing to database...")
        write_samples_to_db(all_samples)
    else:
        LOG.warning("No samples to write!")

    # Summary
    LOG.info("\n=== Summary ===")
    LOG.info(f"Tracklets processed:  {processed}")
    LOG.info(f"Samples generated:    {len(all_samples)}")
    LOG.info(f"CMEMS grid points:    {len(cmems_df)}")
    LOG.info("\n✓ Done! Ready to compute SIS scores: python -m spvx.cli sea-state-join")


if __name__ == "__main__":
    main()
