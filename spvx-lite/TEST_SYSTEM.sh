#!/bin/bash

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  SPVX-LITE SYSTEM TEST                                   ║"
echo "╔══════════════════════════════════════════════════════════╗"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test 1: Consumer Status
echo -e "${BLUE}═══ 1. AIS Consumer Status ═══${NC}"
CONSUMER_PID=$(ps aux | grep "[o]pen-sea-consume" | awk '{print $2}')
if [ -z "$CONSUMER_PID" ]; then
    echo -e "${RED}✗ Consumer NOT running${NC}"
else
    echo -e "${GREEN}✓ Consumer running (PID: $CONSUMER_PID)${NC}"
fi
echo ""

# Test 2: AIS Message Flow
echo -e "${BLUE}═══ 2. AIS Message Flow ═══${NC}"
FIXES_BEFORE=$(curl -s http://localhost:9110/metrics 2>/dev/null | grep "open_sea_fixes_total" | grep -o '[0-9.]*$')
echo "Current AIS fixes: $FIXES_BEFORE"
echo "Waiting 10 seconds to check for new messages..."
sleep 10
FIXES_AFTER=$(curl -s http://localhost:9110/metrics 2>/dev/null | grep "open_sea_fixes_total" | grep -o '[0-9.]*$')
echo "AIS fixes after 10s: $FIXES_AFTER"

if (( $(echo "$FIXES_AFTER > $FIXES_BEFORE" | bc -l) )); then
    DIFF=$(echo "$FIXES_AFTER - $FIXES_BEFORE" | bc)
    echo -e "${GREEN}✓ Receiving new AIS data (+$DIFF messages in 10s)${NC}"
else
    echo -e "${RED}✗ NO new AIS data received${NC}"
fi
echo ""

# Test 3: Database Lock Status
echo -e "${BLUE}═══ 3. Database Status ═══${NC}"
DB_LOCKS=$(lsof db/spvx.duckdb 2>/dev/null | tail -n +2)
if [ -z "$DB_LOCKS" ]; then
    echo -e "${YELLOW}⚠ No database locks (consumer might not be writing)${NC}"
else
    echo -e "${GREEN}✓ Database locked by consumer (active writes)${NC}"
    echo "$DB_LOCKS" | head -3
fi
echo ""

# Test 4: Recent Database Activity
echo -e "${BLUE}═══ 4. Recent Database Activity ═══${NC}"
.venv/bin/python << 'PYEOF'
import duckdb
from datetime import datetime, timedelta
import sys

try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    # Check polygon_events
    result = con.execute("""
        SELECT
            COUNT(*) as total_events,
            COUNT(DISTINCT mmsi) as unique_vessels,
            MAX(ts_in) as latest_event
        FROM polygon_events
        WHERE ts_in >= NOW() - INTERVAL '1 hour'
    """).fetchone()

    if result[0] > 0:
        print(f"✓ Polygon Events (last hour): {result[0]} events, {result[1]} vessels")
        print(f"  Latest event: {result[2]}")
    else:
        print("⚠ No polygon events in last hour")

    # Check AIS fixes table (if exists)
    tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()
    table_names = [t[0] for t in tables]

    if 'ais_fixes' in table_names:
        result = con.execute("""
            SELECT COUNT(*), MAX(msg_time)
            FROM ais_fixes
            WHERE msg_time >= NOW() - INTERVAL '5 minutes'
        """).fetchone()
        if result[0] > 0:
            print(f"✓ AIS Fixes (last 5 min): {result[0]} fixes")
        else:
            print("⚠ No AIS fixes in last 5 minutes")

    con.close()
except Exception as e:
    print(f"✗ Database check failed: {e}")
    sys.exit(1)
PYEOF
echo ""

# Test 5: API Server
echo -e "${BLUE}═══ 5. API Server Status ═══${NC}"
API_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
if echo "$API_HEALTH" | grep -q "ok"; then
    echo -e "${GREEN}✓ API server responding${NC}"
else
    echo -e "${RED}✗ API server not responding${NC}"
fi
echo ""

# Test 6: Recent Polygon Events
echo -e "${BLUE}═══ 6. Recent Polygon Events (Last 5 min) ═══${NC}"
.venv/bin/python << 'PYEOF'
import duckdb
from datetime import datetime

try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    result = con.execute("""
        SELECT
            polygon_id,
            kind,
            COUNT(*) as event_count,
            COUNT(DISTINCT mmsi) as vessels
        FROM polygon_events
        WHERE ts_in >= NOW() - INTERVAL '5 minutes'
        GROUP BY polygon_id, kind
        ORDER BY event_count DESC
        LIMIT 10
    """).fetchall()

    if result:
        print("Polygon              Kind        Events  Vessels")
        print("─" * 50)
        for row in result:
            print(f"{row[0]:<20} {row[1]:<11} {row[2]:<7} {row[3]}")
    else:
        print("⚠ No polygon events in last 5 minutes")

    con.close()
except Exception as e:
    print(f"✗ Query failed: {e}")
PYEOF
echo ""

# Test 7: Metrics Endpoint
echo -e "${BLUE}═══ 7. Consumer Metrics ═══${NC}"
curl -s http://localhost:9110/metrics 2>/dev/null | grep -E "(open_sea_fixes_total|open_sea_polygon_events_total|open_sea_gate_crossings_total)" | head -5
echo ""

# Test 8: Log Check
echo -e "${BLUE}═══ 8. Recent Consumer Logs (Last 20 lines) ═══${NC}"
if [ -f "logs/open_sea_consumer.log" ]; then
    tail -20 logs/open_sea_consumer.log
else
    echo -e "${RED}✗ Log file not found${NC}"
fi
echo ""

# Test 9: Dashboard Status
echo -e "${BLUE}═══ 9. Dashboard Status ═══${NC}"
DASHBOARD_PID=$(lsof -ti:5173 2>/dev/null)
if [ -z "$DASHBOARD_PID" ]; then
    echo -e "${RED}✗ Dashboard NOT running on port 5173${NC}"
else
    echo -e "${GREEN}✓ Dashboard running (PID: $DASHBOARD_PID)${NC}"
    echo "  URL: http://localhost:5173"
fi
echo ""

# Test 10: Sea State Data
echo -e "${BLUE}═══ 10. Sea State Data Status ═══${NC}"
PARQUET_COUNT=$(ls -1 data/processed/sea_state_*.parquet 2>/dev/null | wc -l)
echo "Sea state parquet files: $PARQUET_COUNT"

.venv/bin/python << 'PYEOF'
import duckdb
try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)

    # Check if sea_state_daily exists
    tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name='sea_state_daily'").fetchall()

    if tables:
        count = con.execute("SELECT COUNT(*) FROM sea_state_daily").fetchone()[0]
        if count > 0:
            print(f"✓ Sea state data: {count} rows in database")
        else:
            print("⚠ sea_state_daily table exists but is empty")
    else:
        print("⚠ sea_state_daily table does not exist")

    con.close()
except Exception as e:
    print(f"✗ Check failed: {e}")
PYEOF
echo ""

# Summary
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  TEST COMPLETE                                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "To monitor in real-time:"
echo "  - Logs:    tail -f logs/open_sea_consumer.log"
echo "  - Metrics: watch -n 5 'curl -s http://localhost:9110/metrics | grep open_sea_fixes_total'"
echo "  - API:     curl http://localhost:8000/api/open_sea/corridor_view"
