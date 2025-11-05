# AIS-Based Anchorage Generation

## Overview

Generate **realistic anchorage polygons** from historical AIS data using **alpha-shapes** or **convex hulls**. This method analyzes vessel dwell patterns to automatically identify anchorage areas, providing more accurate boundaries than manually-drawn rectangles.

## Key Concepts

### Dwell Detection

A vessel is considered "dwelling" (anchored or waiting) when:
- **SOG ≤ 0.5 knots** (nearly stationary)
- **Position delta < 100 meters** (minimal movement)
- **Duration ≥ 60 minutes** (sustained dwell)

### Alpha-Shape Algorithm

**Alpha-shapes** are a generalization of convex hulls that can capture concave boundaries:

- **α (alpha) parameter**: Controls polygon "tightness"
  - Small α → tight fit around points (may create holes)
  - Large α → approaches convex hull
  - **Auto mode** (α = None): Automatically optimizes α

- **Convex Hull Fallback**: If alpha-shape fails, falls back to simple convex hull

### Polygon Refinement

1. **Buffer**: Expand polygon by N meters to include nearby areas
2. **Simplification**: Reduce vertex count while preserving shape
3. **Validation**: Ensure polygon is valid and non-self-intersecting

## Installation

Dependencies already installed:

```bash
# Already in .venv:
alphashape scipy shapely duckdb
```

## Usage

### Basic Command

```bash
cd spvx-lite
source .venv/bin/activate

# Generate AIS-based anchorages for a corridor
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages <corridor>
```

### Examples

#### 1. Suez Canal (Default Settings)

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez
```

**Output:** `data/geo/suez/anchorages_ais.geojson`

**Default settings:**
- Lookback: 60 days
- SOG max: 0.5 knots
- Min dwell: 60 minutes
- Buffer: 200 meters
- Alpha: Auto

#### 2. Gibraltar (Custom Dwell Threshold)

```bash
# Only include vessels dwelling for 2+ hours
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages gibraltar \
  --dwell-min-minutes 120
```

#### 3. Bosporus (Manual Alpha Parameter)

```bash
# Use tighter alpha-shape (smaller alpha = tighter fit)
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages bosporus \
  --alpha 0.5
```

#### 4. Extended Historical Window

```bash
# Use 90 days of history for more stable polygons
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --lookback-days 90
```

#### 5. Wider Buffer Zone

```bash
# Add 500m buffer around dwell points
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages gibraltar \
  --buffer-meters 500
```

#### 6. Lower Minimum Points Threshold

```bash
# Accept polygons from only 5 dwell points (less stable)
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages bosporus \
  --min-points 5
```

## CLI Reference

```
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages --help

Arguments:
  corridor               Corridor name: suez | gibraltar | bosporus [REQUIRED]

Options:
  --db-path TEXT         Path to DuckDB with AIS data [default: db/spvx.duckdb]
  --outdir TEXT          Output directory [default: data/geo]
  --lookback-days INT    Days of history to analyze [default: 60]
  --sog-max FLOAT        Maximum SOG (knots) for dwell [default: 0.5]
  --dwell-min-minutes INT Min dwell time (minutes) [default: 60]
  --buffer-meters FLOAT  Buffer around points (meters) [default: 200.0]
  --min-points INT       Min points for polygon [default: 10]
  --alpha FLOAT          Alpha-shape parameter (None = auto)
```

## Anchorage Definitions

### 🇪🇬 Suez Canal

```python
SUEZ_ANCHORAGES = [
    {
        "id": "ANCH_PORT_SAID_AIS",
        "bbox": (32.10, 31.30, 32.60, 31.60),  # Port Said area
    },
    {
        "id": "ANCH_GREAT_BITTER_LAKE_AIS",
        "bbox": (32.30, 30.20, 32.50, 30.55),  # Great Bitter Lake
    },
]
```

### 🇬🇮 Gibraltar

```python
GIBRALTAR_ANCHORAGES = [
    {
        "id": "ANCH_GIBRALTAR_BAY_AIS",
        "bbox": (-5.40, 36.08, -5.30, 36.16),  # Gibraltar Bay
    },
    {
        "id": "ANCH_ALGECIRAS_AIS",
        "bbox": (-5.50, 36.08, -5.38, 36.18),  # Algeciras
    },
]
```

### 🇹🇷 Bosporus

```python
BOSPORUS_ANCHORAGES = [
    {
        "id": "ANCH_BOSPORUS_N_AIS",
        "bbox": (28.95, 41.20, 29.20, 41.40),  # Black Sea
    },
    {
        "id": "ANCH_BOSPORUS_S_AIS",
        "bbox": (28.85, 40.90, 29.10, 41.10),  # Marmara Sea
    },
]
```

## Output Format

### anchorages_ais.geojson

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "ANCH_PORT_SAID_AIS",
        "kind": "ANCHORAGE_AIS",
        "source": "ais_dwell",
        "point_count": 142,
        "lookback_days": 60,
        "sog_max": 0.5,
        "dwell_min_minutes": 60
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lon, lat], ...]]
      }
    }
  ]
}
```

**Property Descriptions:**
- `id`: Unique anchorage identifier
- `kind`: Always "ANCHORAGE_AIS" for AIS-derived polygons
- `source`: "ais_dwell" (vs. manual or OSM-derived)
- `point_count`: Number of dwell points used for generation
- `lookback_days`: Historical window analyzed
- `sog_max`: SOG threshold used (knots)
- `dwell_min_minutes`: Minimum dwell duration used

## Integration Workflow

### Option 1: Replace Static Anchorages

```bash
# 1. Generate AIS-based anchorages
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez

# 2. Replace static anchorages with AIS-based ones
cp data/geo/suez/anchorages_ais.geojson data/geo/suez/polygons.geojson

# 3. Use in consumer
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/suez/gates.geojson \
  --polygons data/geo/suez/polygons.geojson
```

### Option 2: Merge Static + AIS Anchorages

```bash
# Merge both types
jq -s '{type: "FeatureCollection", features: [.[].features[]] | flatten}' \
  data/geo/suez/polygons.geojson \
  data/geo/suez/anchorages_ais.geojson \
  > data/geo/suez/polygons_merged.geojson
```

### Option 3: Use AIS for Validation

Compare AIS-derived boundaries with manually-drawn ones:

```bash
# Generate AIS anchorages
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez

# Visual comparison in GIS tool (QGIS, etc.)
# Load both: polygons.geojson (static) and anchorages_ais.geojson (AIS)
```

## Algorithm Details

### 1. Dwell Point Extraction

```sql
SELECT DISTINCT lon, lat, mmsi, ts
FROM open_sea_fixes
WHERE ts >= current_timestamp - interval '60 days'
  AND sog <= 0.5
  AND dwell_min >= 60
  AND lon BETWEEN ? AND ?
  AND lat BETWEEN ? AND ?
ORDER BY ts DESC
```

**Deduplication:** Points rounded to 5 decimal places (~11m precision)

### 2. Alpha-Shape Generation

```python
import alphashape

# Auto-optimize alpha
alpha_shape = alphashape.alphashape(points)

# Or manual alpha
alpha_shape = alphashape.alphashape(points, alpha=0.5)
```

**Geometry Handling:**
- If result is `Polygon` → use directly
- If result is `MultiPolygon` → take largest polygon
- If alpha-shape fails → convex hull fallback

### 3. Buffer Application

```python
# Convert meters to approximate degrees (rough: 1° ≈ 111km)
buffer_degrees = buffer_meters / 111_320.0
polygon = polygon.buffer(buffer_degrees)
```

### 4. Simplification

```python
# Douglas-Peucker algorithm
polygon = polygon.simplify(tolerance=0.0001, preserve_topology=True)
```

**Tolerance:** 0.0001° ≈ 11 meters

## Parameter Tuning Guide

### SOG Threshold (`--sog-max`)

| Value | Effect | Use Case |
|-------|--------|----------|
| 0.3 kn | Stricter (only truly stationary) | Tight anchorages |
| **0.5 kn** | **Default** (recommended) | **General use** |
| 1.0 kn | Looser (includes slow maneuvering) | Sparse data |

### Dwell Duration (`--dwell-min-minutes`)

| Value | Effect | Use Case |
|-------|--------|----------|
| 30 min | Include short stops | Dense traffic areas |
| **60 min** | **Default** (recommended) | **Standard anchorages** |
| 120 min | Only long-term anchorage | Exclude pilot zones |

### Buffer Size (`--buffer-meters`)

| Value | Effect | Use Case |
|-------|--------|----------|
| 100 m | Tight fit | Confined anchorages |
| **200 m** | **Default** | **General use** |
| 500 m | Wide margin | Include approach lanes |

### Alpha Parameter (`--alpha`)

| Value | Effect | Use Case |
|-------|--------|----------|
| 0.1 | Very tight (may create holes) | Complex shapes |
| 0.5 | Moderate tightness | Balanced |
| 1.0 | Loose (approaches convex hull) | Simple shapes |
| **None** | **Auto-optimize** | **Recommended start** |

### Lookback Window (`--lookback-days`)

| Value | Effect | Use Case |
|-------|--------|----------|
| 30 days | Recent behavior only | Rapidly changing areas |
| **60 days** | **Default** | **Stable patterns** |
| 90+ days | Long-term averages | Historical analysis |

## Troubleshooting

### Issue: No Anchorages Generated

**Error:** `Warning: No anchorages generated for suez.`

**Possible Causes:**
1. `open_sea_fixes` table doesn't exist or is empty
2. No vessels meet dwell criteria in lookback window
3. `min_points` threshold too high

**Solutions:**
```bash
# Check table exists
duckdb db/spvx.duckdb "SELECT COUNT(*) FROM open_sea_fixes;"

# Lower min_points threshold
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --min-points 5

# Increase lookback window
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --lookback-days 90

# Relax dwell criteria
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --sog-max 1.0 \
  --dwell-min-minutes 30
```

### Issue: Polygon Too Large

**Symptom:** Anchorage polygon extends far beyond expected area

**Solutions:**
```bash
# Reduce buffer
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --buffer-meters 50

# Use smaller alpha (tighter fit)
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --alpha 0.3

# Stricter dwell criteria
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --sog-max 0.3 \
  --dwell-min-minutes 120
```

### Issue: Polygon Too Small / Holes

**Symptom:** Fragmented polygon with holes or missing expected areas

**Solutions:**
```bash
# Increase buffer
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --buffer-meters 400

# Use larger alpha (looser fit)
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez \
  --alpha 1.0

# Let alpha auto-optimize
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages suez
```

### Issue: Alpha-Shape Crashes

**Error:** `Alpha-shape failed and fallback disabled`

**Solution:** Enable convex hull fallback (enabled by default):
```python
# In code:
config = AnchorageConfig(use_convex_hull_fallback=True)
```

## Testing

Run tests:

```bash
source .venv/bin/activate
PYTHONPATH=src pytest tests/test_anchorage_from_ais.py -v
```

**Test Coverage:**
- ✅ Alpha-shape polygon generation
- ✅ Convex hull fallback
- ✅ Insufficient points handling
- ✅ Buffer application
- ✅ SQL query generation (bbox, polygon_id filters)
- ✅ GeoJSON output
- ✅ Configuration validation
- ✅ Polygon simplification

## Performance

| Corridor | Points | Generation Time | Output Size |
|----------|--------|----------------|-------------|
| Suez     | ~200   | ~2-5s          | ~2-5 KB     |
| Gibraltar| ~150   | ~2-4s          | ~2-4 KB     |
| Bosporus | ~100   | ~1-3s          | ~1-3 KB     |

**Note:** Times depend on:
- Number of dwell points
- Alpha-shape complexity
- Buffer/simplification settings

## Comparison: Static vs. AIS-Based

| Aspect | Static Polygons | AIS-Based Polygons |
|--------|----------------|-------------------|
| **Accuracy** | Approximate | High (data-driven) |
| **Updates** | Manual | Automatic (regenerate) |
| **Coverage** | Fixed boundaries | Adapts to usage patterns |
| **Dependencies** | None | Requires AIS data |
| **Cold Start** | Ready immediately | Needs 30-60 days data |
| **Complexity** | Simple rectangles | Complex, realistic shapes |

**Recommendation:**
- **Production**: Start with static, migrate to AIS-based after 60 days
- **Research**: Use AIS-based from start for maximum accuracy

## Future Enhancements

### Phase 3: Temporal Dynamics

- [ ] Seasonal anchorage variation (summer vs. winter)
- [ ] Weekday vs. weekend patterns
- [ ] Time-of-day heatmaps

### Phase 4: OSM Integration

- [ ] Seed anchorages from OSM `seamark:type=anchorage`
- [ ] Validate AIS polygons against declared anchorage zones
- [ ] Merge OSM + AIS for complete coverage

### Phase 5: Advanced Algorithms

- [ ] DBSCAN clustering for multi-region anchorages
- [ ] Kernel density estimation for usage intensity
- [ ] Anomaly detection (unusual anchorage locations)

## Summary

AIS-based anchorage generation provides **data-driven, accurate polygons** that reflect actual vessel behavior. With alpha-shapes and smart defaults, it's production-ready after accumulating 60 days of AIS dwell data.

**Quick Start:**
```bash
# Generate anchorages for all corridors
for corridor in suez gibraltar bosporus; do
  PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages $corridor
done
```

**Output:**
- `data/geo/suez/anchorages_ais.geojson`
- `data/geo/gibraltar/anchorages_ais.geojson`
- `data/geo/bosporus/anchorages_ais.geojson`

Use these polygons directly in your open-sea consumer for realistic anchorage detection! 🎯
