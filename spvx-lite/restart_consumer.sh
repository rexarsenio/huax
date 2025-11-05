#!/bin/bash
###############################################################################
# Restart the Open-Sea Consumer
#
# This script safely stops and restarts the consumer, ensuring all locks are
# cleared before starting.
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Restarting Open-Sea Consumer${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Stop the consumer
echo -e "${YELLOW}Step 1/3: Stopping consumer...${NC}"
bash stop_consumer.sh
echo ""

# Step 2: Verify no locks remain
echo -e "${YELLOW}Step 2/3: Verifying locks are released...${NC}"
sleep 2

DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"
if command -v lsof >/dev/null 2>&1; then
    if [ -f "$DUCKDB_PATH" ]; then
        REMAINING_LOCKS=$(lsof "$DUCKDB_PATH" 2>/dev/null || true)
        if [ -n "$REMAINING_LOCKS" ]; then
            echo -e "${RED}ERROR: DuckDB locks still exist!${NC}"
            echo "$REMAINING_LOCKS"
            echo ""
            echo -e "${YELLOW}Attempting to clear locks...${NC}"
            bash check_duckdb_locks.sh --kill || {
                echo -e "${RED}Failed to clear locks. Aborting restart.${NC}"
                exit 1
            }
        else
            echo -e "${GREEN}✓ No locks detected${NC}"
        fi
    fi
else
    echo -e "${YELLOW}lsof not available, skipping lock check${NC}"
fi
echo ""

# Step 3: Start the consumer
echo -e "${YELLOW}Step 3/3: Starting consumer...${NC}"
bash start_consumer.sh

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Consumer restart completed${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
