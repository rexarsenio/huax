#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🌊 Gate Weather Collection (CMEMS)"
echo "="*60

if [ -d ".venv" ]; then source .venv/bin/activate
elif [ -d "venv" ]; then source venv/bin/activate; fi

export DUCKDB_PATH="${DUCKDB_PATH:-db/spvx.duckdb}"

if [ -f ".env" ]; then export $(cat .env | grep -v '^#' | xargs); fi

if [ -z "$CMEMS_USERNAME" ] || [ -z "$CMEMS_PASSWORD" ]; then
    echo "❌ CMEMS credentials not set in .env"; exit 1
fi

python3 ingest_gate_weather_final.py
