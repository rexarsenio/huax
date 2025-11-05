# 🌙 Overnight Data Collection - Anleitung

## 📋 Was läuft bereits

**Überprüfen:**
```bash
cd /Users/alongo/Desktop/huax/spvx-lite

# Check welche Prozesse laufen
ps aux | grep -E "(consumer|uvicorn)" | grep -v grep
```

**Sollte zeigen:**
- ✅ AIS Consumer (python -m spvx.cli ingest-ais)
- ✅ API Server (uvicorn spvx.api_app)

## 🚀 Overnight Collection starten

### Option 1: Voller 12-Stunden Run (empfohlen)

Läuft **6 Iterationen** alle 2 Stunden (insgesamt 12 Stunden):

```bash
cd /Users/alongo/Desktop/huax/spvx-lite
chmod +x OVERNIGHT_COLLECTION.sh
nohup ./OVERNIGHT_COLLECTION.sh > logs/overnight_console.log 2>&1 &
```

**Was passiert:**
- Alle 2 Stunden:
  - 🔄 Generiert neue Tracklets aus polygon_events
  - 🌊 Verknüpft Tracklets mit CMEMS Wetter-Daten
  - 📊 Berechnet SIS Scores
  - 📋 Aktualisiert API Snapshot
  - 📈 Zeigt aktuelle Statistiken

**Log verfolgen:**
```bash
tail -f logs/overnight/overnight_*.log
```

**Status checken:**
```bash
ps aux | grep OVERNIGHT_COLLECTION
```

### Option 2: Einzelne Iteration (Test)

Falls du nur eine Iteration testen willst:

```bash
cd /Users/alongo/Desktop/huax/spvx-lite

# 1. Tracklets generieren
python generate_tracklets_from_events.py

# 2. CMEMS Join
python join_tracklets_cmems_fast.py

# 3. SIS berechnen
python -m spvx.cli sea-state-join

# 4. API Snapshot aktualisieren
./UPDATE_API_SNAPSHOT.sh
```

## 📊 Monitoring während der Nacht

### Live-Statistiken anschauen

```bash
cd /Users/alongo/Desktop/huax/spvx-lite

# Zeige aktuelle Zahlen
python << 'EOF'
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)

print("=== CURRENT STATS ===")
fixes = con.execute("SELECT COUNT(*) FROM open_sea_fixes").fetchone()[0]
print(f"AIS Fixes:         {fixes:,}")

events = con.execute("SELECT COUNT(*) FROM polygon_events").fetchone()[0]
print(f"Polygon Events:    {events:,}")

tracklets = con.execute("SELECT COUNT(*) FROM tracklets WHERE tracklet_id < 1000000").fetchone()[0]
print(f"Tracklets (real):  {tracklets:,}")

samples = con.execute("SELECT COUNT(*) FROM sea_state_samples").fetchone()[0]
print(f"Sea State Samples: {samples:,}")

sis = con.execute("SELECT COUNT(*) FROM sea_state_daily").fetchone()[0]
print(f"SIS Daily Records: {sis:,}")

con.close()
EOF
```

### Log in Echtzeit anschauen

```bash
tail -f logs/overnight/overnight_*.log
```

### Prozess stoppen (falls nötig)

```bash
# Find PID
ps aux | grep OVERNIGHT_COLLECTION | grep -v grep

# Kill it
kill <PID>

# Oder force kill
pkill -f OVERNIGHT_COLLECTION
```

## 📈 Erwartete Ergebnisse

Nach einer Nacht (12 Stunden):

**Tracklets:**
- Start: ~920
- Erwartet: 1500-2500 (je nach Schiffsverkehr)

**Sea State Samples:**
- Start: ~237
- Erwartet: 500-1000

**SIS Records:**
- Start: 3 corridor-days
- Erwartet: 5-10 corridor-days (verschiedene Tage/Korridore)

## 🔧 Troubleshooting

### Consumer nicht läuft?

```bash
cd /Users/alongo/Desktop/huax/spvx-lite
./start_consumer.sh
```

### API nicht läuft?

```bash
cd /Users/alongo/Desktop/huax/spvx-lite
source .venv/bin/activate
uvicorn spvx.api_app:app --host 0.0.0.0 --port 8000 --reload &
```

### Disk Space checken

```bash
df -h .
du -sh db/
```

### Database Lock Error?

Falls "database is locked" erscheint:
```bash
# Consumer kurz stoppen
./stop_consumer.sh

# Script nochmal starten
./OVERNIGHT_COLLECTION.sh

# Consumer wieder starten
./start_consumer.sh
```

## ✅ Am Morgen checken

```bash
cd /Users/alongo/Desktop/huax/spvx-lite

# 1. Check ob Script durchgelaufen ist
cat logs/overnight/overnight_*.log | grep "COMPLETED"

# 2. Check finale Statistiken
cat logs/overnight/overnight_*.log | tail -50

# 3. Check aktuelle Daten
python << 'EOF'
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)

print("=== MORNING STATS ===")
print(f"AIS Fixes:         {con.execute('SELECT COUNT(*) FROM open_sea_fixes').fetchone()[0]:,}")
print(f"Polygon Events:    {con.execute('SELECT COUNT(*) FROM polygon_events').fetchone()[0]:,}")
print(f"Tracklets:         {con.execute('SELECT COUNT(*) FROM tracklets WHERE tracklet_id < 1000000').fetchone()[0]:,}")
print(f"Sea State Samples: {con.execute('SELECT COUNT(*) FROM sea_state_samples').fetchone()[0]:,}")

print("\n=== SIS SCORES (Latest) ===")
sis = con.execute("""
    SELECT ds, corridor_id, sis_mean, sis_p90, n_samples
    FROM sea_state_daily
    ORDER BY ds DESC, corridor_id
    LIMIT 10
""").fetchall()

for row in sis:
    print(f"{row[0]} {row[1]:35s} SIS: {row[2]:.3f} (p90: {row[3]:.3f}) - {row[4]} samples")

con.close()
EOF
```

## 🎯 Finale Checks

Nach erfolgreichem Overnight Run:

```bash
# Test API Endpoint
curl -s 'http://localhost:8000/api/open_sea/sis?corridor=CHOKEPOINT_MALACCA->UNK&window=d7' | python -m json.tool

# Check alle Logs
ls -lth logs/overnight/
```

---

**Ready to start!** 🚀

Einfach ausführen:
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
chmod +x OVERNIGHT_COLLECTION.sh
nohup ./OVERNIGHT_COLLECTION.sh > logs/overnight_console.log 2>&1 &
echo "Started! Check: tail -f logs/overnight/overnight_*.log"
```
