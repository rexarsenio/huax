#!/bin/bash
#
# MANAGED_CONSUMER.sh
#
# Manages the AIS consumer with periodic snapshots for the API.
# This script will:
#   1. Start the consumer
#   2. Every 5 minutes: pause consumer, create snapshot, resume consumer
#
# Usage:
#   ./MANAGED_CONSUMER.sh
#

set -euo pipefail

cd "$(dirname "$0")"

CONSUMER_CMD="python -m spvx.cli open-sea-consume --polygons data/geo/polygons.geojson --gates data/geo/gates.geojson --config-path config.yml"
SNAPSHOT_INTERVAL=300  # 5 minutes
CONSUMER_PID=""
LOG_FILE="logs/managed_consumer.log"

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down managed consumer..."
    if [[ -n "$CONSUMER_PID" ]] && ps -p "$CONSUMER_PID" > /dev/null 2>&1; then
        echo "   Killing consumer (PID $CONSUMER_PID)..."
        kill -15 "$CONSUMER_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$CONSUMER_PID" 2>/dev/null || true
    fi
    echo "✅ Cleanup complete"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo "🚀 Starting Managed Consumer with periodic snapshots"
echo "   Consumer will pause every $SNAPSHOT_INTERVAL seconds to create API snapshot"
echo "   Log: $LOG_FILE"
echo ""

source .venv/bin/activate

mkdir -p logs

while true; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 🟢 Starting consumer..."

    # Start consumer in background
    $CONSUMER_CMD > "$LOG_FILE" 2>&1 &
    CONSUMER_PID=$!

    echo "   Consumer PID: $CONSUMER_PID"

    # Wait for the snapshot interval
    echo "   Collecting data for $SNAPSHOT_INTERVAL seconds..."
    sleep "$SNAPSHOT_INTERVAL"

    # Stop consumer
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ⏸️  Pausing consumer for snapshot..."
    if ps -p "$CONSUMER_PID" > /dev/null 2>&1; then
        kill -15 "$CONSUMER_PID" 2>/dev/null || true
        sleep 3
        # Force kill if still running
        if ps -p "$CONSUMER_PID" > /dev/null 2>&1; then
            kill -9 "$CONSUMER_PID" 2>/dev/null || true
            sleep 1
        fi
    fi

    # Create snapshot
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 📸 Creating API snapshot..."
    if ./UPDATE_API_SNAPSHOT.sh; then
        echo "   ✅ Snapshot created successfully"
    else
        echo "   ⚠️  Snapshot creation failed (will retry next cycle)"
    fi

    echo ""
done
