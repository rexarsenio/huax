#!/usr/bin/env python
"""Debug wrapper to run consumer with proper logging."""
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file FIRST
load_dotenv()

# Configure logging BEFORE importing consumer
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/consumer_debug.log')
    ]
)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Now import and run
from spvx.open_sea.config import get_open_sea_config
from spvx.open_sea.consumer import run_open_sea_consumer

if __name__ == "__main__":
    logging.info("=" * 80)
    logging.info("Starting AIS Consumer with DEBUG logging")
    logging.info("=" * 80)

    config_path = Path("config.yml")
    polygons_path = Path("data/geo/polygons.geojson")
    gates_path = Path("data/geo/gates.geojson")

    logging.info(f"Loading configuration from {config_path}")
    cfg = get_open_sea_config(str(config_path))
    logging.info(f"Configuration loaded: {cfg}")

    logging.info(f"Starting consumer with:")
    logging.info(f"  - Polygons: {polygons_path}")
    logging.info(f"  - Gates: {gates_path}")
    logging.info(f"  - API Key: {'SET' if os.getenv('AISSTREAM_API_KEY') else 'MISSING'}")

    run_open_sea_consumer(
        cfg,
        polygons_path.resolve(),
        gates_path.resolve(),
        api_key=os.getenv("AISSTREAM_API_KEY"),
        duckdb_path=Path("db/spvx.duckdb"),
        metrics_host="0.0.0.0",
        metrics_port=9110,
    )
