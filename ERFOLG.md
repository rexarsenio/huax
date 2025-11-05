# ✅ Corridor View - ERFOLGREICH IMPLEMENTIERT!

## 🎉 Status: LIVE mit echten Daten!

Der `/api/open_sea/corridor_view` Endpoint läuft jetzt mit echten Registry-Daten!

### Live-Daten (letzte 24 Stunden):

```json
{
  "corridor_id": "NORTH_SEA",
  "flux_h": 156.0,
  "flux_z": 1.0,
  "delay_ratio": 1.3,
  "sis_p90": 0.85,
  "geometry": {"type": "LineString", "coordinates": [[4.0, 51.9], [3.0, 53.0], [2.0, 55.0], [0.0, 57.0]]}
}

{
  "corridor_id": "MALACCA_STRAIT",
  "flux_h": 128.0,
  "flux_z": -1.0,
  "delay_ratio": 1.246,
  "sis_p90": 0.778,
  "geometry": {"type": "LineString", "coordinates": [[98.0, 2.5], [100.35, 1.4], [103.0, 1.2], [104.0, 1.3]]}
}
```

**156 Schiffsbewegungen** in der Nordsee (Rotterdam + Antwerpen)
**128 Schiffsbewegungen** in der Malacca-Straße (Singapur)

## 🔧 Was wurde repariert

### Problem
Die tatsächliche `polygon_events` Tabelle hat **andere Spalten** als das ursprüngliche Schema:

- ❌ Geplant: `ts`, `lat`, `lon`
- ✅ Tatsächlich: `ts_in`, `ts_out`, `centroid_lon`, `centroid_lat`

### Lösung
[src/spvx/api_open_sea.py:227](src/spvx/api_open_sea.py#L227) angepasst:
- `WHERE ts >=` → `WHERE ts_in >=`

## 📊 API Snapshot

Die API nutzt jetzt den Snapshot `db/spvx_api.duckdb`:
- ✅ **1,621 polygon_events** erfolgreich kopiert
- ✅ **41 Tabellen** insgesamt im Snapshot
- ✅ **Keine Locks** mehr auf die Produktions-DB

## 🚀 Services

| Service | Status | URL |
|---------|--------|-----|
| API Server | ✅ Läuft | http://localhost:8000 |
| Dashboard | ✅ Läuft | http://localhost:5173 |
| Ingestion | ⏸️ Gestoppt | (während Snapshot-Erstellung) |

## 🎯 Nächste Schritte

### 1. Dashboard aufrufen
```bash
open http://localhost:5173
```

Die Korridore sollten jetzt auf der Map sichtbar sein!

### 2. Ingestion neu starten

Du hast die Ingestion gestoppt, um den Snapshot zu erstellen. Starte sie wieder:

```bash
# Falls du LaunchAgent nutzt:
launchctl load ~/Library/LaunchAgents/com.spvx.ais-ingest.plist

# Oder manuell:
./start_consumer.sh
```

### 3. Snapshot regelmäßig aktualisieren

Führe alle 10 Minuten aus:
```bash
./UPDATE_API_SNAPSHOT.sh
```

**Wichtig:** Die Ingestion muss währenddessen kurz gestoppt werden (siehe Skript-Fehlermeldungen).

Alternativ: Cron-Job einrichten (optional):
```bash
*/10 * * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./UPDATE_API_SNAPSHOT.sh >> logs/snapshot.log 2>&1
```

## 🧪 Tests

Endpoint-Tests:
```bash
# 24 Stunden
curl 'http://localhost:8000/api/open_sea/corridor_view?window=h24'

# 7 Tage
curl 'http://localhost:8000/api/open_sea/corridor_view?window=d7'
```

Erwartetes Ergebnis:
- ✅ Status 200 OK
- ✅ JSON-Array mit Korridor-Features
- ✅ flux_h, flux_z, delay_ratio, sis_p90 berechnet
- ✅ GeoJSON LineString geometries

## 📁 Dateien

| Datei | Beschreibung |
|-------|--------------|
| [src/spvx/api_open_sea.py](src/spvx/api_open_sea.py) | ✅ Korrigiert (`ts_in` statt `ts`) |
| [UPDATE_API_SNAPSHOT.sh](UPDATE_API_SNAPSHOT.sh) | Snapshot-Erstellungs-Skript |
| [test_corridor_view.py](test_corridor_view.py) | Test mit FastAPI TestClient |
| [db/spvx_api.duckdb](db/spvx_api.duckdb) | API Snapshot (1.6K events) |

## 🎨 Frontend-Integration

Der Endpoint ist bereit für die Map-Visualisierung. Im Dashboard sollten die Korridore jetzt als farbige LineStrings angezeigt werden:

- **Rot/Orange**: Hoher Traffic (flux_z > 0)
- **Grün/Blau**: Normaler Traffic (flux_z ≈ 0)
- **Grau**: Niedriger Traffic (flux_z < 0)

Die `delay_ratio` und `sis_p90` Werte können für Tooltips/Infos genutzt werden.

---

**Erstellt:** 2025-10-27 21:02 UTC
**Status:** ✅ LIVE & FUNKTIONIERT
