#!/bin/bash
# EMERGENCY: Kill ALL CMEMS download processes

echo "🛑 STOPPING ALL CMEMS DOWNLOADS..."
echo ""

# Kill by process name patterns
pkill -9 -f "join_tracklets_cmems" 2>/dev/null
pkill -9 -f "ingest-sea-state" 2>/dev/null
pkill -9 -f "join_cmems" 2>/dev/null

# Wait a moment
sleep 2

# Check if any are still running
REMAINING=$(ps aux | grep -E "join_tracklets|ingest-sea-state" | grep -v grep | wc -l | tr -d ' ')

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ SUCCESS! All CMEMS processes stopped!"
    echo ""
    echo "Still running (GOOD):"
    ps aux | grep -E "consumer|uvicorn|yarn" | grep -v grep | awk '{print "  ✓", $11, $12, $13}'
else
    echo "⚠️  WARNING: $REMAINING CMEMS processes still running!"
    echo ""
    echo "Remaining processes:"
    ps aux | grep -E "join_tracklets|ingest-sea-state" | grep -v grep | awk '{print "  PID", $2, ":", $11, $12}'
    echo ""
    echo "Run this script again or manually kill with:"
    ps aux | grep -E "join_tracklets|ingest-sea-state" | grep -v grep | awk '{print "  kill -9", $2}'
fi

echo ""
echo "📊 Current disk usage:"
du -sh data/sea_state
