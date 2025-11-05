#!/bin/bash
# SPVX Overnight Collection - MOCK MODE
# Nutzt vorhandene Daten und aggregiert sie regelmäßig

cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate

echo "🌙 Starting SPVX Overnight Collection (MOCK MODE)"
echo "Started at: $(date)"
echo ""
echo "ℹ️  MOCK MODE: Working with existing polygon_events data"
echo "   (For live AIS data, you need AISSTREAM_API_KEY)"
echo ""

# Create logs directory
mkdir -p logs

echo "📊 Starting periodic aggregation loop..."
echo "   - Every 30 minutes: aggregate data and compute index"
echo ""

# Counter for iterations
ITERATION=0

while true; do
    ITERATION=$((ITERATION + 1))
    CURRENT_TIME=$(date +"%Y-%m-%d %H:%M:%S")

    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  Collection Cycle #$ITERATION - $CURRENT_TIME"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""

    # Show current data counts
    echo "📊 Current data status:"
    duckdb db/spvx.duckdb << 'EOSQL' 2>/dev/null
SELECT
    'Polygon Events:  ' || COUNT(*) || ' rows' as status
FROM polygon_events
UNION ALL
SELECT
    'Gate Flux Daily: ' || COUNT(*) || ' rows (latest: ' || COALESCE(CAST(MAX(ds) AS VARCHAR), 'none') || ')'
FROM gate_flux_daily
UNION ALL
SELECT
    'SIS Daily:       ' || COUNT(*) || ' rows (latest: ' || COALESCE(CAST(MAX(ds) AS VARCHAR), 'none') || ')'
FROM sea_state_daily
UNION ALL
SELECT
    'Sea State:       ' || COUNT(*) || ' samples'
FROM sea_state_samples;
EOSQL

    echo ""
    echo "🔄 Running aggregations..."

    # Compute SIS daily
    echo -n "  - Computing SIS daily... "
    if python -m spvx.cli sea-state-join >> logs/overnight_aggregate.log 2>&1; then
        echo "✓"
    else
        echo "⚠ (check logs/overnight_aggregate.log)"
    fi

    # Compute index for today
    echo -n "  - Computing Global Index... "
    if python -m spvx.cli compute-index >> logs/overnight_index.log 2>&1; then
        echo "✓"
    else
        echo "⚠ (check logs/overnight_index.log)"
    fi

    # Generate forecast
    echo -n "  - Generating 7-day forecast... "
    if python -m spvx.cli forecast --horizon=7 >> logs/overnight_forecast.log 2>&1; then
        echo "✓"
    else
        echo "⚠ (check logs/overnight_forecast.log)"
    fi

    # Update API snapshot if script exists
    if [ -f "./UPDATE_API_SNAPSHOT.sh" ]; then
        echo -n "  - Updating API snapshot... "
        if ./UPDATE_API_SNAPSHOT.sh >> logs/overnight_api.log 2>&1; then
            echo "✓"
        else
            echo "⚠ (check logs/overnight_api.log)"
        fi
    fi

    echo ""
    echo "✅ Cycle #$ITERATION complete!"
    echo ""

    # Show latest index value
    echo "📈 Latest Global Index:"
    duckdb db/spvx.duckdb "
        SELECT
            ds as date,
            global_index_scaled as index,
            coverage
        FROM (
            SELECT ds, global_index_scaled, coverage
            FROM spvx_global_daily
            WHERE global_index_scaled IS NOT NULL
            ORDER BY ds DESC
            LIMIT 1
        )
    " 2>/dev/null || echo "   No index data yet"

    echo ""
    NEXT_TIME=$(date -v+30M +"%H:%M:%S")
    echo "💤 Sleeping 30 minutes... (next update at $NEXT_TIME)"
    echo "   Press Ctrl+C to stop"
    echo "════════════════════════════════════════════════════════"
    echo ""

    # Sleep for 30 minutes
    sleep 1800
done
