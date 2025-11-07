#!/usr/bin/env python3
"""
Standalone gate weather collection using CMEMS (Copernicus Marine).
Collects wave and current data independently of ship movements.
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

from spvx.sea_state.cmems import download_waves, download_currents, extract_region_features, _list_days_yyyymmdd
from spvx.db import ensure_core_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOG = logging.getLogger("ingest_gate_weather_cmems")

# Gate/Checkpoint definitions with bounding boxes
GATE_WEATHER_REGIONS = {
    "GATE_HORMUZ": {
        "bbox": {"lat_min": 24.0, "lat_max": 28.2, "lon_min": 54.0, "lon_max": 58.5},
        "name": "Strait of Hormuz",
        "basin": "APAC",
        "bearing_deg": 90.0,
    },
    "GATE_SUEZ_N": {
        "bbox": {"lat_min": 31.0, "lat_max": 31.6, "lon_min": 32.0, "lon_max": 32.7},
        "name": "Suez Canal North (Port Said)",
        "basin": "MED",
        "bearing_deg": 180.0,
    },
    "GATE_SUEZ_S": {
        "bbox": {"lat_min": 29.8, "lat_max": 30.4, "lon_min": 32.2, "lon_max": 33.5},
        "name": "Suez Canal South (Port of Suez)",
        "basin": "MED",
        "bearing_deg": 0.0,
    },
    "GATE_BAB_EL_MANDEB": {
        "bbox": {"lat_min": 12.5, "lat_max": 13.5, "lon_min": 42.5, "lon_max": 44.0},
        "name": "Bab el-Mandeb Strait",
        "basin": "APAC",
        "bearing_deg": 0.0,
    },
    "GATE_GIBRALTAR": {
        "bbox": {"lat_min": 35.8, "lat_max": 36.2, "lon_min": -5.5, "lon_max": -5.2},
        "name": "Strait of Gibraltar",
        "basin": "MED",
        "bearing_deg": 90.0,
    },
    "GATE_BOSPORUS": {
        "bbox": {"lat_min": 40.9, "lat_max": 41.4, "lon_min": 28.6, "lon_max": 29.3},
        "name": "Bosporus Strait",
        "basin": "MED",
        "bearing_deg": 20.0,
    },
    "GATE_MALACCA": {
        "bbox": {"lat_min": 0.5, "lat_max": 2.0, "lon_min": 103.3, "lon_max": 104.3},
        "name": "Singapore & Malacca Strait",
        "basin": "APAC",
        "bearing_deg": 300.0,
    },
    "GATE_PANAMA": {
        "bbox": {"lat_min": 8.5, "lat_max": 9.7, "lon_min": -80.2, "lon_max": -79.3},
        "name": "Panama Canal",
        "basin": "NAM",
        "bearing_deg": 90.0,
    },
    "GATE_YUCATAN": {
        "bbox": {"lat_min": 20.7, "lat_max": 22.3, "lon_min": -87.0, "lon_max": -85.7},
        "name": "Yucatan Channel",
        "basin": "NAM",
        "bearing_deg": 0.0,
    },
    "GATE_WEST_AFRICA_BONNY": {
        "bbox": {"lat_min": 3.8, "lat_max": 5.0, "lon_min": 6.5, "lon_max": 7.6},
        "name": "Bonny Terminal (Nigeria)",
        "basin": "AFRICA",
        "bearing_deg": 270.0,
    },
    "GATE_WEST_AFRICA_ESCRAVOS": {
        "bbox": {"lat_min": 4.6, "lat_max": 6.1, "lon_min": 4.7, "lon_max": 5.8},
        "name": "Escravos Terminal (Nigeria)",
        "basin": "AFRICA",
        "bearing_deg": 270.0,
    },
}

# CMEMS configuration from config.yml
WAVES_DATASET_ID = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
CURRENTS_DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
OUT_DIR = "data/sea_state"


def create_gate_weather_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create standalone gate weather table."""
    LOG.info("Creating gate_weather_standalone table if not exists...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS gate_weather_standalone (
            gate_id VARCHAR NOT NULL,
            gate_name VARCHAR,
            observed_at TIMESTAMP NOT NULL,
            basin VARCHAR,

            -- Wave data (from CMEMS)
            hs_m DOUBLE,              -- Significant wave height (meters)
            tp_s DOUBLE,              -- Wave period (seconds)
            dp_deg DOUBLE,            -- Wave direction (degrees)
            wave_flag INTEGER,        -- High wave flag (1 = significant)

            -- Current data (from CMEMS)
            u_knots DOUBLE,           -- Current u-component (knots)
            v_knots DOUBLE,           -- Current v-component (knots)
            speed_knots DOUBLE,       -- Current speed (knots)
            current_flag INTEGER,     -- High current flag (1 = significant)

            -- Sources
            wave_source VARCHAR,
            current_source VARCHAR,

            -- Metadata
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (gate_id, observed_at)
        )
    """)

    LOG.info("✅ Table gate_weather_standalone ready")


def fetch_gate_weather_cmems(
    gate_id: str,
    bbox: Dict[str, float],
    gate_name: str,
    basin: str,
    bearing_deg: float,
) -> List[Dict]:
    """
    Fetch weather data for a single gate using CMEMS.
    Returns list of weather records (one per timestamp).
    """
    LOG.info(f"Fetching CMEMS data for {gate_id} ({gate_name})...")

    # Get CMEMS credentials from environment
    username = os.getenv("CMEMS_USERNAME")
    password = os.getenv("CMEMS_PASSWORD")

    if not username or not password:
        LOG.warning("⚠️  CMEMS_USERNAME and CMEMS_PASSWORD not set in environment")
        LOG.warning("   Set them with: export CMEMS_USERNAME=your_username")
        LOG.warning("   Or create .env file with credentials")
        return []

    # Download last 2 days of data
    day_filters = _list_days_yyyymmdd(lookback_days=2)

    try:
        # Download waves
        LOG.info(f"  📥 Downloading wave data...")
        wave_files = download_waves(
            dataset_id=WAVES_DATASET_ID,
            out_dir=OUT_DIR,
            day_filters=day_filters,
            username=username,
            password=password,
        )

        # Download currents
        LOG.info(f"  📥 Downloading current data...")
        current_files = download_currents(
            dataset_id=CURRENTS_DATASET_ID,
            out_dir=OUT_DIR,
            day_filters=day_filters,
            username=username,
            password=password,
        )

        if not wave_files and not current_files:
            LOG.warning(f"  ⚠️  No data files downloaded")
            return []

        # Extract features for this gate
        LOG.info(f"  📊 Extracting features...")
        features_df = extract_region_features(
            waves_files=wave_files,
            currents_files=current_files,
            features_cfg=[
                {
                    "id": "hs",
                    "dataset": "waves",
                    "type": "scalar",
                    "variables": ["VHM0", "hs", "swh", "significant_wave_height"],
                    "stats": ["mean"],
                },
                {
                    "id": "current_speed",
                    "dataset": "currents",
                    "type": "vector_magnitude",
                    "variables": ["uo", "vo"],
                    "stats": ["mean"],
                },
                {
                    "id": "u_current",
                    "dataset": "currents",
                    "type": "scalar",
                    "variables": ["uo"],
                    "stats": ["mean"],
                },
                {
                    "id": "v_current",
                    "dataset": "currents",
                    "type": "scalar",
                    "variables": ["vo"],
                    "stats": ["mean"],
                },
            ],
            bbox=bbox,
            bearing_deg=bearing_deg,
            buffer_km=10.0,
        )

        if features_df.empty:
            LOG.warning(f"  ⚠️  No features extracted")
            return []

        # Convert to records
        records = []
        for _, row in features_df.iterrows():
            hs_m = row.get("hs_mean")
            current_speed = row.get("current_speed_mean")
            u_current = row.get("u_current_mean")
            v_current = row.get("v_current_mean")

            # Convert m/s to knots for currents (1 m/s = 1.943844 knots)
            if current_speed is not None:
                current_speed_kn = current_speed * 1.943844
            else:
                current_speed_kn = None

            if u_current is not None:
                u_kn = u_current * 1.943844
            else:
                u_kn = None

            if v_current is not None:
                v_kn = v_current * 1.943844
            else:
                v_kn = None

            # Flags
            wave_flag = 1 if (hs_m is not None and hs_m > 3.5) else 0
            current_flag = 1 if (current_speed_kn is not None and current_speed_kn > 3.0) else 0

            records.append({
                "gate_id": gate_id,
                "gate_name": gate_name,
                "observed_at": row["time"],
                "basin": basin,
                "hs_m": hs_m,
                "tp_s": None,  # Not extracted yet
                "dp_deg": None,  # Not extracted yet
                "wave_flag": wave_flag,
                "u_knots": u_kn,
                "v_knots": v_kn,
                "speed_knots": current_speed_kn,
                "current_flag": current_flag,
                "wave_source": f"CMEMS:{WAVES_DATASET_ID}",
                "current_source": f"CMEMS:{CURRENTS_DATASET_ID}",
            })

        LOG.info(f"  ✅ Extracted {len(records)} records")
        if records:
            latest = records[-1]
            if latest["hs_m"]:
                LOG.info(f"     Waves: {latest['hs_m']:.2f}m")
            if latest["speed_knots"]:
                LOG.info(f"     Current: {latest['speed_knots']:.2f}kn")

        return records

    except Exception as exc:
        LOG.error(f"  ❌ Failed: {exc}", exc_info=True)
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
            tp_s = excluded.tp_s,
            dp_deg = excluded.dp_deg,
            wave_flag = excluded.wave_flag,
            u_knots = excluded.u_knots,
            v_knots = excluded.v_knots,
            speed_knots = excluded.speed_knots,
            current_flag = excluded.current_flag,
            wave_source = excluded.wave_source,
            current_source = excluded.current_source,
            collected_at = CURRENT_TIMESTAMP
        """,
        rows,
    )

    return len(rows)


def run_collection() -> int:
    """Main collection loop."""
    LOG.info("=" * 80)
    LOG.info("🌊 Gate Weather Collection Started (CMEMS)")
    LOG.info("=" * 80)

    # Check credentials
    if not os.getenv("CMEMS_USERNAME") or not os.getenv("CMEMS_PASSWORD"):
        LOG.error("❌ CMEMS credentials not set!")
        LOG.error("")
        LOG.error("Please set environment variables:")
        LOG.error("  export CMEMS_USERNAME='your_username'")
        LOG.error("  export CMEMS_PASSWORD='your_password'")
        LOG.error("")
        LOG.error("Or create .env file with:")
        LOG.error("  CMEMS_USERNAME=your_username")
        LOG.error("  CMEMS_PASSWORD=your_password")
        LOG.error("")
        LOG.error("Get credentials at: https://data.marine.copernicus.eu/register")
        return 0

    db_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
    con = duckdb.connect(db_path)

    try:
        ensure_core_tables(con)
        create_gate_weather_table(con)

        all_records = []

        for gate_id, config in GATE_WEATHER_REGIONS.items():
            try:
                records = fetch_gate_weather_cmems(
                    gate_id=gate_id,
                    bbox=config["bbox"],
                    gate_name=config["name"],
                    basin=config["basin"],
                    bearing_deg=config["bearing_deg"],
                )
                if records:
                    all_records.extend(records)
            except Exception as exc:
                LOG.error(f"❌ Failed to process {gate_id}: {exc}")

        if all_records:
            count = upsert_gate_weather(con, all_records)
            LOG.info(f"✅ Inserted/updated {count} gate weather records")
        else:
            LOG.warning("⚠️  No weather data collected")
            count = 0

        LOG.info("=" * 80)
        LOG.info(f"🌊 Gate Weather Collection Complete: {count} records")
        LOG.info("=" * 80)

        return count

    finally:
        con.close()


if __name__ == "__main__":
    try:
        run_collection()
    except KeyboardInterrupt:
        LOG.info("⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as exc:
        LOG.error(f"❌ Fatal error: {exc}", exc_info=True)
        sys.exit(1)
