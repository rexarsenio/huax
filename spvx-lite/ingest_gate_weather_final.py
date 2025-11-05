#!/usr/bin/env python3
"""
Final working gate weather collection using CMEMS.
Handles different time resolutions for waves (3h) and currents (6h).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from typing import Dict, List

import duckdb
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    import copernicusmarine
except ImportError:
    print("❌ copernicusmarine not installed!")
    print("   Install with: pip install copernicusmarine")
    sys.exit(1)

from spvx.db import ensure_core_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOG = logging.getLogger("gate_weather")

# Gate definitions
GATE_WEATHER_REGIONS = {
    "GATE_HORMUZ": {
        "bbox": {"lat_min": 24.0, "lat_max": 28.2, "lon_min": 54.0, "lon_max": 58.5},
        "name": "Strait of Hormuz",
        "basin": "APAC",
    },
    "GATE_SUEZ_N": {
        "bbox": {"lat_min": 31.0, "lat_max": 31.6, "lon_min": 32.0, "lon_max": 32.7},
        "name": "Suez Canal North (Port Said)",
        "basin": "MED",
    },
    "GATE_SUEZ_S": {
        "bbox": {"lat_min": 29.8, "lat_max": 30.4, "lon_min": 32.2, "lon_max": 33.5},
        "name": "Suez Canal South (Port of Suez)",
        "basin": "MED",
    },
    "GATE_BAB_EL_MANDEB": {
        "bbox": {"lat_min": 12.5, "lat_max": 13.5, "lon_min": 42.5, "lon_max": 44.0},
        "name": "Bab el-Mandeb Strait",
        "basin": "APAC",
    },
    "GATE_GIBRALTAR": {
        "bbox": {"lat_min": 35.8, "lat_max": 36.2, "lon_min": -5.5, "lon_max": -5.2},
        "name": "Strait of Gibraltar",
        "basin": "MED",
    },
    "GATE_BOSPORUS": {
        "bbox": {"lat_min": 40.9, "lat_max": 41.4, "lon_min": 28.6, "lon_max": 29.3},
        "name": "Bosporus Strait",
        "basin": "MED",
    },
    "GATE_MALACCA": {
        "bbox": {"lat_min": 0.5, "lat_max": 2.0, "lon_min": 103.3, "lon_max": 104.3},
        "name": "Singapore & Malacca Strait",
        "basin": "APAC",
    },
    "GATE_PANAMA": {
        "bbox": {"lat_min": 8.5, "lat_max": 9.7, "lon_min": -80.2, "lon_max": -79.3},
        "name": "Panama Canal",
        "basin": "NAM",
    },
    "GATE_YUCATAN": {
        "bbox": {"lat_min": 20.7, "lat_max": 22.3, "lon_min": -87.0, "lon_max": -85.7},
        "name": "Yucatan Channel",
        "basin": "NAM",
    },
    "GATE_WEST_AFRICA_BONNY": {
        "bbox": {"lat_min": 3.8, "lat_max": 5.0, "lon_min": 6.5, "lon_max": 7.6},
        "name": "Bonny Terminal (Nigeria)",
        "basin": "AFRICA",
    },
    "GATE_WEST_AFRICA_ESCRAVOS": {
        "bbox": {"lat_min": 4.6, "lat_max": 6.1, "lon_min": 4.7, "lon_max": 5.8},
        "name": "Escravos Terminal (Nigeria)",
        "basin": "AFRICA",
    },
}

WAVES_DATASET_ID = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
CURRENTS_DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"


def create_gate_weather_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create table."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS gate_weather_standalone (
            gate_id VARCHAR NOT NULL,
            gate_name VARCHAR,
            observed_at TIMESTAMP NOT NULL,
            basin VARCHAR,
            hs_m DOUBLE,
            tp_s DOUBLE,
            dp_deg DOUBLE,
            wave_flag INTEGER,
            u_knots DOUBLE,
            v_knots DOUBLE,
            speed_knots DOUBLE,
            current_flag INTEGER,
            wave_source VARCHAR,
            current_source VARCHAR,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (gate_id, observed_at)
        )
    """)


def fetch_gate_weather(gate_id: str, bbox: Dict, gate_name: str, basin: str) -> List[Dict]:
    """Fetch weather data for one gate."""
    LOG.info(f"📍 {gate_id} ({gate_name})")

    username = os.getenv("CMEMS_USERNAME")
    password = os.getenv("CMEMS_PASSWORD")

    if not username or not password:
        LOG.warning("⚠️  Credentials missing")
        return []

    end_time = dt.datetime.now(dt.UTC)
    start_time = end_time - dt.timedelta(hours=24)

    records = []

    try:
        # Fetch waves
        LOG.info(f"  🌊 Fetching waves...")
        wave_ds = copernicusmarine.open_dataset(
            dataset_id=WAVES_DATASET_ID,
            minimum_longitude=bbox["lon_min"],
            maximum_longitude=bbox["lon_max"],
            minimum_latitude=bbox["lat_min"],
            maximum_latitude=bbox["lat_max"],
            start_datetime=start_time,
            end_datetime=end_time,
            username=username,
            password=password,
        )

        # Find wave variable
        wave_var = None
        for var in ["VHM0", "hs", "swh", "VAVH"]:
            if var in wave_ds.data_vars:
                wave_var = var
                break

        if wave_var and "time" in wave_ds.coords:
            # Get all dimensions to average over (excluding time)
            dims_to_avg = [d for d in wave_ds[wave_var].dims if d != "time"]

            # Calculate spatial mean for each timestep
            wave_mean = wave_ds[wave_var].mean(dim=dims_to_avg)

            for time_val in wave_mean.coords["time"].values:
                obs_time = pd.Timestamp(time_val).to_pydatetime()
                hs_val = wave_mean.sel(time=time_val).values
                hs_m = float(hs_val.item() if hasattr(hs_val, 'item') else hs_val)

                records.append({
                    "gate_id": gate_id,
                    "gate_name": gate_name,
                    "observed_at": obs_time,
                    "basin": basin,
                    "hs_m": hs_m,
                    "wave_flag": 1 if hs_m > 3.5 else 0,
                    "wave_source": f"CMEMS:{WAVES_DATASET_ID}",
                })

        wave_ds.close()
        LOG.info(f"  ✅ Waves: {len(records)} records")

        # Fetch currents
        LOG.info(f"  🌀 Fetching currents...")
        current_ds = copernicusmarine.open_dataset(
            dataset_id=CURRENTS_DATASET_ID,
            minimum_longitude=bbox["lon_min"],
            maximum_longitude=bbox["lon_max"],
            minimum_latitude=bbox["lat_min"],
            maximum_latitude=bbox["lat_max"],
            start_datetime=start_time,
            end_datetime=end_time,
            username=username,
            password=password,
        )

        # Find current variables
        u_var = "uo" if "uo" in current_ds.data_vars else None
        v_var = "vo" if "vo" in current_ds.data_vars else None

        current_records = []
        if u_var and v_var and "time" in current_ds.coords:
            # Get all dimensions to average over (excluding time)
            dims_to_avg = [d for d in current_ds[u_var].dims if d != "time"]

            # Calculate spatial mean (including depth if present)
            u_mean = current_ds[u_var].mean(dim=dims_to_avg)
            v_mean = current_ds[v_var].mean(dim=dims_to_avg)

            for time_val in u_mean.coords["time"].values:
                obs_time = pd.Timestamp(time_val).to_pydatetime()
                u_val = u_mean.sel(time=time_val).values
                v_val = v_mean.sel(time=time_val).values

                # Ensure scalar values
                u_ms = float(u_val.item() if hasattr(u_val, 'item') else u_val)
                v_ms = float(v_val.item() if hasattr(v_val, 'item') else v_val)

                # Convert to knots
                u_kn = u_ms * 1.943844
                v_kn = v_ms * 1.943844
                speed_kn = ((u_ms**2 + v_ms**2)**0.5) * 1.943844

                current_records.append({
                    "gate_id": gate_id,
                    "gate_name": gate_name,
                    "observed_at": obs_time,
                    "basin": basin,
                    "u_knots": u_kn,
                    "v_knots": v_kn,
                    "speed_knots": speed_kn,
                    "current_flag": 1 if speed_kn > 3.0 else 0,
                    "current_source": f"CMEMS:{CURRENTS_DATASET_ID}",
                })

        current_ds.close()
        LOG.info(f"  ✅ Currents: {len(current_records)} records")

        # Merge wave and current records on nearest timestamps
        if current_records:
            # Create DataFrames
            wave_df = pd.DataFrame(records)
            current_df = pd.DataFrame(current_records)

            if not wave_df.empty and not current_df.empty:
                # Merge on nearest time (within 3 hours)
                wave_df["observed_at"] = pd.to_datetime(wave_df["observed_at"])
                current_df["observed_at"] = pd.to_datetime(current_df["observed_at"])

                merged = pd.merge_asof(
                    wave_df.sort_values("observed_at"),
                    current_df[["observed_at", "u_knots", "v_knots", "speed_knots", "current_flag", "current_source"]].sort_values("observed_at"),
                    on="observed_at",
                    direction="nearest",
                    tolerance=pd.Timedelta(hours=3)
                )

                records = merged.to_dict("records")
            elif not current_df.empty:
                records = current_records

        if records:
            latest = records[-1]
            LOG.info(f"  📊 Latest: Waves {latest.get('hs_m', 0):.2f}m, Current {latest.get('speed_knots', 0):.2f}kn")

        return records

    except Exception as exc:
        LOG.error(f"  ❌ Error: {exc}")
        return []


def upsert_records(con: duckdb.DuckDBPyConnection, records: List[Dict]) -> int:
    """Insert records."""
    if not records:
        return 0

    rows = []
    for r in records:
        rows.append((
            r["gate_id"], r["gate_name"], r["observed_at"], r["basin"],
            r.get("hs_m"), r.get("tp_s"), r.get("dp_deg"), r.get("wave_flag", 0),
            r.get("u_knots"), r.get("v_knots"), r.get("speed_knots"), r.get("current_flag", 0),
            r.get("wave_source"), r.get("current_source"),
        ))

    con.executemany("""
        INSERT INTO gate_weather_standalone
        (gate_id, gate_name, observed_at, basin, hs_m, tp_s, dp_deg, wave_flag,
         u_knots, v_knots, speed_knots, current_flag, wave_source, current_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (gate_id, observed_at) DO UPDATE SET
            hs_m = excluded.hs_m, speed_knots = excluded.speed_knots,
            u_knots = excluded.u_knots, v_knots = excluded.v_knots,
            wave_flag = excluded.wave_flag, current_flag = excluded.current_flag
    """, rows)

    return len(rows)


def run_collection() -> int:
    """Main."""
    LOG.info("="*80)
    LOG.info("🌊 Gate Weather Collection (CMEMS)")
    LOG.info("="*80)

    if not os.getenv("CMEMS_USERNAME") or not os.getenv("CMEMS_PASSWORD"):
        LOG.error("❌ CMEMS credentials not set!")
        return 0

    db_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
    con = duckdb.connect(db_path)

    try:
        ensure_core_tables(con)
        create_gate_weather_table(con)

        all_records = []
        for gate_id, config in GATE_WEATHER_REGIONS.items():
            records = fetch_gate_weather(gate_id, config["bbox"], config["name"], config["basin"])
            all_records.extend(records)

        count = upsert_records(con, all_records)

        LOG.info("="*80)
        LOG.info(f"✅ Complete: {count} records inserted")
        LOG.info("="*80)

        return count

    finally:
        con.close()


if __name__ == "__main__":
    try:
        run_collection()
    except KeyboardInterrupt:
        LOG.info("⚠️  Interrupted")
        sys.exit(1)
    except Exception as exc:
        LOG.error(f"❌ Fatal: {exc}", exc_info=True)
        sys.exit(1)
