#!/bin/bash
echo "=== AIS Data Flow Test ==="
BEFORE=$(curl -s http://localhost:9110/metrics | grep "open_sea_fixes_total" | tail -1 | awk '{print $2}')
echo "Vor: $BEFORE fixes"
echo "Warte 30 Sekunden..."
sleep 30
AFTER=$(curl -s http://localhost:9110/metrics | grep "open_sea_fixes_total" | tail -1 | awk '{print $2}')
echo "Nach: $AFTER fixes"
DIFF=$(echo "$AFTER - $BEFORE" | bc)
echo "Neue Daten: $DIFF fixes in 30s"
if (( $(echo "$DIFF > 0" | bc -l) )); then
    echo "✅ AIS Datenfluss aktiv!"
else
    echo "❌ Keine neuen AIS Daten"
fi
