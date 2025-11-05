#!/usr/bin/env python
"""
Ultra-optimized CMEMS-Tracklet Join using point-by-point sampling.

Instead of loading the entire grid into memory, this version:
1. Opens the NetCDF file once
2. For each tracklet fix, samples the nearest grid point directly
3. Much faster and lower memory usage
"""

import numpy as np
import pandas as pd
import xarray as xr
import duckdb
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def load_tracklets(limit=4200):
    """Load recent real tracklets."""
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    try:
        cutoff = pd.Timestamp(datetime.now(timezone.utc) - timedelta(hours=24))

        tracklets = con.execute(
            """
            SELECT
                tracklet_id,
                mmsi,
                poly_from_id,
                start_ts,
                end_ts,
                mean_cog,
                n_fixes
            FROM tracklets
            WHERE start_ts >= ?
              AND poly_from_id IS NOT NULL
            ORDER BY start_ts DESC
            LIMIT ?
            """,
            [cutoff, limit],
        ).fetchdf()

        return tracklets

    finally:
        con.close()


def get_tracklet_fixes(mmsi, start_ts, end_ts):
    """Get AIS fixes for a tracklet."""
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


def sample_cmems_at_point(ds, lat, lon, timestamp):
    """
    Sample CMEMS data at a specific point using nearest-neighbor.

    This is much faster than loading the entire grid!
    """
    try:
        # Convert timestamp to numpy datetime64
        time_val = pd.Timestamp(timestamp).to_datetime64()

        # Use xarray's fast nearest-neighbor selection
        point = ds.sel(
            latitude=lat,
            longitude=lon,
            time=time_val,
            method='nearest'
        )

        # Extract values
        result = {
            'hs': float(point['VHM0'].values) if 'VHM0' in point else 0.0,
            'u10': 0.0,  # Wind not in wave dataset
            'v10': 0.0,
            'uo': 0.0,  # Currents not in wave dataset
            'vo': 0.0,
            'sst_anom': 0.0,
        }

        return result

    except Exception as e:
        LOG.debug(f"Failed to sample at ({lat:.2f}, {lon:.2f}): {e}")
        return None


def process_tracklet(tracklet, ds):
    """Process a single tracklet and match with CMEMS data."""
    fixes = get_tracklet_fixes(
        tracklet['mmsi'],
        tracklet['start_ts'],
        tracklet['end_ts']
    )

    if not fixes:
        return []

    samples = []
    mean_cog = tracklet['mean_cog']
    cos_cog = np.cos(mean_cog)
    sin_cog = np.sin(mean_cog)

    for ts, lat, lon, sog, cog in fixes:
        # Sample CMEMS at this exact point
        cmems = sample_cmems_at_point(ds, lat, lon, ts)

        if cmems is None:
            continue

        # Compute head components
        head_current_ms = -(cmems['uo'] * cos_cog + cmems['vo'] * sin_cog)
        head_current_kn = head_current_ms * 1.94384

        head_wind_ms = -(cmems['u10'] * cos_cog + cmems['v10'] * sin_cog)
        wave_encounter_m = cmems['hs']

        sample = {
            'tracklet_id': tracklet['tracklet_id'],
            'ts': ts,
            'lat': lat,
            'lon': lon,
            'hs': cmems['hs'],
            'u10': cmems['u10'],
            'v10': cmems['v10'],
            'uo': cmems['uo'],
            'vo': cmems['vo'],
            'sst_anom': cmems['sst_anom'],
            'head_current_kn': head_current_kn,
            'head_wind_ms': head_wind_ms,
            'wave_encounter_m': wave_encounter_m,
        }
        samples.append(sample)

    return samples


def write_samples_to_db(samples):
    """Write samples to database."""
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
    LOG.info("=== Fast CMEMS-Tracklet Join (Point Sampling) ===\n")

    # Step 1: Load tracklets
    LOG.info("Step 1: Loading recent tracklets...")
    tracklets = load_tracklets()  # Will use default limit=4200

    if tracklets.empty:
        LOG.error("No tracklets found!")
        return

    LOG.info(f"✓ Loaded {len(tracklets)} tracklets")

    # Step 2: Open CMEMS NetCDF (keep it open for fast sampling)
    LOG.info("\nStep 2: Opening CMEMS NetCDF file...")
    netcdf_dir = Path("data/sea_state/waves")
    netcdf_files = sorted(netcdf_dir.glob("*.nc"), reverse=True)

    if not netcdf_files:
        LOG.error(f"No NetCDF files in {netcdf_dir}")
        return

    netcdf_file = netcdf_files[0]
    LOG.info(f"Using: {netcdf_file.name}")

    ds = xr.open_dataset(netcdf_file)
    LOG.info(f"✓ Opened dataset: {len(ds['time'])} times, "
             f"{len(ds['latitude'])} lats, {len(ds['longitude'])} lons")

    # Step 3: Process tracklets
    LOG.info("\nStep 3: Processing tracklets with point sampling...")

    all_samples = []
    processed = 0

    try:
        for _, tracklet in tracklets.iterrows():
            samples = process_tracklet(tracklet, ds)
            all_samples.extend(samples)
            processed += 1

            if processed % 10 == 0:
                LOG.info(f"  Processed {processed}/{len(tracklets)} tracklets, "
                         f"{len(all_samples)} samples so far...")

        LOG.info(f"✓ Processed {processed} tracklets, generated {len(all_samples)} samples")

    finally:
        ds.close()

    # Step 4: Write to database
    if all_samples:
        LOG.info("\nStep 4: Writing to database...")
        write_samples_to_db(all_samples)
    else:
        LOG.warning("No samples generated!")

    # Summary
    LOG.info("\n=== Summary ===")
    LOG.info(f"Tracklets processed:  {processed}")
    LOG.info(f"Samples generated:    {len(all_samples)}")
    LOG.info(f"Avg samples/tracklet: {len(all_samples)/processed:.1f}" if processed > 0 else "N/A")

    if len(all_samples) > 0:
        LOG.info("\n✓ Done! Next step:")
        LOG.info("  python -m spvx.cli sea-state-join")
    else:
        LOG.warning("\n⚠ No samples generated. Possible issues:")
        LOG.warning("  - Tracklets outside CMEMS time range")
        LOG.warning("  - Tracklets outside CMEMS spatial coverage")
        LOG.warning("  - Need different NetCDF file")


if __name__ == "__main__":
    main()
