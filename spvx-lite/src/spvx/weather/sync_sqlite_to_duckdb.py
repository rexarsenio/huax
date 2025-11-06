"""Sync weather data from SQLite to DuckDB (no lock conflicts!)"""

import sqlite3
import duckdb
import logging
import os
from datetime import datetime

LOG = logging.getLogger(__name__)


def sync_weather_sqlite_to_duckdb(
    sqlite_path: str = "db/weather.db",
    duckdb_path: str | None = None
) -> int:
    """Copy weather data from SQLite to DuckDB weather_observations table"""

    if not os.path.exists(sqlite_path):
        LOG.warning(f"SQLite DB not found: {sqlite_path}")
        return 0

    # Use env variable or default
    if not duckdb_path:
        duckdb_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")

    # Read from SQLite
    sqlite_con = sqlite3.connect(sqlite_path)
    sqlite_cur = sqlite_con.cursor()

    rows = sqlite_cur.execute("""
        SELECT
            observed_at,
            region,
            basin,
            wind_speed_kn,
            wind_gust_kn,
            wave_height_m,
            weather_flag,
            raw_payload
        FROM weather_obs
        ORDER BY observed_at DESC
        LIMIT 1000
    """).fetchall()

    sqlite_con.close()

    if not rows:
        LOG.info("No weather data in SQLite to sync")
        return 0

    # Write to DuckDB (quick operation, minimal lock time)
    duck_con = duckdb.connect(duckdb_path)

    try:
        # Ensure table exists
        from spvx.db import ensure_core_tables
        ensure_core_tables(duck_con)

        # Upsert into DuckDB
        duck_con.executemany("""
            INSERT INTO weather_observations
            (observed_at, region, basin, wind_speed_kn, wind_gust_kn, wave_height_m, weather_flag, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (observed_at, region, source) DO UPDATE SET
                wind_speed_kn = excluded.wind_speed_kn,
                wind_gust_kn = excluded.wind_gust_kn,
                wave_height_m = excluded.wave_height_m,
                weather_flag = excluded.weather_flag,
                raw_payload = excluded.raw_payload
        """, rows)

        LOG.info(f"✅ Synced {len(rows)} weather samples SQLite → DuckDB")
        return len(rows)

    finally:
        duck_con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    synced = sync_weather_sqlite_to_duckdb()
    print(f"Synced {synced} weather samples")
