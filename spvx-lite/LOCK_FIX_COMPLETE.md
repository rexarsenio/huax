# DuckDB Lock-Problem - GELÖST ✅

## Ursprüngliches Problem

Der Open-Sea-Consumer konnte nicht starten, weil:
- `DuckDBWriter` versuchte `db/spvx.duckdb` exklusiv zu öffnen
- Alte Prozesse hielten den Lock
- Fehler: `IO Error: Could not set lock on file`
- Resultat: Consumer crashte sofort, `fixes_10m = 0`

## Implementierte Lösung

### 1. ✅ Retry-Logik im DuckDBWriter

**Datei:** `src/spvx/open_sea/db.py`

```python
class DuckDBWriter:
    def __init__(self, path: Path, max_retries: int = 5, retry_delay: float = 2.0):
        # Versucht bis zu 5x mit exponential backoff
        # Wartezeiten: 2s, 4s, 8s, 16s, 32s (~62s total)
```

**Features:**
- Exponential backoff bei Lock-Konflikten
- Detaillierte Logging-Ausgaben
- Unterscheidet Lock- vs. andere IO-Fehler
- Zeigt PID des Lock-Halters

### 2. ✅ Verbesserte Shell-Skripte

- **stop_consumer.sh**: Graceful shutdown + Lock-Bereinigung
- **start_consumer.sh**: Pre-flight Lock-Check + Konfliktlösung
- **restart_consumer.sh**: Sichere Stop → Verify → Start Sequenz
- **check_duckdb_locks.sh**: Lock-Management-Tool

### 3. ✅ Tests & Dokumentation

- Unit Tests: `tests/test_duckdb_retry.py`
- Vollständige Doku: `DUCKDB_LOCK_HANDLING.md`
- Zusammenfassung: `LOCK_FIX_SUMMARY.md`

## Test-Ergebnisse

### ✅ Lock-Problem gelöst:

1. **Retry-Logik funktioniert:**
   ```
   Attempting to connect to DuckDB (attempt 1/5)
   DuckDB file is locked. Waiting 2.0 seconds...
   Attempting to connect to DuckDB (attempt 2/5)
   Successfully connected to DuckDB
   ```

2. **Consumer startet erfolgreich:**
   - Keine Lock-Fehler beim Start
   - DuckDB-Verbindung hergestellt
   - Läuft stabil (PID 52669)
   - Metrics Server läuft (Port 9110)

3. **Shell-Skripte arbeiten korrekt:**
   - `stop_consumer.sh` beendet Prozesse und bereinigt Locks
   - `start_consumer.sh` prüft Locks vor Start
   - `restart_consumer.sh` führt sichere Sequenz aus

## Verwendung

### Normal:
```bash
./restart_consumer.sh              # Empfohlen
# oder
./start_consumer.sh
./stop_consumer.sh
```

### Bei Problemen:
```bash
./check_duckdb_locks.sh            # Zeigt Locks
./check_duckdb_locks.sh --kill     # Bereinigt Locks
```

## Separates Problem: Keine AIS-Daten

⚠️ **Nach dem Fix wurde ein weiteres Problem entdeckt:**

Der Consumer läuft, empfängt aber keine AIS-Daten:
- `open_sea_fixes_total` = leer
- `open_sea_data_gap_ratio` = 1.0 (100% Lücke)

**Mögliche Ursachen:**
1. Websocket-Verbindung fehlgeschlagen
2. API Key ungültig
3. Subscription-Filter zu restriktiv
4. Keine Tanker in den Bounding Boxes

**Zum Debuggen:**
```bash
# Logs überwachen
tail -f logs/open_sea_consumer.log

# Metriken prüfen
curl http://localhost:9110/metrics | grep open_sea_

# DuckDB prüfen (wenn Consumer gestoppt)
./stop_consumer.sh
duckdb db/spvx.duckdb "SELECT COUNT(*) FROM open_sea_fixes"
```

## Zusammenfassung

✅ **Lock-Problem: GELÖST**
- Retry-Logik implementiert
- Shell-Skripte verbessert
- Tests hinzugefügt
- Dokumentation erstellt

⚠️ **AIS-Daten-Problem: IDENTIFIZIERT**
- Consumer läuft, empfängt aber keine Daten
- Separates Problem (nicht Lock-bezogen)
- Weitere Untersuchung nötig

## Nächste Schritte

Für das AIS-Daten-Problem:

1. **Log-Level erhöhen:**
   ```bash
   export LOG_LEVEL=DEBUG
   ./restart_consumer.sh
   ```

2. **Websocket-Verbindung prüfen:**
   - Ist `wss://stream.aisstream.io/v0/stream` erreichbar?
   - Ist der API Key gültig?

3. **Bounding Boxes prüfen:**
   - Sind die Koordinaten korrekt?
   - Gibt es Tanker in diesen Bereichen?

4. **Alternative Datenquelle:**
   - Mock-Daten zum Testen verwenden
   - Andere AIS-Quellen evaluieren

## Dateien

**Geändert:**
- ✅ `src/spvx/open_sea/db.py` (Retry-Logik)
- ✅ `start_consumer.sh` (Lock-Check)
- ✅ `stop_consumer.sh` (Lock-Bereinigung)

**Neu erstellt:**
- ✅ `restart_consumer.sh` (Safe Restart)
- ✅ `check_duckdb_locks.sh` (Lock-Tool)
- ✅ `tests/test_duckdb_retry.py` (Tests)
- ✅ `DUCKDB_LOCK_HANDLING.md` (Doku)
- ✅ `LOCK_FIX_SUMMARY.md` (Summary)
- ✅ `LOCK_FIX_COMPLETE.md` (Dieses Dokument)

---

**Status:** Lock-Problem gelöst ✅ | AIS-Daten-Problem identifiziert ⚠️

**Datum:** $(date)
**Consumer PID:** 52669
**Metrics:** http://localhost:9110/metrics
