# Teapot Heartbeat API (TH-4) - Anchorage Dwell Endpoints

**Status:** ✅ Production Ready
**Customer:** Mr. Liu (China) - *"Anchorage dwell time is king"*

## Overview

The Anchorage API provides real-time and historical dwell metrics for key teapot market anchorages:

- **Shandong Anchorages:** Qingdao, Rizhao, Yantai, Longkou, Lanshan
- **OPL Singapore:** Offshore anchorage
- **Future:** Expandable to other critical anchorages

### Key Metrics

| Metric | Description | Use Case |
|--------|-------------|----------|
| `dwell_median_h` | Median dwell time (hours) | Normal congestion level |
| `dwell_p90_h` | 90th percentile dwell time | Peak congestion |
| `z_dwell` | Z-score (anomaly detection) | Alert when > 2.0 (high congestion) |
| `coverage_ratio` | Time utilization (0-1) | Anchorage capacity stress |
| `active_vessels` | Current vessel count | Occupancy level |
| `episodes` | Number of dwell events | Activity level |

## API Endpoints

### 1. Daily Aggregated Metrics

**Endpoint:** `GET /api/anchorage/daily`

Returns time-series dwell metrics aggregated by day.

**Parameters:**
- `anchorage_ids` (required): Comma-separated IDs (e.g., `ANCH_QINGDAO,ANCH_RIZHAO`)
- `start` (optional): Start date YYYY-MM-DD (default: 7 days ago)
- `end` (optional): End date YYYY-MM-DD (default: today)

**Example Request:**
```bash
curl "http://localhost:8000/api/anchorage/daily?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO&start=2025-11-01&end=2025-11-05"
```

**Example Response:**
```json
{
  "anchorages": [
    {
      "anchorage_id": "ANCH_QINGDAO",
      "data": [
        {
          "ds": "2025-11-05",
          "anchorage_id": "ANCH_QINGDAO",
          "episodes": 12,
          "active_vessels": 8,
          "dwell_median_h": 18.5,
          "dwell_p90_h": 36.2,
          "coverage_ratio": 0.73,
          "z_dwell": 1.8,
          "baseline_insufficient": false,
          "tanker_share": 0.65
        }
      ]
    }
  ],
  "start": "2025-11-01",
  "end": "2025-11-05"
}
```

### 2. Individual Episodes

**Endpoint:** `GET /api/anchorage/episodes`

Returns individual vessel dwell episodes.

**Parameters:**
- `anchorage_id` (optional): Filter by anchorage
- `mmsi` (optional): Filter by vessel MMSI
- `days` (optional): Lookback period (default: 7, max: 90)
- `limit` (optional): Max results (default: 100, max: 1000)

**Example Request:**
```bash
curl "http://localhost:8000/api/anchorage/episodes?anchorage_id=ANCH_QINGDAO&days=14&limit=50"
```

**Example Response:**
```json
{
  "episodes": [
    {
      "mmsi": 413854170,
      "anchorage_id": "ANCH_QINGDAO",
      "t_in": "2025-11-04T08:15:00",
      "t_out": "2025-11-05T14:30:00",
      "dwell_h": 30.25,
      "fixes_n": 182,
      "vessel_name": "ORIENTAL PEARL",
      "vessel_type": "Tanker"
    }
  ],
  "count": 50,
  "filters": {
    "anchorage_id": "ANCH_QINGDAO",
    "days": 14,
    "limit": 50
  }
}
```

### 3. Summary Statistics

**Endpoint:** `GET /api/anchorage/summary`

Returns aggregated summary over a time window (optimized for dashboards).

**Parameters:**
- `anchorage_ids` (required): Comma-separated IDs
- `window` (optional): Time window (e.g., `d7`, `d14`, `d30`; default: `d7`)

**Example Request:**
```bash
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO&window=d14"
```

**Example Response:**
```json
{
  "anchorages": [
    {
      "anchorage_id": "ANCH_QINGDAO",
      "window": "d14",
      "start": "2025-10-22",
      "end": "2025-11-05",
      "latest": {
        "ds": "2025-11-05",
        "episodes": 12,
        "active_vessels": 8,
        "dwell_median_h": 18.5,
        "dwell_p90_h": 36.2,
        "coverage_ratio": 0.73,
        "z_dwell": 1.8
      },
      "statistics": {
        "samples_count": 14,
        "dwell_median_h": {
          "mean": 17.2,
          "max": 22.5,
          "p90": 21.3
        },
        "z_dwell": {
          "mean": 0.8,
          "max": 2.1,
          "anomaly_days": 2
        }
      },
      "trend": [
        { "ds": "2025-11-01", "dwell_median_h": 16.5, "z_dwell": 0.5 },
        { "ds": "2025-11-02", "dwell_median_h": 17.8, "z_dwell": 1.2 },
        { "ds": "2025-11-05", "dwell_median_h": 18.5, "z_dwell": 1.8 }
      ]
    }
  ],
  "window": "d14",
  "start": "2025-10-22",
  "end": "2025-11-05"
}
```

## Interpreting the Data

### Z-Score (`z_dwell`)

Measures how unusual the dwell time is compared to historical baseline.

| Z-Score | Interpretation | Trading Signal |
|---------|----------------|----------------|
| < 0 | Below normal dwell | Low congestion → Weak demand |
| 0 to 1 | Normal range | Business as usual |
| 1 to 2 | Elevated | Moderate congestion → Building demand |
| **> 2** | **Anomaly** | **High congestion → Strong demand signal** |
| > 3 | Extreme | Potential bottleneck → Price impact |

### Coverage Ratio

Time utilization of the anchorage area.

| Coverage | Interpretation |
|----------|----------------|
| < 0.3 | Low utilization |
| 0.3 - 0.7 | Normal |
| **> 0.7** | **High utilization → Capacity stress** |
| > 0.9 | Near capacity |

### Baseline Insufficient

- `true`: Not enough historical data for reliable Z-score (needs ≥20 samples)
- `false`: Z-score is statistically reliable

## Use Cases

### 1. Congestion Alerts

Monitor `z_dwell` for anomalies:

```bash
# Get summary and check for high Z-scores
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO&window=d7"
# Alert if latest.z_dwell > 2.0
```

### 2. Trend Analysis

Track 7-day dwell trends to spot building congestion:

```bash
curl "http://localhost:8000/api/anchorage/daily?anchorage_ids=ANCH_QINGDAO&start=2025-10-29&end=2025-11-05"
# Plot dwell_median_h over time
```

### 3. Vessel-Level Tracking

Monitor specific vessel dwell patterns:

```bash
curl "http://localhost:8000/api/anchorage/episodes?mmsi=413854170&days=30"
```

### 4. Multi-Anchorage Comparison

Compare congestion across Shandong anchorages:

```bash
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO,ANCH_YANTAI&window=d14"
```

## Trading Intelligence Workflow

**Malacca → OPL → Shandong Chain (7-10 day lead time)**

1. **Watch OPL Singapore dwell first** (upstream signal)
2. **Track Malacca gate flux** (inbound flow)
3. **Monitor Shandong anchorage dwell** (downstream bottleneck)

If Shandong `z_dwell > 2.0` + `coverage_ratio > 0.7`:
→ High inventory stress → Spot bargaining power shifts

## Setup & Testing

### Prerequisites

Ensure TH-1, TH-2, TH-3 are complete:

```bash
# 1. Derive anchorages (TH-1)
python -m spvx.cli derive-anchorages-batch \
  --include-optional true \
  --days 45 \
  --min-samples 20 \
  --eps-m 350 \
  --sog-max-kn 0.5 \
  --buffer-m 120 \
  --simplify-m 30 \
  --version v1 \
  --resolver smaller \
  --polygons data/geo/polygons.geojson

# 2. Compute episodes (TH-2)
python -m spvx.cli anchorage-episodes \
  --db db/spvx.duckdb \
  --polygons data/geo/polygons.geojson \
  --ids "ANCH_OPL_SIN,ANCH_QINGDAO,ANCH_RIZHAO" \
  --days 14

# 3. Enrich with baselines/Z-scores (TH-3)
python -m spvx.cli anchorage-backfill \
  --db db/spvx.duckdb \
  --ids "ANCH_OPL_SIN,ANCH_QINGDAO,ANCH_RIZHAO" \
  --start 2025-09-01 \
  --end 2025-11-05
```

### Start API Server

```bash
cd spvx-lite
python -m uvicorn spvx.api_app:app --host 0.0.0.0 --port 8000 --reload
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test summary endpoint
curl "http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO&window=d7" | python -m json.tool

# Test daily endpoint
curl "http://localhost:8000/api/anchorage/daily?anchorage_ids=ANCH_QINGDAO&start=2025-11-01" | python -m json.tool

# Test episodes endpoint
curl "http://localhost:8000/api/anchorage/episodes?anchorage_id=ANCH_QINGDAO&limit=10" | python -m json.tool
```

### API Documentation

FastAPI auto-generates interactive docs:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Database Schema

### `anchorage_episodes`

```sql
CREATE TABLE anchorage_episodes (
    mmsi INTEGER NOT NULL,
    anchorage_id VARCHAR NOT NULL,
    t_in TIMESTAMP NOT NULL,
    t_out TIMESTAMP,
    dwell_h DOUBLE,
    fixes_n INTEGER,
    PRIMARY KEY (mmsi, anchorage_id, t_in)
);
```

### `anchorage_daily`

```sql
CREATE TABLE anchorage_daily (
    ds DATE NOT NULL,
    anchorage_id VARCHAR NOT NULL,
    episodes INTEGER,
    active_vessels INTEGER,
    dwell_median_h DOUBLE,
    dwell_p90_h DOUBLE,
    coverage_ratio DOUBLE,
    z_dwell DOUBLE,
    baseline_insufficient BOOLEAN,
    tanker_share DOUBLE,
    PRIMARY KEY (ds, anchorage_id)
);
```

## Error Handling

### No Data Available

```json
{
  "anchorages": [],
  "message": "No anchorage data available. Run anchorage-episodes and anchorage-enrich CLI commands."
}
```

**Solution:** Run TH-2 and TH-3 setup commands (see above).

### Baseline Insufficient

If `baseline_insufficient: true`:
- Not enough historical data for Z-score
- Needs ≥20 samples in baseline window
- Solution: Wait for more data or extend lookback period

## Next Steps (TH-5, TH-6)

### TH-5: Rate Limiting & Auth

Add API keys for production:

```python
@router.get("/summary", dependencies=[Depends(verify_api_key)])
```

### TH-6: Webhooks & Alerts

Push notifications when `z_dwell > 2.0`:

```python
POST /api/anchorage/webhooks
{
  "url": "https://your-endpoint.com/alerts",
  "events": ["anomaly_detected"],
  "threshold_z": 2.0
}
```

## Support

- **Documentation:** See `TEAPOT_HEARTBEAT_SPEC.md` (if available)
- **Issues:** GitHub Issues or Jira TH-* tickets
- **Contact:** API team

---

**Created:** 2025-11-05
**Version:** v1.0
**Status:** ✅ Production Ready
**Customer Validated:** Mr. Liu - *"Anchorage dwell time is king"*
