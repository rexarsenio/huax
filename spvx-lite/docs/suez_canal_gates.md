# Suez Canal Gate & Anchorage Builder

## Overview

The Suez Canal gate builder generates **precise orthogonal transects** for approach monitoring at the Suez Canal, plus anchorage polygons for dwell detection. It uses geodetically accurate calculations with WGS84 ellipsoid.

## Key Features

✅ **Geodetically Correct**: Uses `pyproj` for accurate distance/bearing calculations
✅ **Orthogonal Gates**: Gates are perpendicular to the canal axis at each distance
✅ **Distance-Specific Widths**: Gates get wider as you move further from entry
✅ **OSM Integration**: Can fetch real seamark separation lines from Overpass API
✅ **Fallback Strategy**: Uses hardcoded axis if Overpass unavailable (CI/production-safe)
✅ **Two Approaches**: North (Port Said) and South (Port of Suez)
✅ **Anchorage Polygons**: Port Said Anchorage and Great Bitter Lake

## Installation

Dependencies are already installed in your virtual environment:

```bash
# Already installed:
shapely pyproj requests
```

## Usage

### Basic Usage (Recommended Widths)

```bash
cd spvx-lite
source .venv/bin/activate

# Generate gates with recommended widths
PYTHONPATH=src python -m spvx.cli open-sea-build-suez \
  --width-map "10:1.0,25:1.5,50:2.0,100:2.5,150:3.0"
```

This creates:
- `data/geo/gates.geojson` - 10 gates (5 distances × 2 approaches)
- `data/geo/polygons.geojson` - 2 anchorage polygons

### Gate Width Specifications

| Distance | Half-Width | Total Width | Purpose |
|----------|-----------|-------------|---------|
| 10 nm    | 1.0 nm    | 2.0 nm      | Near approach |
| 25 nm    | 1.5 nm    | 3.0 nm      | Medium approach |
| 50 nm    | 2.0 nm    | 4.0 nm      | Far approach |
| 100 nm   | 2.5 nm    | 5.0 nm      | Very far approach |
| 150 nm   | 3.0 nm    | 6.0 nm      | Extended approach |

**Rationale**: Wider gates at greater distances capture natural dispersion of vessel tracks while avoiding false positives from unrelated traffic.

### Advanced Options

#### Custom Distances

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-suez \
  --distances "5,10,20,50" \
  --width-map "5:0.5,10:1.0,20:1.5,50:2.0"
```

#### Offline Mode (No Overpass API)

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-suez \
  --use-overpass false \
  --width-map "10:1.0,25:1.5,50:2.0,100:2.5,150:3.0"
```

#### Custom Entry Points

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-suez \
  --north-entry "32.310,31.270" \
  --south-entry "32.570,29.970" \
  --width-map "10:1.0,25:1.5,50:2.0,100:2.5,150:3.0"
```

## Generated Files

### gates.geojson

GeoJSON FeatureCollection with gate properties:

```json
{
  "type": "Feature",
  "properties": {
    "id": "GATE_SUEZ_N_10NM",
    "width_nm": 2.0,
    "half_width_nm": 1.0,
    "distance_nm": 10,
    "dir_hint": "BIDIR",
    "kind": "APPROACH_GATE",
    "corridor": "SUEZ_N"
  },
  "geometry": {
    "type": "LineString",
    "coordinates": [[lon1, lat1], [lon2, lat2]]
  }
}
```

### polygons.geojson

GeoJSON FeatureCollection with anchorage polygons:

- **ANCH_PORT_SAID** (kind: "ANCHORAGE") - Expanded Port Said anchorage area
- **ANCH_GREAT_BITTER_LAKE** (kind: "ANCHORAGE_INLAND") - Great Bitter Lake waiting area

## Integration with Open Sea System

### 1. Generate Gates

```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-suez \
  --width-map "10:1.0,25:1.5,50:2.0,100:2.5,150:3.0"
```

### 2. Run Consumer (with AIS data)

```bash
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/gates.geojson \
  --polygons data/geo/polygons.geojson
```

### 3. Compute Aggregates

```bash
PYTHONPATH=src python -m spvx.cli open-sea-aggregate
```

### 4. (Optional) Derive Convoy Windows

Analyze historical gate crossings to identify peak traffic hours:

```bash
PYTHONPATH=src python -m spvx.cli open-sea-convoy-windows \
  --gates-csv "GATE_SUEZ_N_10NM,GATE_SUEZ_S_10NM" \
  --days 30
```

This creates `data/geo/convoy_windows.json` with peak time windows (90th percentile traffic).

## Technical Details

### Geodesic Calculations

All distance and bearing calculations use the WGS84 ellipsoid via `pyproj.Geod`:

- **Forward calculation**: From point + bearing + distance → new point
- **Inverse calculation**: From two points → bearing and distance
- **Orthogonal transects**: Perpendicular lines at ±90° from axis bearing

### Axis Determination

1. **With Overpass**: Fetches OSM seamark separation lines/boundaries, merges into single axis
2. **Fallback**: Uses hardcoded LineString approximations if Overpass unavailable
3. **Sampling**: Walks along axis from entry point, placing gates at specified distances

### Width Strategy

Three approaches (in priority order):

1. **width_map_half_nm**: Explicit mapping of distance → half-width (recommended)
2. **auto_width_from_tss**: Derive from TSS boundaries (stub - future enhancement)
3. **half_width_nm**: Global fallback (default: 1.0 nm)

## Validation

Run the test suite:

```bash
source .venv/bin/activate
PYTHONPATH=src pytest tests/test_suez_builder.py -v
```

Tests verify:
- ✅ Correct number of gates (10) and polygons (2)
- ✅ Gate IDs match expected pattern
- ✅ Width map correctly applied to each gate
- ✅ GeoJSON structure is valid

## Attribution

**OSM/Seamarks Data**: © OpenStreetMap contributors, licensed under ODbL.
When displaying gates publicly, include: "© OpenStreetMap contributors"

## Future Enhancements

### Phase 2: Additional Corridors

The same builder pattern can be extended to:

- **Gibraltar** (10/25/50/100/150 nm, widths: 1.5/2.0/2.5/3.0/3.5 nm)
- **Bosporus** (10/25/50 nm, widths: 0.75/1.0/1.5 nm)

### Anchorage Refinement

Current polygons are conservative rectangles. Future improvements:

1. **AIS-based hulls**: Analyze dwell patterns from historical AIS data
2. **Alpha shapes**: Create tighter polygons around actual anchorage usage
3. **OSM anchorage seeds**: Use `seamark:type=anchorage` as starting point

### Auto-Width from TSS

The `auto_width_from_tss` parameter is currently a stub. Future implementation:

1. Measure distance to nearest TSS boundaries at each gate location
2. Add configurable margin (default: 0.3 nm)
3. Fallback to width_map if TSS data unavailable

## Troubleshooting

### Overpass API Rate Limiting

**Error**: HTTP 429 or timeout from Overpass

**Solution**: Use offline mode:
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-suez --use-overpass false
```

### Gate Width Too Narrow

**Symptom**: Missing valid vessel crossings

**Solution**: Increase widths in width-map:
```bash
--width-map "10:1.5,25:2.0,50:2.5,100:3.0,150:3.5"
```

### Gate Width Too Wide

**Symptom**: Too many false crossings from parallel routes

**Solution**: Decrease widths or reduce distances:
```bash
--distances "10,25,50" --width-map "10:0.8,25:1.2,50:1.8"
```

## CLI Reference

```
python -m spvx.cli open-sea-build-suez --help

Options:
  --outdir TEXT               Output directory [default: data/geo]
  --distances TEXT            CSV of distances in nm [default: 10,25,50,100,150]
  --half-width-nm FLOAT       Global half-width (overridden by width-map)
  --width-map TEXT            Distance:half-width mapping (e.g., "10:1.0,25:1.5")
  --auto-width-from-tss       Derive width from TSS data [default: False]
  --use-overpass             Fetch OSM seamark data [default: True]
  --north-entry TEXT         Port Said entry lon,lat [default: 32.301,31.265]
  --south-entry TEXT         Port of Suez entry lon,lat [default: 32.566,29.966]
```

## Performance

- **Offline mode**: ~0.1s per gate set
- **With Overpass**: ~2-5s (depends on API response time)
- **File size**: gates.geojson ~6KB, polygons.geojson ~1KB

## Summary

The Suez gate builder provides a production-ready, geodetically accurate solution for approach monitoring. Use the recommended width-map for optimal coverage without false positives. The fallback strategy ensures reliability even when external APIs are unavailable.
