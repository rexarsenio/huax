#!/bin/bash
###############################################################################
# Stop Prometheus + Grafana Monitoring Stack
###############################################################################

set -euo pipefail

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${YELLOW}Stopping SPVX Monitoring Stack...${NC}"

docker compose -f docker-compose.monitoring.yml down

echo -e "${GREEN}✓ Monitoring stack stopped${NC}"
echo ""
echo "To start again: ./start_monitoring.sh"
echo "To remove all data: docker compose -f docker-compose.monitoring.yml down -v"
