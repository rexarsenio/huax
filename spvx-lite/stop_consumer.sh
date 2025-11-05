#!/bin/bash
###############################################################################
# Stop the Open-Sea Consumer
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="logs/consumer.pid"
DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Stopping Open-Sea Consumer${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Function to stop process by PID
stop_process() {
    local pid=$1
    local name=$2
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        return 0
    fi
    
    echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
    kill "$pid" 2>/dev/null || true
    
    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $name stopped gracefully${NC}"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    echo -e "${RED}$name did not stop gracefully, forcing...${NC}"
    kill -9 "$pid" 2>/dev/null || true
    sleep 1
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name force-stopped${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to stop $name${NC}"
        return 1
    fi
}

# Stop consumer from PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        stop_process "$PID" "Consumer"
    else
        echo -e "${YELLOW}Consumer PID file exists but process not running (stale PID file)${NC}"
    fi
    rm -f "$PID_FILE"
else
    echo -e "${YELLOW}No PID file found at $PID_FILE${NC}"
fi

# Kill any remaining open-sea consumer processes
echo ""
echo -e "${YELLOW}Checking for any remaining open-sea consumer processes...${NC}"
REMAINING_PIDS=$(pgrep -f "spvx.cli open-sea-consume" 2>/dev/null || true)
if [ -n "$REMAINING_PIDS" ]; then
    echo -e "${YELLOW}Found remaining consumer processes: $REMAINING_PIDS${NC}"
    for pid in $REMAINING_PIDS; do
        stop_process "$pid" "Consumer (found by pattern)"
    done
else
    echo -e "${GREEN}✓ No remaining consumer processes found${NC}"
fi

# Check for DuckDB locks
echo ""
echo -e "${YELLOW}Checking for DuckDB locks on $DUCKDB_PATH...${NC}"
if command -v lsof >/dev/null 2>&1; then
    if [ -f "$DUCKDB_PATH" ]; then
        LOCK_PIDS=$(lsof "$DUCKDB_PATH" 2>/dev/null | awk 'NR>1 {print $2}' | sort -u || true)
        if [ -n "$LOCK_PIDS" ]; then
            echo -e "${RED}WARNING: DuckDB is still locked by the following processes:${NC}"
            lsof "$DUCKDB_PATH" 2>/dev/null || true
            echo ""
            echo -e "${YELLOW}Attempting to stop processes holding the lock...${NC}"
            for pid in $LOCK_PIDS; do
                if ps -p "$pid" > /dev/null 2>&1; then
                    PROC_NAME=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                    stop_process "$pid" "Process $PROC_NAME holding DuckDB lock"
                fi
            done
            
            # Final check
            sleep 1
            FINAL_LOCKS=$(lsof "$DUCKDB_PATH" 2>/dev/null | awk 'NR>1 {print $2}' | sort -u || true)
            if [ -n "$FINAL_LOCKS" ]; then
                echo -e "${RED}✗ WARNING: DuckDB is still locked by processes: $FINAL_LOCKS${NC}"
                echo -e "${RED}  You may need to manually kill these processes.${NC}"
            else
                echo -e "${GREEN}✓ DuckDB lock released${NC}"
            fi
        else
            echo -e "${GREEN}✓ No DuckDB locks found${NC}"
        fi
    else
        echo -e "${YELLOW}DuckDB file not found at $DUCKDB_PATH${NC}"
    fi
else
    echo -e "${YELLOW}lsof not available, cannot check for DuckDB locks${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Stop procedure completed${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
