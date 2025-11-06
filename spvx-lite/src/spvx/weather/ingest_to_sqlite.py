"""Weather ingestion to separate SQLite DB (no DuckDB lock conflicts)"""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from spvx.weather.openweather import WeatherSample, fetch_all_samples

LOG = logging.getLogger(__name__)


def init_weather_db(db_path: str) -> None:
    """Initialize weather SQLite database with schema"""
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS weather_obs (
            observed_at TEXT NOT NULL,
            region TEXT NOT NULL,
            basin TEXT,
            wind_speed_kn REAL,
            wind_gust_kn REAL,
            wave_height_m REAL,
            weather_flags TEXT,
            raw_payload TEXT,
            PRIMARY KEY (observed_at, region)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_weather_region_time ON weather_obs(region, observed_at)")
    con.commit()
    con.close()


def upsert_weather_samples(db_path: str, samples: List[WeatherSample]) -> int:
    """Upsert weather samples into SQLite"""
    if not samples:
        return 0

    con = sqlite3.connect(db_path)
    cursor = con.cursor()

    upserted = 0
    for sample in samples:
        cursor.execute("""
            INSERT OR REPLACE INTO weather_obs
            (observed_at, region, basin, wind_speed_kn, wind_gust_kn, wave_height_m, weather_flags, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample.observed_at.isoformat(),
            sample.region,
            sample.basin,
            sample.wind_speed_kn,
            sample.wind_gust_kn,
            sample.wave_height_m,
            sample.weather_flags,
            sample.raw_payload
        ))
        upserted += 1

    con.commit()
    con.close()
    return upserted


def run_weather_to_sqlite(regions: List[str] | None = None, db_path: str = "db/weather.db") -> int:
    """Fetch weather and write to SQLite (no DuckDB locks!)"""
    import os
    from spvx.config import AppSettings

    # Get API key
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        LOG.error("OPENWEATHER_API_KEY not set")
        return 0

    # Ensure DB exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    init_weather_db(db_path)

    # Fetch samples
    samples = fetch_all_samples(api_key, regions)
    if not samples:
        LOG.warning("No weather samples fetched")
        return 0

    # Write to SQLite
    upserted = upsert_weather_samples(db_path, samples)
    LOG.info(f"Upserted {upserted} weather samples to {db_path}")
    return upserted
