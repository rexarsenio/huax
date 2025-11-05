#!/usr/bin/env python3
"""
Standalone weather data collection for all gates/checkpoints.
Collects wave, current, and wind data independently of ship movements.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import duckdb

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from spvx.weather.sea_state import fetch_rtofs_currents, fetch_ww3_waves, CurrentSample, WaveSample
from spvx.db import ensure_core_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOG = logging.getLogger("ingest_gate_weather")

# Gate/Checkpoint definitions with bounding boxes and names
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
            hs_m DOUBLE,              -- Significant wave height (meters)
            tp_s DOUBLE,              -- Wave period (seconds)
            dp_deg DOUBLE,            -- Wave direction (degrees)
            wave_flag INTEGER,        -- High wave flag (1 = significant)

            -- Current data
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


def fetch_gate_weather_noaa(
    gate_id: str,
    bbox: Dict[str, float],
    gate_name: str,
    basin: str,
) -> Optional[Dict]:
    """
    Fetch weather data for a single gate using NOAA RTOFS/WW3.
    Returns combined wave + current data.
    """
    LOG.info(f"Fetching weather for {gate_id} ({gate_name})...")

    # Create a region key for the sea_state module
    region_key = gate_id.lower().replace("gate_", "")

    # Temporarily add this region to CHOKEPOINTS for fetch functions
    from chokepoints import CHOKEPOINTS
    CHOKEPOINTS[region_key] = [
        bbox["lon_min"],
        bbox["lat_min"],
        bbox["lon_max"],
        bbox["lat_max"],
    ]

    result = {
        "gate_id": gate_id,
        "gate_name": gate_name,
        "basin": basin,
    }

    # Fetch current data
    try:
        current_sample = fetch_rtofs_currents(region_key)
        if current_sample:
            result.update({
                "observed_at": current_sample.observed_at,
                "u_knots": current_sample.u_ms * 1.943844,  # m/s to knots
                "v_knots": current_sample.v_ms * 1.943844,
                "speed_knots": current_sample.speed_kn,
                "current_flag": current_sample.flag,
                "current_source": current_sample.source_url,
            })
            LOG.info(f"  ✅ Current: {current_sample.speed_kn:.2f} kn")
    except Exception as exc:
        LOG.warning(f"  ⚠️  Failed to fetch currents: {exc}")

    # Fetch wave data
    try:
        wave_sample = fetch_ww3_waves(region_key)
        if wave_sample:
            result.update({
                "observed_at": wave_sample.observed_at,
                "hs_m": wave_sample.hs_m,
                "tp_s": wave_sample.tp_s,
                "dp_deg": wave_sample.dp_deg,
                "wave_flag": wave_sample.flag,
                "wave_source": wave_sample.source_url,
            })
            LOG.info(f"  ✅ Waves: {wave_sample.hs_m:.2f} m")
    except Exception as exc:
        LOG.warning(f"  ⚠️  Failed to fetch waves: {exc}")

    # Clean up temporary region
    if region_key in CHOKEPOINTS:
        del CHOKEPOINTS[region_key]

    # Only return if we got at least some data
    if "observed_at" in result:
        return result
    return None


def upsert_gate_weather(con: duckdb.DuckDBPyConnection, weather_data: List[Dict]) -> int:
    """Insert or update gate weather records."""
    if not weather_data:
        return 0

    rows = []
    for data in weather_data:
        rows.append((
            data["gate_id"],
            data["gate_name"],
            data.get("observed_at", dt.datetime.utcnow()),
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
    LOG.info("🌊 Gate Weather Collection Started")
    LOG.info("=" * 80)

    db_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
    con = duckdb.connect(db_path)

    try:
        ensure_core_tables(con)
        create_gate_weather_table(con)

        weather_data = []

        for gate_id, config in GATE_WEATHER_REGIONS.items():
            try:
                data = fetch_gate_weather_noaa(
                    gate_id=gate_id,
                    bbox=config["bbox"],
                    gate_name=config["name"],
                    basin=config["basin"],
                )
                if data:
                    weather_data.append(data)
            except Exception as exc:
                LOG.error(f"❌ Failed to process {gate_id}: {exc}")

        if weather_data:
            count = upsert_gate_weather(con, weather_data)
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
