#!/bin/bash
#
# COMPUTE_INDEX_NOW.sh
#
# Temporarily pauses consumer, computes index, updates snapshot, resumes consumer
#

set -euo pipefail

cd "$(dirname "$0")"

echo "🔄 Index-Berechnung Workflow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Find and stop consumer
echo "1️⃣  Consumer pausieren..."
CONSUMER_PID=$(ps aux | grep "open-sea-consume" | grep -v grep | awk '{print $2}' | head -1 || echo "")

if [[ -n "$CONSUMER_PID" ]]; then
    echo "   Stoppe Consumer (PID $CONSUMER_PID)..."
    kill -15 "$CONSUMER_PID" 2>/dev/null || true
    sleep 3
    # Force kill if still running
    if ps -p "$CONSUMER_PID" > /dev/null 2>&1; then
        kill -9 "$CONSUMER_PID" 2>/dev/null || true
        sleep 1
    fi
    echo "   ✅ Consumer gestoppt"
else
    echo "   ℹ️  Consumer läuft nicht"
fi

echo ""

# Step 2: Compute index
echo "2️⃣  Index berechnen..."
source .venv/bin/activate

# Compute for the last 7 days
START_DATE=$(date -v-7d '+%Y-%m-%d' 2>/dev/null || date -d '7 days ago' '+%Y-%m-%d')
END_DATE=$(date '+%Y-%m-%d')

echo "   Zeitraum: $START_DATE bis $END_DATE"
echo ""

python -m spvx.cli compute-index --version=1.5 --start-date="$START_DATE" --end-date="$END_DATE"

if [[ $? -eq 0 ]]; then
    echo "   ✅ Index erfolgreich berechnet"
else
    echo "   ⚠️  Index-Berechnung hatte Fehler (wird trotzdem fortgesetzt)"
fi

echo ""

# Step 3: Update snapshot
echo "3️⃣  API-Snapshot aktualisieren..."
./UPDATE_API_SNAPSHOT.sh

echo ""

# Step 4: Restart consumer
echo "4️⃣  Consumer neu starten..."
python -m spvx.cli open-sea-consume --polygons data/geo/polygons.geojson --gates data/geo/gates.geojson --config-path config.yml > logs/consumer.log 2>&1 &
NEW_PID=$!
echo "   ✅ Consumer gestartet (PID $NEW_PID)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Fertig! Index wurde berechnet und Snapshot aktualisiert."
echo "   Dashboard sollte jetzt Hero-KPI mit 4 Tiles zeigen!"
echo ""
