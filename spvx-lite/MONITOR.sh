#!/bin/bash
#
# MONITOR.sh - Real-time monitoring of SPVX-Lite data ingestion
#
# Shows:
# - AIS data ingestion rate
# - Polygon events growth
# - Ship registry size
# - Database size
# - Recent activity
#

cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Header
clear
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         SPVX-Lite Real-Time Data Ingestion Monitor            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to format large numbers
format_number() {
    printf "%'d" "$1" 2>/dev/null || echo "$1"
}

# Check processes
echo -e "${YELLOW}📊 System Status${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check ingestion
if pgrep -f ingest_aisstream.py > /dev/null; then
    PID=$(pgrep -f ingest_aisstream.py)
    echo -e "  ${GREEN}✓${NC} AIS Ingestion:    ${GREEN}Running${NC} (PID: $PID)"
else
    echo -e "  ${RED}✗${NC} AIS Ingestion:    ${RED}Stopped${NC}"
fi

# Check API
if lsof -ti:8000 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} API Server:       ${GREEN}Running${NC} (http://localhost:8000)"
else
    echo -e "  ${RED}✗${NC} API Server:       ${RED}Stopped${NC}"
fi

# Check Dashboard
if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Dashboard:        ${GREEN}Running${NC} (http://localhost:5173)"
else
    echo -e "  ${YELLOW}⚠${NC} Dashboard:        ${YELLOW}Not detected${NC}"
fi

echo ""

# Database stats
echo -e "${YELLOW}💾 Database Statistics${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

DB_FILE="db/spvx.duckdb"
if [ -f "$DB_FILE" ]; then
    DB_SIZE=$(du -h "$DB_FILE" | cut -f1)
    echo -e "  Database size:    ${BLUE}$DB_SIZE${NC}"

    # Query database
    python3 << 'EOF'
import duckdb
import sys
from pathlib import Path

db_path = Path("db/spvx.duckdb")

# Try to connect read-only
try:
    con = duckdb.connect(str(db_path), read_only=True)

    # Get key table counts
    tables = {
        'ais_raw': 'Raw AIS messages',
        'ais_canon': 'Canonicalized AIS',
        'polygon_events': 'Polygon events',
        'ship_registry': 'Ship registry',
        'gate_crossings': 'Gate crossings',
        'open_sea_fixes': 'Open sea fixes'
    }

    for table, desc in tables.items():
        try:
            result = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            count = result[0] if result else 0
            print(f"  {desc:.<30} {count:>15,}")
        except:
            pass

    # Get latest timestamp
    try:
        result = con.execute("SELECT MAX(ts) FROM ais_raw").fetchone()
        if result and result[0]:
            print(f"\n  Latest AIS data:  {result[0]}")
    except:
        pass

    con.close()

except Exception as e:
    print(f"  ⚠️  Database locked (ingestion running)")
    print(f"     This is normal - data is being written")

EOF
else
    echo -e "  ${RED}Database not found: $DB_FILE${NC}"
fi

echo ""

# API Snapshot stats
echo -e "${YELLOW}📸 API Snapshot (for dashboard)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SNAPSHOT_FILE="db/spvx_api.duckdb"
if [ -f "$SNAPSHOT_FILE" ]; then
    SNAPSHOT_SIZE=$(du -h "$SNAPSHOT_FILE" | cut -f1)
    SNAPSHOT_AGE=$(python3 -c "import time; from pathlib import Path; mtime = Path('$SNAPSHOT_FILE').stat().st_mtime; age_min = int((time.time() - mtime) / 60); print(f'{age_min} minutes ago')")
    echo -e "  Snapshot size:    ${BLUE}$SNAPSHOT_SIZE${NC}"
    echo -e "  Last updated:     ${BLUE}$SNAPSHOT_AGE${NC}"

    python3 << 'EOF'
import duckdb
from pathlib import Path

snapshot_path = Path("db/spvx_api.duckdb")
try:
    con = duckdb.connect(str(snapshot_path), read_only=True)
    result = con.execute("SELECT COUNT(*) FROM polygon_events").fetchone()
    count = result[0] if result else 0
    print(f"  Polygon events:   {count:>15,}")
    con.close()
except:
    pass
EOF

    echo ""
    echo -e "  ${CYAN}💡 Tip: Run ./UPDATE_API_SNAPSHOT.sh to refresh${NC}"
else
    echo -e "  ${RED}No snapshot found${NC}"
    echo -e "  ${CYAN}💡 Run ./UPDATE_API_SNAPSHOT.sh to create one${NC}"
fi

echo ""

# Recent log activity
echo -e "${YELLOW}📝 Recent Activity (last 10 lines)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

LOG_FILE="logs/ais-ingest.error.log"
if [ -f "$LOG_FILE" ]; then
    tail -n 10 "$LOG_FILE" | while read line; do
        echo "  $line"
    done
else
    echo "  No log file found at $LOG_FILE"
fi

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Press Ctrl+C to exit • Run './MONITOR.sh' to refresh         ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
