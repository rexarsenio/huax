#!/usr/bin/env python3
"""
Ultra-simple AISStream test - minimal subscription
"""
import asyncio
import json
import os
from urllib.parse import urlparse

try:
    from python_socks.async_.asyncio import Proxy as AsyncProxy
    PROXY_SUPPORT = True
except ImportError:
    PROXY_SUPPORT = False

import websockets

API_KEY = "e85ed5726782b45ba7eb720d9d47136a56d4ba03"
WS_URL = "wss://stream.aisstream.io/v0/stream"

async def connect_via_proxy(url, proxy_url):
    """Connect to WebSocket through HTTP CONNECT proxy."""
    parsed_proxy = urlparse(proxy_url)
    parsed_ws = urlparse(url)

    proxy = AsyncProxy.from_url(proxy_url)
    sock = await proxy.connect(
        dest_host=parsed_ws.hostname,
        dest_port=parsed_ws.port or 443
    )

    return await websockets.connect(url, sock=sock)

async def test_minimal():
    print("Testing MINIMAL AISStream subscription...")
    print(f"API Key: {API_KEY[:20]}...")

    proxy_url = os.getenv("HTTPS_PROXY")
    print(f"Proxy: {proxy_url[:60] if proxy_url else 'None'}...")

    try:
        if proxy_url and PROXY_SUPPORT:
            print("Connecting via proxy...")
            ws = await connect_via_proxy(WS_URL, proxy_url)
        else:
            print("Connecting directly...")
            ws = await websockets.connect(WS_URL)

        async with ws:
            print("✅ Connected!")

            # MINIMAL subscription - API key + bounding box
            subscription = {
                "APIKey": API_KEY,
                "BoundingBoxes": [[[1.0, 103.5], [1.5, 104.0]]],  # Singapore
                "FilterMessageTypes": ["PositionReport"]
            }

            print(f"Sending subscription: {json.dumps(subscription, indent=2)}")
            await ws.send(json.dumps(subscription))
            print("✅ Subscription sent!")

            print("Waiting for message (30s timeout)...")
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                print(f"✅ Received: {message[:200]}...")
                return True
            except asyncio.TimeoutError:
                print("⏱️ Timeout - no messages received")
                return False

    except websockets.exceptions.InvalidStatus as e:
        print(f"❌ WebSocket rejected: {e}")
        print("\nProblem: AISStream is rejecting the connection")
        print("Possible causes:")
        print("  1. API key is invalid/expired")
        print("  2. Account is suspended")
        print("  3. IP/proxy is blocked")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_minimal())
    exit(0 if result else 1)
