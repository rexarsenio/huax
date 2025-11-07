#!/usr/bin/env python3
"""
CMEMS Scheduler - Uses efficient subset API for all 18 chokepoints
Collects wave and current data every hour
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


def run_cmems_ingest():
    """Run CMEMS subset ingestion for ALL 18 chokepoints"""
    LOG.info("=" * 60)
    LOG.info("Starting CMEMS ingestion (subset API for 18 chokepoints)...")
    LOG.info("=" * 60)

    try:
        result = subprocess.run(
            ['python3', '-m', 'spvx.cli', 'ingest-sea-state-subset',
             '--lookback-days=1',
             '--buffer-km=50'],
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes max
        )

        if result.returncode == 0:
            LOG.info("✅ CMEMS ingestion successful")
            LOG.info(result.stdout)
        else:
            LOG.error(f"❌ CMEMS ingestion failed with code {result.returncode}")
            LOG.error(result.stderr)

    except subprocess.TimeoutExpired:
        LOG.error("❌ CMEMS ingestion timed out after 30 minutes")
    except Exception as exc:
        LOG.error(f"❌ CMEMS ingestion error: {exc}")


if __name__ == "__main__":
    LOG.info("🌊 CMEMS Scheduler started")
    LOG.info("📅 Schedule: Every 1 hour")
    LOG.info("📍 Regions: All 18 chokepoints (subset API)")
    LOG.info("📊 Data: Waves + Currents")
    LOG.info("")

    # Run immediately on startup
    run_cmems_ingest()

    # Schedule every 1 hour
    schedule.every(1).hours.do(run_cmems_ingest)

    LOG.info("⏰ Next run in 1 hour...")

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
