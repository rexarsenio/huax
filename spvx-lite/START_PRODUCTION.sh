#!/bin/bash
# PRODUCTION-MODUS Startup Script
# Dieses Script nutzt ECHTE Produktionsdaten: db/spvx.duckdb

set -e  # Stop on error

echo "🚀 STARTING HUAX IN PRODUCTION MODE"
echo "===================================="
echo "Production Database: db/spvx.duckdb"
echo "Mock Database: db/spvx_MOCK.duckdb (wird NICHT verwendet)"
echo ""

# Setze Production-Umgebungsvariablen
export RUN_MODE=production
export DUCKDB_PATH=db/spvx.duckdb

cd "$(dirname "$0")"

# Setup virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Check if spvx module is installed, if not install it
if ! python -c "import spvx" 2>/dev/null; then
    echo "📦 Installing SPVX module and dependencies..."
    pip install -e . --quiet || {
        echo "❌ Failed to install spvx module"
        echo "Please run manually:"
        echo "  source .venv/bin/activate"
        echo "  pip install -e ."
        exit 1
    }
    echo "✅ SPVX module installed"
    echo ""
fi

# Prüfe ob Produktionsdatenbank existiert
if [ ! -f "db/spvx.duckdb" ]; then
    echo "⚠️  WARNING: Production database not found!"
    echo ""
    echo "   To set up production data, run:"
    echo "   1. python -m spvx.cli ingest --mode live"
    echo "   2. python -m spvx.cli build-basins"
    echo "   3. python -m spvx.cli compute-index"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 Starting API Server on port 8080..."
echo "   Backend: http://localhost:8080"
echo "   Mediterranean Index: http://localhost:8080/api/index/MED"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python -m spvx.cli serve --port 8080
