# SPVX AIS Monitoring - Automated Setup

## Übersicht

Das System läuft jetzt vollständig automatisiert mit einem LaunchAgent. Der AIS Ingestion Service sammelt Live-Daten, schreibt sie nach DuckDB und stößt alle 10 Minuten im selben Prozess die Aggregation an – damit entfallen DuckDB-Lock-Konflikte zwischen getrennten Prozessen.

## Installierter Service

### AIS Ingestion Service (`com.spvx.ais-ingest`)
- **Status**: Läuft kontinuierlich im Hintergrund und startet beim Boot
- **Funktion**: WebSocket-Verbindung zu AISStream.io, Persistenz der Rohdaten und periodische Aggregation
- **Daten**: Schiffspositionen aus vier Chokepoints (Singapore/Malacca, Suez, Bosporus, Hormuz)
- **Logs**: `logs/ais-ingest.log` (stdout, inkl. Aggregationsmeldungen) und `logs/ais-ingest.error.log` (stderr)

## Service Management

### Status prüfen
```bash
launchctl list | grep com.spvx.ais-ingest
```

### Logs ansehen
```bash
tail -f logs/ais-ingest.log
tail -f logs/ais-ingest.error.log
```

Die Log-Einträge enthalten pro Aggregationslauf Dauer, Jitter und Fensteranzahl, z. B.:
```
[AGG] completed in 1.24s | jitter=0.012s | windows=6
```

### Health & Metrics
```bash
# Liveness
curl -s http://localhost:9109/health | jq

# Readiness (Aggregation ≤ 2 Intervalle alt)
curl -s http://localhost:9109/ready | jq

# Prometheus-Metriken
curl -s http://localhost:9108/metrics
```

Die Ports lassen sich bei Bedarf über `.env` (`SPVX_HEALTH_PORT`, `SPVX_METRICS_PORT`) oder direkt in `install_services.sh` anpassen.
Mit `SPVX_HEALTH_HOST`/`SPVX_METRICS_HOST` lässt sich das Binding auf `127.0.0.1` einschränken.

### Service stoppen
```bash
launchctl unload ~/Library/LaunchAgents/com.spvx.ais-ingest.plist
```

### Service starten
```bash
launchctl load ~/Library/LaunchAgents/com.spvx.ais-ingest.plist
```

### Service neu installieren / aktualisieren
```bash
./install_services.sh
```

### Database Backup & Restore
```bash
# Parquet-Snapshot erzeugen
make backup-db

# Wiederherstellen (siehe bin/restore_duckdb.sh für Parameter)
bin/restore_duckdb.sh backups/spvx_YYYY-MM-DD
```

### Golden Probe verwalten
```bash
# MMSI in die Watchlist aufnehmen
duckdb db/spvx.duckdb "INSERT OR IGNORE INTO ais_golden_mmsi VALUES ('123456789')"

# Golden-Probe-Messages ansehen (API)
curl -s http://localhost:9109/golden-probe | jq
```

## Datenbank

### Struktur
- **Rohdaten**: `ais_raw` – alle eingehenden AIS-Positionen
- **Kanonsiert**: `ais_canon` – deduplizierte, normalisierte Messages (inkl. Tanker-Flag)
- **Aggregiert**: `chokepoint_dwell` – Zeitfenster-basierte Statistiken über langsame Schiffe

### Manuell Daten prüfen
```bash
# Anzahl roher und kanonisierter Messages
python -c "import duckdb; con=duckdb.connect('db/spvx.duckdb');\nprint('ais_raw:', con.execute('SELECT COUNT(*) FROM ais_raw').fetchone()[0]);\nprint('ais_canon:', con.execute('SELECT COUNT(*) FROM ais_canon').fetchone()[0])"

# Aggregierte Daten ansehen (Service vorher mit launchctl unload stoppen)
./run_aggregation.sh
```

Der Aggregator merkt sich den zuletzt erfolgreich verarbeiteten Zeitslot (`job_state`-Tabelle) und holt bei Neustarts automatisch nach – inklusive eines Überlappungsfensters, damit verspätete AIS-Meldungen noch berücksichtigt werden.

## Automatische Features

✓ **Auto-Start & Restart**: launchd startet den Service beim Boot und nach Crash neu  
✓ **Periodische Aggregation**: alle 10 Minuten im selben Prozess wie die Ingestion  
✓ **Keine DuckDB-Locks**: ein einziger Writer vermeidet konkurrierende Schreibzugriffe  
✓ **Observability**: Health-/Readiness-Endpoints (9109) und Prometheus-Metriken (9108)  
✓ **Logging**: stdout/stderr landen in `logs/ais-ingest.log` bzw. `.error.log`
✓ **Alerts**: Prometheus-Regeln unter `prometheus/alerts.yml` (inkl. Jitter & Freshness)
✓ **Canonicalizer**: `ais_canon` speichert Message- und Empfangszeit, Tanker-Flag und ShipType für deduplizierte Roll-ups

## Konfiguration

### API-Key ändern
`.env` bearbeiten:
```bash
AISSTREAM_API_KEY=ihr-neuer-key
```

Anschließend den Service neu installieren:
```bash
./install_services.sh
```

### Aggregationsintervall anpassen
In `.env` (oder via launchctl-Umgebung) Sekundenwert setzen:
```bash
AGGREGATION_INTERVAL_SECONDS=900  # Beispiel: 15 Minuten
```

Danach den Service neu installieren:
```bash
./install_services.sh
```

## Troubleshooting

### Service läuft nicht
```bash
launchctl list | grep com.spvx.ais-ingest
cat logs/ais-ingest.error.log
```

### Keine neuen Daten
1. `tail -f logs/ais-ingest.log` auf Fehlermeldungen prüfen  
2. API-Key in `.env` kontrollieren  
3. Internet-Verbindung sicherstellen  
4. Readiness checken: `curl -s http://localhost:9109/ready`

### Manuelle Aggregation schlägt mit Lock-Fehler fehl
Der Service hält die DuckDB-Verbindung permanent offen. Vor manuellen Aggregationsläufen den LaunchAgent mit `launchctl unload` stoppen, anschließend `./run_aggregation.sh` ausführen und den Service wieder starten.

## Performance

- **Daten-Rate**: ~100–300 AIS-Messages pro Minute  
- **DB-Größe**: ~1–2 MB pro Tag (ohne Cleanup)  
- **CPU-Last**: < 5 %  
- **Speicher**: ~50 MB pro Prozess  
- **Metriken**: `spvx_aggregation_duration_seconds`, `spvx_aggregation_jitter_seconds`, `spvx_ingest_raw_msgs_total`, `spvx_ingest_canon_msgs_total`, `spvx_ingest_unique_mmsi_5m`, `spvx_ingest_tanker_share_5m`

## Nächste Schritte

Das System läuft vollständig automatisiert. Überwachen Sie bei Bedarf die Logs, greifen Sie auf die aggregierten Daten zu oder binden Sie sie ins Dashboard ein. Weitere Anpassungen – etwa zusätzliche Chokepoints oder andere Aggregationen – lassen sich jetzt ohne Lock-Konflikte implementieren.
