# Maritime Corridor Builder - Complete Guide

## Overview

The **corridor builder** generates geodetically accurate approach gates and anchorage polygons for major maritime chokepoints: **Suez Canal**, **Strait of Gibraltar**, and **Turkish Straits (Bosporus)**.

## Quick Start

### Generate All Corridors (with defaults)

```bash
cd spvx-lite
source .venv/bin/activate

# Suez Canal
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor suez

# Strait of Gibraltar
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar

# Bosporus (Turkish Straits)
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor bosporus
```

This generates:
- `data/geo/suez/gates.geojson` & `polygons.geojson`
- `data/geo/gibraltar/gates.geojson` & `polygons.geojson`
- `data/geo/bosporus/gates.geojson` & `polygons.geojson`

## Corridor Specifications

### 🇪🇬 Suez Canal

**Approaches:**
- **North (Port Said)**: Entry at 32.301°E, 31.265°N
- **South (Port of Suez)**: Entry at 32.566°E, 29.966°N

**Gate Configuration:**
| Distance | Half-Width | Total Width | Purpose |
|----------|-----------|-------------|---------|
| 10 nm    | 1.0 nm    | 2.0 nm      | Near approach |
| 25 nm    | 1.5 nm    | 3.0 nm      | Medium approach |
| 50 nm    | 2.0 nm    | 4.0 nm      | Far approach |
| 100 nm   | 2.5 nm    | 5.0 nm      | Very far approach |
| 150 nm   | 3.0 nm    | 6.0 nm      | Extended approach |

**Anchorages:**
- Port Said Anchorage
- Great Bitter Lake Anchorage (inland)

**Total Gates:** 10 (5 distances × 2 approaches)

---

### 🇬🇮 Strait of Gibraltar

**Approaches:**
- **West (Atlantic)**: Entry at -5.45°E, 35.95°N
- **East (Mediterranean)**: Entry at -5.30°E, 35.88°N

**Gate Configuration:**
| Distance | Half-Width | Total Width | Purpose |
|----------|-----------|-------------|---------|
| 10 nm    | 1.5 nm    | 3.0 nm      | Near approach |
| 25 nm    | 2.0 nm    | 4.0 nm      | Medium approach |
| 50 nm    | 2.5 nm    | 5.0 nm      | Far approach |
| 100 nm   | 3.0 nm    | 6.0 nm      | Very far approach |
| 150 nm   | 3.5 nm    | 7.0 nm      | Extended approach |

**Rationale:** Gibraltar has wider approaches than Suez due to greater traffic dispersion and wider strait.

**Anchorages:**
- Gibraltar Bay Anchorage
- Algeciras Anchorage

**Total Gates:** 10 (5 distances × 2 approaches)

---

### 🇹🇷 Turkish Straits (Bosporus)

**Approaches:**
- **North (Black Sea)**: Entry at 29.08°E, 41.23°N
- **South (Marmara Sea)**: Entry at 29.00°E, 41.02°N

**Gate Configuration:**
| Distance | Half-Width | Total Width | Purpose |
|----------|-----------|-------------|---------|
| 10 nm    | 0.75 nm   | 1.5 nm      | Near approach |
| 25 nm    | 1.0 nm    | 2.0 nm      | Medium approach |
| 50 nm    | 1.5 nm    | 3.0 nm      | Far approach |

**Rationale:** Bosporus requires narrower gates due to confined geography and tighter traffic lanes. Only 3 distances due to shorter approaches.

**Anchorages:**
- Bosporus North Anchorage (Black Sea)
- Bosporus South Anchorage (Marmara Sea)

**Total Gates:** 6 (3 distances × 2 approaches)

---

## CLI Usage

### Basic Command Structure

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor <corridor> [OPTIONS]
```

### Options

```
Arguments:
  corridor    Corridor name: suez | gibraltar | bosporus [REQUIRED]

Options:
  --outdir TEXT          Output directory [default: data/geo]
  --distances TEXT       CSV of distances in nm (empty = corridor defaults)
  --width-map TEXT       CSV mapping 'dist:halfwidth' (empty = corridor defaults)
  --use-overpass BOOL    Fetch OSM seamark data [default: True]
  --help                 Show help message
```

### Examples

#### 1. Default Configuration (Recommended)

```bash
# Use corridor-specific defaults for distances and widths
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor suez
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor bosporus
```

#### 2. Custom Distances

```bash
# Only generate 10nm and 50nm gates for Gibraltar
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar \
  --distances "10,50"
```

#### 3. Custom Widths

```bash
# Use wider gates for Gibraltar
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar \
  --width-map "10:2.0,25:2.5,50:3.0,100:3.5,150:4.0"
```

#### 4. Offline Mode (No Overpass API)

```bash
# Use fallback axes instead of fetching from OSM
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor bosporus \
  --use-overpass false
```

#### 5. Custom Output Directory

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor suez \
  --outdir "data/custom_gates"
```

## Technical Details

### Geodesic Calculations

All calculations use **WGS84 ellipsoid** via `pyproj.Geod`:

- **Forward**: Point + bearing + distance → new point
- **Inverse**: Two points → bearing + distance
- **Orthogonal transects**: Gates perpendicular to corridor axis (±90°)

### Axis Determination Strategy

For each approach:

1. **With Overpass API** (`--use-overpass true`):
   - Fetch OSM seamark separation lines/boundaries
   - Merge into single axis using `shapely.linemerge`
   - If fetch fails or no data → fallback

2. **Fallback** (always available):
   - Use hardcoded LineString approximations
   - Based on established shipping routes
   - Production-safe (no external dependencies)

### Gate Placement Algorithm

1. Find nearest axis point to entry coordinates
2. Calculate cumulative geodesic distance along axis
3. For each target distance:
   - Find axis point with closest cumulative distance
   - Calculate local axis azimuth
   - Create orthogonal transect at ±90° to axis
   - Extend transect by half-width in each direction

### Width Selection

Width map provides distance-specific half-widths:

```python
width_map_half_nm = {
    10: 1.5,   # 10 nm gate: 3.0 nm total width
    25: 2.0,   # 25 nm gate: 4.0 nm total width
    50: 2.5,   # 50 nm gate: 5.0 nm total width
}
```

Rationale for distance-dependent widths:
- **Near approach** (10 nm): Vessels tightly concentrated in traffic lanes
- **Far approach** (150 nm): Natural dispersion increases, wider gates needed

## GeoJSON Output Format

### gates.geojson

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "GATE_GIBRALTAR_W_10NM",
        "width_nm": 3.0,
        "half_width_nm": 1.5,
        "distance_nm": 10,
        "dir_hint": "BIDIR",
        "kind": "APPROACH_GATE",
        "corridor": "GIBRALTAR_W"
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [[lon1, lat1], [lon2, lat2]]
      }
    }
  ]
}
```

### polygons.geojson

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "ANCH_GIBRALTAR_BAY",
        "kind": "ANCHORAGE",
        "name": "Gibraltar Bay Anchorage"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lon1, lat1], [lon2, lat2], ...]]
      }
    }
  ]
}
```

## Integration with Open Sea System

### Full Pipeline

```bash
cd spvx-lite
source .venv/bin/activate

# 1. Generate gates for all corridors
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor suez
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor bosporus

# 2. Run AIS consumer (for each corridor)
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/suez/gates.geojson \
  --polygons data/geo/suez/polygons.geojson

PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/gibraltar/gates.geojson \
  --polygons data/geo/gibraltar/polygons.geojson

# 3. Aggregate results
PYTHONPATH=src python -m spvx.cli open-sea-aggregate
```

### Multi-Corridor Monitoring

To monitor all corridors simultaneously, you can:

1. **Merge gates** into single file:
   ```bash
   jq -s '{type: "FeatureCollection", features: [.[].features[]] | flatten}' \
     data/geo/*/gates.geojson > data/geo/all_gates.geojson
   ```

2. **Run single consumer** with merged file:
   ```bash
   PYTHONPATH=src python -m spvx.cli open-sea-consume \
     --gates data/geo/all_gates.geojson \
     --polygons data/geo/all_polygons.geojson
   ```

## Testing

### Run All Tests

```bash
source .venv/bin/activate
PYTHONPATH=src pytest tests/test_corridor_builder.py -v
```

**Test Coverage:**
- ✅ Offline generation for all corridors
- ✅ Gate ID validation (Suez, Gibraltar, Bosporus)
- ✅ Width map application
- ✅ Anchorage polygon structure
- ✅ Configuration validity
- ✅ Error handling (invalid corridor names)

### Manual Verification

Check generated files:

```bash
# Count gates per corridor
jq '.features | length' data/geo/suez/gates.geojson      # Should be 10
jq '.features | length' data/geo/gibraltar/gates.geojson # Should be 10
jq '.features | length' data/geo/bosporus/gates.geojson  # Should be 6

# List gate IDs
jq '.features[].properties.id' data/geo/suez/gates.geojson

# Check widths
jq '.features[] | {id: .properties.id, width: .properties.width_nm}' \
  data/geo/gibraltar/gates.geojson
```

## Performance

| Corridor  | Generation Time | Gates File | Polygons File |
|-----------|----------------|------------|---------------|
| Suez      | ~0.8s          | 5.4 KB     | 1.3 KB        |
| Gibraltar | ~0.8s          | 5.5 KB     | 1.3 KB        |
| Bosporus  | ~2.2s          | 3.3 KB     | 1.3 KB        |

**Note:** Times with `--use-overpass false`. Add 2-5s when fetching from OSM.

## Troubleshooting

### Issue: Overpass API Timeout

**Error:** `requests.exceptions.Timeout` or HTTP 429

**Solution:**
```bash
# Use offline mode
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor suez \
  --use-overpass false
```

### Issue: Gates Too Narrow (Missing Crossings)

**Symptom:** Valid vessel crossings not detected

**Solution:** Increase gate widths
```bash
# For Gibraltar: use wider gates
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gibraltar \
  --width-map "10:2.0,25:2.5,50:3.0,100:3.5,150:4.0"
```

### Issue: Gates Too Wide (False Positives)

**Symptom:** Detecting crossings from parallel routes

**Solution:** Reduce gate widths or distances
```bash
# For Bosporus: use narrower gates
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor bosporus \
  --width-map "10:0.5,25:0.75,50:1.0"
```

### Issue: Custom Entry Points Needed

**Workaround:** Currently entry points are hardcoded in `corridor_builder.py`. To customize:

1. Edit `spvx/open_sea/tools/corridor_builder.py`
2. Modify `ApproachConfig.entry_point` for target corridor
3. Regenerate gates

**Future Enhancement:** CLI option `--entry-points` for runtime customization.

## Comparison: Corridor vs. Suez-Specific Builder

| Feature | `open-sea-build-suez` | `open-sea-build-corridor` |
|---------|----------------------|---------------------------|
| Corridors | Suez only | Suez, Gibraltar, Bosporus |
| Defaults | Must specify widths | Smart defaults per corridor |
| Entry Points | CLI options | Hardcoded (corridor-optimized) |
| Use Case | Fine-tuning Suez | Multi-corridor deployment |

**Recommendation:** Use `open-sea-build-corridor` for production deployments. Use `open-sea-build-suez` only for specialized Suez tuning.

## Attribution

**OSM/Seamarks Data:** © OpenStreetMap contributors, licensed under ODbL.

When displaying gates publicly, include:
> "Gate data derived from OpenStreetMap seamark features
> © OpenStreetMap contributors"

## Roadmap

### Phase 2.5: Enhanced Anchorages

- [ ] AIS-based anchorage hulls (from dwell patterns)
- [ ] Alpha-shape polygon generation
- [ ] OSM anchorage seeds (`seamark:type=anchorage`)

### Phase 3: Additional Corridors

- [ ] Malacca Strait
- [ ] Panama Canal approaches
- [ ] Strait of Hormuz

### Phase 4: Dynamic Width Adjustment

- [ ] TSS-based width calculation (real-time from OSM)
- [ ] Historical traffic density analysis
- [ ] Seasonal width adjustments

## Summary

The corridor builder provides a **production-ready, geodetically accurate** solution for monitoring major maritime chokepoints. With smart defaults and extensible architecture, it scales from single-corridor prototypes to global multi-corridor deployments.

**Generated Files:**
- ✅ 26 gates total (Suez: 10, Gibraltar: 10, Bosporus: 6)
- ✅ 6 anchorage polygons (2 per corridor)
- ✅ Ready for AIS consumer integration
- ✅ Tested and validated

Use `open-sea-build-corridor <corridor>` to get started! 🚀
