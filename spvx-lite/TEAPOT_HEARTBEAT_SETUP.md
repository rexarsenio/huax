# 🛢️ Teapot Heartbeat - Complete Setup Guide

## Malacca → OPL Singapore → Shandong Supply Chain

This guide shows how to set up **real episode detection** (not test data) for tracking the critical teapot crude oil supply chain.

---

## 📊 Overview: The Full Pipeline

```
TH-1: Derive Anchorages       (DBSCAN clustering from AIS dwell)
  ↓
TH-2: Episode Detection        (Polygon crossing detection)
  ↓
TH-3: Baseline & Z-Scores      (Anomaly detection)
  ↓
TH-4: REST API                 (Trading intelligence endpoints)
```

---

## 🚀 Quick Start

### Prerequisites

```bash
cd ~/Desktop/huax/spvx-lite
git pull
source .venv/bin/activate
```

### Step 0: Database & Configuration Setup

```bash
# Create database tables and anchorage definitions
python3 setup_supply_chain.py
```

This creates:
- ✅ Database tables (anchorage_polygons, anchorage_episodes, anchorage_daily_dwell)
- ✅ 6 Anchorage definitions (OPL + 5 Shandong ports)
- ✅ GATE_MALACCA_v1 in gates.geojson

### Step 1: Start Consumer (Collect AIS Data)

```bash
# Restart consumer with new Malacca gate
./stop_consumer.sh
./start_consumer.sh

# Monitor logs
tail -f logs/open_sea_consumer.log
```

**Wait 4-6 hours** for sufficient AIS data to accumulate.

---

## 🔄 The Full Pipeline (After AIS Data Collection)

### TH-1: Derive Anchorage Polygons (Optional)

If you want to derive anchorages from actual AIS dwell patterns instead of using pre-defined locations:

```bash
# For OPL Singapore (derive from actual vessel dwell)
PYTHONPATH=src python -m spvx.cli derive-anchorage \
  --name ANCH_OPL_SIN \
  --feature-name "OPL Singapore Anchorage" \
  --center-lat 1.20 \
  --center-lon 103.75 \
  --radius-km 25 \
  --days 14 \
  --sog-max-kn 0.5 \
  --eps-m 350 \
  --min-samples 20

# For Qingdao
PYTHONPATH=src python -m spvx.cli derive-anchorage \
  --name ANCH_QINGDAO \
  --feature-name "Qingdao Anchorage" \
  --center-lat 36.07 \
  --center-lon 120.33 \
  --radius-km 30 \
  --days 14
```

**Note**: This requires significant AIS data in the region. For quick setup, use the pre-defined locations from `setup_supply_chain.py`.

---

### TH-2: Detect Episodes ⭐

This is the core engine that detects when vessels enter/exit anchorages:

```bash
# Detect all episodes from collected AIS data
PYTHONPATH=src python -m spvx.cli anchorage-episodes \
  --db db/spvx.duckdb \
  --polygons data/geo/polygons.geojson \
  --min-dwell-min 60
```

**Output Example:**
```
TH-2: Anchorage Episode Detection

Loaded 6 anchorage polygons from data/geo/polygons.geojson
Processing AIS fixes from 2025-10-30 to 2025-11-06
Processing 540,228 AIS fixes
Created 1,234 new episodes, 45 sessions remain open

Episode Summary:
  ANCH_OPL_SIN              :   156 episodes |   89 vessels |  18.3h avg
  ANCH_QINGDAO              :   125 episodes |   78 vessels |  24.5h avg
  ANCH_RIZHAO               :    98 episodes |   62 vessels |  22.0h avg
  ANCH_YANTAI               :    45 episodes |   32 vessels |  20.1h avg
  ANCH_LONGKOU              :    23 episodes |   18 vessels |  19.5h avg
  ANCH_LANSHAN              :    12 episodes |   10 vessels |  21.2h avg
```

---

### TH-3: Compute Baselines & Z-Scores ⭐

Aggregates episodes into daily metrics and computes anomaly scores:

```bash
# Compute daily metrics and baselines
PYTHONPATH=src python -m spvx.cli anchorage-backfill \
  --db db/spvx.duckdb \
  --lookback-days 90 \
  --min-samples 20
```

**Output Example:**
```
TH-3: Anchorage Baseline & Z-Score Enrichment

Computing daily metrics from 2025-10-30 to 2025-11-06
Created/updated 42 daily metric rows

Computing baselines with 90 day lookback, min 20 samples
Computing baselines from 42 daily records
Created 28 baseline buckets (DoW × WoY)

Enriched 38 records with Z-scores
Detected 3 anomalies (|Z| > 2.0)

Recent anomalies (last 7 days):
  2025-11-02 | ANCH_OPL_SIN        |  35 eps |  28.0h | Z=+2.80
  2025-11-03 | ANCH_QINGDAO        |  32 eps |  36.5h | Z=+2.10
  2025-11-05 | ANCH_RIZHAO         |  28 eps |  32.0h | Z=+2.05

Daily Metrics Summary:
  ✅ ANCH_OPL_SIN               :   7 days |  18.3h avg |  1 anomalies | Latest: 2025-11-05
  ✅ ANCH_QINGDAO               :   7 days |  24.5h avg |  1 anomalies | Latest: 2025-11-05
  ✅ ANCH_RIZHAO                :   7 days |  22.0h avg |  1 anomalies | Latest: 2025-11-05
  ✅ ANCH_YANTAI                :   6 days |  20.1h avg |  0 anomalies | Latest: 2025-11-05
  ✅ ANCH_LONGKOU               :   5 days |  19.5h avg |  0 anomalies | Latest: 2025-11-04
  ✅ ANCH_LANSHAN               :   4 days |  21.2h avg |  0 anomalies | Latest: 2025-11-03
```

---

### TH-4: Test the API ⭐

```bash
# Start API server (if not already running)
PYTHONPATH=src python -m uvicorn spvx.api_app:app --port 8000 --reload

# In another terminal:

# 1. Summary endpoint (Mr. Liu's primary use case)
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_OPL_SIN,ANCH_QINGDAO&window=d7" | python -m json.tool

# 2. Daily time-series
curl "http://localhost:8000/api/anchorage/daily?anchorage_ids=ANCH_QINGDAO&start=2025-11-01" | python -m json.tool

# 3. Individual episodes
curl "http://localhost:8000/api/anchorage/episodes?anchorage_id=ANCH_OPL_SIN&limit=10" | python -m json.tool
```

---

## 🔍 Verification & Monitoring

### Check Supply Chain Coverage

```bash
python3 diagnose_supply_chain.py
```

Expected output:
```
🔍 Malacca → OPL → Shandong Supply Chain Coverage
================================================================================

1️⃣  MALACCA PULSE
   ✅ GATE_MALACCA_v1: 1,234 crossings | 7/7 active days
   ✅ SIS Data: CHOKEPOINT_MALACCA->UNK

2️⃣  OPL SINGAPORE DWELL
   ✅ ANCH_OPL_SIN - OPL Singapore
      Episodes (7d): 156 | Vessels: 89 | Avg dwell: 18.3h
      Latest: 2025-11-05 | 22 episodes | 18.0h median | Z=0.33

3️⃣  SHANDONG ANCHORAGES
   ✅ ANCH_QINGDAO: 125 episodes | 78 vessels | 24.5h avg
   ✅ ANCH_RIZHAO: 98 episodes | 62 vessels | 22.0h avg
   [... more ...]

4️⃣  SUPPLY CHAIN COMPLETENESS
   ✅ Malacca Gate Crossings
   ✅ Malacca Sea State (SIS)
   ✅ OPL Singapore Anchorage
   ✅ Shandong Anchorages: 5/5 with data

   🎉 SUPPLY CHAIN COMPLETE!
```

---

## 📈 Trading Intelligence Use Cases

### 1. Malacca Pulse → OPL Congestion Signal

```bash
# Check if Malacca traffic spike leads to OPL congestion
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_OPL_SIN&window=d14" | jq '.anchorages[0].statistics.z_dwell.max'
```

If **Z-score > 2.0**: 🔴 High congestion at OPL

### 2. OPL → Shandong Queue Prediction

```bash
# Check OPL dwell → Shandong dwell lag
curl "http://localhost:8000/api/anchorage/daily?anchorage_ids=ANCH_OPL_SIN,ANCH_QINGDAO&start=2025-10-15" | jq '.anchorages'
```

Look for **2-3 week lag** between OPL spike and Shandong congestion.

### 3. Multi-Port Comparison

```bash
# Compare all 5 Shandong ports
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO,ANCH_YANTAI,ANCH_LONGKOU,ANCH_LANSHAN&window=d7" | jq '.anchorages[].latest | {id: .anchorage_id, episodes: .episodes, dwell: .dwell_median_h, z: .z_dwell}'
```

Identifies which ports are experiencing congestion.

---

## ⚙️ Maintenance & Updates

### Daily Operations

```bash
# 1. Process new episodes (run daily)
PYTHONPATH=src python -m spvx.cli anchorage-episodes

# 2. Update baselines (run daily)
PYTHONPATH=src python -m spvx.cli anchorage-backfill

# 3. Update API snapshot
./UPDATE_API_SNAPSHOT.sh
```

### Weekly Operations

```bash
# Collect sea-state data for Malacca corridor
PYTHONPATH=src python -m spvx.cli ingest-sea-state --provider auto --lookback-days 7

# Migrate sea-state schema
python3 migrate_sea_state.py

# Update API
./UPDATE_API_SNAPSHOT.sh
```

---

## 🐛 Troubleshooting

### No Episodes Detected

**Problem**: TH-2 returns 0 episodes

**Solutions**:
```bash
# Check if anchorage polygons exist
python3 -c "import json; print(json.load(open('data/geo/polygons.geojson'))['features'])"

# Check if AIS data exists in region
python3 << 'EOF'
import duckdb
con = duckdb.connect('db/spvx.duckdb', read_only=True)
result = con.execute("""
    SELECT COUNT(*) FROM open_sea_fixes
    WHERE lat BETWEEN 35.0 AND 38.0
      AND lon BETWEEN 119.0 AND 122.0
      AND ts >= CURRENT_DATE - INTERVAL '7 days'
""").fetchone()[0]
print(f"Shandong region AIS fixes (7d): {result:,}")
con.close()
EOF
```

### Baseline Insufficient

**Problem**: `baseline_insufficient: true` in API responses

**Cause**: Not enough historical data (< 20 samples per DoW×WoY bucket)

**Solution**: Wait for more data or reduce `--min-samples`:
```bash
PYTHONPATH=src python -m spvx.cli anchorage-backfill --min-samples 10
```

### API Returns Empty

**Problem**: API shows "No data available"

**Solution**: Sync data to API database:
```bash
./UPDATE_API_SNAPSHOT.sh
```

---

## 📚 Reference: CLI Commands

### TH-1: Derive Anchorage
```bash
PYTHONPATH=src python -m spvx.cli derive-anchorage --help
```

### TH-2: Episode Detection
```bash
PYTHONPATH=src python -m spvx.cli anchorage-episodes --help
```

### TH-3: Baseline & Z-Scores
```bash
PYTHONPATH=src python -m spvx.cli anchorage-backfill --help
```

---

## 🎯 Success Criteria

✅ **Malacca Pulse**: 500+ crossings per week
✅ **OPL Episodes**: 100+ episodes per week, avg dwell 15-20h
✅ **Shandong Episodes**: 200+ episodes per week across all ports
✅ **Anomaly Detection**: Z-scores > 2.0 for congestion events
✅ **API Response Time**: < 200ms for summary endpoint

---

## 💡 Next Steps

1. **Automate Pipeline**: Create cron jobs for daily TH-2, TH-3 execution
2. **Add Webhooks**: Alert on anomalies (Z > 2.5)
3. **Expand Coverage**: Add more anchorages (Rotterdam, Fujairah, etc.)
4. **Machine Learning**: Predict congestion from Malacca flux

---

## 📞 Support

For issues:
- Check logs: `logs/open_sea_consumer.log`
- Run diagnostics: `python3 diagnose_supply_chain.py`
- Verify data: `python3 diagnose_data.py`

---

**Built with**: DuckDB, Shapely, DBSCAN, FastAPI
**For**: Teapot Market Intelligence (Mr. Liu's Team)
**Status**: ✅ Production Ready
