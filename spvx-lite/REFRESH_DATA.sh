#!/bin/bash
# Quick refresh script for stale SPVX data
# Refreshes sea-state, SIS, and API snapshot

set -e  # Exit on error

echo "🔄 SPVX Data Refresh"
echo "="
echo ""

# Check we're in the right directory
if [ ! -f "config.yml" ]; then
    echo "❌ Error: Must run from spvx-lite directory"
    exit 1
fi

# Activate venv
if [ -d ".venv" ]; then
    echo "✓ Activating virtual environment..."
    source .venv/bin/activate
else
    echo "❌ Error: .venv not found"
    exit 1
fi

# Check for CMEMS credentials
if [ -z "$CMEMS_USERNAME" ] || [ -z "$CMEMS_PASSWORD" ]; then
    echo "⚠️  Warning: CMEMS credentials not set in environment"
    echo "   Sea-state ingestion will use fallback providers"
    echo ""
fi

# 1. Refresh Sea State Data
echo "1️⃣  Refreshing sea-state data (CMEMS/RTOFS)..."
echo "   This may take 2-5 minutes depending on provider..."
PYTHONPATH=src python -m spvx.cli ingest-sea-state \
    --provider auto \
    --lookback-days 3 \
    2>&1 | grep -E "✓|✗|Sea-state|files|rows|ERROR" || true

echo ""

# 2. Compute SIS aggregations
echo "2️⃣  Computing SIS daily aggregations..."
PYTHONPATH=src python -m spvx.cli sea-state-join 2>&1 | grep -E "✓|✗|refreshed|ERROR" || true

echo ""

# 3. Refresh gate weather (if script exists)
if [ -f "./COLLECT_GATE_WEATHER.sh" ]; then
    echo "3️⃣  Refreshing gate weather data..."
    ./COLLECT_GATE_WEATHER.sh 2>&1 | tail -20
    echo ""
fi

# 4. Update API snapshot
echo "4️⃣  Updating API snapshot database..."
if [ -f "./UPDATE_API_SNAPSHOT.sh" ]; then
    ./UPDATE_API_SNAPSHOT.sh
else
    echo "   Creating API snapshot manually..."
    python3 << 'EOF'
import duckdb
from pathlib import Path

main_db = Path("db/spvx.duckdb")
api_db = Path("db/spvx_api.duckdb")

if not main_db.exists():
    print("   ❌ Main database not found")
    exit(1)

# Create/update API database
print(f"   Copying {main_db} -> {api_db}")
api_con = duckdb.connect(str(api_db))
api_con.execute(f"ATTACH '{main_db}' AS main_db")

# Copy key tables
tables = [
    'open_sea_fixes',
    'gate_flux',
    'gate_crossings',
    'sis_daily',
    'sea_state_samples',
    'gate_weather_standalone',
    'anchorage_polygons',
    'anchorage_episodes',
    'anchorage_daily_dwell'
]

for table in tables:
    try:
        # Check if table exists in main DB
        api_con.execute(f"SELECT 1 FROM main_db.{table} LIMIT 1").fetchone()

        # Copy it
        api_con.execute(f"DROP TABLE IF EXISTS {table}")
        api_con.execute(f"CREATE TABLE {table} AS SELECT * FROM main_db.{table}")

        count = api_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"   ✓ {table}: {count:,} rows")
    except Exception as e:
        print(f"   ⚠️  {table}: {e}")

api_con.commit()
api_con.close()
print("   ✅ API snapshot updated")
EOF
fi

echo ""
echo "="
echo "✅ Data refresh complete!"
echo ""
echo "Next steps:"
echo "  • Restart dashboard: npm run dev (in dashboard/ directory)"
echo "  • Or restart API: python -m uvicorn spvx.api_app:app --reload"
echo ""
echo "To verify data freshness:"
echo "  python3 diagnose_data.py"
