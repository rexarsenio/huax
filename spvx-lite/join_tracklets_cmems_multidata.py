"""
Join tracklets with CMEMS data from multiple datasets (waves + physics).

This script:
1. Loads waves data (VHM0 for wave height)
2. Loads physics data (uo, vo for currents, u10m, v10m for wind)
3. Joins both datasets with tracklets based on time/space
4. Computes head current, head wind, wave encounter
5. Writes to sea_state_samples table
6. Aggregates to sea_state_daily
"""

import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import xarray as xr

from spvx.config import AppSettings
from spvx.open_sea.sis import SISConfig, compute_sis_daily

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

def main():
    LOG.info("=== CMEMS Multi-Dataset Join (Waves + Physics) ===\n")
    
    settings = AppSettings()
    db_path = settings.duckdb_path
    con = duckdb.connect(str(db_path))
    
    # Step 1: Load recent tracklets
    LOG.info("Step 1: Loading recent tracklets...")
    tracklets = con.execute("""
        SELECT 
            tracklet_id,
            mean_lat,
            mean_lon,
            mean_cog,
            start_ts,
            end_ts
        FROM tracklets
        WHERE start_ts >= CURRENT_TIMESTAMP - INTERVAL '2 days'
        ORDER BY start_ts DESC
        LIMIT 5000
    """).fetchdf()
    
    LOG.info(f"✓ Loaded {len(tracklets)} recent tracklets\n")
    
    if tracklets.empty:
        LOG.warning("No tracklets found. Exiting.")
        return
    
    # Step 2: Open CMEMS NetCDF files
    LOG.info("Step 2: Opening CMEMS NetCDF files...")
    waves_dir = Path("data/sea_state/waves")
    physics_dir = Path("data/sea_state/currents")
    
    # Find latest files
    waves_files = sorted(waves_dir.glob("*.nc"))
    physics_files = sorted(physics_dir.glob("*.nc"))
    
    if not waves_files:
        LOG.error("No waves NetCDF files found!")
        return
    if not physics_files:
        LOG.error("No physics NetCDF files found!")
        return
    
    waves_file = waves_files[-1]
    physics_file = physics_files[-1]
    
    LOG.info(f"  Waves: {waves_file.name}")
    LOG.info(f"  Physics: {physics_file.name}")
    
    ds_waves = xr.open_dataset(waves_file)
    ds_physics = xr.open_dataset(physics_file)
    
    LOG.info(f"  Waves dataset: {len(ds_waves.time)} times, {len(ds_waves.latitude)} lats, {len(ds_waves.longitude)} lons")
    LOG.info(f"  Physics dataset: {len(ds_physics.time)} times, {len(ds_physics.latitude)} lats, {len(ds_physics.longitude)} lons\n")
    
    # Step 3: Process tracklets
    LOG.info("Step 3: Processing tracklets with point sampling...")
    
    samples_list = []
    batch_size = 10
    
    for idx, row in tracklets.iterrows():
        tracklet_id = row['tracklet_id']
        lat = row['mean_lat']
        lon = row['mean_lon']
        cog_rad = np.radians(row['mean_cog'])
        start_ts = pd.Timestamp(row['start_ts'])
        
        # Sample waves data
        try:
            waves_sample = ds_waves.sel(
                latitude=lat,
                longitude=lon,
                time=start_ts,
                method='nearest'
            )
            
            hs = float(waves_sample['VHM0'].values)
            
        except Exception as e:
            hs = np.nan
        
        # Sample physics data
        try:
            physics_sample = ds_physics.sel(
                latitude=lat,
                longitude=lon,
                time=start_ts,
                method='nearest'
            )
            
            # Try different variable names
            if 'u10m' in ds_physics.data_vars:
                u10 = float(physics_sample['u10m'].values)
                v10 = float(physics_sample['v10m'].values)
            elif 'u10' in ds_physics.data_vars:
                u10 = float(physics_sample['u10'].values)
                v10 = float(physics_sample['v10'].values)
            else:
                u10, v10 = np.nan, np.nan
            
            if 'uo' in ds_physics.data_vars:
                uo = float(physics_sample['uo'].values)
                vo = float(physics_sample['vo'].values)
            else:
                uo, vo = np.nan, np.nan
                
        except Exception as e:
            u10, v10, uo, vo = np.nan, np.nan, np.nan, np.nan
        
        # Compute head components
        if not (np.isnan(uo) or np.isnan(vo)):
            head_current_kn = -(uo * np.cos(cog_rad) + vo * np.sin(cog_rad)) * 1.94384
        else:
            head_current_kn = 0.0
        
        if not (np.isnan(u10) or np.isnan(v10)):
            head_wind_ms = -(u10 * np.cos(cog_rad) + v10 * np.sin(cog_rad))
        else:
            head_wind_ms = 0.0
        
        wave_encounter_m = hs if not np.isnan(hs) else 0.0
        
        samples_list.append({
            'tracklet_id': tracklet_id,
            'ts': start_ts,
            'lat': lat,
            'lon': lon,
            'hs': wave_encounter_m,
            'u10': u10,
            'v10': v10,
            'uo': uo,
            'vo': vo,
            'sst_anom': 0.0,  # Not available
            'head_current_kn': head_current_kn,
            'head_wind_ms': head_wind_ms,
            'wave_encounter_m': wave_encounter_m,
        })
        
        if (idx + 1) % batch_size == 0:
            LOG.info(f"  Processed {idx + 1}/{len(tracklets)} tracklets, {len(samples_list)} samples so far...")
    
    LOG.info(f"✓ Processed {len(tracklets)} tracklets, generated {len(samples_list)} samples\n")
    
    # Step 4: Write to database
    LOG.info("Step 4: Writing to database...")
    
    df_samples = pd.DataFrame(samples_list)
    df_samples["ts"] = pd.to_datetime(df_samples["ts"], utc=True)

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

    if not df_samples.empty:
        min_ts = df_samples["ts"].min().to_pydatetime()
        max_ts = df_samples["ts"].max().to_pydatetime()
        LOG.info(
            "Deleting existing samples between %s and %s",
            min_ts.isoformat(),
            max_ts.isoformat(),
        )
        con.execute(
            "DELETE FROM sea_state_samples WHERE ts BETWEEN ? AND ?",
            [min_ts, max_ts],
        )
        con.register("df_samples_temp", df_samples)
        con.execute("INSERT INTO sea_state_samples SELECT * FROM df_samples_temp")
        con.unregister("df_samples_temp")
    LOG.info(f"✓ Written {len(df_samples)} samples to sea_state_samples table\n")
    
    # Step 5: Aggregate to sea_state_daily
    LOG.info("Step 5: Aggregating to sea_state_daily...")
    
    rows_inserted = compute_sis_daily(con, SISConfig())
    
    LOG.info(f"✓ Aggregated {rows_inserted} corridor-day rows to sea_state_daily\n")
    
    # Step 6: Show results
    LOG.info("=" * 80)
    LOG.info("RESULTS")
    LOG.info("=" * 80)
    
    results = con.execute("""
        SELECT 
            corridor_id,
            ds,
            sis_mean,
            we_p90_m,
            hc_p90_kn,
            hw_p90_ms,
            n_samples
        FROM sea_state_daily
        ORDER BY ds DESC, corridor_id
        LIMIT 10
    """).fetchall()
    
    for row in results:
        LOG.info(f"\n{row[0]} - {row[1]}:")
        LOG.info(f"  SIS: {row[2]:.3f} ({int(row[2]*100)}%)")
        LOG.info(f"  Wave P90: {row[3]:.2f}m")
        LOG.info(f"  Current P90: {row[4]:.2f}kn {'✓' if abs(row[4]) > 0.01 else '⚠ Still 0'}")
        LOG.info(f"  Wind P90: {row[5]:.2f}m/s {'✓' if abs(row[5]) > 0.01 else '⚠ Still 0'}")
        LOG.info(f"  Samples: {row[6]}")
    
    con.close()
    ds_waves.close()
    ds_physics.close()
    
    LOG.info("\n✅ DONE!")

if __name__ == "__main__":
    main()
