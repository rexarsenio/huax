#!/bin/bash
#
# Collect standalone weather data using CMEMS (Copernicus Marine)
#

set -e

cd "$(dirname "$0")"

echo "🌊 Starting Gate Weather Collection (CMEMS)..."
echo "====================================="

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set database path
export DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"

# Load .env if exists
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check credentials
if [ -z "$CMEMS_USERNAME" ] || [ -z "$CMEMS_PASSWORD" ]; then
    echo "❌ CMEMS credentials not set!"
    echo ""
    echo "Please create .env file with:"
    echo "  CMEMS_USERNAME=your_username"
    echo "  CMEMS_PASSWORD=your_password"
    echo ""
    echo "Or set environment variables:"
    echo "  export CMEMS_USERNAME='your_username'"
    echo "  export CMEMS_PASSWORD='your_password'"
    echo ""
    echo "Get credentials at: https://data.marine.copernicus.eu/register"
    exit 1
fi

# Run collection
python3 ingest_gate_weather_cmems.py

echo ""
echo "✅ Gate weather collection completed"
echo "====================================="

# Optional: Show latest records
if command -v python3 &> /dev/null; then
    echo ""
    echo "Latest gate weather records:"
    python3 -c "
import duckdb
con = duckdb.connect('${DUCKDB_PATH}', read_only=True)
try:
    result = con.execute('''
        SELECT
            gate_id,
            gate_name,
            observed_at,
            ROUND(hs_m, 2) as wave_height_m,
            ROUND(speed_knots, 2) as current_kn
        FROM gate_weather_standalone
        ORDER BY observed_at DESC
        LIMIT 10
    ''').fetchall()
    for row in result:
        print(f'  {row[0]:<25} | {row[1]:<30} | Waves: {row[3]}m | Current: {row[4]}kn | {row[2]}')
except:
    print('  No data yet')
finally:
    con.close()
"
fi
