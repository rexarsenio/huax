# DuckDB Lock Problem - Lösung Zusammenfassung

## Problem Beschreibung

Der Open-Sea-Consumer konnte nicht starten, weil:

1. `DuckDBWriter` versuchte sofort `db/spvx.duckdb` exklusiv zu öffnen
2. Wenn ein alter Prozess den Lock hielt, brach der neue Prozess sofort ab
3. Der Fehler war: `IO Error: Could not set lock on file ...`
4. Resultat: `fixes_10m = 0`, keine Gate-Flux-/STS-Zahlen

## Implementierte Lösung

### 1. Retry-Logik in `DuckDBWriter` ✅

**Datei:** `src/spvx/open_sea/db.py`

```python
class DuckDBWriter:
    def __init__(self, path: Path, max_retries: int = 5, retry_delay: float = 2.0):
        # Versucht bis zu 5 Mal mit exponential backoff
        # Wartezeiten: 2s, 4s, 8s, 16s, 32s (~62s total)
```

**Features:**
- ✅ Exponential backoff bei Lock-Konflikten
- ✅ Detaillierte Logging-Ausgaben
- ✅ Unterscheidung zwischen Lock- und anderen IO-Fehlern
- ✅ Klare Fehlermeldungen mit `lsof`-Hinweis

### 2. Verbessertes `stop_consumer.sh` ✅

**Neue Features:**
- ✅ Graceful shutdown (10s Wartezeit, dann SIGKILL)
- ✅ Findet alle Consumer-Prozesse (nicht nur PID-File)
- ✅ Überprüft und beendet Prozesse mit DuckDB-Locks
- ✅ Detailliertes Feedback mit farbigen Statusmeldungen

### 3. Verbessertes `start_consumer.sh` ✅

**Neue Features:**
- ✅ Automatisches Stoppen existierender Consumer
- ✅ Pre-flight Lock-Check mit `lsof`
- ✅ Automatische Lock-Bereinigung vor dem Start
- ✅ Besseres Error-Handling

### 4. Neues `check_duckdb_locks.sh` ✅

**Verwendung:**
```bash
# Nur prüfen
./check_duckdb_locks.sh

# Prüfen und Prozesse killen
./check_duckdb_locks.sh --kill
```

### 5. Neues `restart_consumer.sh` ✅

**Verwendung:**
```bash
./restart_consumer.sh
```

Führt sicher aus:
1. Stop Consumer
2. Verify Locks cleared
3. Start Consumer

### 6. Tests ✅

**Datei:** `tests/test_duckdb_retry.py`

Tests für:
- ✅ Erfolgreiche Verbindung ohne Lock
- ✅ Retry mit Lock-Release
- ✅ Fehler nach max_retries
- ✅ Exponential backoff Timing
- ✅ Logging-Ausgaben

### 7. Dokumentation ✅

**Datei:** `DUCKDB_LOCK_HANDLING.md`

Vollständige Dokumentation mit:
- ✅ Problem-Beschreibung
- ✅ Technische Details
- ✅ Verwendungsszenarien
- ✅ Debugging-Guide
- ✅ Best Practices

## Verwendung

### Normaler Betrieb

```bash
# Consumer starten (automatische Lock-Bereinigung)
./start_consumer.sh

# Consumer stoppen (saubere Lock-Freigabe)
./stop_consumer.sh

# Consumer neu starten
./restart_consumer.sh
```

### Bei Lock-Problemen

```bash
# Variante 1: Restart-Skript (empfohlen)
./restart_consumer.sh

# Variante 2: Manuelle Bereinigung
./stop_consumer.sh
./check_duckdb_locks.sh --kill
./start_consumer.sh

# Variante 3: Lock-Status prüfen
./check_duckdb_locks.sh
lsof db/spvx.duckdb
```

## Technische Parameter

### Retry-Konfiguration

Default-Werte im `DuckDBWriter`:
- `max_retries=5` → 5 Verbindungsversuche
- `retry_delay=2.0` → 2s initiale Wartezeit

**Wartezeiten:**
- Versuch 1: sofort
- Versuch 2: nach 2s
- Versuch 3: nach 4s  
- Versuch 4: nach 8s
- Versuch 5: nach 16s
- **Total:** ~30 Sekunden

### Lock-Check in Shell-Skripten

Alle Skripte verwenden `lsof` zum Identifizieren von Lock-Haltern:

```bash
lsof db/spvx.duckdb
```

Falls `lsof` nicht verfügbar ist, geben die Skripte Warnungen aus, funktionieren aber trotzdem.

## Testergebnisse

### Syntax Checks ✅

- ✅ `db.py` Python-Syntax valide
- ✅ `DuckDBWriter` import erfolgreich
- ✅ Alle Shell-Skripte syntax-validiert

### Integration

Der Consumer verwendet automatisch die neue Retry-Logik:

```python
# In consumer.py, Zeile 77:
self.writer = DuckDBWriter(settings.duckdb_path)
# Verwendet automatisch: max_retries=5, retry_delay=2.0
```

## Vorteile der Lösung

1. **Robustheit:** Toleriert kurzzeitige Lock-Konflikte
2. **Transparenz:** Klare Log-Meldungen bei jedem Retry
3. **Automatisierung:** Skripte bereinigen Locks automatisch
4. **Diagnostics:** Hilfs-Tools für manuelles Debugging
5. **Zero Breaking Changes:** Bestehender Code funktioniert weiterhin

## Deployment

### Sofort verwendbar

Alle Änderungen sind:
- ✅ Rückwärtskompatibel
- ✅ Keine neuen Dependencies
- ✅ Keine Schema-Änderungen
- ✅ Keine Config-Änderungen nötig

### Empfohlene Schritte

1. Stop bestehenden Consumer:
   ```bash
   ./stop_consumer.sh
   ```

2. Code aktualisieren (Git pull/merge)

3. Consumer neu starten:
   ```bash
   ./start_consumer.sh
   ```

4. Logs überwachen:
   ```bash
   tail -f logs/open_sea_consumer.log
   ```

## Monitoring

### Log-Ausgaben

**Erfolgreicher Start:**
```
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 1/5)
Successfully connected to DuckDB at db/spvx.duckdb
```

**Mit Retry:**
```
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 1/5)
DuckDB file is locked (attempt 1/5). Waiting 2.0 seconds before retry.
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 2/5)
Successfully connected to DuckDB at db/spvx.duckdb
```

**Fehler nach Retries:**
```
Failed to connect to DuckDB after 5 attempts.
RuntimeError: Could not acquire DuckDB lock on db/spvx.duckdb after 5 attempts.
```

### Metriken

Nach erfolgreichem Start sollten folgende Metriken wieder normal sein:

- ✅ `fixes_10m > 0`
- ✅ `open_sea_fixes_total` steigt
- ✅ `open_sea_gate_crossings_total` wird erfasst
- ✅ `open_sea_consumer_running = 1`

## Rollback

Falls Probleme auftreten, Rollback ist einfach:

```bash
git revert <commit-hash>
./restart_consumer.sh
```

Die alte Version startet dann ohne Retry-Logik (sofortiger Fail bei Lock).

## Nächste Schritte

Optionale Verbesserungen für die Zukunft:

1. **Systemd-Integration:** Automatischer Restart bei Crashes
2. **Health-Check-Script:** Cron-Job für regelmäßige Überwachung
3. **Metrics-Alert:** Prometheus-Alert bei `fixes_10m = 0`
4. **Read-Only Mode für API:** Separate DB-Connection ohne Locks

## Fragen & Support

Bei Problemen:

1. Check Logs: `tail -100 logs/open_sea_consumer.log`
2. Check Locks: `./check_duckdb_locks.sh`
3. Check Prozesse: `pgrep -af spvx`
4. Dokumentation: `DUCKDB_LOCK_HANDLING.md`
