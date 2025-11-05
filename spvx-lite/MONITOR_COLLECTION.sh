#!/bin/bash
# Simple monitoring script for SPVX data collection

cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate

while true; do
    clear
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║     SPVX Data Collection Status                        ║"
    echo "║     $(date '+%Y-%m-%d %H:%M:%S')                              ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""

    # Check if consumer is running
    if pgrep -f "spvx.open_sea.consumer" > /dev/null; then
        echo "✅ Consumer: RUNNING"
    else
        echo "❌ Consumer: STOPPED"
    fi
    echo ""

    # Database status
    echo "📊 Database Status:"
    duckdb db/spvx.duckdb << 'EOSQL'
SELECT
    '  Polygon Events:  ' || COUNT(*) || ' rows  (latest: ' || COALESCE(CAST(MAX(ts) AS VARCHAR), 'none') || ')' as status
FROM polygon_events
UNION ALL
SELECT
    '  Gate Flux Daily: ' || COUNT(*) || ' rows  (latest: ' || COALESCE(CAST(MAX(ds) AS VARCHAR), 'none') || ')'
FROM gate_flux_daily
UNION ALL
SELECT
    '  SIS Daily:       ' || COUNT(*) || ' rows  (latest: ' || COALESCE(CAST(MAX(ds) AS VARCHAR), 'none') || ')'
FROM sea_state_daily
UNION ALL
SELECT
    '  Sea State:       ' || COUNT(*) || ' samples'
FROM sea_state_samples;
EOSQL

    echo ""
    echo "🔄 Next update in 15 seconds... (Press Ctrl+C to stop)"
    echo ""

    sleep 15
done
