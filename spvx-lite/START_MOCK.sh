#!/bin/bash
# MOCK-MODUS Startup Script
# Dieses Script nutzt SEPARATE Mock-Datenbank: db/spvx_MOCK.duckdb
# Echte Produktionsdaten bleiben in: db/spvx.duckdb

set -e  # Stop on error

echo "🧪 STARTING HUAX IN MOCK MODE"
echo "================================"
echo "Mock Database: db/spvx_MOCK.duckdb"
echo "Production Database: db/spvx.duckdb (bleibt unberührt!)"
echo ""

# Setze Mock-Umgebungsvariablen
export RUN_MODE=mock
export DUCKDB_PATH=db/spvx_MOCK.duckdb

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

echo "📦 Step 1: Generating Mock Data..."
python -m spvx.cli ingest --mode mock

echo "🔧 Step 2: Building Basin Components & Indices..."
python -m spvx.cli build-basins

echo ""
echo "✅ Mock data ready in: db/spvx_MOCK.duckdb"
echo "✅ Components built for all basins including MED (Mediterranean)"
echo "✅ Basin indices computed: APAC, NAM, SAM, MED"
echo "✅ Global index computed"
echo ""
echo "🚀 Starting API Server on port 8080..."
echo "   Backend: http://localhost:8080"
echo "   Mediterranean Index: http://localhost:8080/api/index/MED"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python -m spvx.cli serve --port 8080
