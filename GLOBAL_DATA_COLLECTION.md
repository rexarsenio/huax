# Global Maritime Data Collection - MEGA Setup 🌍🚢

## Overview

Wir sammeln jetzt AIS-Daten von **ALLEN wichtigen maritimen Chokepoints weltweit**!

### Coverage

**54+ Gates** und **43+ Anchorages** über:
- **Südostasien**: Malacca, Singapore, Lombok, Sunda
- **Mittelmeer**: Gibraltar, Suez, Bosporus
- **Naher Osten**: Hormuz, Bab el-Mandeb
- **Europa**: Dover, Danish Straits, Rotterdam, Antwerp
- **Nord/Südamerika**: Panama, Houston, New York, LA, Santos
- **Ostasien**: Taiwan, Korea, Japan, Shanghai, Hong Kong
- **Afrika**: Cape of Good Hope, Lagos, Durban
- **Australien**: Sydney, Melbourne, Perth
- **Arktis/Antarktis**: Murmansk, Drake Passage

## Dateien

### 1. Gates (54 Chokepoints)
**Datei**: [`data/geo/global_gates_mega.geojson`](spvx-lite/data/geo/global_gates_mega.geojson)

**Regionen**:
- **Malacca Strait** (4): 100nm/50nm/25nm/10nm
- **Suez Canal** (8): North + South approaches 100nm/50nm/25nm/10nm
- **Panama Canal** (13): Atlantic/Pacific + Locks (from previous implementation)
- **Bosporus** (4): Black Sea + Marmara
- **Strait of Hormuz** (6): Gulf + Oman approaches
- **Bab el-Mandeb** (4): Red Sea + Aden
- **Gibraltar** (4): Atlantic + Mediterranean
- **Dover Strait** (2): North + South
- **Danish Straits** (2): Kattegat + Great Belt
- **Cape of Good Hope** (2): Atlantic + Indian Ocean
- Plus: Torres, Lombok, Sunda, Luzon, Taiwan, Korean, La Pérouse, Tsugaru, Magellan, Drake

### 2. Anchorages (43 Major Ports)
**Datei**: [`data/geo/global_anchorages_mega.geojson`](spvx-lite/data/geo/global_anchorages_mega.geojson)

**Major Hubs**:
- **Asia**: Singapore (2), Shanghai, Ningbo, Hong Kong, Shenzhen, Busan, Tokyo, Yokohama
- **Middle East**: Dubai, Ras Tanura, Fujairah
- **Europe**: Rotterdam, Antwerp, Istanbul (2), Primorsk, Novorossiysk, Murmansk
- **Mediterranean**: Port Said, Suez
- **Americas**: Houston, New York, LA, Santos, Rio, Buenos Aires, Vancouver, Prince Rupert, Montreal
- **Africa**: Cape Town, Durban, Lagos, Bonny
- **Australia**: Perth, Melbourne, Sydney

## Quick Start - Datensammlung starten 🚀

### Option 1: Alle Geometrien kombinieren

```bash
cd spvx-lite

# Merge alle GeoJSONs
python3 << 'EOF'
import json
from pathlib import Path

# Panama Gates
with open('data/geo/panama_gates.geojson') as f:
    panama_gates = json.load(f)

# Global Gates
with open('data/geo/global_gates_mega.geojson') as f:
    global_gates = json.load(f)

# Panama Anchorages
with open('data/geo/panama_polygons.geojson') as f:
    panama_anch = json.load(f)

# Global Anchorages
with open('data/geo/global_anchorages_mega.geojson') as f:
    global_anch = json.load(f)

# Combine
all_gates = {
    "type": "FeatureCollection",
    "features": panama_gates["features"] + global_gates["features"]
}

all_anchorages = {
    "type": "FeatureCollection",
    "features": panama_anch["features"] + global_anch["features"]
}

# Save
with open('data/geo/ALL_GATES.geojson', 'w') as f:
    json.dump(all_gates, f, indent=2)

with open('data/geo/ALL_ANCHORAGES.geojson', 'w') as f:
    json.dump(all_anchorages, f, indent=2)

print(f"✅ Created ALL_GATES.geojson with {len(all_gates['features'])} gates")
print(f"✅ Created ALL_ANCHORAGES.geojson with {len(all_anchorages['features'])} anchorages")
EOF
```

### Option 2: Consumer mit ALLEN Gates starten

```bash
cd spvx-lite

# Starte Consumer mit allen Geometrien
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/ALL_GATES.geojson \
  --polygons data/geo/ALL_ANCHORAGES.geojson
```

### Option 3: Background Consumer (dauerhaft)

```bash
cd spvx-lite

# Erstelle Start-Script
cat > START_GLOBAL_CONSUMER.sh << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

echo "🌍 Starting GLOBAL Maritime Data Collection..."
echo "📊 Monitoring 67+ gates and 45+ anchorages worldwide"

PYTHONPATH=src nohup python -m spvx.cli open-sea-consume \
  --gates data/geo/ALL_GATES.geojson \
  --polygons data/geo/ALL_ANCHORAGES.geojson \
  > logs/global_consumer.log 2>&1 &

PID=$!
echo "✅ Consumer started with PID $PID"
echo "$PID" > logs/global_consumer.pid

echo ""
echo "Monitor with: tail -f logs/global_consumer.log"
echo "Stop with: kill \$(cat logs/global_consumer.pid)"
SCRIPT

chmod +x START_GLOBAL_CONSUMER.sh

# Starte!
./START_GLOBAL_CONSUMER.sh
```

## Data Monitoring 📊

### Check Database Activity

```bash
cd spvx-lite
source .venv/bin/activate

python3 << 'EOF'
import duckdb
import pandas as pd

con = duckdb.connect("db/spvx.duckdb", read_only=True)

# Gate Crossings per Region
print("=== GATE CROSSINGS PER REGION (Last 24h) ===")
gates = con.execute("""
    SELECT
        CASE
            WHEN gate_id LIKE 'GATE_MALACCA%' THEN 'MALACCA_STRAIT'
            WHEN gate_id LIKE 'GATE_SUEZ%' THEN 'SUEZ_CANAL'
            WHEN gate_id LIKE 'GATE_PANAMA%' THEN 'PANAMA_CANAL'
            WHEN gate_id LIKE 'GATE_BOSPORUS%' THEN 'BOSPORUS'
            WHEN gate_id LIKE 'GATE_HORMUZ%' THEN 'STRAIT_OF_HORMUZ'
            WHEN gate_id LIKE 'GATE_GIBRALTAR%' THEN 'GIBRALTAR'
            WHEN gate_id LIKE 'GATE_BABELMANDEB%' THEN 'BAB_EL_MANDEB'
            ELSE 'OTHER'
        END as region,
        COUNT(*) as crossings,
        COUNT(DISTINCT mmsi) as unique_vessels
    FROM gate_crossings
    WHERE ts >= NOW() - INTERVAL '24 hours'
    GROUP BY region
    ORDER BY crossings DESC
""").df()
print(gates)

print("\n=== TOP 10 BUSIEST GATES (Last 24h) ===")
top_gates = con.execute("""
    SELECT
        gate_id,
        COUNT(*) as crossings,
        COUNT(DISTINCT mmsi) as unique_vessels
    FROM gate_crossings
    WHERE ts >= NOW() - INTERVAL '24 hours'
    GROUP BY gate_id
    ORDER BY crossings DESC
    LIMIT 10
""").df()
print(top_gates)

print("\n=== ANCHORAGE ACTIVITY (Last 24h) ===")
anchorages = con.execute("""
    SELECT
        polygon_id,
        COUNT(*) as events,
        COUNT(DISTINCT mmsi) as unique_vessels,
        AVG(EXTRACT(EPOCH FROM (ts_out - ts_in)) / 60.0) as avg_dwell_minutes
    FROM polygon_events
    WHERE ts_in >= NOW() - INTERVAL '24 hours'
      AND ts_out IS NOT NULL
    GROUP BY polygon_id
    ORDER BY events DESC
    LIMIT 10
""").df()
print(anchorages)

print("\n=== TOTAL COVERAGE ===")
totals = con.execute("""
    SELECT
        'Gates' as type,
        COUNT(DISTINCT gate_id) as unique_locations,
        COUNT(*) as total_events
    FROM gate_crossings
    UNION ALL
    SELECT
        'Anchorages' as type,
        COUNT(DISTINCT polygon_id) as unique_locations,
        COUNT(*) as total_events
    FROM polygon_events
""").df()
print(totals)

con.close()
EOF
```

### Real-time Monitoring Dashboard

```bash
# Watch script - updates every 5 seconds
cat > WATCH_GLOBAL.sh << 'SCRIPT'
#!/bin/bash
while true; do
    clear
    echo "🌍 GLOBAL MARITIME DATA COLLECTION - $(date)"
    echo "=================================================="

    cd "$(dirname "$0")"
    source .venv/bin/activate

    python3 << 'PYEOF'
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)

# Quick stats
stats = con.execute("""
    SELECT
        COUNT(DISTINCT gate_id) as active_gates,
        COUNT(*) as gate_crossings_24h
    FROM gate_crossings
    WHERE ts >= NOW() - INTERVAL '24 hours'
""").fetchone()

poly_stats = con.execute("""
    SELECT
        COUNT(DISTINCT polygon_id) as active_anchorages,
        COUNT(*) as anchorage_events_24h
    FROM polygon_events
    WHERE ts_in >= NOW() - INTERVAL '24 hours'
""").fetchone()

print(f"\n📊 LAST 24 HOURS:")
print(f"  Active Gates: {stats[0]}")
print(f"  Gate Crossings: {stats[1]:,}")
print(f"  Active Anchorages: {poly_stats[0]}")
print(f"  Anchorage Events: {poly_stats[1]:,}")

# Hottest gates right now
print(f"\n🔥 HOTTEST GATES (Last hour):")
hot = con.execute("""
    SELECT gate_id, COUNT(*) as crossings
    FROM gate_crossings
    WHERE ts >= NOW() - INTERVAL '1 hour'
    GROUP BY gate_id
    ORDER BY crossings DESC
    LIMIT 5
""").fetchall()
for gate_id, count in hot:
    print(f"  {gate_id}: {count}")

con.close()
PYEOF

    echo ""
    echo "=================================================="
    echo "Press Ctrl+C to stop | Refreshing every 5s"
    sleep 5
done
SCRIPT

chmod +x WATCH_GLOBAL.sh
./WATCH_GLOBAL.sh
```

## Expected Data Volume 📈

Mit **67+ Gates** und **45+ Anchorages** weltweit:

**Konservative Schätzung** (basiert auf typischen AIS-Raten):
- **Gate Crossings**: ~500-2000 pro Stunde (12,000-48,000 pro Tag)
- **Anchorage Events**: ~200-800 pro Stunde (4,800-19,200 pro Tag)
- **Unique Vessels**: ~5,000-15,000 pro Tag
- **Database Growth**: ~50-200 MB pro Tag

**Peak Times** (Rush Hours in major hubs):
- Singapore: 06:00-10:00 UTC
- Rotterdam/Antwerp: 08:00-12:00 UTC
- Houston/LA: 14:00-18:00 UTC
- Shanghai/Hong Kong: 00:00-04:00 UTC

## Optimization Tips ⚡

### 1. Disk Space Management

```bash
# Check database size
du -h db/spvx.duckdb

# Auto-cleanup old data (keep 90 days)
cat > CLEANUP_OLD_DATA.sh << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

python3 << 'EOF'
import duckdb
con = duckdb.connect("db/spvx.duckdb")

# Delete gate crossings older than 90 days
deleted_gates = con.execute("""
    DELETE FROM gate_crossings
    WHERE ts < NOW() - INTERVAL '90 days'
""").fetchone()[0]

# Delete polygon events older than 90 days
deleted_poly = con.execute("""
    DELETE FROM polygon_events
    WHERE ts_in < NOW() - INTERVAL '90 days'
""").fetchone()[0]

print(f"✅ Deleted {deleted_gates:,} old gate crossings")
print(f"✅ Deleted {deleted_poly:,} old polygon events")

# Vacuum to reclaim space
con.execute("VACUUM")
print(f"✅ Database optimized")

con.close()
EOF
SCRIPT

chmod +x CLEANUP_OLD_DATA.sh

# Run weekly via cron
# 0 2 * * 0 /path/to/CLEANUP_OLD_DATA.sh
```

### 2. Performance Tuning

Add to your consumer config:

```python
# In config.yml or environment
CONSUMER_BATCH_SIZE=1000  # Process in batches
CONSUMER_FLUSH_INTERVAL=60  # Flush every 60s
DUCKDB_MEMORY_LIMIT="8GB"  # Adjust based on available RAM
```

### 3. Parallel Consumers (Advanced)

Split by region for better performance:

```bash
# Asia Consumer
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/asia_gates.geojson \
  --polygons data/geo/asia_anchorages.geojson &

# Europe Consumer
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/europe_gates.geojson \
  --polygons data/geo/europe_anchorages.geojson &

# Americas Consumer
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/americas_gates.geojson \
  --polygons data/geo/americas_anchorages.geojson &
```

## Troubleshooting 🔧

### Consumer not starting?

```bash
# Check logs
tail -f logs/global_consumer.log

# Common issues:
# 1. Port already in use → Kill old consumer
pkill -f "open-sea-consume"

# 2. GeoJSON syntax error → Validate
python3 -c "import json; json.load(open('data/geo/ALL_GATES.geojson'))"

# 3. Database locked → Wait or kill locks
lsof db/spvx.duckdb
```

### Low data volume?

```bash
# Check AIS stream connection
tail -f logs/ais-ingest.log

# Verify geometries are correct
python3 -c "
import json
with open('data/geo/ALL_GATES.geojson') as f:
    data = json.load(f)
    print(f'Total gates: {len(data[\"features\"])}')
    for feat in data['features'][:5]:
        print(f\"  {feat['properties']['gate_id']}: {feat['geometry']['coordinates']}\")
"
```

## Next Steps 🎯

1. **Starte Consumer** mit globalen Geometrien (siehe oben)
2. **Warte 24-48h** für erste signifikante Datenmengen
3. **Run Aggregation** um tägliche Metriken zu berechnen
4. **Dashboard Integration** - zeige globale Heatmap
5. **Alerts Setup** - Prometheus alerts für kritische Chokepoints

## Visualization Ideas 💡

Mit diesen Daten kannst du bauen:

- **Global Chokepoint Heatmap**: Echtzeit-Flux pro Region
- **Transit Time Dashboard**: Suez vs Panama vs Cape of Good Hope Vergleich
- **Queue Prediction**: ML-basierte Wartezeit-Vorhersagen
- **Geopolitical Alerts**: Traffic-Drops als Frühindikatoren
- **Seasonal Patterns**: Winterrouten vs Sommerrouten
- **Carbon Footprint**: Route-Optimierung basierend auf Traffic

---

**Created**: 2025-10-28
**Status**: Ready to deploy
**Coverage**: 67+ Gates, 45+ Anchorages, Global
**Expected Volume**: 15,000-65,000 events/day

🚢 **HAPPY DATA COLLECTING!** 🌍
