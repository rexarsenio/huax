#!/bin/bash
# DASHBOARD Startup Script
# Startet das Huax Frontend Dashboard

set -e  # Stop on error

echo "🎨 STARTING HUAX DASHBOARD"
echo "=========================="
echo ""

cd "$(dirname "$0")"

# Prüfe ob Backend läuft
if ! curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "⚠️  WARNING: Backend is not running!"
    echo ""
    echo "Please start the backend first:"
    echo "  cd ../spvx-lite"
    echo "  ./START_MOCK.sh       (for testing with mock data)"
    echo "  or"
    echo "  ./START_PRODUCTION.sh (for production with real data)"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📦 Installing dependencies (if needed)..."
yarn install --silent

echo ""
echo "🚀 Starting Development Server..."
echo "   Dashboard: http://localhost:5173"
echo ""
echo "   ✅ Test Mediterranean Basin:"
echo "      - Click on 'Mediterranean' tab"
echo "      - Check components: CQ_SUEZ, CQ_GIBRALTAR, PORT_MED"
echo "      - Switch languages: EN → ES → IT → PT"
echo ""
echo "Press Ctrl+C to stop"
echo ""

yarn dev
