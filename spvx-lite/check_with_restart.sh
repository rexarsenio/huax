#!/bin/bash
# Temporarily stop ingestion, run check, then restart

echo "🛑 Stopping AIS ingestion..."
pkill -f ingest_aisstream.py
sleep 2

echo "📊 Running Port Said check..."
python check_port_said_tankers.py

echo ""
echo "🔄 Restarting AIS ingestion in background..."
nohup python ingest_aisstream.py > logs/ingest.log 2>&1 &
echo "✅ Ingestion restarted (PID: $!)"
