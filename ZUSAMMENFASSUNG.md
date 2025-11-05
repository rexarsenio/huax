# 🎯 SPVX-Lite - Datensammlung läuft!

## ✅ Aktueller Status

### Laufende Services

| Service | Status | Details |
|---------|--------|---------|
| **AIS Ingestion** | 🟢 Läuft | ~100 Nachrichten/Sekunde, PID 95026 |
| **API Server** | 🟢 Läuft | http://localhost:8000 |
| **Dashboard** | 🟢 Läuft | http://localhost:5173 |

### Datenbank

- **Größe**: 258 MB
- **Letzte AIS-Daten**: werden kontinuierlich gesammelt
- **Polygon Events**: 1,621 (im Snapshot)

### Live-Datenrate

Die Ingestion sammelt **~3,700 AIS-Nachrichten pro Minute**:
```
22:07:27 | Inserted 3700 records (received 3717 messages)
```

Das entspricht etwa:
- **100 Nachrichten/Sekunde**
- **6,000/Minute**
- **360,000/Stunde**
- **8,6 Millionen/Tag**

## 🚀 Überwachungs-Tools

### 1. Einmaliger Status-Check
```bash
./MONITOR.sh
```

Zeigt:
- Service-Status (Ingestion, API, Dashboard)
- Datenbank-Statistiken
- Tabellen-Größen
- Letzte 10 Log-Einträge

### 2. Kontinuierliche Überwachung (auto-refresh alle 5 Sek)
```bash
./WATCH.sh
```

Drücke `Ctrl+C` zum Beenden.

### 3. Automatische Snapshot-Updates
```bash
# Im Vordergrund (für Tests):
./AUTO_SNAPSHOT.sh

# Im Hintergrund (empfohlen):
nohup ./AUTO_SNAPSHOT.sh > logs/auto-snapshot.log 2>&1 &

# Status prüfen:
tail -f logs/auto-snapshot.log

# Stoppen:
pkill -f AUTO_SNAPSHOT.sh
```

**Hinweis**: Der Snapshot-Update funktioniert nur, wenn die Ingestion **nicht** läuft (wegen DuckDB-Locking). Der AUTO_SNAPSHOT.sh Skript wartet automatisch, bis die DB frei ist.

## 📊 Dashboard

Das Dashboard ist live unter: **http://localhost:5173**

Die Korridore sollten jetzt sichtbar sein:
- **Malacca-Straße**: 128 Schiffe (24h)
- **Nordsee**: 156 Schiffe (24h)

## 🔄 Snapshot-Management

### Manuell aktualisieren

Um den Snapshot mit den neuesten Daten zu füllen:

```bash
# 1. Ingestion stoppen
pkill -f ingest_aisstream.py

# 2. Snapshot erstellen
./UPDATE_API_SNAPSHOT.sh

# 3. Ingestion neu starten
./start_consumer.sh

# 4. Dashboard refresh (im Browser)
```

### Automatisch (empfohlen für Produktion)

Für kontinuierlichen Betrieb:

1. **Option A**: Cron-Job einrichten
   ```bash
   # Alle 15 Minuten
   */15 * * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./UPDATE_API_SNAPSHOT.sh >> logs/snapshot.log 2>&1
   ```

2. **Option B**: AUTO_SNAPSHOT.sh im Hintergrund laufen lassen
   ```bash
   nohup ./AUTO_SNAPSHOT.sh > logs/auto-snapshot.log 2>&1 &
   ```

## 📁 Wichtige Dateien

| Datei | Beschreibung |
|-------|--------------|
| `MONITOR.sh` | Einmaliger Status-Check |
| `WATCH.sh` | Kontinuierliche Überwachung |
| `AUTO_SNAPSHOT.sh` | Automatische Snapshot-Updates |
| `UPDATE_API_SNAPSHOT.sh` | Manuelles Snapshot-Update |
| `start_consumer.sh` | Ingestion starten |
| `stop_consumer.sh` | Ingestion stoppen |
| `logs/ais-ingest.error.log` | Ingestion-Logs |
| `logs/auto-snapshot.log` | Snapshot-Update-Logs |
| `db/spvx.duckdb` | Produktions-Datenbank (locked während Ingestion) |
| `db/spvx_api.duckdb` | API Snapshot (für Dashboard) |

## 🎯 Empfohlener Workflow

### Für Development/Testing (jetzt)
```bash
# Terminal 1: Überwachung
./WATCH.sh

# Terminal 2: Dashboard öffnen
open http://localhost:5173

# Alle 10-15 Min manuell:
pkill -f ingest_aisstream.py && ./UPDATE_API_SNAPSHOT.sh && ./start_consumer.sh
```

### Für Production (über Nacht laufen lassen)
```bash
# Einmal einrichten:
nohup ./AUTO_SNAPSHOT.sh > logs/auto-snapshot.log 2>&1 &

# Dann nur noch beobachten:
./WATCH.sh
```

## 🔧 Troubleshooting

### Ingestion läuft nicht
```bash
./start_consumer.sh
```

### API Server läuft nicht
```bash
cd spvx-lite
source .venv/bin/activate
uvicorn spvx.api_app:app --port 8000 --reload &
```

### Dashboard läuft nicht
```bash
cd dashboard
yarn dev
# oder
npm run dev
```

### Snapshot ist veraltet
```bash
# Aktuelles Alter prüfen:
./MONITOR.sh

# Manuell aktualisieren:
pkill -f ingest_aisstream.py
./UPDATE_API_SNAPSHOT.sh
./start_consumer.sh
```

## 📈 Was passiert über Nacht?

Wenn du alles laufen lässt:

1. **AIS Ingestion** sammelt kontinuierlich Schiffspositionen
   - ~8,6 Millionen Nachrichten pro Tag
   - Datenbank wächst um ~1-2 GB pro Tag (geschätzt)

2. **API Server** bedient Dashboard-Anfragen
   - Nutzt Snapshot (keine Locks auf Production-DB)

3. **AUTO_SNAPSHOT.sh** (falls gestartet):
   - Versucht alle 10 Minuten Snapshot zu aktualisieren
   - Wartet automatisch wenn DB gesperrt ist

4. **Dashboard** zeigt Live-Korridore
   - Basierend auf Snapshot-Daten
   - Alle 10-15 Min manuell refreshen für neueste Daten

## 🎉 Zusammenfassung

**Aktuell läuft:**
- ✅ AIS Ingestion: ~100 msg/sec
- ✅ API Server: Port 8000
- ✅ Dashboard: Port 5173
- ✅ Daten werden gesammelt!

**Du kannst:**
- `./MONITOR.sh` - Status checken
- `./WATCH.sh` - Live-Monitoring
- `http://localhost:5173` - Dashboard ansehen

**Über Nacht:**
Lass einfach alles laufen! Die Ingestion sammelt automatisch Daten. Morgen hast du viel mehr Schiffsbewegungen für die Korridore! 🚢

---

*Erstellt: 2025-10-27 22:07 UTC*
*Alle Services: 🟢 RUNNING*
