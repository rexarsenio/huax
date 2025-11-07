#!/bin/bash
#
# Optimized gate weather collection - only downloads specific regions
#

set -e

cd "$(dirname "$0")"

echo "🌊 Gate Weather Collection (Optimized - No Global Downloads)"
echo "================================================================"
echo ""
echo "This script uses CMEMS spatial subsetting to download ONLY"
echo "the data for specific gate regions (~50-100MB instead of GB)"
echo ""

# Activate venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

export DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"

# Load .env
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check credentials
if [ -z "$CMEMS_USERNAME" ] || [ -z "$CMEMS_PASSWORD" ]; then
    echo "❌ CMEMS credentials not set!"
    echo ""
    echo "Create .env file with:"
    echo "  CMEMS_USERNAME=your_username"
    echo "  CMEMS_PASSWORD=your_password"
    exit 1
fi

echo "✅ Credentials found"
echo "✅ Will fetch data for 11 gates (spatial subsets only)"
echo ""

# Run optimized collection
python3 ingest_gate_weather_cmems_optimized.py

echo ""
echo "✅ Collection completed"
echo "================================================================"
