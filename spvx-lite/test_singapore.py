#!/usr/bin/env python
"""Test consumer with Singapore area only (high traffic, usually in free tier)."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import websockets


async def test_aisstream_singapore():
    """Test raw AISStream connection with Singapore bounding box."""

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

    LOG.info(f"Using API Key: {api_key[:10]}...")

    # Singapore Strait - high traffic area
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [
            [[1.0, 103.5], [1.5, 104.2]]  # Singapore Strait
        ],
        "FiltersShipType": list(range(80, 90)),  # Tankers only
        "FilterMessageTypes": ["PositionReport"],
    }

    LOG.info(f"Subscription: {json.dumps(subscription, indent=2)}")

    ws_url = "wss://stream.aisstream.io/v0/stream"

    try:
        LOG.info(f"Connecting to {ws_url}...")
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
            LOG.info("✓ Connected to AISStream!")

            LOG.info("Sending subscription...")
            await ws.send(json.dumps(subscription))
            LOG.info("✓ Subscription sent")

            LOG.info("Waiting for messages (30 seconds)...")
            message_count = 0

            try:
                async for message in ws:
                    message_count += 1
                    try:
                        data = json.loads(message)
                        mmsi = data.get("MetaData", {}).get("MMSI", "unknown")
                        ship_type = data.get("MetaData", {}).get("ShipType", "unknown")
                        msg_type = data.get("MessageType", "unknown")

                        pos = data.get("Message", {}).get("PositionReport", {})
                        lat = pos.get("Latitude")
                        lon = pos.get("Longitude")
                        sog = pos.get("Sog")

                        LOG.info(f"✓ Message {message_count}: MMSI={mmsi}, Type={ship_type}, "
                                f"Pos=({lat:.3f}, {lon:.3f}), SOG={sog}")

                        if message_count >= 10:
                            LOG.info("✓ Received 10 messages - test successful!")
                            break

                    except Exception as e:
                        LOG.warning(f"Failed to parse message: {e}")

                    if message_count >= 10:
                        break

            except asyncio.TimeoutError:
                pass

            if message_count == 0:
                LOG.warning("⚠️  NO MESSAGES RECEIVED - possible issues:")
                LOG.warning("  1. API Key may not have access to Singapore area")
                LOG.warning("  2. No tanker traffic in the area at this time")
                LOG.warning("  3. Try removing FiltersShipType to see all vessels")
            else:
                LOG.info(f"✓ Test completed - received {message_count} messages")

    except Exception as e:
        LOG.error(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_aisstream_singapore())
