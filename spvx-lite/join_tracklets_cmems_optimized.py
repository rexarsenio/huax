#!/usr/bin/env python
"""
Optimized spatial-temporal join of CMEMS NetCDF data with real vessel tracklets.

This version extracts only relevant geographic regions instead of the entire global grid.
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


def get_bbox_from_tracklets(tracklets):
    """Get bounding box from tracklet positions."""
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    try:
        # Get all AIS fixes for recent tracklets
        mmsis = tracklets['mmsi'].tolist()
        start_min = tracklets['start_ts'].min()
        end_max = tracklets['end_ts'].max()

        fixes = con.execute("""
            SELECT MIN(lat) as min_lat, MAX(lat) as max_lat,
                   MIN(lon) as min_lon, MAX(lon) as max_lon
            FROM open_sea_fixes
            WHERE mmsi = ANY(?)
              AND ts BETWEEN ? AND ?
        """, [mmsis, start_min, end_max]).fetchone()

        # Add buffer
        buffer = 2.0  # degrees
        bbox = {
            'min_lat': fixes[0] - buffer,
            'max_lat': fixes[1] + buffer,
            'min_lon': fixes[2] - buffer,
            'max_lon': fixes[3] + buffer,
        }

        LOG.info(f"Bounding box: lat [{bbox['min_lat']:.2f}, {bbox['max_lat']:.2f}], "
                 f"lon [{bbox['min_lon']:.2f}, {bbox['max_lon']:.2f}]")

        return bbox

    finally:
        con.close()


def load_cmems_region(netcdf_path, bbox):
    """Load CMEMS NetCDF file for a specific region."""
    LOG.info(f"Loading CMEMS NetCDF region: {netcdf_path}")

    ds = xr.open_dataset(netcdf_path)

    # Select region
    ds_region = ds.sel(
        latitude=slice(bbox['min_lat'], bbox['max_lat']),
        longitude=slice(bbox['min_lon'], bbox['max_lon'])
    )

    LOG.info(f"  Regional grid: {len(ds_region['time'])} times × "
             f"{len(ds_region['latitude'])} lats × {len(ds_region['longitude'])} lons")

    # Extract to DataFrame
    records = []

    for t in ds_region['time'].values:
        for lat in ds_region['latitude'].values:
            for lon in ds_region['longitude'].values:
                # Get values at this point
                point = ds_region.sel(time=t, latitude=lat, longitude=lon, method='nearest')

                record = {
                    'time': pd.Timestamp(t),
                    'lat': float(lat),
                    'lon': float(lon),
                    'hs': float(point['VHM0'].values) if 'VHM0' in point else 0.0,
                    'u10': 0.0,  # Wind not in wave dataset
                    'v10': 0.0,
                    'uo': 0.0,  # Currents not in wave dataset
                    'vo': 0.0,
                    'sst_anom': 0.0,
                }
                records.append(record)

    df = pd.DataFrame(records)
    df['time'] = pd.to_datetime(df['time'], utc=True)

    LOG.info(f"  Loaded {len(df)} grid points")

    ds.close()
    return df


def get_tracklet_fixes(tracklet_id, mmsi, start_ts, end_ts):
    """Get actual AIS fixes for a tracklet."""
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

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


def spatial_temporal_join_single(tracklet_fixes, cmems_df, mean_cog, max_distance_km=50, max_time_hours=6):
    """Perform nearest-neighbor spatial-temporal join for a single tracklet."""
    if cmems_df is None or cmems_df.empty or not tracklet_fixes:
        return []

    results = []

    # Build spatial index
    cmems_coords = cmems_df[['lat', 'lon']].values
    tree = cKDTree(cmems_coords)

    for ts, lat, lon, sog, cog in tracklet_fixes:
        # Find nearest CMEMS points
        distances, indices = tree.query([lat, lon], k=5)

        fix_time = pd.Timestamp(ts, tz='UTC')
        best_match = None
        best_score = float('inf')

        for dist_deg, idx in zip(distances, indices):
            dist_km = dist_deg * 111

            if dist_km > max_distance_km:
                continue

            cmems_time = cmems_df.iloc[idx]['time']
            time_diff_hours = abs((fix_time - cmems_time).total_seconds()) / 3600

            if time_diff_hours > max_time_hours:
                continue

            score = dist_km + time_diff_hours * 10

            if score < best_score:
                best_score = score
                best_match = idx

        if best_match is not None:
            cmems_row = cmems_df.iloc[best_match]

            # Compute head components
            cos_cog = np.cos(mean_cog)
            sin_cog = np.sin(mean_cog)

            head_current_ms = -(cmems_row['uo'] * cos_cog + cmems_row['vo'] * sin_cog)
            head_current_kn = head_current_ms * 1.94384

            head_wind_ms = -(cmems_row['u10'] * cos_cog + cmems_row['v10'] * sin_cog)
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


def write_samples_to_db(samples):
    """Write sea state samples to database."""
    if not samples:
        LOG.warning("No samples to write")
        return 0

    con = duckdb.connect("db/spvx.duckdb")

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
    LOG.info("=== Optimized CMEMS-Tracklet Join ===\n")

    # Step 1: Load recent tracklets
    LOG.info("Step 1: Loading recent tracklets...")
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    cutoff = pd.Timestamp(datetime.now(timezone.utc) - timedelta(hours=24))

    tracklets = con.execute("""
        SELECT tracklet_id, mmsi, poly_from_id, start_ts, end_ts, mean_sog, mean_cog, n_fixes
        FROM tracklets
        WHERE tracklet_id < 1000000
          AND start_ts >= ?
        ORDER BY start_ts DESC
        LIMIT 100
    """, [cutoff]).fetchdf()

    con.close()

    LOG.info(f"✓ Loaded {len(tracklets)} recent tracklets")

    if tracklets.empty:
        LOG.error("No recent tracklets found!")
        return

    # Step 2: Get bounding box
    LOG.info("\nStep 2: Computing bounding box...")
    bbox = get_bbox_from_tracklets(tracklets)

    # Step 3: Load NetCDF region
    LOG.info("\nStep 3: Loading CMEMS NetCDF region...")
    netcdf_dir = Path("data/sea_state/waves")
    netcdf_files = list(netcdf_dir.glob("*.nc"))

    if not netcdf_files:
        LOG.error(f"No NetCDF files found in {netcdf_dir}")
        return

    netcdf_file = netcdf_files[0]  # Use most recent
    cmems_df = load_cmems_region(netcdf_file, bbox)

    # Step 4: Join
    LOG.info("\nStep 4: Performing spatial-temporal join...")

    all_samples = []
    processed = 0

    for _, tracklet in tracklets.iterrows():
        fixes = get_tracklet_fixes(
            tracklet['tracklet_id'],
            tracklet['mmsi'],
            tracklet['start_ts'],
            tracklet['end_ts']
        )

        if not fixes:
            continue

        samples = spatial_temporal_join_single(
            fixes,
            cmems_df,
            tracklet['mean_cog'],
            max_distance_km=50,
            max_time_hours=6
        )

        for sample in samples:
            sample['tracklet_id'] = tracklet['tracklet_id']

        all_samples.extend(samples)
        processed += 1

        if processed % 20 == 0:
            LOG.info(f"  Processed {processed} tracklets, {len(all_samples)} samples...")

    LOG.info(f"✓ Matched {len(all_samples)} samples from {processed} tracklets")

    # Step 5: Write to DB
    if all_samples:
        LOG.info("\nStep 5: Writing to database...")
        write_samples_to_db(all_samples)

    LOG.info("\n=== Summary ===")
    LOG.info(f"Tracklets processed:  {processed}")
    LOG.info(f"Samples generated:    {len(all_samples)}")
    LOG.info(f"CMEMS grid points:    {len(cmems_df)}")
    LOG.info("\n✓ Done! Ready to compute SIS: python -m spvx.cli sea-state-join")


if __name__ == "__main__":
    main()
