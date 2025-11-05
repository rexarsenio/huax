#!/bin/bash
###############################################################################
# END-TO-END SHIP REGISTRY & TANKER CLASSIFICATION TEST
#
# Tests the complete pipeline:
# 1. Polygon Detection (dwells at terminals/STS zones)
# 2. Ship Registry Bootstrap (find all vessels)
# 3. Registry Enrichment (classify tankers via H1, H2, H3)
# 4. Backfill (label all historical AIS records)
#
# Database: Uses test snapshot to avoid disrupting live consumer
###############################################################################

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

DB_TEST="db/spvx_E2E_TEST.duckdb"
DB_PROD="db/spvx.duckdb"

echo -e "${CYAN}========================================================================${NC}"
echo -e "${CYAN}END-TO-END SHIP REGISTRY & TANKER CLASSIFICATION TEST${NC}"
echo -e "${CYAN}========================================================================${NC}"

# Activate venv
source .venv312/bin/activate

# Step 0: Create fresh test snapshot
echo -e "\n${YELLOW}[0/5] Creating test database snapshot...${NC}"
if [ -f "$DB_TEST" ]; then
    rm "$DB_TEST"
fi
cp "$DB_PROD" "$DB_TEST"
echo -e "${GREEN}✓ Snapshot created: $DB_TEST${NC}"

# Clean old tables from test DB
echo -e "\n${YELLOW}[0/5] Cleaning old tables...${NC}"
python -c "
import duckdb
con = duckdb.connect('$DB_TEST')
con.execute('DROP TABLE IF EXISTS polygon_events CASCADE')
con.execute('DROP TABLE IF EXISTS polygon_sessions_open CASCADE')
con.execute('DROP TABLE IF EXISTS ship_registry CASCADE')
con.execute('DROP TABLE IF EXISTS ship_registry_audit CASCADE')
con.execute('DROP SEQUENCE IF EXISTS ship_registry_audit_seq CASCADE')
con.close()
print('✓ Old tables dropped')
"

# Step 1: Polygon Detection
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}[1/5] POLYGON DETECTION (Oil Terminals & STS Zones)${NC}"
echo -e "${CYAN}========================================================================${NC}"
python -m spvx.cli polygon-detect \
    --db-path "$DB_TEST" \
    --terminals data/geo/oil_terminals.geojson \
    --sts data/geo/sts_zones.geojson \
    --since 7d \
    --batch-size 10000

# Step 2: Bootstrap Ship Registry
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}[2/5] SHIP REGISTRY BOOTSTRAP${NC}"
echo -e "${CYAN}========================================================================${NC}"
python -m spvx.cli registry-bootstrap \
    --db-path "$DB_TEST" \
    --since 7d

# Step 3: Enrich with Heuristics
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}[3/5] REGISTRY ENRICHMENT (Heuristics H1, H2, H3)${NC}"
echo -e "${CYAN}========================================================================${NC}"
python -m spvx.cli registry-enrich \
    --db-path "$DB_TEST" \
    --horizon 90d \
    --geo-term data/geo/oil_terminals.geojson \
    --geo-sts data/geo/sts_zones.geojson

# Step 4: Backfill Historical Records
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}[4/5] BACKFILL TANKER FLAGS (Historical AIS Records)${NC}"
echo -e "${CYAN}========================================================================${NC}"
python -m spvx.cli registry-backfill \
    --db-path "$DB_TEST"

# Step 5: Final Statistics
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}[5/5] FINAL RESULTS${NC}"
echo -e "${CYAN}========================================================================${NC}"
python -m spvx.cli registry-stats \
    --db-path "$DB_TEST"

# Generate detailed report
echo -e "\n${CYAN}========================================================================${NC}"
echo -e "${CYAN}DETAILED ANALYSIS${NC}"
echo -e "${CYAN}========================================================================${NC}"

python -c "
import duckdb
con = duckdb.connect('$DB_TEST', read_only=True)

print('\n${YELLOW}[POLYGON EVENTS]${NC}')
result = con.execute('''
    SELECT
        kind,
        COUNT(*) as events,
        COUNT(DISTINCT mmsi) as unique_vessels,
        SUM(dwell_min) as total_dwell_min,
        AVG(dwell_min) as avg_dwell_min,
        MIN(dwell_min) as min_dwell,
        MAX(dwell_min) as max_dwell
    FROM polygon_events
    GROUP BY kind
''').fetchall()

for row in result:
    kind, events, vessels, total, avg, min_d, max_d = row
    print(f'  {kind}:')
    print(f'    Events: {events:,}')
    print(f'    Unique vessels: {vessels:,}')
    print(f'    Total dwell: {total:,} min ({total/60:.1f} hours)')
    print(f'    Avg dwell: {avg:.1f} min')
    print(f'    Range: {min_d}-{max_d} min')

print('\n${YELLOW}[TOP 10 POLYGONS]${NC}')
result = con.execute('''
    SELECT polygon_id, kind, COUNT(*) as visits, SUM(dwell_min) as total_dwell
    FROM polygon_events
    GROUP BY polygon_id, kind
    ORDER BY visits DESC
    LIMIT 10
''').fetchall()

for polygon_id, kind, visits, dwell in result:
    print(f'  {polygon_id:25} ({kind:15}): {visits:4} visits, {dwell:8,} min')

print('\n${YELLOW}[TANKER CLASSIFICATION BREAKDOWN]${NC}')
result = con.execute('''
    SELECT
        type_source,
        COUNT(*) as count,
        AVG(confidence) as avg_conf,
        MIN(confidence) as min_conf,
        MAX(confidence) as max_conf
    FROM ship_registry
    WHERE type_source IS NOT NULL
    GROUP BY type_source
    ORDER BY count DESC
''').fetchall()

if result:
    for source, count, avg_c, min_c, max_c in result:
        print(f'  {source:20}: {count:5,} vessels (confidence: {avg_c:.2f} avg, {min_c:.2f}-{max_c:.2f} range)')
else:
    print('  No tanker classifications yet')

print('\n${YELLOW}[AIS CANON TANKER STATISTICS]${NC}')
result = con.execute('''
    SELECT
        COUNT(*) as total_fixes,
        SUM(CASE WHEN is_tanker THEN 1 ELSE 0 END) as tanker_fixes,
        SUM(CASE WHEN is_tanker THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as tanker_pct,
        COUNT(DISTINCT mmsi) as unique_vessels,
        COUNT(DISTINCT CASE WHEN is_tanker THEN mmsi END) as unique_tankers
    FROM ais_canon
''').fetchone()

if result:
    total, tankers, pct, vessels, t_vessels = result
    print(f'  Total AIS fixes: {total:,}')
    print(f'  Tanker fixes: {tankers:,} ({pct:.1f}%)')
    print(f'  Unique vessels: {vessels:,}')
    print(f'  Unique tankers: {t_vessels:,}')

con.close()
"

echo -e "\n${GREEN}========================================================================${NC}"
echo -e "${GREEN}✓ END-TO-END TEST COMPLETE!${NC}"
echo -e "${GREEN}========================================================================${NC}"
echo -e "${CYAN}Test database: $DB_TEST${NC}"
echo -e "${CYAN}Production database untouched: $DB_PROD${NC}"
echo ""
