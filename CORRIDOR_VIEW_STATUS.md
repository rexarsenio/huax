# Corridor View - Status Update

## ✅ Was wurde gemacht

### 1. Code-Änderungen in `src/spvx/api_open_sea.py`

- **Zeile 227 & 238**: SQL-Abfrage korrigiert - `ts_in` → `ts` (entspricht dem Schema der `polygon_events` Tabelle)
- **Zeile 21**: `_connect()` Funktion nutzt bereits korrekt den API-Snapshot (`spvx_api.duckdb`), wenn vorhanden
- **Zeile 12**: Kein `re`-Import vorhanden (bereits entfernt)

### 2. Funktionsweise des `/api/open_sea/corridor_view` Endpoints

Der Endpoint:
- Aggregiert `polygon_events` aus dem konfigurierten Zeitfenster (z.B. `h24` = 24 Stunden)
- Gruppiert nach `polygon_id` und zählt:
  - `event_count`: Anzahl Events
  - `vessel_count`: Anzahl eindeutiger MMSIs (Schiffe)
- Mappt Polygone auf Korridore:
  - **MALACCA_STRAIT**: `SINGAPORE_STS`, `SINGAPORE_JURONG`
  - **NORTH_SEA**: `ROTTERDAM_OIL`, `ANTWERP_OIL`
  - **SUEZ_APPROACH**: `PORT_SAID_ANCHORAGE`
- Berechnet Live-Metriken:
  - `flux_h`: Schiffe pro Stunde (basierend auf vessel_count)
  - `flux_z`: Z-Score (-3 bis +3, normalisiert)
  - `delay_ratio`: Geschätzte Verzögerung (1.0 - 1.5)
  - `sis_p90`: Sea-State Index Schätzung (0.45 - 0.85)
- Gibt GeoJSON LineString Features für Map-Visualisierung zurück

### 3. Test-Ergebnisse

Test mit FastAPI TestClient (`test_corridor_view.py`):
```
✅ Status: 200 OK
✅ MALACCA_STRAIT: flux_h=25.0, flux_z=1.2, delay_ratio=1.3, sis_p90=0.85
✅ NORTH_SEA: flux_h=13.0, flux_z=0.0, delay_ratio=1.156, sis_p90=0.658
✅ SUEZ_APPROACH: flux_h=3.0, flux_z=-1.0, delay_ratio=1.036, sis_p90=0.498
```

## 🚀 Aktueller Status

### API-Server läuft auf Port 8000
```bash
✅ Uvicorn läuft auf http://127.0.0.1:8000
✅ Endpoint antwortet mit 200 OK (keine 500 Fehler mehr!)
⚠️  Snapshot-Datenbank ist leer → API gibt `[]` zurück
```

### Dashboard läuft auf Port 5173
Das Dashboard ist bereits aktiv (PIDs: 955, 51553).

## 📋 Nächste Schritte

### Option 1: Mit echten Live-Daten arbeiten

Um den Snapshot mit echten Daten zu füllen:

1. **Ingestion-Prozess temporär stoppen:**
   ```bash
   pkill -f ingest_aisstream.py
   ```

2. **Snapshot aktualisieren:**
   ```bash
   cd /Users/alongo/Desktop/huax/spvx-lite
   ./UPDATE_API_SNAPSHOT.sh
   ```

3. **Ingestion neu starten:**
   ```bash
   ./start_consumer.sh  # oder wie auch immer du es normalerweise startest
   ```

4. **Dashboard im Browser aufrufen:**
   ```
   http://localhost:5173
   ```

### Option 2: Mit Mock-Daten testen

Wenn du erstmal nur testen willst:

1. **Mock-Datenbank verwenden:**
   ```bash
   ./START_MOCK.sh
   ```

2. **Dashboard aufrufen:**
   ```
   http://localhost:5173
   ```

### Option 3: Periodisches Snapshot-Update einrichten

Für produktiven Betrieb kannst du den Snapshot regelmäßig aktualisieren (z.B. alle 10 Minuten):

```bash
# Cron-Job hinzufügen (optional)
*/10 * * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./UPDATE_API_SNAPSHOT.sh >> logs/snapshot_update.log 2>&1
```

**Wichtig:** Das Snapshot-Update funktioniert nur, wenn die Ingestion gerade NICHT schreibt (DuckDB-Locking).

## 🔧 Neue Skripte

### `UPDATE_API_SNAPSHOT.sh`
- Kopiert alle relevanten Tabellen von `db/spvx.duckdb` → `db/spvx_api.duckdb`
- Verwendet `ATTACH DATABASE` für effizientes Kopieren
- Führt atomares Swap durch (keine Downtime)
- Erkennt, wenn die Quell-DB gesperrt ist und gibt hilfreiche Fehlermeldungen

### `test_corridor_view.py`
- Testet den `/api/open_sea/corridor_view` Endpoint
- Erstellt Mock-Datenbank mit realistischen polygon_events
- Verifiziert alle drei Korridore und berechnete Metriken

## 📊 Datenbank-Lock-Problem

**Problem:**
Der Ingestion-Prozess (`ingest_aisstream.py`, PID 34742) hält einen Write-Lock auf `db/spvx.duckdb`. DuckDB erlaubt keine gleichzeitigen Read-Locks während ein Write-Lock aktiv ist.

**Lösung:**
Der API-Server nutzt jetzt den Snapshot `db/spvx_api.duckdb`, der unabhängig vom Ingestion-Prozess ist:

```python
# In src/spvx/api_open_sea.py:21
def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    api_db_path = Path(settings.duckdb_path).parent / "spvx_api.duckdb"
    if api_db_path.exists():
        return duckdb.connect(str(api_db_path), read_only=read_only)
    return duckdb.connect(settings.duckdb_path, read_only=read_only)
```

## 🎯 Zusammenfassung

| Feature | Status |
|---------|--------|
| SQL-Abfrage korrigiert (`ts_in` → `ts`) | ✅ |
| `_connect()` nutzt Snapshot | ✅ |
| Kein `re`-Import mehr | ✅ |
| API-Server läuft (Port 8000) | ✅ |
| Endpoint gibt 200 OK zurück | ✅ |
| Dashboard läuft (Port 5173) | ✅ |
| Snapshot mit Daten gefüllt | ⏳ (siehe Option 1 oben) |

**Nächster Schritt:** Wähle eine der drei Optionen oben, um Daten in die API zu laden und die Korridore auf der Map zu sehen!

---

*Erstellt am: 2025-10-27*
*API-Server: http://127.0.0.1:8000*
*Dashboard: http://localhost:5173*
