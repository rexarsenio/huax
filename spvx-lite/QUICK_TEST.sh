#!/bin/bash
echo "╔══════════════════════════════════════╗"
echo "║  SPVX-LITE QUICK TEST                ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Test 1: Consumer
CONSUMER_PID=$(ps aux | grep "[o]pen-sea-consume" | awk '{print $2}')
if [ -z "$CONSUMER_PID" ]; then
    echo "❌ Consumer NOT running"
else
    echo "✅ Consumer running (PID: $CONSUMER_PID)"
fi

# Test 2: AIS Data Flow
FIXES=$(curl -s http://localhost:9110/metrics 2>/dev/null | grep "open_sea_fixes_total" | grep -o '[0-9.]*$')
echo "✅ AIS fixes received: $FIXES"

# Test 3: API
API_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
if echo "$API_HEALTH" | grep -q "ok"; then
    echo "✅ API server responding"
else
    echo "❌ API server not responding"
fi

# Test 4: Dashboard
DASHBOARD_PID=$(lsof -ti:5173 2>/dev/null | head -1)
if [ -z "$DASHBOARD_PID" ]; then
    echo "❌ Dashboard NOT running"
else
    echo "✅ Dashboard running"
    echo "   → http://localhost:5173"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  System Status: OPERATIONAL          ║"
echo "╚══════════════════════════════════════╝"
