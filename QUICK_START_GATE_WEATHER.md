# 🚀 Quick Start - Gate Weather System testen

## Aktueller Status: System nicht gestartet

Das Gate Weather System ist installiert, aber noch nicht gestartet.
Hier ist wie du es testest:

---

## Option 1: 🔥 Minimaler Test (nur Gate Weather, ohne vollständiges System)

### Schritt 1: Datenbank erstellen und Daten sammeln

```bash
cd /home/user/huax/spvx-lite

# Datenbank-Verzeichnis erstellen
mkdir -p db

# Python-Abhängigkeiten prüfen/installieren (falls nicht vorhanden)
pip3 install duckdb xarray netCDF4 requests

# Erste Wetterdaten sammeln (dauert 2-5 Minuten)
python3 ingest_gate_weather.py
```

**Was passiert:**
- Sammelt Wetterdaten von NOAA für 11 Gates (Hormuz, Suez, Gibraltar, etc.)
- Erstellt automatisch die Tabelle `gate_weather_standalone`
- Zeigt Live-Output für jedes Gate

### Schritt 2: Daten in der Datenbank prüfen

```bash
python3 << 'EOF'
import duckdb
import os

db_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
con = duckdb.connect(db_path, read_only=True)

print("\n" + "="*60)
print("📊 GATE WEATHER DATABASE STATUS")
print("="*60)

# Count total records
total = con.execute("SELECT COUNT(*) FROM gate_weather_standalone").fetchone()[0]
print(f"\n✅ Total weather records: {total}")

# Show latest by gate
print("\n📍 Latest observations per gate:")
print("-"*60)
result = con.execute("""
    SELECT
        gate_id,
        gate_name,
        observed_at,
        ROUND(hs_m, 2) as wave_m,
        ROUND(speed_knots, 2) as current_kn
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY gate_id ORDER BY observed_at DESC) as rn
        FROM gate_weather_standalone
    )
    WHERE rn = 1
    ORDER BY gate_id
""").fetchall()

for row in result:
    print(f"  {row[0]:<30} | Waves: {row[3]:>5}m | Current: {row[4]:>5}kn | {row[2]}")

con.close()
print("\n" + "="*60)
EOF
```

---

## Option 2: 🌐 Vollständiges System (API + Dashboard)

Wenn du das System komplett testen willst:

### Schritt 1: Services starten

```bash
cd /home/user/huax

# 1. API Server starten (Backend)
cd spvx-lite
./START_API.sh > /tmp/api_server.log 2>&1 &
cd ..

# 2. Dashboard starten (Frontend)
cd dashboard
yarn dev > /tmp/dashboard.log 2>&1 &
cd ..

# Warte 10 Sekunden bis Services hochgefahren sind
sleep 10
```

### Schritt 2: Gate Weather Daten sammeln

```bash
cd spvx-lite
./COLLECT_GATE_WEATHER.sh
```

### Schritt 3: Im Browser öffnen

**Dashboard:**
```
http://localhost:5173/operations
```

Dort siehst du oben das **"Gate Weather Conditions"** Panel mit allen Wetterdaten!

**API Direktzugriff:**
```
http://localhost:8000/api/open_sea/gate_weather?window=h24
```

**API Dokumentation:**
```
http://localhost:8000/docs
```

### Schritt 4: Services stoppen

```bash
# API stoppen
pkill -f uvicorn

# Dashboard stoppen
pkill -f vite
```

---

## 🧪 Schnelltest per curl (wenn API läuft)

```bash
# Health Check
curl http://localhost:8000/health

# Gate Weather abrufen (alle Gates, 24h)
curl http://localhost:8000/api/open_sea/gate_weather?window=h24 | python3 -m json.tool

# Nur bestimmte Gates
curl "http://localhost:8000/api/open_sea/gate_weather?window=h24&gate_ids=GATE_HORMUZ,GATE_SUEZ_N" | python3 -m json.tool

# 7 Tage Fenster
curl http://localhost:8000/api/open_sea/gate_weather?window=d7 | python3 -m json.tool
```

---

## 📊 Was du sehen solltest:

### Im Dashboard (localhost:5173/operations):

```
╔══════════════════════════════════════════════╗
║  Gate Weather Conditions (24h)              ║
╠══════════════════════════════════════════════╣
║                                              ║
║  ┌─────────────────────────────────────┐   ║
║  │ Strait of Hormuz                    │   ║
║  │ GATE_HORMUZ • APAC                  │   ║
║  │                                      │   ║
║  │ 🌊 Waves          🌀 Currents       │   ║
║  │ 2.15 m            1.44 kn            │   ║
║  │ Period: 8.2s      U: 1.2 / V: 0.8   │   ║
║  │ Mean: 2.05m       Mean: 1.35kn      │   ║
║  │                                      │   ║
║  │ Based on 8 observations             │   ║
║  └─────────────────────────────────────┘   ║
║                                              ║
║  ┌─────────────────────────────────────┐   ║
║  │ Suez Canal North (Port Said)       │   ║
║  │ ...                                  │   ║
╚══════════════════════════════════════════════╝
```

### API Response:

```json
{
  "window": "h24",
  "start": "2025-11-04T12:00:00Z",
  "end": "2025-11-05T12:00:00Z",
  "gates": [
    {
      "gate_id": "GATE_HORMUZ",
      "gate_name": "Strait of Hormuz",
      "basin": "APAC",
      "latest_observation": {
        "observed_at": "2025-11-05T09:00:00",
        "waves": {
          "height_m": 2.15,
          "period_s": 8.2,
          "direction_deg": 245.0,
          "flag": 0,
          "severity": "normal"
        },
        "currents": {
          "u_knots": 1.2,
          "v_knots": 0.8,
          "speed_knots": 1.44,
          "flag": 0,
          "severity": "normal"
        }
      },
      "statistics": {
        "samples_count": 8,
        "waves": {
          "mean_height_m": 2.05,
          "max_height_m": 2.45,
          "p90_height_m": 2.38
        },
        "currents": {
          "mean_speed_kn": 1.35,
          "max_speed_kn": 1.82,
          "p90_speed_kn": 1.75
        }
      }
    }
  ]
}
```

---

## 🐛 Troubleshooting

### Problem: "No module named 'duckdb'"

```bash
pip3 install duckdb pandas xarray netCDF4 requests shapely pyproj
```

### Problem: "Could not resolve dataset" beim Sammeln

**Ursache:** NOAA Server manchmal offline oder langsam

**Lösung:** 30 Minuten warten und erneut versuchen

### Problem: API startet nicht

```bash
# Logs ansehen
tail -f /tmp/api_server.log

# Port prüfen
netstat -tlnp | grep 8000

# Manuell starten
cd spvx-lite
source .venv/bin/activate  # falls venv existiert
python3 -m uvicorn spvx.api_app:app --host 0.0.0.0 --port 8000
```

### Problem: Dashboard zeigt keine Daten

1. Prüfe ob API läuft: `curl http://localhost:8000/health`
2. Prüfe ob Daten gesammelt wurden (siehe Schritt 2 oben)
3. Browser Console öffnen (F12) und nach Errors suchen

---

## ✅ Erfolg!

Wenn du:
- ✅ Daten in der Datenbank siehst (via Python-Skript)
- ✅ API Response mit Gates erhältst (via curl)
- ✅ Dashboard das Weather Panel zeigt

Dann funktioniert alles! 🎉

---

## 📚 Weiterführende Infos

Siehe `GATE_WEATHER_README.md` für:
- Architektur-Details
- Cron-Job-Setup für automatische Updates
- Vollständige API-Dokumentation
- Erweiterte Konfiguration
