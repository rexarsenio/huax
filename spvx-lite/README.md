# SPVX-Lite

Lightweight open-data pipeline for maritime chokepoint analytics and energy-market signals. Provides:

- Ingestion of public port and strait status feeds (with mock fallback).
- Feature engineering for SPVX-Lite components and spread/throughput models.
- Daily signals for spread-direction (Model A) and port throughput nowcasts (Model B).
- FastAPI + Typer CLI for local experimentation.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m spvx.cli ingest --mode mock
python -m spvx.cli compute-index
python -m spvx.cli build-basins
# Optional enrichments:
# python -m spvx.cli ingest-portstays      # tanker stays (Antwerp)
# python -m spvx.cli ingest-weather        # OpenWeather wind flags
# python -m spvx.cli ingest-sea-state      # RTOFS currents + WW3 waves
python -m spvx.cli train
python -m spvx.cli serve
# Optional (requires NxtPort credentials):
# python -m spvx.cli ingest-portstays
```

The mock ingest produces synthetic data so the rest of the pipeline runs without external keys.

## Smoke Checks & Tests

- `make run-mock && make compute-index` to build components and index artifacts.
- `make train` to fit both models (metrics logged via Rich).
- `make score` (add `--simulate-degradation` for drills) to refresh `data/outputs/signals.json` for dashboards/newsletters.
- `pytest` runs lightweight checks on components, index outputs, and model artifacts.

## Dashboard Companion

- A production-ready SPA lives in `../dashboard`.
- Ensure the API is running (`python -m spvx.cli serve --port 8081`).
- Then in `dashboard/`: `pnpm install && pnpm dev` to launch the UI, or `pnpm build` for static assets.

## AISStream.io Integration

Real-time vessel tracking from AISStream.io enriches the index with live chokepoint congestion data.

### Quick Setup

1. Add your API key to `.env`:
   ```bash
   AISSTREAM_API_KEY=your_key_here
   ```

2. Install dependencies (if not already installed):
   ```bash
   pip install websockets duckdb python-dotenv
   ```

3. Start the AIS ingestion (runs continuously):
   ```bash
   make ingest-ais
   # Or: python ingest_aisstream.py
   ```

4. Aggregate dwell data (run every 10 minutes; in der Launchd-Automation passiert das inzwischen im Ingest-Service selbst):
   ```bash
   make aggregate-dwell
   # Or: python aggregate_dwell.py
   ```

5. Compute index with AIS components:
   ```bash
   make compute-index
   ```

### Observability

- Health: `curl -s http://localhost:9109/health | jq`
- Readiness: `curl -s http://localhost:9109/ready | jq`
- Prometheus: `curl -s http://localhost:9108/metrics` (enthält u. a. `spvx_aggregation_duration_seconds`, `spvx_aggregation_jitter_seconds`, `spvx_ingest_messages_total`)
- Alerts: rule file unter `prometheus/alerts.yml` einbinden (`--rule.file=prometheus/alerts.yml`)
- AIS-Metriken: `spvx_ingest_raw_msgs_total`, `spvx_ingest_canon_msgs_total`, `spvx_ingest_unique_mmsi_5m`, `spvx_ingest_tanker_share_5m`
- Golden Probe: `GET /golden-probe?limit=200` liefert die zuletzt kanonisierten MMSI aus der Watchlist `ais_golden_mmsi`
- Dashboard-Metadaten: `GET /meta` liefert Hero-Text, Tooltips, Coverage- & Methodik-Hinweise für das Frontend
- Basin-Datensuite: siehe `docs/basin_indices.md` (Methodik) & `docs/release_checklist.md` (Gating)
- PortStays (Antwerpen/Zeebrugge) UAT-Anbindung: `docs/portstays.md`

### What Gets Tracked

- **Regions:** Singapore/Malacca, Suez, Bosporus, Strait of Hormuz
- **Vessels:** Tankers (ship types 80-89) only
- **Metric:** Count of slow-moving vessels (SOG < 0.5 knots) per 10-minute window
- **Components:** `CQ_CHOKE` (composite), `CQ_SG_AIS`, `CQ_SUEZ`, `CQ_BOSPORUS`, `CQ_HORMUZ`

### Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for:
- systemd/launchd service setup for 24/7 operation
- Cron/timer configuration for scheduled aggregation
- Docker deployment
- Monitoring and troubleshooting
- Database maintenance and retention policies
- Backup/Restore-Skripte (`bin/backup_duckdb.sh`, `bin/restore_duckdb.sh`)
- Prometheus/Grafana Integration (Dashboards + Alerts)
- AIS-Ingest Validierung: Canonicalizer (`ais_canon`), dedupe-Layer, Golden-Probe-View und Health-Metriken

## Operational Playbook (extract)

- **SLOs:** T+1 fix by 12:00 UTC with ≥99.5 % adherence; API `/spvx-lite` availability 99.9 %; median revision <0.10 index points.
- **Health Checks:** `/health` (liveness), `/ready` (artifact readiness), `/metrics` (Prometheus scrape).
- **Runbooks:**
  - *Missed fix:* rerun `spvx.cli ingest --mode live` and `spvx.cli compute-index`; if still failing, activate `make score --simulate-degradation` and flag downstream consumers.
  - *Data gap:* inspect `data/processed/components.parquet`; if Pandera validation fails, fall back to prior values and append annotation in `signals.json`.
  - *Index anomaly:* compare staging vs prod artifacts; pause publish (retain staging file), confirm source integrity before swap.
