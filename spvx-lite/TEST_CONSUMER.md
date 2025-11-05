# Consumer Test-Kommandos ✅

## Schnelltest (alle 2-5 Minuten ausführen)

```bash
cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate

# Alles-in-einem Test
echo "=== Consumer Status ===" && \
ps aux | grep "[r]un_consumer_debug" && \
echo -e "\n=== Messages (sollte steigen!) ===" && \
curl -s http://localhost:9110/metrics | grep "open_sea_fixes_total" && \
echo -e "\n=== Data Gap (sollte < 0.8 sein) ===" && \
curl -s http://localhost:9110/metrics | grep "open_sea_data_gap_ratio"
```

**Erwartetes Ergebnis:**
```
=== Consumer Status ===
alongo  64381  ...  Python -u run_consumer_debug.py

=== Messages (sollte steigen!) ===
open_sea_fixes_total{source="aisstream"} 250.0  ← Steigt jede Minute!

=== Data Gap (sollte < 0.8 sein) ===
open_sea_data_gap_ratio 0.7  ← Unter 0.8 = gut!
```

---

## Detaillierte Tests

### 1. Prozess-Status

```bash
# Consumer läuft?
ps aux | grep run_consumer_debug | grep -v grep

# Sollte zeigen:
# alongo  xxxxx  ...  Python -u run_consumer_debug.py
```

### 2. Live-Logs ansehen

```bash
# Letzte 20 Zeilen
tail -20 /tmp/consumer_simple.log

# Live verfolgen (Ctrl+C zum Beenden)
tail -f /tmp/consumer_simple.log
```

**Erwartung:** Nur Start-Messages, KEINE Errors/Exceptions

### 3. Alle Metriken

```bash
curl -s http://localhost:9110/metrics | grep "^open_sea"
```

**Wichtige Metriken:**
```
open_sea_consumer_running 1.0              ← Muss 1.0 sein
open_sea_fixes_total{source="aisstream"} 250.0  ← Steigt (~40-80/min)
open_sea_data_gap_ratio 0.7                ← Sollte 0.6-0.8 sein
```

### 4. Datenbank prüfen (nach 10+ Minuten)

```bash
# WICHTIG: Consumer muss gestoppt werden!
pkill -9 -f run_consumer_debug
sleep 2

# Datenbank ansehen
python -c "
import duckdb
con = duckdb.connect('db/spvx.duckdb', read_only=True)

print('=== TABELLEN ===')
tables = con.sql('SHOW TABLES').fetchall()
for t in tables:
    print(f'  {t[0]}')

print('\n=== AIS POSITIONS ===')
count = con.sql('SELECT COUNT(*) FROM open_sea_fixes').fetchone()[0]
print(f'  {count} Positionen')

print('\n=== POLYGON EVENTS ===')
count = con.sql('SELECT COUNT(*) FROM polygon_events').fetchone()[0]
print(f'  {count} Events')

print('\n=== GATE CROSSINGS ===')
count = con.sql('SELECT COUNT(*) FROM gate_crossings').fetchone()[0]
print(f'  {count} Crossings')

print('\n=== Sample Data ===')
sample = con.sql('SELECT mmsi, ts, lat, lon FROM open_sea_fixes LIMIT 3').fetchall()
for row in sample:
    print(f'  MMSI {row[0]}: {row[1]} at ({row[2]:.4f}, {row[3]:.4f})')
"

# Consumer wieder starten!
python -u run_consumer_debug.py > /tmp/consumer_simple.log 2>&1 &
echo "Consumer neu gestartet!"
```

---

## Problem-Diagnose

### Consumer crashed?

```bash
# Letzte Fehler ansehen
tail -50 /tmp/consumer_simple.log | grep -A 10 "ERROR\|Exception"

# Consumer neu starten
cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate
python -u run_consumer_debug.py > /tmp/consumer_simple.log 2>&1 &
```

### Keine Daten (fixes_total steigt nicht)?

```bash
# AIS Stream erreichbar?
curl -I https://stream.aisstream.io/v0/stream

# API Key gesetzt?
grep AISSTREAM_API_KEY .env

# Anzahl Gates/Polygons prüfen
python -c "
import json
gates = json.load(open('data/geo/gates.geojson'))
polygons = json.load(open('data/geo/polygons.geojson'))
print(f'Gates: {len(gates[\"features\"])}')
print(f'Polygons: {len(polygons[\"features\"])}')
"
# Sollte sein: Gates: 42, Polygons: 8
```

---

## Erwartete Performance

**Nach 1 Minute:** 40-80 Fixes
**Nach 5 Minuten:** 200-400 Fixes
**Nach 10 Minuten:** 400-800 Fixes
**Nach 1 Stunde:** 2400-4800 Fixes

**Data Gap Ratio:** 0.6-0.8 (normal)
**Wenn > 0.9:** Zu wenig Daten, prüfen!

---

## Consumer 24/7 laufen lassen

Der Consumer sollte permanent laufen um Daten zu sammeln:

```bash
# Status prüfen (alle paar Stunden)
ps aux | grep run_consumer_debug | grep -v grep

# Falls abgestürzt - neu starten:
cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate
python -u run_consumer_debug.py > /tmp/consumer_simple.log 2>&1 &
```

**Tipp:** Nach 1-2 Stunden hast du genug Daten für:
- Gate Crossings (Hormuz, Suez, Panama, etc.)
- Anchorage Occupancy
- API Dashboard mit echten Daten

---

## ✅ Alles läuft wenn:

- `ps` zeigt Consumer-Prozess ✓
- `open_sea_fixes_total` steigt jede Minute ✓
- `open_sea_data_gap_ratio` unter 0.8 ✓
- Keine Errors in Logs ✓
