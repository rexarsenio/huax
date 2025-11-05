#!/usr/bin/env python
"""Test that canonicalize works with real AISStream messages."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import websockets
from spvx.ingest.canonicalize import canonicalize


async def test_canonicalize_pipeline():
    """Test canonicalization with real messages."""

    # Load .env
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

    api_key = os.getenv("AISSTREAM_API_KEY")
    if not api_key:
        LOG.error("AISSTREAM_API_KEY not set!")
        return

    # Singapore Strait
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [
            [[1.0, 103.5], [1.5, 104.2]]
        ],
        "FiltersShipType": list(range(80, 90)),  # Tankers
        "FilterMessageTypes": ["PositionReport"],
    }

    ws_url = "wss://stream.aisstream.io/v0/stream"

    LOG.info("Connecting to AISStream...")
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(subscription))
        LOG.info("✓ Connected and subscribed\n")

        total_received = 0
        total_canonical = 0
        total_rejected = 0

        async for raw in ws:
            total_received += 1

            try:
                payload = json.loads(raw)
                canonical = canonicalize(payload)

                if canonical:
                    total_canonical += 1
                    LOG.info(f"✓ Message {total_received} ACCEPTED:")
                    LOG.info(f"  MMSI: {canonical['mmsi']}")
                    LOG.info(f"  Position: ({canonical['lat']:.4f}, {canonical['lon']:.4f})")
                    LOG.info(f"  SOG: {canonical['sog']} kn, COG: {canonical.get('cog')}")
                    LOG.info(f"  Tanker: {canonical['is_tanker']}")
                    LOG.info(f"  ShipType: {canonical.get('shiptype_num')} / {canonical.get('shiptype_str')}")
                else:
                    total_rejected += 1
                    # Debug why rejected
                    msg = payload.get("Message", {})
                    pos = msg.get("PositionReport", {})
                    mmsi = payload.get("MetaData", {}).get("MMSI")
                    lat = pos.get("Latitude")
                    lon = pos.get("Longitude")
                    sog = pos.get("Sog")

                    LOG.warning(f"✗ Message {total_received} REJECTED:")
                    LOG.warning(f"  MMSI: {mmsi}, Lat: {lat}, Lon: {lon}, SOG: {sog}")
                    LOG.warning(f"  Raw: {json.dumps(payload, indent=2)[:500]}...")

            except Exception as e:
                LOG.error(f"Error processing message: {e}")

            if total_received >= 20:
                break

        LOG.info("\n" + "=" * 60)
        LOG.info(f"Summary:")
        LOG.info(f"  Total received: {total_received}")
        LOG.info(f"  Accepted: {total_canonical}")
        LOG.info(f"  Rejected: {total_rejected}")
        LOG.info("=" * 60)

        if total_canonical == 0:
            LOG.error("⚠️  NO MESSAGES ACCEPTED - check canonicalize logic!")
        else:
            LOG.info("✓ Canonicalization working!")


if __name__ == "__main__":
    asyncio.run(test_canonicalize_pipeline())
