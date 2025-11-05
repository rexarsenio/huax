# 🎯 Tier-Based Maritime Infrastructure Architecture

## Philosophie

Fokussierte Überwachung der **ölkritischen Chokepoints und Hubs** basierend auf globalem Business-Impact, nicht geografischer Vollständigkeit.

---

## Tier 1: Absolut Kritisch (Nicht verhandelbar)

### Chokepoints

**Straße von Hormuz** - 20-25% des globalen Ölverbrauchs
- Files: `data/geo/hormuz/gates.geojson` + `polygons.geojson`
- Coverage: 5-6 gates (Gulf/Oman approaches 10nm, 25nm, 50nm, 100nm)
- Status: ⚠️  Needs consolidation from mega files

**Straße von Malakka** - Hauptroute Indischer Ozean ↔ Pazifik
- Files: `data/geo/singapore/gates.geojson` + `polygons.geojson`
- Coverage: 4-5 gates + Singapore anchorages
- Status: ✅ Exists (via `gates_singapore_test.geojson`)

**Suezkanal**
- Files: `data/geo/suez/gates.geojson` + `polygons.geojson`
- Coverage: 10 gates (North/South approaches)
- Status: ✅ Complete

**Bab el-Mandeb** - Südeingang Suez
- Files: `data/geo/bab_el_mandeb/gates.geojson`
- Coverage: 4 gates (Red Sea/Aden approaches 25nm, 50nm)
- Status: ⚠️  Needs extraction from mega files

**Panamakanal**
- Files: `data/geo/panama/gates.geojson` + `polygons.geojson`
- Coverage: 13 gates (Atlantic/Pacific approaches + lock gates) + 2 anchorages
- Status: ✅ Complete (`panama_gates.geojson`, `panama_polygons.geojson`)

### Hubs (Ports)

**Rotterdam** - Europas größter Öl-Hub
- Files: `data/geo/rotterdam/polygons.geojson`
- Coverage: Oil terminal + outer anchorage
- Status: ✅ Exists (via `oil_terminals.geojson`)

**Singapur** - Asiens wichtigster Öl-Hub
- Files: `data/geo/singapore/polygons.geojson`
- Coverage: STS zones, oil terminals, anchorages
- Status: ✅ Complete (via `sts_zones.geojson`, `oil_terminals.geojson`)

**Houston (US Gulf Coast)** - Herz der US-Ölindustrie
- Files: `data/geo/houston/gates.geojson` + `polygons.geojson`
- Coverage: Ship channel + outer anchorage
- Status: ✅ Complete (dedicated directory exists)

**Fujairah (VAE)** - Top 3 Bunkering Hub + Hormuz-Frühindikator
- Files: `data/geo/fujairah/polygons.geojson`
- Coverage: OPL + STS zones
- Status: ✅ Exists (via `oil_terminals.geojson`, `sts_zones.geojson`)

---

## Tier 2: Sehr Wichtig

### Chokepoints

**Türkische Meerengen (Bosporus & Dardanellen)**
- Files: `data/geo/bosporus/gates.geojson` + `polygons.geojson`
- Coverage: 6 gates + 2 anchorages
- Status: ✅ Complete

**Kap der Guten Hoffnung** - Suez-Alternative
- Files: `data/geo/cape_good_hope/gates.geojson`
- Coverage: 2 gates (monitoring for Suez-bypass traffic)
- Status: ⚠️  Needs creation or extraction

**Straße von Gibraltar**
- Files: `data/geo/gibraltar/gates.geojson`
- Coverage: 4 gates (Mittelmeer Ein-/Ausgang)
- Status: ⚠️  Needs extraction from mega files

### Hubs

**Antwerpen** - Europas zweitgrößter Hafen
- Files: `data/geo/antwerp/polygons.geojson`
- Coverage: Outer anchorage (NxtPort integration)
- Status: ✅ Exists (via oil_terminals or mega files)

**Ningbo-Zhoushan** - Chinas Öl-Import Hub
- Files: `data/geo/ningbo/polygons.geojson`
- Status: ❌ Missing (Datenzugang schwierig)

**Las Palmas** - Atlantik Bunkering Hub
- Files: `data/geo/las_palmas/gates.geojson` + `polygons.geojson`
- Status: ✅ Complete (dedicated directory exists)

---

## Tier 3: Wichtig, aber sekundär

**Los Angeles / Long Beach**
- Status: 🔵 Optional (weniger systemisch für globalen Ölhandel)

**Santos**
- Status: 🔵 Optional (regionale Bedeutung)

**Mittelmeer-Hub** (Augusta/Lavera/Piräus)
- Status: 🔵 Optional (mediterrane Versorgung)

---

## Aktuelle Dateien-Struktur

### ✅ Bereits in regionalen Directories

```
data/geo/
├── suez/
│   ├── gates.geojson (10 gates)
│   ├── polygons.geojson (2 anchorages)
│   └── anchorages_ais.geojson (AIS-derived)
├── bosporus/
│   ├── gates.geojson (6 gates)
│   ├── polygons.geojson (2 anchorages)
│   └── anchorages_ais.geojson
├── houston/
│   ├── gates.geojson
│   └── polygons.geojson
├── las_palmas/
│   ├── gates.geojson
│   └── polygons.geojson
└── gulf_mexico/
    ├── gates.geojson
    └── polygons.geojson
```

### ⚠️  In Root-Directory (needs organization)

```
data/geo/
├── panama_gates.geojson (13 gates) → Move to panama/
├── panama_polygons.geojson (2 anchorages) → Move to panama/
├── oil_terminals.geojson (Rotterdam, Fujairah, etc.) → Keep as global
├── sts_zones.geojson (Singapore, Fujairah, etc.) → Keep as global
├── gates.geojson (10 Suez gates) → Main config, keep
└── polygons.geojson (2 polygons) → Main config, keep
```

### 🗑️  Mega Files to DELETE (after consolidation)

```
data/geo/
├── ALL_GATES.geojson (57 gates - redundant)
├── ALL_ANCHORAGES.geojson (39 anchorages - redundant)
├── global_gates_mega.geojson (44 gates - redundant)
└── global_anchorages_mega.geojson (37 anchorages - redundant)
```

**But FIRST extract:**
- Hormuz gates → `data/geo/hormuz/gates.geojson`
- Bab el-Mandeb gates → `data/geo/bab_el_mandeb/gates.geojson`
- Gibraltar gates → `data/geo/gibraltar/gates.geojson`
- Cape Good Hope gates → `data/geo/cape_good_hope/gates.geojson`

---

## Consumer Strategy

### Option A: One Regional Consumer per Tier 1 Area

```bash
# Suez + Bab el-Mandeb Consumer
start_consumer.sh --region suez --db db/spvx_suez.duckdb --port 9110

# Hormuz + Fujairah Consumer
start_consumer.sh --region hormuz --db db/spvx_hormuz.duckdb --port 9111

# Singapore + Malacca Consumer
start_consumer.sh --region singapore --db db/spvx_singapore.duckdb --port 9112

# Panama Consumer
start_consumer.sh --region panama --db db/spvx_panama.duckdb --port 9113

# Bosporus Consumer
start_consumer.sh --region bosporus --db db/spvx_bosporus.duckdb --port 9114

# Houston + Gulf Mexico Consumer
start_consumer.sh --region gulf_coast --db db/spvx_gulf.duckdb --port 9115
```

### Option B: Tier-Based Consumers

```bash
# Tier 1 Consumer (All Critical Infrastructure)
start_consumer.sh --tier 1 --db db/spvx_tier1.duckdb --port 9110

# Tier 2 Consumer (Important Secondary)
start_consumer.sh --tier 2 --db db/spvx_tier2.duckdb --port 9111
```

---

## Next Steps

1. ✅ **Preserve Panama** - Move to `data/geo/panama/` directory
2. ⚠️  **Extract Missing Tier 1** - Create Hormuz, Bab el-Mandeb directories
3. ⚠️  **Extract Missing Tier 2** - Create Gibraltar, Cape Good Hope directories
4. 🗑️  **Delete Mega Files** - After consolidation complete
5. 📝 **Create Regional Configs** - YAML configs per tier/region
6. 🚀 **Start Focused Consumers** - One per critical region

---

**Prinzip:** Jede Region mit echtem Business-Impact bekommt eigenes Directory + eigenen Consumer. Kein Mega-Consumer der alles überwacht, sondern fokussierte Überwachung der kritischen Infrastruktur.
