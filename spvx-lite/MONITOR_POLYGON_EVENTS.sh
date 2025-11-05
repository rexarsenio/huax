#!/bin/bash

# Monitor for polygon events to start Sea State pipeline

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Monitoring for Polygon Events                           ║"
echo "║  Warte auf Schiffe in definierten Polygonen...          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

source .venv/bin/activate

# Check which polygons are defined
echo "=== Defined Polygons ==="
python << 'PYEOF'
import json
with open('data/geo/polygons.geojson', 'r') as f:
    data = json.load(f)
    print(f"Total polygons: {len(data['features'])}")
    for feature in data['features'][:10]:
        props = feature['properties']
        print(f"  - {props.get('id', 'unnamed')}: {props.get('name', 'no name')} ({props.get('kind', 'unknown')})")
    if len(data['features']) > 10:
        print(f"  ... and {len(data['features']) - 10} more")
PYEOF
echo ""

echo "=== Monitoring Loop (Ctrl+C to stop) ==="
echo "Checking every 30 seconds..."
echo ""

LAST_COUNT=0
ITERATION=0

while true; do
    ITERATION=$((ITERATION + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Get counts from database
    RESULT=$(python << 'PYEOF'
import duckdb
try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    # Polygon events
    poly_count = con.execute("SELECT COUNT(*) FROM polygon_events").fetchone()[0]

    # Open sea fixes
    fix_count = con.execute("SELECT COUNT(*) FROM open_sea_fixes").fetchone()[0]

    # Recent polygon events (last 5 min)
    recent = con.execute("""
        SELECT COUNT(*)
        FROM polygon_events
        WHERE ts >= NOW() - INTERVAL '5 minutes'
    """).fetchone()[0]

    # Unique vessels in polygons
    if poly_count > 0:
        vessels = con.execute("""
            SELECT COUNT(DISTINCT mmsi)
            FROM polygon_events
        """).fetchone()[0]
    else:
        vessels = 0

    print(f"{poly_count}|{fix_count}|{recent}|{vessels}")
    con.close()
except Exception as e:
    print(f"0|0|0|0")
PYEOF
)

    # Parse results
    IFS='|' read -r POLY_COUNT FIX_COUNT RECENT_COUNT VESSEL_COUNT <<< "$RESULT"

    # Get AIS metrics
    AIS_FIXES=$(curl -s http://localhost:9110/metrics 2>/dev/null | grep "open_sea_fixes_total" | tail -1 | awk '{print $2}' | cut -d'.' -f1)

    # Print status
    printf "[%s] Iteration #%d\n" "$TIMESTAMP" "$ITERATION"
    printf "  AIS Fixes (Metrics):  %s\n" "${AIS_FIXES:-0}"
    printf "  DB Open Sea Fixes:    %s\n" "$FIX_COUNT"
    printf "  Polygon Events Total: %s" "$POLY_COUNT"

    if [ "$POLY_COUNT" -gt "$LAST_COUNT" ]; then
        NEW=$((POLY_COUNT - LAST_COUNT))
        echo " (+$NEW NEW! 🎉)"
    else
        echo ""
    fi

    printf "  Recent (5 min):       %s\n" "$RECENT_COUNT"
    printf "  Unique Vessels:       %s\n" "$VESSEL_COUNT"

    LAST_COUNT=$POLY_COUNT

    # If we have polygon events, show details
    if [ "$POLY_COUNT" -gt 0 ]; then
        echo ""
        echo "  === Recent Polygon Events ==="
        python << 'PYEOF'
import duckdb
try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)
    result = con.execute("""
        SELECT
            polygon_id,
            event,
            mmsi,
            ts
        FROM polygon_events
        ORDER BY ts DESC
        LIMIT 5
    """).fetchall()

    for row in result:
        print(f"    {row[3]} | {row[0]} | {row[1]} | MMSI {row[2]}")

    con.close()
except Exception as e:
    pass
PYEOF
        echo ""
        echo "  ✅ Polygon Events vorhanden! Bereit für Tracklet-Generierung."
    fi

    echo "  ────────────────────────────────────────"
    echo ""

    sleep 30
done
