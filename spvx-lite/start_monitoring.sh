#!/bin/bash
###############################################################################
# Start Prometheus + Grafana Monitoring Stack
###############################################################################

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting SPVX Monitoring Stack...${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}Error: Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Start docker compose
docker compose -f docker-compose.monitoring.yml up -d

# Wait for services to be healthy
echo ""
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 5

# Check Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null; then
    echo -e "${GREEN}✓ Prometheus is running at http://localhost:9090${NC}"
else
    echo -e "${YELLOW}⚠ Prometheus might still be starting...${NC}"
fi

# Check Grafana
if curl -s http://localhost:3000/api/health > /dev/null; then
    echo -e "${GREEN}✓ Grafana is running at http://localhost:3000${NC}"
    echo -e "  Login: admin / spvx-admin"
else
    echo -e "${YELLOW}⚠ Grafana might still be starting...${NC}"
fi

echo ""
echo -e "${GREEN}Monitoring stack started!${NC}"
echo ""
echo "Access points:"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana: http://localhost:3000 (admin / spvx-admin)"
echo ""
echo "Dashboard: SPVX Open-Sea AIS Monitoring"
echo ""
echo "To view logs:"
echo "  docker compose -f docker-compose.monitoring.yml logs -f"
echo ""
echo "To stop:"
echo "  ./stop_monitoring.sh"
