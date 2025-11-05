# 🚨 AIS Data Collection - KRITISCHES PROBLEM

**Date**: 2025-10-29 08:50 CET
**Status**: 🔴 **CRITICAL** - NO AIS DATA BEING COLLECTED

---

## Das Problem

### ❌ System sammelt KEINE echten AIS-Daten

**Was fehlt**:
- ❌ Keine `gate_crossings` Tabelle (Gate Flux Messungen)
- ❌ Keine `polygon_events` Tabelle (Anchorage Queue Metrics)
- ❌ Keine `ais_positions` Tabelle (Vessel Movement Analytics)
- ❌ Kein SIS (Sea Impact Score) Berechnungen

**Impact**:
- Kein Echtzeit-Tracking von Vessel-Bewegungen durch Hormuz, Suez, Panama
- Keine Anchorage Congestion Metrics (Dwell Times, Queue Länge)
- Keine Gate Flux Analysen für Business-kritische Chokepoints
- API liefert nur alte Port-Daten (MPA Singapore, Rotterdam, Turkish Straits)

---

## Root Cause Analysis

### Consumer Problem

**Symptom**: Consumer lädt Config, aber etabliert keine AIS-Verbindung

**Log Output**:
```
Loading open-sea configuration...
Loading open-sea configuration completed in 0.01s
[DANN NICHTS MEHR]
```

**Erwartetes Verhalten**:
```
Loading open-sea configuration... ✅
Loading geometries... ✅
Loaded 10 gates, 2 polygons ✅
Connecting to AIS stream... ✅
Connected to wss://stream.aisstream.io/v0/stream ✅
Subscribing to bounding boxes... ✅
Received first AIS message... ✅
```

**Mögliche Ursachen**:
1. **GeoJSON Validierungsfehler** - Consumer hängt beim Laden der Geometrien
2. **Fehlende .env Datei** - AISSTREAM_API_KEY nicht gefunden
3. **Netzwerk/Firewall** - Kann AIS stream nicht erreichen
4. **DuckDB Lock** - Database ist gelockt und blockiert Consumer
5. **Silent Crash** - Consumer startet aber crasht sofort ohne Error-Log

---

## Aktuelle Situation

### Consumer Status
- **PID 3321**: Läuft seit 2+ Minuten, aber keine Aktivität
- **CPU**: 0% (sollte 5-10% sein wenn AIS-Daten empfangen werden)
- **Logs**: Nur "Loading configuration" - keine weiteren Messages
- **Database**: Gelockt von Consumer, aber keine Tabellen erstellt

### Database Status
- **Größe**: 1.3 MB
- **Tabellen**: 4 (nur alte Port-Daten)
- **AIS Tables**: Keine vorhanden
- **Letztes Update**: 2025-10-12 (17 Tage alt!)

### GeoJSON Files
- **Suez gates**: ✅ Existiert (10 gates)
- **Suez polygons**: ✅ Existiert (2 anchorages)
- **Struktur**: ⚠️  Möglicherweise falsche 'id' Property-Struktur

---

## Lösungsversuche

### Versuch 1: Suez Consumer starten ⏳
```bash
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/suez/gates.geojson \
  --polygons data/geo/suez/polygons.geojson
```
**Ergebnis**: Consumer läuft, aber keine AIS-Verbindung

### Versuch 2: GeoJSON Struktur prüfen ⏳
Prüfe ob 'id' property korrekt in 'properties' object ist (nicht an root)

### Versuch 3: .env Datei prüfen ⏳
Fehlende .env Datei könnte AISSTREAM_API_KEY nicht laden

---

## Nächste Debug-Schritte

### 1. Prüfe .env Datei
```bash
cat .env | grep AISSTREAM_API_KEY
# Sollte zeigen: AISSTREAM_API_KEY=94a1eaf...
```

### 2. Teste GeoJSON Validierung manuell
```python
from spvx.open_sea.geo import load_gates, load_polygons
from pathlib import Path

gates = load_gates(Path('data/geo/suez/gates.geojson'))
polygons = load_polygons(Path('data/geo/suez/polygons.geojson'))
print(f"✅ Loaded {len(gates)} gates, {len(polygons)} polygons")
```

### 3. Teste AIS-Verbindung manuell
```python
import websocket
import json

api_key = "YOUR_KEY_HERE"
ws = websocket.create_connection("wss://stream.aisstream.io/v0/stream")
ws.send(json.dumps({"APIKey": api_key}))
print(ws.recv())  # Should get {"StatusCode":200}
```

### 4. Run Consumer im Foreground (nicht background)
```bash
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/suez/gates.geojson \
  --polygons data/geo/suez/polygons.geojson
# Sehe ALLE Errors direkt
```

---

## Business Impact

### Ohne echte AIS-Daten:

**Tier 1 Chokepoints - Nicht überwacht**:
- ❌ Hormuz (20-25% global oil) - BLIND
- ❌ Suez (Asia-Europe route) - BLIND
- ❌ Malacca (Asia oil supply) - BLIND
- ❌ Panama (Americas route) - BLIND
- ❌ Bab el-Mandeb (Suez south) - BLIND

**Tier 1 Hubs - Keine Queue Metrics**:
- ❌ Rotterdam - No dwell time data
- ❌ Singapore - No congestion metrics
- ❌ Houston - No queue lengths
- ❌ Fujairah - No bunkering activity

**Analytics - Nicht funktionsfähig**:
- ❌ Gate Flux Analysen
- ❌ Anomaly Detection
- ❌ Traffic Predictions
- ❌ SIS Berechnung
- ❌ Congestion Alerts

---

## Dringlichkeit

**KRITISCH**: Das System ist aktuell **komplett blind** für Echtzeit-Vessel-Traffic.

**Timeline**:
- Consumer muss **JETZT** funktionieren
- Erste Daten nach 5-30 Minuten
- Meaningful Volumen nach 24 Stunden

**Blocker**: Consumer lädt Config aber etabliert keine AIS-Verbindung
