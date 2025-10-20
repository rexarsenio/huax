# SPVX-Lite AIS Deployment Guide

## Overview

This guide explains how to run the AIS stream ingestion continuously and aggregate the data regularly.

## Components

1. **ingest_aisstream.py** - Connects to AISStream.io WebSocket and writes raw AIS data to `ais_raw` table
2. **aggregate_dwell.py** - Aggregates raw data into `chokepoint_dwell` table with 10-minute windows
3. **components.py** - Computes CQ components from dwell data for index calculation

## Quick Start

### 1. Run AIS Ingestion (Development)

```bash
# Activate virtual environment
source .venv312/bin/activate

# Start ingestion (runs continuously)
python ingest_aisstream.py

# Or use make
make ingest-ais
```

### 2. Aggregate Dwell Data

```bash
# Run aggregation manually
python aggregate_dwell.py

# Or use make
make aggregate-dwell
```

Die Aggregation speichert den letzten erfolgreich verarbeiteten Zeitslot in `job_state`; beim nächsten Lauf werden neue Fenster sowie das vorherige Fenster (Catch-up) verarbeitet, sodass verspätete AIS-Meldungen einfließen.

### 3. Compute Index with AIS Data

```bash
make compute-index
```

## Production Deployment

### Option 1: systemd Service (Linux)

#### Install the Service

```bash
# Copy service file
sudo cp systemd/spvx-ais-ingest.service /etc/systemd/system/

# Edit paths if needed
sudo nano /etc/systemd/system/spvx-ais-ingest.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable spvx-ais-ingest

# Start service
sudo systemctl start spvx-ais-ingest

# Check status
sudo systemctl status spvx-ais-ingest

# View logs
sudo journalctl -u spvx-ais-ingest -f
```

#### Stop the Service

```bash
sudo systemctl stop spvx-ais-ingest
sudo systemctl disable spvx-ais-ingest
```

### Option 2: macOS launchd

Use the helper script (renders a plist with the correct absolute paths and python binary):

```bash
./install_services.sh
```

The script will:
1. Pick the local virtualenv interpreter (falls back to `python3` on PATH).
2. Render `com.spvx.ais-ingest.plist` into `~/Library/LaunchAgents/`.
3. (Re)load the LaunchAgent via `launchctl -w`.
4. Remove the deprecated aggregation LaunchAgent if still present.

You can manage the service afterwards with:

```bash
launchctl list | grep com.spvx.ais-ingest   # status
launchctl unload ~/Library/LaunchAgents/com.spvx.ais-ingest.plist   # stop
launchctl load ~/Library/LaunchAgents/com.spvx.ais-ingest.plist     # start
tail -f logs/ais-ingest.log                                          # live logs
```

Health- und Readiness-Checks laufen standardmäßig auf `http://localhost:9109`, Prometheus-Metriken auf `http://localhost:9108/metrics`. Werte lassen sich über `.env` (`SPVX_HEALTH_PORT`, `SPVX_METRICS_PORT`) anpassen.
Für lokale Bindings können zusätzlich `SPVX_HEALTH_HOST=127.0.0.1` und `SPVX_METRICS_HOST=127.0.0.1` gesetzt werden (Reverse-Proxy übernimmt externen Zugriff).

### Option 3: Docker

```dockerfile
# Add to Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "ingest_aisstream.py"]
```

Run:

```bash
docker build -t spvx-ais-ingest .
docker run -d --name spvx-ais \
  --restart unless-stopped \
  -v $(pwd)/db:/app/db \
  --env-file .env \
  spvx-ais-ingest
```

## Scheduled Aggregation

> **Hinweis:** Wenn Sie den LaunchAgent/Systemd-Service aus diesem Repo verwenden, ist die 10-Minuten-Aggregation bereits im Ingest-Prozess integriert – zusätzliche Cron-Jobs oder Timer sind nicht nötig. Die folgenden Optionen sind nur für alternative Deployments oder Fallsback-Orchestrierung relevant.

### Cron (Linux/macOS)

Add to crontab (`crontab -e`):

```cron
# Aggregate dwell data every 10 minutes (falls nicht vom Service abgedeckt)
*/10 * * * * cd /path/to/spvx-lite && ./run_aggregation.sh >> logs/aggregate-dwell.log 2>&1

# Compute index every hour at minute 5
5 * * * * cd /path/to/spvx-lite && .venv/bin/python -m spvx.cli compute-index >> logs/compute-index.log 2>&1
```

### systemd Timer (Linux)

Create `/etc/systemd/system/spvx-aggregate-dwell.service`:

```ini
[Unit]
Description=SPVX Aggregate Dwell Data

[Service]
Type=oneshot
User=alongo
WorkingDirectory=/path/to/spvx-lite
Environment="PATH=/path/to/spvx-lite/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/path/to/spvx-lite/run_aggregation.sh
```

Create `/etc/systemd/system/spvx-aggregate-dwell.timer`:

```ini
[Unit]
Description=Run SPVX Aggregate Dwell Every 10 Minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable spvx-aggregate-dwell.timer
sudo systemctl start spvx-aggregate-dwell.timer
sudo systemctl list-timers
```

## Monitoring

### Health & Metrics

- Health: `curl -s http://localhost:9109/health | jq`
- Readiness: `curl -s http://localhost:9109/ready | jq` (liefert 503, wenn die letzte Aggregation > 2 Intervalle zurückliegt)
- Prometheus: `curl -s http://localhost:9108/metrics` (u. a. `spvx_aggregation_duration_seconds`, `spvx_aggregation_jitter_seconds`, `spvx_ingest_messages_total`)
- Ingest-Metriken: `spvx_ingest_raw_msgs_total`, `spvx_ingest_canon_msgs_total`, `spvx_ingest_unique_mmsi_5m`, `spvx_ingest_tanker_share_5m`
- Alerts: `prometheus/alerts.yml` als Rule-File (Missed Aggregation, Jitter, Freshness, Ready-Probe, Ressourcen)

### Golden Probe

```bash
# MMSI zur Watchlist hinzufügen
duckdb db/spvx.duckdb "INSERT OR IGNORE INTO ais_golden_mmsi VALUES ('123456789')"

# API-Ausgabe prüfen
curl -s http://localhost:9109/golden-probe | jq
```

### Check Database Contents

```bash
python -c "
import duckdb
con = duckdb.connect('db/spvx.duckdb')

# Raw AIS records
print('Raw AIS records:', con.execute('SELECT COUNT(*) FROM ais_raw').fetchone()[0])

# Dwell aggregation
print('\nDwell by region:')
con.execute('SELECT region, COUNT(*) as windows FROM chokepoint_dwell GROUP BY region').show()

# Latest observations
print('\nLatest 5 observations:')
con.execute('SELECT ts, region, slow_count FROM chokepoint_dwell ORDER BY ts DESC LIMIT 5').show()
"
```

### Log Rotation

Add to `/etc/logrotate.d/spvx-ais` (wenn Logs nach `/var/log` gesymlinkt sind):

```
/var/log/spvx-ais-ingest.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}

### Backups

```bash
# Snapshot erzeugen (legt Parquet-Export in backups/ an)
make backup-db

# Restore (falls kein Makefile-Kontext vorhanden)
bin/restore_duckdb.sh backups/spvx_YYYY-MM-DD

# Optional: nach S3 syncen (z. B. mit aws s3 sync backups/ s3://bucket/spvx-lite/)
```
```

## Troubleshooting

### No data being inserted

1. Check WebSocket connection:
   ```bash
   # Should see "Inserted N records" periodically
   tail -f logs/ais-ingest.log
   ```

2. Verify API key:
   ```bash
   grep AISSTREAM_API_KEY .env
   ```

3. Check message structure (first 3 messages are printed):
   ```bash
   # Restart ingestion to see debug output
   python ingest_aisstream.py
   ```

### Database locked

DuckDB allows only einen aktiven Writer. Stellen Sie sicher, dass kein zweiter Prozess offen ist:
```bash
lsof db/spvx.duckdb
```

Falls Sie die Aggregation manuell starten möchten, zuerst den LaunchAgent/Systemd-Dienst stoppen, danach `./run_aggregation.sh` ausführen und den Dienst wieder starten.

### Empty components

If `build_components()` returns empty AIS data:
```bash
# Check if aggregation ran
python aggregate_dwell.py

# Verify data exists
python -c "import duckdb; duckdb.connect('db/spvx.duckdb').execute('SELECT COUNT(*) FROM chokepoint_dwell').show()"
```

## Performance Tuning

### Database Optimization

```sql
-- Add index for faster aggregation
CREATE INDEX IF NOT EXISTS idx_ais_raw_region_ts ON ais_raw(region, ts);

-- Vacuum to reclaim space
VACUUM;
```

### Retention Policy

```sql
-- Delete old raw data (keep 30 days)
DELETE FROM ais_raw WHERE ts < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- Keep aggregated dwell data longer (1 year)
DELETE FROM chokepoint_dwell WHERE ts < CURRENT_TIMESTAMP - INTERVAL '1 year';
```

## Integration with SPVX Index

The AIS dwell components are automatically integrated when you run:

```bash
make compute-index
```

This will:
1. Load `ais_raw` data
2. Aggregate into `chokepoint_dwell`
3. Compute `CQ_CHOKE`, `CQ_SUEZ`, `CQ_BOSPORUS`, `CQ_HORMUZ`, `CQ_SG_AIS` components
4. Merge with other components (Turkish Straits, MPA Singapore, Rotterdam)
5. Apply weights from `config.yml`
6. Output `SPVX_LITE` index to `data/outputs/spvx_lite.csv`

Adjust component weights in `config.yml`:

```yaml
index:
  weights:
    CQ_TR: 1.0
    CQ_SG: 1.0
    PORT_EU: 1.0
    CQ_CHOKE: 0.8  # AIS composite signal
```
