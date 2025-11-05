# SPVX Open-Sea Monitoring Setup

## Overview

Complete Prometheus + Grafana monitoring stack for the SPVX Open-Sea AIS consumer.

## Architecture

```
Open-Sea Consumer (:9110/metrics)
    ↓
Prometheus (:9090) - Scrapes metrics every 10s
    ↓
Grafana (:3000) - Visualizations & Dashboards
```

## Quick Start

### 1. Start the Monitoring Stack

```bash
./start_monitoring.sh
```

This will:
- Start Prometheus on http://localhost:9090
- Start Grafana on http://localhost:3000
- Auto-configure datasource and dashboards

**Default Credentials:**
- Username: `admin`
- Password: `spvx-admin`

### 2. Start the Consumer

The monitoring stack expects the consumer to be running:

```bash
./start_consumer.sh
```

### 3. Access Grafana

Open http://localhost:3000 in your browser and login.

The dashboard "SPVX Open-Sea AIS Monitoring" will be automatically provisioned.

## Dashboard Panels

### Overview Metrics
1. **Consumer Status** - Liveness indicator (0 = down, 1 = running)
2. **Total Fixes Processed** - Cumulative count of AIS fixes
3. **Ingest Lag** - Seconds between now and latest fix timestamp
4. **Data Quality - Gap Ratio** - Percentage of missing 60s buckets

### Traffic Metrics
5. **Tanker Occupancy by Polygon** - Real-time vessel count per polygon
6. **Gate Crossings Rate** - Crossings per second by gate & direction
7. **Fix Processing Rate** - Fixes processed per second
8. **Spoof Score** - Percentage of teleport-speed fixes (>40kn)

### Summary Views
9. **Total Gate Crossings** - Aggregate crossing count
10. **Polygon Occupancy Heatmap** - Horizontal bar chart of polygon occupancy

## Prometheus Queries

You can also query Prometheus directly at http://localhost:9090/graph

**Useful queries:**

```promql
# Consumer uptime
up{job="open-sea-consumer"}

# Fix processing rate (per minute)
rate(open_sea_fixes_total[1m])

# Current tanker count by polygon
open_sea_tanker_occupancy_now

# Gate crossings in last hour
sum(increase(open_sea_gate_crossings_total[1h])) by (gate, direction)

# Data quality metrics
open_sea_data_gap_ratio
open_sea_spoof_score

# Ingest lag
open_sea_ingest_lag_seconds
```

## Configuration

### Prometheus

Edit `prometheus/prometheus.yml` to:
- Change scrape intervals
- Add more services
- Configure alerting rules

### Grafana

Dashboards are in `grafana/provisioning/dashboards/`.

To customize:
1. Edit `open_sea_dashboard.json` directly, OR
2. Edit in Grafana UI and export JSON

## Maintenance

### View Logs

```bash
# All logs
docker-compose -f docker-compose.monitoring.yml logs -f

# Specific service
docker-compose -f docker-compose.monitoring.yml logs -f prometheus
docker-compose -f docker-compose.monitoring.yml logs -f grafana
```

### Restart Services

```bash
docker-compose -f docker-compose.monitoring.yml restart
```

### Stop Stack

```bash
./stop_monitoring.sh
```

### Remove All Data (including metrics history)

```bash
docker-compose -f docker-compose.monitoring.yml down -v
```

## Data Retention

- **Prometheus:** 30 days (configurable in docker-compose.yml)
- **Grafana:** Permanent (uses Prometheus as data source)

## Alerting (Optional)

To add alerts, create `prometheus/alerts.yml`:

```yaml
groups:
  - name: open_sea_alerts
    interval: 30s
    rules:
      - alert: ConsumerDown
        expr: open_sea_consumer_running == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Open-Sea consumer is down"

      - alert: HighIngestLag
        expr: open_sea_ingest_lag_seconds > 60
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Ingest lag is high (>60s)"

      - alert: HighSpoofScore
        expr: open_sea_spoof_score > 0.3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High spoof score detected (>30%)"
```

Then update `prometheus/prometheus.yml`:

```yaml
rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']  # Add Alertmanager
```

## Troubleshooting

### Prometheus can't reach consumer

**Error:** "context deadline exceeded" in Prometheus logs

**Solutions:**
1. Ensure consumer is running: `ps aux | grep open-sea-consume`
2. Check metrics endpoint: `curl http://localhost:9110/metrics`
3. On Linux, change `host.docker.internal` to `172.17.0.1` in `prometheus.yml`

### Grafana shows "No data"

**Solutions:**
1. Check Prometheus is scraping: http://localhost:9090/targets
2. Verify consumer metrics: `curl http://localhost:9110/metrics | grep open_sea`
3. Wait 30s for first scrape
4. Check Grafana datasource: Configuration → Data Sources → Prometheus

### Dashboard not appearing

**Solutions:**
1. Check provisioning logs: `docker-compose -f docker-compose.monitoring.yml logs grafana`
2. Verify JSON syntax: `python -m json.tool grafana/provisioning/dashboards/open_sea_dashboard.json`
3. Manually import: Dashboards → Import → Upload JSON

## Best Practices

1. **Run consumer continuously** - Metrics are more meaningful with sustained operation
2. **Monitor ingest lag** - Should stay < 5 seconds
3. **Watch data gap ratio** - Should be < 30% for good coverage
4. **Check spoof score** - High values (>10%) indicate data quality issues
5. **Set up alerting** - Get notified when consumer goes down

## Advanced: Exporting Metrics to Grafana Cloud

To send metrics to Grafana Cloud:

1. Get Grafana Cloud API key
2. Add remote_write to `prometheus/prometheus.yml`:

```yaml
remote_write:
  - url: https://<your-instance>.grafana.net/api/prom/push
    basic_auth:
      username: <instance-id>
      password: <api-key>
```

3. Restart Prometheus
