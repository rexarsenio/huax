#!/usr/bin/env python
"""Test script to verify consumer can connect and start receiving data."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from spvx.open_sea.consumer import OpenSeaConsumer, ConsumerSettings, load_geometries
from spvx.open_sea.config import get_open_sea_config
from spvx.config import AppSettings


async def test_consumer_connection():
    """Test that consumer can connect to AISStream."""

    # Load configuration
    print("Loading configuration...")
    config = get_open_sea_config("config.yml")

    # Load geometries
    print("Loading geometries...")
    polygons_path = Path("data/geo/polygons.geojson")
    gates_path = Path("data/geo/gates.geojson")
    polygons, gates = load_geometries(polygons_path, gates_path)

    print(f"✓ Loaded {len(polygons)} polygons and {len(gates)} gates")

    # Get API key
    api_key = os.getenv("AISSTREAM_API_KEY")
    if not api_key:
        print("❌ AISSTREAM_API_KEY not set!")
        return False

    print(f"✓ API Key: {api_key[:10]}...")

    # Create consumer
    settings = ConsumerSettings(
        api_key=api_key,
        duckdb_path=Path(AppSettings().duckdb_path),
        metrics_port=9110,
    )

    consumer = OpenSeaConsumer(config, polygons, gates, settings)

    # Show bounding boxes
    print("\nBounding boxes that will be subscribed:")
    for i, bbox in enumerate(consumer.bounding_boxes, 1):
        lat_range = f"{bbox[0][0]:.2f} to {bbox[1][0]:.2f}"
        lon_range = f"{bbox[0][1]:.2f} to {bbox[1][1]:.2f}"
        print(f"  {i}. Lat: {lat_range}, Lon: {lon_range}")

    print(f"\nTotal bounding boxes: {len(consumer.bounding_boxes)}")
    print("\n" + "=" * 60)
    print("Starting consumer for 120 seconds to test data ingestion...")
    print("=" * 60)
    print()

    # Start consumer with timeout
    try:
        await asyncio.wait_for(consumer.run(), timeout=120.0)
    except asyncio.TimeoutError:
        print("\n⏱️  120-second test completed")
        consumer.stop_event.set()
    except KeyboardInterrupt:
        print("\n⛔ Stopped by user")
        consumer.stop_event.set()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    # Load .env file
    env_path = Path(".env")
    if env_path.exists():
        print("Loading .env file...")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value
        print("✓ Environment variables loaded\n")

    asyncio.run(test_consumer_connection())
