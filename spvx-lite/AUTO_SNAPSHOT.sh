#!/bin/bash
#
# AUTO_SNAPSHOT.sh - Automatic periodic snapshot updates
#
# Updates the API snapshot every 10 minutes
# Run this in the background to keep the dashboard up-to-date
#
# Usage:
#   ./AUTO_SNAPSHOT.sh &
#   # Or with nohup to keep running after logout:
#   nohup ./AUTO_SNAPSHOT.sh > logs/auto-snapshot.log 2>&1 &
#

cd "$(dirname "$0")"

echo "🔄 Starting automatic snapshot updates (every 10 minutes)"
echo "   Log: logs/auto-snapshot.log"
echo "   To stop: pkill -f AUTO_SNAPSHOT.sh"
echo ""

mkdir -p logs

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] Starting snapshot update..."

    # Check if ingestion is running
    if pgrep -f ingest_aisstream.py > /dev/null; then
        echo "[$TIMESTAMP] ⚠️  Ingestion is running - snapshot may fail due to locks"
        echo "[$TIMESTAMP] Skipping this cycle, will try again in 10 minutes"
    else
        # Run the snapshot update
        if ./UPDATE_API_SNAPSHOT.sh >> logs/auto-snapshot.log 2>&1; then
            echo "[$TIMESTAMP] ✅ Snapshot updated successfully"
        else
            echo "[$TIMESTAMP] ❌ Snapshot update failed (see logs/auto-snapshot.log)"
        fi
    fi

    echo "[$TIMESTAMP] Sleeping for 10 minutes..."
    echo ""
    sleep 600  # 10 minutes
done
