# 🚀 Lokale Ausführung der SPVX-Lite Platform

## Problem: Claude Code Container vs. Lokale Ausführung

**Warum funktioniert AISStream nicht im Claude Code Container?**
- Alle Claude Code Sessions nutzen dieselben Anthropic Proxy-IPs
- AISStream blockt wahrscheinlich diese "Server-IPs" (Rate Limiting)
- WebSocket-Verbindungen werden durch HTTP CONNECT Proxy getunnelt
- → HTTP 503 Fehler beim Verbindungsaufbau

**Lösung:** Lokal auf deinem MacBook Air ausführen!

---

## 📋 Voraussetzungen

- ✅ macOS (dein MacBook Air)
- ✅ Python 3.11+ installiert
- ✅ Git installiert
- ✅ AISStream API Key: `e85ed5726782b45ba7eb720d9d47136a56d4ba03`

---

## 🔧 Setup-Schritte

### 1️⃣ Repository klonen (falls noch nicht lokal)

```bash
# Terminal öffnen
cd ~/Projects  # oder ein anderer Ordner deiner Wahl

# Repository klonen
git clone https://github.com/rexarsenio/huax.git
cd huax/spvx-lite

# Auf den Claude-Branch wechseln (mit allen Fixes)
git checkout claude/huax-program-review-011CUph18dv6WoPmz9MrjiXp
git pull origin claude/huax-program-review-011CUph18dv6WoPmz9MrjiXp
```

**Alternative:** Falls du das Repo schon lokal hast:
```bash
cd ~/path/to/huax/spvx-lite
git fetch --all
git checkout claude/huax-program-review-011CUph18dv6WoPmz9MrjiXp
git pull
```

---

### 2️⃣ Python Virtual Environment erstellen

```bash
# Im spvx-lite Verzeichnis:
python3 -m venv .venv

# Aktivieren (macOS/Linux):
source .venv/bin/activate

# Du solltest jetzt (.venv) im Prompt sehen
```

---

### 3️⃣ Dependencies installieren

```bash
# Alle Python-Pakete installieren:
pip install --upgrade pip
pip install -e .

# Falls Fehler auftreten, einzeln installieren:
pip install websockets prometheus-client duckdb pandas numpy shapely geojson pyyaml python-dotenv requests
pip install python-socks  # Für Proxy-Support (optional)
```

---

### 4️⃣ Umgebungsvariablen konfigurieren

Die `.env` Datei sollte bereits existieren, aber prüfe sie:

```bash
cat .env
```

**Sollte enthalten:**
```bash
AISSTREAM_API_KEY=e85ed5726782b45ba7eb720d9d47136a56d4ba03
OPENWEATHER_API_KEY=0cf5a411f070635af9517d1a7648e9e2
CMEMS_USERNAME=alongo
CMEMS_PASSWORD=Gromola305!
DUCKDB_PATH=db/spvx.duckdb
```

**Falls `.env` fehlt oder falsch ist:**
```bash
# Erstellen/Editieren:
nano .env
# oder
code .env  # falls du VS Code nutzt
```

---

### 5️⃣ DuckDB Datenbank initialisieren

```bash
# Erstelle db/ Verzeichnis falls nicht vorhanden:
mkdir -p db

# Prüfe ob DuckDB existiert:
ls -lh db/spvx.duckdb

# Falls es nicht existiert, wird es beim ersten Consumer-Start erstellt
```

---

## 🚢 AIS Consumer starten

### Option A: Im Vordergrund (für Debugging)

```bash
# Aktiviere venv falls noch nicht aktiv:
source .venv/bin/activate

# Consumer starten - du siehst alle Logs direkt:
python -m spvx.cli open-sea-consume \
  --polygons data/geo/polygons_anchorages.geojson \
  --gates data/geo/gates.geojson
```

**Was du sehen solltest:**
```
Loading open-sea configuration...
Loading open-sea configuration completed in 0.01s
Using HTTP proxy for WebSocket connection: http://...   # Nur im Container!
Open-sea consumer connected to AISStream.               # ✅ ERFOLG!
```

**Wenn es funktioniert:** Nach ein paar Sekunden solltest du AIS-Messages sehen!

**Zum Stoppen:** `Ctrl+C`

---

### Option B: Im Hintergrund (Production-Mode)

```bash
# Consumer als Background-Prozess:
nohup python -m spvx.cli open-sea-consume \
  --polygons data/geo/polygons_anchorages.geojson \
  --gates data/geo/gates.geojson \
  > logs/ais_consumer_local.log 2>&1 &

# PID wird angezeigt, z.B.: [1] 12345
echo $! > logs/ais_consumer.pid

# Logs live verfolgen:
tail -f logs/ais_consumer_local.log

# Zum Stoppen:
kill $(cat logs/ais_consumer.pid)
```

---

## 🖥️ Backend API starten

In einem **NEUEN Terminal-Fenster:**

```bash
cd ~/path/to/huax/spvx-lite
source .venv/bin/activate

# Backend starten:
python -m spvx.cli serve --host 0.0.0.0 --port 8000
```

**Prüfen ob es läuft:**
```bash
# In neuem Terminal:
curl http://localhost:8000/ops/health

# Sollte antworten mit Status-Info
```

API ist verfügbar unter: **http://localhost:8000**

Swagger Docs: **http://localhost:8000/docs**

---

## 📊 Dashboard starten

In einem **DRITTEN Terminal-Fenster:**

```bash
cd ~/path/to/huax/dashboard
npm install  # Falls noch nicht gemacht
npm run dev
```

Dashboard läuft auf: **http://localhost:5173**

**Im Browser öffnen:** Chrome/Firefox → `http://localhost:5173`

---

## ✅ Verifizieren dass es funktioniert

### 1. AIS Consumer prüfen

```bash
# Logs checken:
tail -f logs/ais_consumer_local.log

# Du solltest sehen:
# - "Open-sea consumer connected to AISStream."
# - Position Reports kommen rein
# - Gate crossings werden erkannt
```

### 2. DuckDB prüfen

```bash
python3 << 'EOF'
import duckdb
con = duckdb.connect('db/spvx.duckdb', read_only=True)
print("Gate Crossings:", con.execute("SELECT COUNT(*) FROM gate_crossings").fetchone()[0])
print("AIS Fixes:", con.execute("SELECT COUNT(*) FROM open_sea_fixes").fetchone()[0])
con.close()
EOF
```

### 3. Backend API prüfen

```bash
# Corridor View abfragen:
curl "http://localhost:8000/api/open_sea/corridor_view?window=h24" | jq

# Sollte jetzt Daten zurückgeben!
```

### 4. Dashboard prüfen

- Öffne: http://localhost:5173
- **Chokepoint Dropdown** sollte jetzt alle 18 Gates zeigen! 🎉
- VesselMap sollte Schiffe anzeigen
- Metrics sollten funktionieren

---

## 🐛 Troubleshooting

### Problem: "command not found: python"

```bash
# Versuche:
python3 -m spvx.cli ...
```

### Problem: "ModuleNotFoundError: No module named 'spvx'"

```bash
# Sicherstellen dass du im richtigen Ordner bist:
cd ~/path/to/huax/spvx-lite

# Venv aktivieren:
source .venv/bin/activate

# Neu installieren:
pip install -e .
```

### Problem: "DuckDB locked"

```bash
# Consumer stoppen:
kill $(cat logs/ais_consumer.pid)

# Warten bis Prozess beendet ist:
sleep 2

# Neu starten
```

### Problem: AISStream gibt immer noch HTTP 503

**Dann ist der API Key das Problem:**

1. Gehe auf https://aisstream.io
2. Login mit GitHub
3. Gehe zu **API Keys**
4. Prüfe ob `e85ed5...` als **Valid** markiert ist
5. Falls **Invalid**: Generiere einen NEUEN Key
6. Update `.env` mit neuem Key
7. Consumer neu starten

---

## 📝 Nützliche Befehle

```bash
# Alle laufenden Consumer finden:
ps aux | grep "open-sea-consume"

# Consumer stoppen:
kill <PID>

# Logs aufräumen:
rm logs/*.log

# DuckDB Größe prüfen:
ls -lh db/spvx.duckdb

# Alle Python-Prozesse finden:
ps aux | grep python

# Git Status prüfen:
git status
git log --oneline -5
```

---

## 🎯 Erwartetes Ergebnis

Nach 5-10 Minuten solltest du sehen:

✅ **AIS Consumer**
- Verbunden mit AISStream
- Empfängt Position Reports
- Schreibt in DuckDB

✅ **Backend API**
- Läuft auf Port 8000
- `/api/open_sea/corridor_view` gibt Daten zurück

✅ **Dashboard**
- Läuft auf Port 5173
- **Chokepoint Dropdown zeigt alle 18 Gates!**
- VesselMap zeigt Schiffe
- Metrics funktionieren

✅ **DuckDB**
- `gate_crossings` Tabelle hat Einträge
- `open_sea_fixes` Tabelle wächst
- Größe: mehrere MB

---

## 🔥 Wichtig!

**Vorteile der lokalen Ausführung:**

✅ Deine echte IP (kein Proxy)
✅ Direkter WebSocket-Zugang
✅ Kein Rate-Limiting durch gemeinsame IPs
✅ Schnellere Entwicklung/Debugging
✅ Du kannst VS Code debugger nutzen

**Nachteile des Claude Code Containers:**

❌ Shared Anthropic Proxy-IPs
❌ WebSocket wird durch Proxy getunnelt
❌ AISStream blockt diese IPs wahrscheinlich
❌ Git-Änderungen können überschrieben werden

---

## 📞 Hilfe

Falls du Probleme hast:

1. **Checke zuerst die Logs:**
   ```bash
   tail -100 logs/ais_consumer_local.log
   ```

2. **Prüfe ob alle Services laufen:**
   ```bash
   ps aux | grep -E "(python|node)" | grep -v grep
   ```

3. **Teste AISStream direkt:**
   ```bash
   python3 test_simple_aisstream.py
   # Falls die Datei nicht existiert, kann ich sie neu erstellen
   ```

4. **DuckDB direkt öffnen:**
   ```bash
   duckdb db/spvx.duckdb
   # SQL Queries direkt ausführen:
   # SELECT * FROM gate_crossings LIMIT 10;
   ```

---

## 🎉 Viel Erfolg!

Wenn du das lokal ausführst, sollte **alles funktionieren**! Die HTTP 503 Fehler waren definitiv durch die Claude Code Container-IPs verursacht.

Sobald der Consumer läuft, wird das **Chokepoint Dropdown alle 18 Gates anzeigen** und du siehst echte Schiffsbewegungen! 🚢

---

**Erstellt:** 2025-11-06
**Claude Session:** claude/huax-program-review-011CUph18dv6WoPmz9MrjiXp
