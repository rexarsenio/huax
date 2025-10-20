#!/bin/bash
# Safely check Port Said tankers by temporarily pausing the launchd service

set -e

echo "⏸️  Pausing AIS ingestion service..."
launchctl unload ~/Library/LaunchAgents/com.spvx.ais-ingest.plist 2>/dev/null || true
sleep 2

echo "📊 Running Port Said check..."
echo ""
python check_port_said_tankers.py

echo ""
echo "▶️  Resuming AIS ingestion service..."
launchctl load ~/Library/LaunchAgents/com.spvx.ais-ingest.plist 2>/dev/null || true
echo "✅ Service restarted"
