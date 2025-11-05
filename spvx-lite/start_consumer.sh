#!/bin/bash
###############################################################################
# AIS Open-Sea Consumer Startup Script
# 
# This script starts the open-sea AIS consumer with proper environment setup.
# It handles:
# - Loading environment variables from .env
# - Checking for DuckDB locks
# - Starting the consumer in the background
# - Logging output
###############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

POLYGONS_PATH="${POLYGONS_PATH:-data/geo/polygons.geojson}"
GATES_PATH="${GATES_PATH:-data/geo/gates.geojson}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_DIR}/open_sea_consumer.log"
PID_FILE="${LOG_DIR}/consumer.pid"

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment from .env...${NC}"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${RED}ERROR: .env file not found!${NC}"
    exit 1
fi

# Validate API key
if [ -z "${AISSTREAM_API_KEY:-}" ]; then
    echo -e "${RED}ERROR: AISSTREAM_API_KEY not set in .env${NC}"
    exit 1
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Check for existing consumer process
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}Consumer already running with PID $OLD_PID${NC}"
        echo "Stop it first with: kill $OLD_PID"
        exit 1
    else
        echo -e "${YELLOW}Removing stale PID file${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Stop any conflicting processes
echo -e "${YELLOW}Checking for conflicting processes...${NC}"

# Kill any existing consumer processes
EXISTING_CONSUMERS=$(pgrep -f "spvx.cli open-sea-consume" 2>/dev/null || true)
if [ -n "$EXISTING_CONSUMERS" ]; then
    echo -e "${YELLOW}Found existing consumer processes: $EXISTING_CONSUMERS${NC}"
    echo -e "${YELLOW}Stopping them first...${NC}"
    bash stop_consumer.sh || true
    sleep 2
fi

# Also stop API processes that might hold locks
pkill -f "spvx.cli serve" || true
pkill -f "uvicorn spvx.api_app" || true
sleep 2

# Check DuckDB lock
DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"
if command -v lsof >/dev/null 2>&1; then
    if [ -f "$DUCKDB_PATH" ]; then
        LOCK_HOLDERS=$(lsof "$DUCKDB_PATH" 2>/dev/null | awk 'NR>1 {print $2}' | sort -u || true)
        if [ -n "$LOCK_HOLDERS" ]; then
            echo -e "${RED}ERROR: DuckDB is locked by the following processes:${NC}"
            lsof "$DUCKDB_PATH" 2>/dev/null || true
            echo ""
            echo -e "${YELLOW}Attempting to stop processes holding the lock...${NC}"
            for pid in $LOCK_HOLDERS; do
                if ps -p "$pid" > /dev/null 2>&1; then
                    PROC_NAME=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                    echo -e "${YELLOW}Killing process $pid ($PROC_NAME)...${NC}"
                    kill -9 "$pid" 2>/dev/null || true
                fi
            done
            sleep 2
            
            # Final check
            if lsof "$DUCKDB_PATH" 2>/dev/null | grep -q "$DUCKDB_PATH"; then
                echo -e "${RED}ERROR: DuckDB is still locked. Manual intervention required.${NC}"
                lsof "$DUCKDB_PATH" 2>/dev/null || true
                exit 1
            else
                echo -e "${GREEN}✓ DuckDB lock released${NC}"
            fi
        else
            echo -e "${GREEN}✓ No DuckDB locks found${NC}"
        fi
    fi
else
    echo -e "${YELLOW}lsof not available, skipping lock check${NC}"
fi

# Validate polygon and gate files
if [ ! -f "$POLYGONS_PATH" ]; then
    echo -e "${RED}ERROR: Polygons file not found: $POLYGONS_PATH${NC}"
    exit 1
fi

if [ ! -f "$GATES_PATH" ]; then
    echo -e "${RED}ERROR: Gates file not found: $GATES_PATH${NC}"
    exit 1
fi

# Resolve Python interpreter (prefer project venv)
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/.venv312/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv312/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo -e "${RED}ERROR: No python interpreter found (activate venv or install Python).${NC}"
    exit 1
fi

# Start consumer
echo -e "${GREEN}Starting open-sea consumer...${NC}"
echo "  Polygons: $POLYGONS_PATH"
echo "  Gates: $GATES_PATH"
echo "  Python: $PYTHON_BIN"
echo "  Logging to: $LOG_FILE"
echo ""

PYTHONUNBUFFERED=1 nohup "$PYTHON_BIN" -m spvx.cli open-sea-consume \
    --polygons "$POLYGONS_PATH" \
    --gates "$GATES_PATH" \
    > "$LOG_FILE" 2>&1 &

CONSUMER_PID=$!
echo $CONSUMER_PID > "$PID_FILE"

# Wait a moment and check if it's still running
sleep 3
if ps -p $CONSUMER_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Consumer started successfully (PID: $CONSUMER_PID)${NC}"
    echo ""
    echo "Monitor logs with: tail -f $LOG_FILE"
    echo "Check metrics at: http://localhost:9110/metrics"
    echo "Stop consumer with: kill $CONSUMER_PID"
    echo ""
    
    # Show initial log output
    echo -e "${YELLOW}Initial log output:${NC}"
    tail -20 "$LOG_FILE"
else
    echo -e "${RED}✗ Consumer failed to start. Check logs:${NC}"
    tail -50 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
