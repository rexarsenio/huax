#!/bin/bash
#
# Collect standalone weather data for all gates/checkpoints
# Run this every 3-6 hours to keep weather data fresh
#

set -e

cd "$(dirname "$0")"

echo "🌊 Starting Gate Weather Collection..."
echo "====================================="

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set database path
export DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"

# Run collection
python3 ingest_gate_weather.py

echo ""
echo "✅ Gate weather collection completed"
echo "====================================="

# Optional: Show latest records
echo ""
echo "Latest gate weather records:"
python3 -c "
import duckdb
con = duckdb.connect('${DUCKDB_PATH}', read_only=True)
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
con.close()
"
