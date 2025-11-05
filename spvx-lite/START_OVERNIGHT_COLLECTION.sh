#!/bin/bash
# SPVX Overnight Data Collection Script
# Startet Consumer und sammelt kontinuierlich Daten

cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✓ Loaded .env file"
fi

echo "🌙 Starting SPVX Overnight Collection..."
echo "Started at: $(date)"
echo ""

# Create logs directory if not exists
mkdir -p logs

# Kill any old consumers
pkill -f "spvx.open_sea.consumer" 2>/dev/null || true
sleep 2

# Resolve python binary from venv
PYTHON_BIN="${VIRTUAL_ENV:-.venv}/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "   ❌ Python interpreter not found at $PYTHON_BIN"
    exit 1
fi

# Start Consumer with logging (Typer CLI ensures proper config)
echo "🚀 Starting AIS Consumer..."
nohup "$PYTHON_BIN" -m spvx.cli open-sea-consume \
    --polygons data/geo/polygons.geojson \
    --gates data/geo/gates.geojson \
    --config-path config.yml \
    > logs/consumer_overnight.log 2>&1 &
CONSUMER_PID=$!
echo "   Consumer PID: $CONSUMER_PID"

# Wait a bit to check if it started successfully
sleep 5

if ps -p $CONSUMER_PID > /dev/null; then
    echo "   ✅ Consumer running successfully"
else
    echo "   ❌ Consumer failed to start - check logs/consumer_overnight.log"
    exit 1
fi

echo ""
echo "📊 Starting periodic aggregation loop..."
echo "   - Every 2 hours: aggregate data and compute index"
echo ""

# Periodic aggregation (every 2 hours)
while true; do
    CURRENT_TIME=$(date +"%Y-%m-%d %H:%M:%S")
    echo "=== $CURRENT_TIME ==="

    # Check if consumer is still running
    if ! ps -p $CONSUMER_PID > /dev/null; then
        echo "⚠️  Consumer died! Restarting..."
        nohup "$PYTHON_BIN" -m spvx.cli open-sea-consume \
            --polygons data/geo/polygons.geojson \
            --gates data/geo/gates.geojson \
            --config-path config.yml \
            > logs/consumer_overnight.log 2>&1 &
        CONSUMER_PID=$!
        echo "   New Consumer PID: $CONSUMER_PID"
    else
        echo "✓ Consumer still running (PID: $CONSUMER_PID)"
    fi

    # Show current data counts
    echo ""
    echo "Current data status:"
    duckdb db/spvx.duckdb "
        SELECT
            'Polygon Events' as table_name,
            COUNT(*) as rows,
            CAST(MAX(ts) AS VARCHAR) as latest
        FROM polygon_events
        UNION ALL
        SELECT 'Gate Flux Daily', COUNT(*), CAST(MAX(ds) AS VARCHAR) FROM gate_flux_daily
        UNION ALL
        SELECT 'SIS Daily', COUNT(*), CAST(MAX(ds) AS VARCHAR) FROM sea_state_daily
    " 2>/dev/null || echo "Database query failed"

    echo ""
    echo "Running aggregations..."

    # Aggregate polygon events to daily gate flux
    python -m spvx.open_sea.aggregate compute-aggregates --date=$(date +%Y-%m-%d) 2>/dev/null && echo "✓ Aggregation complete" || echo "⚠ Aggregation failed"

    # Compute SIS daily if we have new sea state samples
    python -m spvx.cli sea-state-join 2>/dev/null && echo "✓ SIS computation complete" || echo "⚠ SIS computation failed"

    # Compute index
    python -m spvx.cli compute-index 2>/dev/null && echo "✓ Index computation complete" || echo "⚠ Index computation failed"

    # Update API snapshot
    if [ -f "./UPDATE_API_SNAPSHOT.sh" ]; then
        ./UPDATE_API_SNAPSHOT.sh 2>/dev/null && echo "✓ API snapshot updated" || echo "⚠ API snapshot update failed"
    fi

    echo ""
    echo "Next update in 2 hours at $(date -v+2H +"%Y-%m-%d %H:%M:%S")..."
    echo "----------------------------------------"
    echo ""

    # Sleep for 2 hours (7200 seconds)
    sleep 7200
done
