#!/bin/bash
#
# Quick test script for Gate Weather System
#

echo "======================================"
echo "🧪 Gate Weather System - Quick Test"
echo "======================================"
echo ""

cd "$(dirname "$0")/spvx-lite"

# Check if database exists
if [ ! -f "db/spvx.duckdb" ]; then
    echo "❌ Database not found at db/spvx.duckdb"
    echo "   Please create it first or check the path"
    exit 1
fi

echo "✅ Database found"
echo ""

# Check if API is running
echo "🔍 Checking if API is running on localhost:8000..."
if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API is running!"
    echo ""

    echo "📊 Testing gate_weather endpoint..."
    echo "-----------------------------------"

    # Test the endpoint
    response=$(curl -s http://localhost:8000/api/open_sea/gate_weather?window=h24)

    if echo "$response" | grep -q "message"; then
        echo "⚠️  API Response:"
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        echo ""
        echo "💡 This means: No weather data collected yet."
        echo "   Run: ./COLLECT_GATE_WEATHER.sh to collect data"
    elif echo "$response" | grep -q "gates"; then
        gate_count=$(echo "$response" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('gates', [])))" 2>/dev/null || echo "?")
        echo "✅ Weather data available for $gate_count gates!"
        echo ""
        echo "📍 Sample data:"
        echo "$response" | python3 -m json.tool 2>/dev/null | head -50
    else
        echo "❌ Unexpected response:"
        echo "$response"
    fi

else
    echo "❌ API is NOT running"
    echo ""
    echo "To start the API:"
    echo "  cd spvx-lite"
    echo "  ./START_API.sh"
    echo ""
    echo "Or check the SYSTEM_READY.md guide"
fi

echo ""
echo "======================================"
echo "🌐 Dashboard URLs (if running):"
echo "======================================"
echo "  Dashboard:  http://localhost:5173"
echo "  API Health: http://localhost:8000/health"
echo "  API Docs:   http://localhost:8000/docs"
echo "  Gate Weather: http://localhost:8000/api/open_sea/gate_weather?window=h24"
echo ""
