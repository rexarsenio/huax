#!/bin/bash
# Full pipeline test: polygon detection -> registry enrichment -> backfill

set -e

DB="db/spvx_POLYGON_TEST.duckdb"

echo "========================================================================"
echo "FULL SHIP REGISTRY PIPELINE TEST"
echo "========================================================================"

source .venv312/bin/activate

echo ""
echo "[1/4] Bootstrap ship registry..."
python -m spvx.cli registry-bootstrap --db-path "$DB" --since 7d

echo ""
echo "[2/4] Enrich with heuristics (H1, H2, H3)..."
python -m spvx.cli registry-enrich --db-path "$DB" --horizon 90d \
    --geo-term data/geo/oil_terminals.geojson \
    --geo-sts data/geo/sts_zones.geojson

echo ""
echo "[3/4] Backfill tanker flags..."
python -m spvx.cli registry-backfill --db-path "$DB"

echo ""
echo "[4/4] Show final statistics..."
python -m spvx.cli registry-stats --db-path "$DB"

echo ""
echo "========================================================================"
echo "✓ FULL PIPELINE COMPLETE!"
echo "========================================================================"
