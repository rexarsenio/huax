#!/usr/bin/env python3
"""
Quick test script to verify AISStream WebSocket connection.
"""
import asyncio
import json
import websockets

API_KEY = "e85ed5726782b45ba7eb720d9d47136a56d4ba03"
WS_URL = "wss://stream.aisstream.io/v0/stream"

async def test_connection():
    print(f"Testing AISStream connection...")
    print(f"URL: {WS_URL}")
    print(f"API Key: {API_KEY[:20]}...")

    try:
        async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
            print("✅ WebSocket connection established!")

            subscription = {
                "APIKey": API_KEY,
                "BoundingBoxes": [[[1.0, 103.5], [1.5, 104.0]]],  # Singapore area
                "FiltersShipType": [80, 81, 82, 83, 84, 85, 86, 87, 88, 89],
                "FilterMessageTypes": ["PositionReport"]
            }

            print("Sending subscription message...")
            await ws.send(json.dumps(subscription))
            print("✅ Subscription sent!")

            print("Waiting for first AIS message (timeout: 30s)...")
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                data = json.loads(message)
                print(f"✅ Received message: {data.get('MessageType', 'Unknown')}")
                print(f"   MMSI: {data.get('MetaData', {}).get('MMSI', 'N/A')}")
                return True
            except asyncio.TimeoutError:
                print("⚠️ No messages received within 30 seconds")
                print("   This could mean:")
                print("   - No ships in the bounding box")
                print("   - API key valid but no data available")
                return False

    except websockets.exceptions.InvalidStatus as e:
        print(f"❌ WebSocket connection rejected: {e}")
        print("   HTTP Status: 503 (Service Unavailable)")
        print("\n   Possible causes:")
        print("   1. API key is invalid or not activated")
        print("   2. Account has been suspended")
        print("   3. Rate limit exceeded")
        print("   4. IP address blocked")
        print("   5. AISStream service is down")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_connection())
    exit(0 if result else 1)
