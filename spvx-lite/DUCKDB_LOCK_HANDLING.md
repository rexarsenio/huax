# DuckDB Lock Handling

## Problem

Der Open-Sea-Consumer konnte nicht starten, weil die DuckDB-Datei von einem alten Prozess gesperrt war:

- Der `DuckDBWriter` versuchte die Datei `db/spvx.duckdb` exklusiv zu öffnen
- Wenn ein alter Prozess noch den Lock hielt, brach der neue Prozess sofort ab
- Dies führte dazu, dass keine AIS-Fixes geschrieben wurden (`fixes_10m = 0`)
- Dadurch fehlten Gate-Flux- und STS-Zahlen

## Lösung

Es wurden mehrere Maßnahmen implementiert:

### 1. Retry-Logik im DuckDBWriter (`src/spvx/open_sea/db.py`)

Der `DuckDBWriter` versucht jetzt mit exponential backoff bis zu 5 Mal, die Datenbankverbindung herzustellen:

```python
class DuckDBWriter:
    def __init__(self, path: Path, max_retries: int = 5, retry_delay: float = 2.0):
        # Retry logic with exponential backoff
        # Wartet: 2s, 4s, 8s, 16s, 32s = ~62s total
```

**Vorteile:**
- Toleriert kurzzeitige Locks während Prozess-Übergängen
- Gibt klare Fehlermeldungen bei andauernden Lock-Problemen
- Unterscheidet zwischen Lock-Fehlern und anderen IO-Fehlern

### 2. Verbessertes Stop-Skript (`stop_consumer.sh`)

Das Stop-Skript wurde erweitert um:

- **Graceful Shutdown:** 10 Sekunden Wartezeit, dann SIGKILL
- **Pattern-basierte Suche:** Findet alle Consumer-Prozesse, nicht nur PID-File
- **DuckDB Lock Check:** Überprüft und beendet Prozesse, die Locks halten
- **Detailliertes Logging:** Zeigt genau was passiert

**Verwendung:**
```bash
./stop_consumer.sh
```

### 3. Verbessertes Start-Skript (`start_consumer.sh`)

Das Start-Skript wurde erweitert um:

- **Automatische Bereinigung:** Stoppt existierende Consumer automatisch
- **Lock-Überprüfung:** Erkennt und behebt Lock-Probleme vor dem Start
- **Aggressive Lock-Freigabe:** Killt Prozesse, die Locks halten, falls nötig

**Verwendung:**
```bash
./start_consumer.sh
```

### 4. Lock-Check-Hilfs-Skript (`check_duckdb_locks.sh`)

Neues Skript zur manuellen Überprüfung und Bereinigung von Locks:

**Nur prüfen:**
```bash
./check_duckdb_locks.sh
```

**Prüfen und Prozesse killen:**
```bash
./check_duckdb_locks.sh --kill
```

### 5. Restart-Skript (`restart_consumer.sh`)

Vereinfachtes Skript für sichere Neustarts:

```bash
./restart_consumer.sh
```

Führt aus:
1. Stop des Consumers
2. Überprüfung und Bereinigung von Locks
3. Start des Consumers

## Verwendungsszenarien

### Consumer startet nicht wegen Lock

**Symptome:**
- Consumer startet und terminiert sofort
- Log zeigt: `IO Error: Could not set lock on file`
- `fixes_10m = 0` in den Metriken

**Lösung:**
```bash
# Option 1: Restart-Skript (empfohlen)
./restart_consumer.sh

# Option 2: Manuell
./stop_consumer.sh
./check_duckdb_locks.sh --kill  # Falls Locks verbleiben
./start_consumer.sh
```

### Manuelles Lock-Management

**Lock-Status prüfen:**
```bash
./check_duckdb_locks.sh
```

**Prozesse mit Locks identifizieren:**
```bash
lsof db/spvx.duckdb
```

**Spezifischen Prozess beenden:**
```bash
kill -9 <PID>
```

### Consumer läuft bereits

Das Start-Skript erkennt laufende Consumer automatisch und stoppt sie:

```bash
./start_consumer.sh
# Erkennt automatisch: "Found existing consumer processes: 12345"
# Stoppt sie und startet neu
```

## Technische Details

### Retry-Parameter

Im `DuckDBWriter` können die Retry-Parameter angepasst werden:

```python
writer = DuckDBWriter(
    path,
    max_retries=5,      # Anzahl Versuche
    retry_delay=2.0     # Initiale Wartezeit in Sekunden
)
```

**Wartezeiten bei Default-Werten:**
- Versuch 1: sofort
- Versuch 2: nach 2s
- Versuch 3: nach 4s
- Versuch 4: nach 8s
- Versuch 5: nach 16s
- **Total:** ~30s

### DuckDB Lock-Mechanismus

DuckDB verwendet File-System-Locks zur Sicherstellung exklusiver Zugriffe:

- **Ein Prozess** kann schreibend zugreifen
- **Mehrere Prozesse** können lesend zugreifen (mit Einschränkungen)
- Locks werden beim `duckdb.connect()` gesetzt
- Locks werden beim `con.close()` freigegeben

**Häufige Ursachen für hängende Locks:**
- Prozess wurde mit `kill -9` beendet (ungraceful shutdown)
- Python-Exception vor `writer.close()`
- Mehrere Consumer-Instanzen gestartet
- API-Prozess hält DB-Verbindung offen

## Debugging

### Log-Ausgaben verstehen

**Erfolgreicher Start:**
```
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 1/5)
Successfully connected to DuckDB at db/spvx.duckdb
```

**Lock-Problem mit Retry:**
```
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 1/5)
DuckDB file is locked (attempt 1/5). Waiting 2.0 seconds before retry.
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 2/5)
Successfully connected to DuckDB at db/spvx.duckdb
```

**Lock-Problem fatal:**
```
Attempting to connect to DuckDB at db/spvx.duckdb (attempt 5/5)
Failed to connect to DuckDB after 5 attempts.
RuntimeError: Could not acquire DuckDB lock on db/spvx.duckdb after 5 attempts.
```

### Prozesse finden

**Alle Python-Prozesse:**
```bash
ps aux | grep python
```

**Consumer-Prozesse:**
```bash
pgrep -af "spvx.cli open-sea-consume"
```

**API-Prozesse:**
```bash
pgrep -af "uvicorn spvx.api_app"
```

**Prozesse mit DuckDB-Lock:**
```bash
lsof db/spvx.duckdb
```

## Best Practices

1. **Immer Restart-Skript verwenden:**
   ```bash
   ./restart_consumer.sh
   ```

2. **Bei Problemen erst Stop, dann Check:**
   ```bash
   ./stop_consumer.sh
   ./check_duckdb_locks.sh
   ```

3. **Logs überwachen:**
   ```bash
   tail -f logs/open_sea_consumer.log
   ```

4. **Graceful Shutdown bevorzugen:**
   ```bash
   # Gut:
   kill <PID>
   
   # Vermeiden (nur als letztes Mittel):
   kill -9 <PID>
   ```

5. **Consumer und API nicht gleichzeitig laufen lassen:**
   - Consumer schreibt kontinuierlich
   - API sollte nur lesend zugreifen oder separaten Read-Only-Modus verwenden

## Automatisierung

Für Production-Umgebungen kann ein Watchdog-Service eingerichtet werden:

```bash
# Cron-Job für regelmäßige Health-Checks
*/5 * * * * /path/to/check_consumer_health.sh
```

Oder systemd mit automatischem Restart:

```ini
[Service]
Restart=always
RestartSec=10
```

## Zusammenfassung

Die implementierte Lösung behebt das Lock-Problem durch:

1. ✅ **Resiliente DuckDB-Verbindung** mit Retry-Logik
2. ✅ **Automatische Lock-Bereinigung** in Start/Stop-Skripten
3. ✅ **Hilfs-Tools** für manuelles Lock-Management
4. ✅ **Detailliertes Logging** für Debugging
5. ✅ **Einfache Restart-Prozedur** für Operatoren

Der Consumer kann jetzt zuverlässig starten, auch wenn kurzzeitige Lock-Probleme auftreten.
