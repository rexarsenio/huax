#!/usr/bin/env python3
"""
Weather Scheduler - Collects wind data every 30 minutes to SQLite DB
No DuckDB lock conflicts!
"""

import subprocess
import time
import schedule
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def run_weather_ingest():
    """Run OpenWeather ingestion to SQLite (no DuckDB locks!)"""
    LOG.info("=" * 60)
    LOG.info("Starting Weather ingestion to SQLite...")
    LOG.info("=" * 60)

    try:
        result = subprocess.run(
            ['python3', '-m', 'spvx.cli', 'ingest-weather-sqlite'],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            LOG.info("✅ Weather ingestion successful")
            LOG.info(result.stdout)

            # Sync SQLite → DuckDB (fast, minimal lock)
            LOG.info("Syncing weather data SQLite → DuckDB...")
            sync_result = subprocess.run(
                ['python3', '-m', 'spvx.weather.sync_sqlite_to_duckdb'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if sync_result.returncode == 0:
                LOG.info("✅ Weather sync successful")
                LOG.info(sync_result.stdout)
            else:
                LOG.warning("⚠️  Weather sync had issues (non-critical)")
                LOG.warning(sync_result.stderr)

        else:
            LOG.error(f"❌ Weather ingestion failed with code {result.returncode}")
            LOG.error(result.stderr)

    except subprocess.TimeoutExpired:
        LOG.error("❌ Weather ingestion timed out after 60s")
    except Exception as exc:
        LOG.error(f"❌ Weather ingestion error: {exc}")


if __name__ == "__main__":
    LOG.info("🌤️  Weather Scheduler started")
    LOG.info("📅 Schedule: Every 30 minutes")
    LOG.info("💾 Target: SQLite DB (db/weather.db)")
    LOG.info("")

    # Run immediately on startup
    run_weather_ingest()

    # Schedule every 30 minutes
    schedule.every(30).minutes.do(run_weather_ingest)

    LOG.info("⏰ Next run in 30 minutes...")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
