#!/usr/bin/env python3
"""
Optimized gate weather collection using CMEMS with spatial subsetting.
Only downloads data for specific gate regions (not global).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from typing import Dict, List, Optional

import duckdb

# Add src to path
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
LOG = logging.getLogger("ingest_gate_weather_optimized")

# Gate/Checkpoint definitions with bounding boxes
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

# CMEMS configuration
WAVES_DATASET_ID = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
CURRENTS_DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"


def create_gate_weather_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create standalone gate weather table."""
    LOG.info("Creating gate_weather_standalone table if not exists...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS gate_weather_standalone (
            gate_id VARCHAR NOT NULL,
            gate_name VARCHAR,
            observed_at TIMESTAMP NOT NULL,
            basin VARCHAR,

            -- Wave data
            hs_m DOUBLE,
            tp_s DOUBLE,
            dp_deg DOUBLE,
            wave_flag INTEGER,

            -- Current data
            u_knots DOUBLE,
            v_knots DOUBLE,
            speed_knots DOUBLE,
            current_flag INTEGER,

            -- Sources
            wave_source VARCHAR,
            current_source VARCHAR,

            -- Metadata
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (gate_id, observed_at)
        )
    """)

    LOG.info("✅ Table gate_weather_standalone ready")


def fetch_gate_weather_subset(
    gate_id: str,
    bbox: Dict[str, float],
    gate_name: str,
    basin: str,
) -> List[Dict]:
    """
    Fetch weather data using CMEMS subset API (spatial + temporal).
    Only downloads data for this specific gate region.
    """
    LOG.info(f"Fetching data for {gate_id} ({gate_name})...")

    username = os.getenv("CMEMS_USERNAME")
    password = os.getenv("CMEMS_PASSWORD")

    if not username or not password:
        LOG.warning("⚠️  CMEMS credentials not set")
        return []

    # Time range: last 24 hours
    end_time = dt.datetime.utcnow()
    start_time = end_time - dt.timedelta(hours=24)

    records = []

    try:
        # Fetch WAVES with spatial/temporal subset
        LOG.info(f"  📥 Fetching wave subset...")
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

        # Fetch CURRENTS with spatial/temporal subset
        LOG.info(f"  📥 Fetching current subset...")
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

        LOG.info(f"  📊 Processing data...")

        # Extract wave height (VHM0 or hs)
        wave_var = None
        for var_name in ["VHM0", "hs", "swh", "VAVH"]:
            if var_name in wave_ds.data_vars:
                wave_var = var_name
                break

        # Extract current components
        u_var = "uo" if "uo" in current_ds.data_vars else None
        v_var = "vo" if "vo" in current_ds.data_vars else None

        if not wave_var and not u_var:
            LOG.warning(f"  ⚠️  No wave or current variables found")
            return []

        # Get time coordinates
        if "time" in wave_ds.coords:
            times = wave_ds.coords["time"].values
        else:
            LOG.warning(f"  ⚠️  No time coordinate in wave data")
            return []

        # Process each timestep
        for time_val in times:
            obs_time = dt.datetime.utcfromtimestamp(time_val.astype('datetime64[s]').astype(int))

            # Wave height (spatial mean)
            hs_m = None
            if wave_var:
                wave_slice = wave_ds[wave_var].sel(time=time_val)
                hs_m = float(wave_slice.mean().values)

            # Current speed (spatial mean)
            u_kn = None
            v_kn = None
            speed_kn = None
            if u_var and v_var:
                u_ms = float(current_ds[u_var].sel(time=time_val).mean().values)
                v_ms = float(current_ds[v_var].sel(time=time_val).mean().values)

                # Convert m/s to knots
                u_kn = u_ms * 1.943844
                v_kn = v_ms * 1.943844
                speed_kn = (u_ms**2 + v_ms**2)**0.5 * 1.943844

            # Flags
            wave_flag = 1 if (hs_m and hs_m > 3.5) else 0
            current_flag = 1 if (speed_kn and speed_kn > 3.0) else 0

            records.append({
                "gate_id": gate_id,
                "gate_name": gate_name,
                "observed_at": obs_time,
                "basin": basin,
                "hs_m": hs_m,
                "tp_s": None,
                "dp_deg": None,
                "wave_flag": wave_flag,
                "u_knots": u_kn,
                "v_knots": v_kn,
                "speed_knots": speed_kn,
                "current_flag": current_flag,
                "wave_source": f"CMEMS:{WAVES_DATASET_ID}",
                "current_source": f"CMEMS:{CURRENTS_DATASET_ID}",
            })

        wave_ds.close()
        current_ds.close()

        LOG.info(f"  ✅ Extracted {len(records)} records")
        if records:
            latest = records[-1]
            if latest["hs_m"]:
                LOG.info(f"     Waves: {latest['hs_m']:.2f}m")
            if latest["speed_knots"]:
                LOG.info(f"     Current: {latest['speed_knots']:.2f}kn")

        return records

    except Exception as exc:
        LOG.error(f"  ❌ Failed: {exc}")
        return []


def upsert_gate_weather(con: duckdb.DuckDBPyConnection, weather_records: List[Dict]) -> int:
    """Insert or update gate weather records."""
    if not weather_records:
        return 0

    rows = []
    for data in weather_records:
        rows.append((
            data["gate_id"],
            data["gate_name"],
            data["observed_at"],
            data["basin"],
            data.get("hs_m"),
            data.get("tp_s"),
            data.get("dp_deg"),
            data.get("wave_flag", 0),
            data.get("u_knots"),
            data.get("v_knots"),
            data.get("speed_knots"),
            data.get("current_flag", 0),
            data.get("wave_source"),
            data.get("current_source"),
        ))

    con.executemany(
        """
        INSERT INTO gate_weather_standalone (
            gate_id, gate_name, observed_at, basin,
            hs_m, tp_s, dp_deg, wave_flag,
            u_knots, v_knots, speed_knots, current_flag,
            wave_source, current_source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (gate_id, observed_at) DO UPDATE SET
            hs_m = excluded.hs_m,
            speed_knots = excluded.speed_knots,
            u_knots = excluded.u_knots,
            v_knots = excluded.v_knots,
            wave_flag = excluded.wave_flag,
            current_flag = excluded.current_flag,
            collected_at = CURRENT_TIMESTAMP
        """,
        rows,
    )

    return len(rows)


def run_collection() -> int:
    """Main collection loop."""
    LOG.info("=" * 80)
    LOG.info("🌊 Gate Weather Collection (Optimized - Spatial Subsetting)")
    LOG.info("=" * 80)

    if not os.getenv("CMEMS_USERNAME") or not os.getenv("CMEMS_PASSWORD"):
        LOG.error("❌ CMEMS credentials not set!")
        LOG.error("Set them in .env file or environment")
        return 0

    db_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
    con = duckdb.connect(db_path)

    try:
        ensure_core_tables(con)
        create_gate_weather_table(con)

        all_records = []

        for gate_id, config in GATE_WEATHER_REGIONS.items():
            try:
                records = fetch_gate_weather_subset(
                    gate_id=gate_id,
                    bbox=config["bbox"],
                    gate_name=config["name"],
                    basin=config["basin"],
                )
                if records:
                    all_records.extend(records)
            except Exception as exc:
                LOG.error(f"❌ Failed {gate_id}: {exc}")

        if all_records:
            count = upsert_gate_weather(con, all_records)
            LOG.info(f"✅ Inserted/updated {count} records")
        else:
            LOG.warning("⚠️  No data collected")
            count = 0

        LOG.info("=" * 80)
        LOG.info(f"🌊 Complete: {count} records")
        LOG.info("=" * 80)

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
