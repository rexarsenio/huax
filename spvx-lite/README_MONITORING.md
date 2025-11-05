# 🚀 SPVX Open-Sea Monitoring - Complete Setup

Alle Monitoring-Komponenten sind jetzt konfiguriert und bereit!

## 📦 Was wurde erstellt

### 1. Aggregates (✅ Fertig)
- `tanker_occupancy_intraday` - Aktuelle Tanker-Counts
- `gate_flux_hourly` - Stündliche Gate-Crossings
- `gate_flux_daily` - Tägliche Gate-Crossings
- `tanker_dwell_daily` - Dwell-Zeiten
- `tanker_entries_daily` - Eintritte pro Tag
- `transit_times_daily` - Transit-Zeiten

### 2. Prometheus Setup (✅ Fertig)
- `prometheus/prometheus.yml` - Scraping-Config
- Targets: Consumer @ localhost:9110
- Retention: 30 Tage
- Scrape-Interval: 10s

### 3. Grafana Dashboard (✅ Fertig)
- 10 Panels mit verschiedenen Visualisierungen
- Auto-provisioned (kein manuelles Setup nötig)
- Zeigt alle wichtigen Metriken

### 4. Docker-Compose (✅ Fertig)
- `docker-compose.monitoring.yml`
- Prometheus + Grafana in einem Stack
- Volumes für persistente Daten

### 5. Scripts (✅ Fertig)
- `start_monitoring.sh` - Startet Prometheus + Grafana
- `stop_monitoring.sh` - Stoppt Stack gracefully

## 🎯 Quick Start

### Schritt 1: Docker starten

```bash
# macOS: Öffne Docker Desktop
open -a Docker

# Linux: 
sudo systemctl start docker
```

### Schritt 2: Monitoring Stack starten

```bash
./start_monitoring.sh
```

Das startet:
- **Prometheus** auf http://localhost:9090
- **Grafana** auf http://localhost:3000

**Login:** admin / spvx-admin

### Schritt 3: Consumer starten

```bash
./start_consumer.sh
```

### Schritt 4: Dashboard öffnen

1. Öffne http://localhost:3000
2. Login mit `admin` / `spvx-admin`
3. Dashboard: "SPVX Open-Sea AIS Monitoring"

## 📊 Dashboard Features

### Overview (Zeile 1)
- **Consumer Status** - 🟢 1.0 = Running, 🔴 0 = Down
- **Total Fixes** - Kumulative Anzahl verarbeiteter Fixes
- **Ingest Lag** - Latenz in Sekunden
- **Data Gap Ratio** - Qualitätsmetrik (0-1)

### Traffic Visualisierungen (Zeile 2)
- **Tanker Occupancy** - Zeitreihe pro Polygon
- **Gate Crossings Rate** - Crossings/sec pro Gate

### Performance (Zeile 3)
- **Fix Processing Rate** - Durchsatz
- **Spoof Score** - Teleport-Detektion

### Summaries (Zeile 4)
- **Total Crossings** - Aggregate
- **Occupancy Heatmap** - Bar chart

## 🔍 Nützliche Queries

Öffne Prometheus Explorer (http://localhost:9090/graph):

```promql
# Aktuelle Occupancy
open_sea_tanker_occupancy_now

# Fix-Rate (letzte 5min)
rate(open_sea_fixes_total[5m])

# Gate-Crossings letzte Stunde
increase(open_sea_gate_crossings_total[1h])

# Consumer Uptime
up{job="open-sea-consumer"}
```

## 📂 Dateistruktur

```
.
├── docker-compose.monitoring.yml
├── start_monitoring.sh
├── stop_monitoring.sh
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml
│       └── dashboards/
│           ├── dashboard.yml
│           └── open_sea_dashboard.json
└── docs/
    └── monitoring_setup.md
```

## 🛠️ Maintenance

### Logs ansehen

```bash
docker-compose -f docker-compose.monitoring.yml logs -f
```

### Stack neu starten

```bash
./stop_monitoring.sh
./start_monitoring.sh
```

### Daten löschen

```bash
docker-compose -f docker-compose.monitoring.yml down -v
```

## 🚨 Troubleshooting

### "No data" in Grafana

**Lösung:**
1. Consumer läuft? `ps aux | grep open-sea-consume`
2. Metrics verfügbar? `curl http://localhost:9110/metrics`
3. Prometheus scraping? http://localhost:9090/targets
4. Warte 30s für ersten Scrape

### Prometheus erreicht Consumer nicht

**Lösung (Linux):**
```bash
# Ändere in prometheus/prometheus.yml:
# von: host.docker.internal:9110
# zu:  172.17.0.1:9110
```

### Dashboard fehlt

**Lösung:**
```bash
# Prüfe Provisioning
docker-compose -f docker-compose.monitoring.yml logs grafana

# JSON-Syntax prüfen
python -m json.tool grafana/provisioning/dashboards/open_sea_dashboard.json
```

## 🎓 Best Practices

1. **Consumer dauerhaft laufen lassen** - Mindestens 1-2 Stunden für aussagekräftige Metriken
2. **Ingest Lag monitoren** - Sollte < 5s bleiben
3. **Data Gap Ratio** - < 30% ist gut
4. **Alerting einrichten** - Für produktiven Betrieb (siehe docs/monitoring_setup.md)

## 📈 Nächste Schritte

1. **Dashboard anpassen** - Edit in Grafana UI, dann Export als JSON
2. **Alerting hinzufügen** - Siehe docs/monitoring_setup.md
3. **Mehr Polygone/Gates** - data/geo/*.geojson erweitern
4. **Langzeit-Monitoring** - 24h+ laufen lassen für Trends

## 🔗 Dokumentation

- **Vollständige Monitoring-Doku:** `docs/monitoring_setup.md`
- **Engine-Doku:** `docs/open_sea_polygon_gate_engine.md`
- **Prometheus Docs:** https://prometheus.io/docs/
- **Grafana Docs:** https://grafana.com/docs/

---

**Status:** ✅ Alles bereit! Starte Docker und führe `./start_monitoring.sh` aus.
