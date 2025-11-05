#!/usr/bin/env python
"""
Process existing CMEMS NetCDF files to Parquet without re-downloading.
"""
from pathlib import Path
import pandas as pd
from spvx.config import load_config
from spvx.sea_state.cmems import extract_region_features, DEFAULT_FEATURES

# Load config
cfg = load_config()
sea_cfg = cfg.get("sea_state", {})
cps_cfg = cfg.get("chokepoints", {})

buffer_km = float(sea_cfg.get("buffer_km", 50))
features_cfg = sea_cfg.get("features") or DEFAULT_FEATURES

# Find existing files
waves_dir = Path("data/sea_state/waves")
currents_dir = Path("data/sea_state/currents")

wav_files = sorted([str(f) for f in waves_dir.glob("*.nc") if f.is_file()])
cur_files = sorted([str(f) for f in currents_dir.glob("*.nc") if f.is_file()])

print(f"Found {len(wav_files)} wave files")
print(f"Found {len(cur_files)} current files")

if not wav_files:
    print("ERROR: No wave files found!")
    exit(1)

# Process each chokepoint
chokepoints_to_process = ["CQ_SG", "CQ_TR", "PORT_EU", "CQ_SUEZ", "CQ_GIBRALTAR"]

for cid in chokepoints_to_process:
    if cid not in cps_cfg:
        print(f"Skipping {cid} (not in config)")
        continue

    meta = cps_cfg[cid]
    print(f"\nProcessing {cid}...")

    try:
        df = extract_region_features(
            waves_files=wav_files,
            currents_files=cur_files,
            features_cfg=features_cfg,
            bbox=meta["bbox"],
            bearing_deg=float(meta.get("bearing_deg", 0.0)),
            buffer_km=buffer_km,
        ).sort_values("time")

        outp = Path(f"data/processed/sea_state_{cid}.parquet")
        outp.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(outp, index=False)
        print(f"✓ Saved {len(df)} rows to {outp}")
    except Exception as e:
        print(f"✗ ERROR processing {cid}: {e}")

print("\n✓ Done!")
