#!/bin/bash
###############################################################################
# Check and Clear DuckDB Locks
#
# This script identifies and optionally kills processes holding locks on the
# DuckDB database file.
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"
FORCE_KILL="${1:-}"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  DuckDB Lock Check${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Database: $DUCKDB_PATH"
echo ""

if [ ! -f "$DUCKDB_PATH" ]; then
    echo -e "${YELLOW}Database file does not exist at: $DUCKDB_PATH${NC}"
    exit 0
fi

if ! command -v lsof >/dev/null 2>&1; then
    echo -e "${RED}ERROR: lsof command not found. Cannot check for locks.${NC}"
    echo "Please install lsof or manually check for processes using the database."
    exit 1
fi

# Get processes holding locks
LOCK_INFO=$(lsof "$DUCKDB_PATH" 2>/dev/null || true)

if [ -z "$LOCK_INFO" ]; then
    echo -e "${GREEN}✓ No processes are holding locks on the database${NC}"
    exit 0
fi

echo -e "${YELLOW}The following processes are holding locks on the database:${NC}"
echo ""
echo "$LOCK_INFO"
echo ""

# Extract PIDs
LOCK_PIDS=$(echo "$LOCK_INFO" | awk 'NR>1 {print $2}' | sort -u)

if [ "$FORCE_KILL" == "--kill" ] || [ "$FORCE_KILL" == "-k" ]; then
    echo -e "${RED}Killing processes holding locks...${NC}"
    for pid in $LOCK_PIDS; do
        if ps -p "$pid" > /dev/null 2>&1; then
            PROC_NAME=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
            PROC_CMD=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
            echo -e "${YELLOW}Killing PID $pid ($PROC_NAME): $PROC_CMD${NC}"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
    
    sleep 1
    
    # Verify locks are released
    REMAINING_LOCKS=$(lsof "$DUCKDB_PATH" 2>/dev/null || true)
    if [ -z "$REMAINING_LOCKS" ]; then
        echo -e "${GREEN}✓ All locks released successfully${NC}"
    else
        echo -e "${RED}✗ Some locks still remain:${NC}"
        echo "$REMAINING_LOCKS"
        exit 1
    fi
else
    echo -e "${YELLOW}To kill these processes, run:${NC}"
    echo "  $0 --kill"
    echo ""
    echo -e "${YELLOW}Or kill manually:${NC}"
    for pid in $LOCK_PIDS; do
        echo "  kill -9 $pid"
    done
    exit 1
fi
