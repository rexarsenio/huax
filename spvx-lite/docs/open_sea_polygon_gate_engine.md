# Open-Sea Polygon/Gate Engine - Setup & Betrieb

## Überblick

Der Open-Sea Consumer überwacht AIS-Verkehr in definierten geografischen Bereichen (Polygonen) und misst Gate-Crossings. Er subscribed auf AISStream.io und verarbeitet nur **Tanker** (ShipType 80-89).

## Architektur

```
AISStream.io (WebSocket)
    ↓
Consumer (open-sea-consume)
    ↓
Engine (Polygon/Gate Detection)
    ↓
DuckDB (open_sea_fixes, polygon_events, tracklets, gate_crossings)
    ↓
Metrics (Prometheus :9110)
```

## Wichtige Dateien

- **start_consumer.sh** - Startet den Consumer mit korrektem Environment
- **stop_consumer.sh** - Stoppt den Consumer gracefully
- **data/geo/polygons.geojson** - Definiert Polygone (Chokepoints, Anchorages, Ports)
- **data/geo/gates.geojson** - Definiert Gates (virtuelle Linien zum Messen von Crossings)
- **.env** - Enthält AISSTREAM_API_KEY und andere Credentials

## Setup

### 1. Environment vorbereiten

Stelle sicher, dass `.env` existiert und `AISSTREAM_API_KEY` gesetzt ist:

```bash
cat .env | grep AISSTREAM_API_KEY
```

### 2. DuckDB Schema prüfen

Die Tabelle `tanker_presence` muss einen Primary Key haben:

```sql
-- Sollte PRIMARY KEY (mmsi, polygon_id) zeigen
PRAGMA table_info('tanker_presence');
```

Falls nicht, führe aus:

```sql
DROP TABLE IF EXISTS tanker_presence_backup;
CREATE TABLE tanker_presence_backup AS SELECT * FROM tanker_presence;

DROP TABLE tanker_presence;
CREATE TABLE tanker_presence (
  mmsi BIGINT NOT NULL,
  polygon_id VARCHAR NOT NULL,
  enter_ts TIMESTAMP,
  exit_ts TIMESTAMP,
  last_seen_ts TIMESTAMP,
  inside BOOLEAN,
  samples_inside INTEGER,
  sog_min DOUBLE,
  sog_max DOUBLE,
  sog_avg DOUBLE,
  PRIMARY KEY (mmsi, polygon_id)
);

INSERT INTO tanker_presence SELECT * FROM tanker_presence_backup;
DROP TABLE tanker_presence_backup;
```

### 3. Consumer starten

```bash
./start_consumer.sh
```

Das Script:
- Lädt `.env` automatisch
- Prüft auf DuckDB-Locks
- Stoppt konkurrierende Prozesse
- Startet den Consumer im Hintergrund
- Zeigt initiale Logs

### 4. Monitoring

**Logs verfolgen:**
```bash
tail -f logs/open_sea_consumer.log
```

**Prometheus Metrics:**
```bash
curl http://localhost:9110/metrics | grep open_sea
```

**Wichtige Metrics:**
- `open_sea_consumer_running` - Liveness (sollte 1.0 sein)
- `open_sea_fixes_total` - Anzahl verarbeiteter AIS-Fixes
- `open_sea_tanker_occupancy_now{polygon="..."}` - Aktuelle Tanker-Anzahl pro Polygon
- `open_sea_gate_crossings_total{gate="...",direction="..."}` - Gate-Crossings

**DuckDB-Daten prüfen:**
```bash
# Consumer stoppen (DuckDB ist exklusiv gelockt während Consumer läuft)
./stop_consumer.sh

# Daten abfragen
duckdb db/spvx.duckdb -c "
SELECT 
  COUNT(*) as total_fixes,
  COUNT(DISTINCT mmsi) as unique_tankers,
  MIN(ts) as earliest,
  MAX(ts) as latest
FROM open_sea_fixes
WHERE is_tanker = true;
"

# Polygon Events
duckdb db/spvx.duckdb -c "
SELECT polygon_id, event, COUNT(*) as count
FROM polygon_events
GROUP BY polygon_id, event
ORDER BY count DESC;
"

# Gate Crossings
duckdb db/spvx.duckdb -c "
SELECT gate_id, direction, COUNT(*) as crossings
FROM gate_crossings
GROUP BY gate_id, direction
ORDER BY crossings DESC;
"
```

### 5. Consumer stoppen

```bash
./stop_consumer.sh
```

## Troubleshooting

### Problem: "IOException: Could not set lock on file"

**Ursache:** Ein anderer Prozess (z.B. `serve`, `uvicorn`) hat DuckDB gelockt.

**Lösung:**
```bash
# Finde den Prozess
lsof db/spvx.duckdb

# Stoppe ihn
pkill -f "spvx.cli serve"
pkill -f "uvicorn spvx.api_app"
```

### Problem: Consumer startet nicht - "AISSTREAM_API_KEY not provided"

**Ursache:** `.env` wird nicht geladen oder API-Key fehlt.

**Lösung:**
```bash
# Prüfen
cat .env | grep AISSTREAM_API_KEY

# Falls leer, setzen
echo "AISSTREAM_API_KEY=your_key_here" >> .env
```

### Problem: Metrics zeigen Fixes, aber DuckDB bleibt leer

**Ursache 1:** Tanker-Filter ist aktiv – nur ShipType 80-89 werden geschrieben.

**Lösung:** Warte auf Tanker-Traffic oder deaktiviere temporär den Filter in `src/spvx/open_sea/engine.py:210-211`.

**Ursache 2:** Polygone/Gates liegen außerhalb der tatsächlichen AIS-Traffic-Bereiche.

**Lösung:** Prüfe Bounding Boxes in Logs und passe `data/geo/polygons.geojson` an.

### Problem: Keine Gate-Crossings trotz Traffic

**Ursache:** Gates sind zu schmal (`width_nm`) oder falsch positioniert.

**Lösung:** Erhöhe `width_nm` in `data/geo/gates.geojson` oder verschiebe Gates.

## Konfiguration

### Polygone hinzufügen

Editiere `data/geo/polygons.geojson`:

```json
{
  "type": "Feature",
  "properties": {
    "id": "MY_NEW_POLYGON",
    "kind": "CHOKEPOINT",  // oder "ANCHORAGE", "PORT"
    "buffer_m": 500,
    "notes": "Description"
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [lon1, lat1], [lon2, lat2], [lon3, lat3], [lon4, lat4], [lon1, lat1]
    ]]
  }
}
```

**Wichtig:**
- `kind`: Beeinflusst TTL (Anchorages haben längere TTL)
- `buffer_m`: Buffer um Polygon-Kanten (für Hysteresis)

### Gates hinzufügen

Editiere `data/geo/gates.geojson`:

```json
{
  "type": "Feature",
  "properties": {
    "id": "MY_NEW_GATE",
    "width_nm": 1.0,  // Breite des Gates in Nautischen Meilen
    "dir_hint": "BIDIR",  // oder "EASTBOUND", "WESTBOUND", etc.
    "notes": "Description"
  },
  "geometry": {
    "type": "LineString",
    "coordinates": [[lon1, lat1], [lon2, lat2]]
  }
}
```

**Wichtig:**
- `width_nm`: Buffer um die LineString (z.B. 1.0 = 1 NM Radius)
- Gates sollten quer zur Verkehrsrichtung liegen

### Config.yml Anpassungen

```yaml
open_sea:
  downsample_secs: 60        # Max 1 fix / 60s / MMSI
  hysteresis_hits: 2         # Enter/Exit benötigt 2 konsekutive Hits
  ttl_min:
    moving: 30               # TTL für bewegende Schiffe
    anchorage: 90            # TTL in Anchorages
  sog_thresholds:
    dwell_max_kn: 1.0        # SOG-Schwelle für Dwell
  gates:
    width_nm_default: 0.8    # Default Gate-Breite
```

## Best Practices

1. **Immer `./stop_consumer.sh` verwenden** – Vermeidet DuckDB-Locks
2. **Polygone groß genug machen** – Besser zu groß als zu klein
3. **Gates breit genug** – Mindestens 0.5 NM, besser 1.0 NM
4. **Tanker-Traffic ist sporadisch** – Warte mindestens 10-15 Minuten für aussagekräftige Daten
5. **Monitor Metrics** – Zeigt Echtzeit-Status ohne DB-Access

## Datenfluss

1. **AIS-Message kommt rein** → `_handle_message()`
2. **Canonicalize** → Standardisiert Format
3. **Downsample** → Max 1 fix / 60s / MMSI
4. **Tanker-Filter** → Nur ShipType 80-89
5. **Polygon-Check** → Ist Schiff in einem Polygon?
   - Hysteresis: 2 konsekutive Hits für Enter/Exit
   - Presence-Record aktualisieren
6. **Gate-Check** → Hat Schiff ein Gate überquert?
   - Berechne Crossing-Richtung
   - Emit Gate-Crossing-Event
7. **Tracklet-Logik** → Baue Trajektorien zwischen Polygonen
8. **Write to DuckDB** → Batch-Insert aller Events

## Weiterführende Infos

- **Hysteresis:** Verhindert "Flapping" an Polygon-Grenzen
- **TTL (Time-to-Live):** Automatisches Exit nach X Minuten ohne Signal
- **Downsampling:** Reduziert Daten-Volumen, verhindert Duplikate
- **Gate Direction:** Berechnet via COG (Course Over Ground) und Gate-Normal

