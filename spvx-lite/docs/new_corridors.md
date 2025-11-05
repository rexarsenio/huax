# New Maritime Corridors - Americas & Atlantic

## Overview

Extended corridor coverage with **5 new regions** focusing on **oil trade routes**, **major ports**, and **bunkering hubs** in the Americas and Atlantic:

1. 🇻🇪 **Venezuela** (Maracaibo/Jose Terminal)
2. 🇲🇽 **Gulf of Mexico** (Yucatan Channel)
3. 🇺🇸 **Houston** (Texas ports)
4. 🇧🇷 **Brazil Ports** (Santos/Rio de Janeiro)
5. 🇪🇸 **Las Palmas** (Gran Canaria bunkering hub)

**Total New Gates:** 36 (8+8+6+8+6)

## 1. 🇻🇪 Venezuela (Maracaibo/Jose Terminal)

### Strategic Importance
- Major oil export terminal (Jose Terminal)
- Lake Maracaibo crude oil production
- Caribbean shipping route

### Approaches
- **North (VENEZUELA_N)**: Caribbean approach to Jose Terminal
- **West (VENEZUELA_W)**: Maracaibo Lake entrance

### Gate Configuration
| Distance | Half-Width | Total Width |
|----------|-----------|-------------|
| 10 nm    | 1.0 nm    | 2.0 nm      |
| 25 nm    | 1.5 nm    | 3.0 nm      |
| 50 nm    | 2.0 nm    | 4.0 nm      |
| 100 nm   | 2.5 nm    | 5.0 nm      |

### Anchorages
- **Jose Terminal Anchorage** (offshore)
- **Lake Maracaibo Anchorage** (inland)

### Generation
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor venezuela
```

**Output:** `data/geo/venezuela/` (8 gates, 2 anchorages)

---

## 2. 🇲🇽 Gulf of Mexico (Yucatan Channel)

### Strategic Importance
- Main entry/exit for Gulf of Mexico
- Between Yucatan Peninsula (Mexico) and Cuba
- Critical for US Gulf Coast oil trade

### Approaches
- **North (YUCATAN_N)**: Gulf of Mexico side
- **South (YUCATAN_S)**: Caribbean Sea side

### Gate Configuration
| Distance | Half-Width | Total Width | Rationale |
|----------|-----------|-------------|-----------|
| 10 nm    | 1.5 nm    | 3.0 nm      | Wider channel |
| 25 nm    | 2.0 nm    | 4.0 nm      | Dispersed traffic |
| 50 nm    | 2.5 nm    | 5.0 nm      | Far approach |
| 100 nm   | 3.0 nm    | 6.0 nm      | Extended coverage |

**Rationale:** Wider gates than Suez due to broader channel (~200 km wide)

### Anchorages
- **Yucatan Channel North Anchorage**
- **Yucatan Channel South Anchorage**

### Generation
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor gulf_mexico
```

**Output:** `data/geo/gulf_mexico/` (8 gates, 2 anchorages)

---

## 3. 🇺🇸 Houston (Texas Ports)

### Strategic Importance
- Largest US oil export port
- Houston Ship Channel
- Galveston Bay complex
- USGC (US Gulf Coast) benchmark pricing

### Approaches
- **Southeast (HOUSTON_SE)**: Main shipping lane
- **South (HOUSTON_S)**: Alternate approach

### Gate Configuration
| Distance | Half-Width | Total Width |
|----------|-----------|-------------|
| 10 nm    | 1.0 nm    | 2.0 nm      |
| 25 nm    | 1.5 nm    | 3.0 nm      |
| 50 nm    | 2.0 nm    | 4.0 nm      |

**Note:** Only 3 distances (shorter approaches due to coastal location)

### Anchorages
- **Galveston Anchorage** (outer)
- **Houston Ship Channel Anchorage** (inner)

### Generation
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor houston
```

**Output:** `data/geo/houston/` (6 gates, 2 anchorages)

---

## 4. 🇧🇷 Brazil Ports (Santos/Rio de Janeiro)

### Strategic Importance
- **Santos**: Largest port in Latin America
- **Rio de Janeiro**: Major oil terminal (Petrobras)
- South Atlantic trade routes
- Brazil exports: crude oil, refined products

### Approaches
- **East (SANTOS_E)**: Santos approach
- **Southeast (RIO_SE)**: Rio de Janeiro approach

### Gate Configuration
| Distance | Half-Width | Total Width | Rationale |
|----------|-----------|-------------|-----------|
| 10 nm    | 1.2 nm    | 2.4 nm      | Moderate width |
| 25 nm    | 1.8 nm    | 3.6 nm      | Balanced |
| 50 nm    | 2.3 nm    | 4.6 nm      | Far approach |
| 100 nm   | 2.8 nm    | 5.6 nm      | Extended |

**Rationale:** Slightly wider than standard due to open ocean approaches

### Anchorages
- **Santos Anchorage**
- **Rio de Janeiro Anchorage**

### Generation
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor brazil_ports
```

**Output:** `data/geo/brazil_ports/` (8 gates, 2 anchorages)

---

## 5. 🇪🇸 Las Palmas (Gran Canaria)

### Strategic Importance
- **Major bunkering hub** (one of world's largest)
- Mid-Atlantic refueling stop
- Between Europe, Africa, and Americas
- 24/7 bunker fuel supply

### Approaches
- **North (LAS_PALMAS_N)**: North Atlantic approach
- **East (LAS_PALMAS_E)**: From Mediterranean/Africa

### Gate Configuration
| Distance | Half-Width | Total Width | Rationale |
|----------|-----------|-------------|-----------|
| 10 nm    | 0.8 nm    | 1.6 nm      | Compact island |
| 25 nm    | 1.2 nm    | 2.4 nm      | Moderate |
| 50 nm    | 1.6 nm    | 3.2 nm      | Far approach |

**Rationale:** Narrower gates (island port, concentrated traffic)

### Anchorages
- **Las Palmas Bay Anchorage**
- **Las Palmas Bunkering Area** (designated bunker zone)

### Generation
```bash
PYTHONPATH=src python -m spvx.cli open-sea-build-corridor las_palmas
```

**Output:** `data/geo/las_palmas/` (6 gates, 2 anchorages)

---

## Complete Corridor Summary

| Corridor | Gates | Distances | Width Range | Strategic Role |
|----------|-------|-----------|-------------|----------------|
| Suez | 10 | 10-150 nm | 2.0-6.0 nm | Asia-Europe chokepoint |
| Gibraltar | 10 | 10-150 nm | 3.0-7.0 nm | Med-Atlantic chokepoint |
| Bosporus | 6 | 10-50 nm | 1.5-3.0 nm | Black Sea chokepoint |
| **Venezuela** | **8** | **10-100 nm** | **2.0-5.0 nm** | **Oil exports** |
| **Gulf Mexico** | **8** | **10-100 nm** | **3.0-6.0 nm** | **Gulf access** |
| **Houston** | **6** | **10-50 nm** | **2.0-4.0 nm** | **USGC exports** |
| **Brazil Ports** | **8** | **10-100 nm** | **2.4-5.6 nm** | **S. America trade** |
| **Las Palmas** | **6** | **10-50 nm** | **1.6-3.2 nm** | **Bunkering hub** |
| **TOTAL** | **62** | - | - | **Global coverage** |

**Total Anchorages:** 16 (2 per corridor)

---

## Batch Generation

### Generate All Corridors

```bash
cd spvx-lite
source .venv/bin/activate

# All 8 corridors
for corridor in suez gibraltar bosporus venezuela gulf_mexico houston brazil_ports las_palmas; do
  PYTHONPATH=src python -m spvx.cli open-sea-build-corridor $corridor
done
```

### Americas Only

```bash
# New regions only
for corridor in venezuela gulf_mexico houston brazil_ports las_palmas; do
  PYTHONPATH=src python -m spvx.cli open-sea-build-corridor $corridor
done
```

### Verify Output

```bash
# Count gates per corridor
for dir in data/geo/*/; do
  echo -n "$(basename $dir): "
  jq '.features | length' $dir/gates.geojson
done

# Total gates
find data/geo -name "gates.geojson" -exec jq '.features | length' {} + | awk '{s+=$1} END {print "Total gates:", s}'
```

**Expected Output:**
```
suez: 10
gibraltar: 10
bosporus: 6
venezuela: 8
gulf_mexico: 8
houston: 6
brazil_ports: 8
las_palmas: 6
Total gates: 62
```

---

## Use Cases

### Oil Trade Monitoring

**Venezuela → US Gulf Coast:**
```bash
# Track Venezuelan exports to Houston
# Gates: VENEZUELA_N → YUCATAN → HOUSTON_SE
```

**Brazil → Europe:**
```bash
# Track Brazilian crude to Europe
# Gates: SANTOS_E → LAS_PALMAS → GIBRALTAR
```

### Bunkering Analysis

**Las Palmas Traffic:**
```bash
# Analyze bunkering patterns
PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages las_palmas
# → anchorages_ais.geojson shows actual bunkering zones
```

### US Gulf Coast Exports

**Houston Production:**
```bash
# Monitor USGC exports
# Gates: HOUSTON_S → YUCATAN_N → Atlantic routes
```

---

## Integration with Existing System

### Option 1: Per-Corridor Consumer

```bash
# Run separate consumers for each region
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/venezuela/gates.geojson \
  --polygons data/geo/venezuela/polygons.geojson

PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/houston/gates.geojson \
  --polygons data/geo/houston/polygons.geojson
```

### Option 2: Merged Global Gates

```bash
# Merge all gates into single file
jq -s '{type: "FeatureCollection", features: [.[].features[]] | flatten}' \
  data/geo/*/gates.geojson > data/geo/all_gates_global.geojson

# Single consumer for all corridors
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/all_gates_global.geojson \
  --polygons data/geo/all_polygons_global.geojson
```

### Option 3: Regional Grouping

```bash
# Americas only
jq -s '{type: "FeatureCollection", features: [.[].features[]] | flatten}' \
  data/geo/{venezuela,gulf_mexico,houston,brazil_ports,las_palmas}/gates.geojson \
  > data/geo/americas_gates.geojson
```

---

## Comparison: New vs. Existing Corridors

### Width Philosophy

| Corridor Type | Width Strategy | Example |
|---------------|---------------|---------|
| **Chokepoints** | Narrower (confined) | Bosporus: 1.5-3.0 nm |
| **Channels** | Moderate | Yucatan: 3.0-6.0 nm |
| **Open Ports** | Variable | Houston: 2.0-4.0 nm |
| **Islands** | Compact | Las Palmas: 1.6-3.2 nm |

### Distance Coverage

| Corridor | Max Distance | Rationale |
|----------|-------------|-----------|
| Suez, Gibraltar | 150 nm | Extended approaches |
| Venezuela, Gulf Mexico, Brazil | 100 nm | Regional coverage |
| Bosporus, Houston, Las Palmas | 50 nm | Coastal/island ports |

---

## Validation Checklist

After generation, verify:

```bash
# 1. File existence
ls data/geo/{venezuela,gulf_mexico,houston,brazil_ports,las_palmas}/gates.geojson

# 2. Gate count per corridor
jq '.features | length' data/geo/venezuela/gates.geojson      # Should be 8
jq '.features | length' data/geo/gulf_mexico/gates.geojson    # Should be 8
jq '.features | length' data/geo/houston/gates.geojson        # Should be 6
jq '.features | length' data/geo/brazil_ports/gates.geojson   # Should be 8
jq '.features | length' data/geo/las_palmas/gates.geojson     # Should be 6

# 3. Gate IDs
jq '.features[].properties.id' data/geo/venezuela/gates.geojson | head -4
# Should show: GATE_VENEZUELA_N_10NM, GATE_VENEZUELA_N_25NM, etc.

# 4. Width values
jq '.features[] | {id: .properties.id, width: .properties.width_nm}' \
  data/geo/las_palmas/gates.geojson
# Verify: 10nm→1.6nm, 25nm→2.4nm, 50nm→3.2nm
```

---

## Next Steps

### Phase 3: Additional Regions

Potential future corridors:
- **Strait of Hormuz** (Persian Gulf)
- **Malacca Strait** (Southeast Asia)
- **Panama Canal** (Pacific-Atlantic)
- **Cape of Good Hope** (Alternative to Suez)
- **Singapore** (Asia hub)
- **Rotterdam** (Europe)

### Phase 4: AIS-Based Anchorages

Generate realistic anchorages from dwell data:

```bash
# Once 60 days of AIS data available
for corridor in venezuela gulf_mexico houston brazil_ports las_palmas; do
  PYTHONPATH=src python -m spvx.cli open-sea-build-anchorages $corridor
done
```

---

## Summary

**New Corridors Added: 5**
- 🇻🇪 Venezuela (oil exports)
- 🇲🇽 Gulf of Mexico (Gulf access)
- 🇺🇸 Houston (USGC hub)
- 🇧🇷 Brazil Ports (S. America trade)
- 🇪🇸 Las Palmas (bunkering hub)

**Total System Coverage: 8 Corridors**
- Original 3: Suez, Gibraltar, Bosporus
- Americas 5: Venezuela, Gulf Mexico, Houston, Brazil, Las Palmas

**Total Gates: 62** (26 original + 36 new)
**Total Anchorages: 16** (2 per corridor)

The system now covers **major oil trade routes** in the **Mediterranean**, **Americas**, and **Atlantic** with production-ready gate geometries! 🌍🛢️
