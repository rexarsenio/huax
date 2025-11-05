# Panama Canal Open-Sea Integration 🚢

## Status: Phase 1 Complete ✅

Die Panama-Kanal Integration ist in den bestehenden Open-Sea-Stack eingebaut und bereit für Datensammlung und Testing.

## Was wurde implementiert

### 1. Geometrien (Gates & Polygone) ✅

**Dateien**:
- [`data/geo/panama_gates.geojson`](spvx-lite/data/geo/panama_gates.geojson) - 13 Gates
- [`data/geo/panama_polygons.geojson`](spvx-lite/data/geo/panama_polygons.geojson) - 2 Ankerfelder

**Gates (13 total)**:

**Atlantic Approaches** (Colón):
- `GATE_PANAMA_ATL_10NM` - 10nm Approach (3nm width, 260°⇄80°)
- `GATE_PANAMA_ATL_25NM` - 25nm Approach (4nm width)
- `GATE_PANAMA_ATL_50NM` - 50nm Approach (5nm width)
- `GATE_PANAMA_ATL_100NM` - 100nm Approach (6nm width)

**Pacific Approaches** (Balboa):
- `GATE_PANAMA_PAC_10NM` - 10nm Approach (3nm width, 240°⇄60°)
- `GATE_PANAMA_PAC_25NM` - 25nm Approach (4nm width)
- `GATE_PANAMA_PAC_50NM` - 50nm Approach (5nm width)
- `GATE_PANAMA_PAC_100NM` - 100nm Approach (6nm width)

**Lock Gates** (Schleusen):
- `GATE_PANAMA_LOCK_AGUA_CLARA` - Agua Clara Locks (Atlantic, new, 0.3nm)
- `GATE_PANAMA_LOCK_GATUN` - Gatún Locks (Atlantic, original, 0.3nm)
- `GATE_PANAMA_LOCK_PEDRO_MIGUEL` - Pedro Miguel Locks (Pacific, 0.3nm)
- `GATE_PANAMA_LOCK_MIRAFLORES` - Miraflores Locks (Pacific, original, 0.3nm)
- `GATE_PANAMA_LOCK_COCOLI` - Cocolí Locks (Pacific, new, 0.3nm)

**Ankerfelder (Anchorages)**:
- `ANCH_PANAMA_ATL_OUTER` - Atlantic Wartezone (Colón)
- `ANCH_PANAMA_PAC_OUTER` - Pacific Wartezone (Balboa)

### 2. API Endpoints ✅

**Modul**: [`src/spvx/api_panama.py`](spvx-lite/src/spvx/api_panama.py)

Alle Endpoints unter `/api/open_sea/panama/`:

#### `GET /api/open_sea/panama/summary`
Übersicht aller Metriken (Flux, Transit, Queues, SIS).

**Query Parameters**:
- `range_days` (int, default: 7) - Tage Lookback

**Response**:
```json
{
  "status": "ok",
  "flux_atl": 45,
  "flux_pac": 48,
  "transit_p50_nb": 840,
  "transit_p50_sb": 820,
  "queue_atl": 12,
  "queue_pac": 8,
  "sis": 0.35,
  "updated_at": "2025-10-28"
}
```

#### `GET /api/open_sea/panama/queues`
Ankerfeld-Metriken über Zeit (Zeitreihe).

**Query Parameters**:
- `range_hours` (int, default: 24, max: 168) - Stunden Lookback

**Response**:
```json
[
  {
    "timestamp": "2025-10-28T12:00:00",
    "anchorage_id": "ANCH_PANAMA_ATL_OUTER",
    "vessel_count": 12,
    "total_dwell_minutes": 8640
  },
  {
    "timestamp": "2025-10-28T12:00:00",
    "anchorage_id": "ANCH_PANAMA_PAC_OUTER",
    "vessel_count": 8,
    "total_dwell_minutes": 5280
  }
]
```

#### `GET /api/open_sea/panama/transit`
Transitzeiten-Historie (p50, p95, count).

**Query Parameters**:
- `direction` (required) - `NB` (Northbound/Atlantic→Pacific) oder `SB` (Southbound/Pacific→Atlantic)
- `range_days` (int, default: 90, max: 365) - Tage Historie

**Response**:
```json
[
  {
    "date": "2025-10-28",
    "direction": "NB",
    "transit_p50_minutes": 840,
    "transit_p95_minutes": 1020,
    "transit_count": 42
  }
]
```

#### `GET /api/open_sea/panama/flux`
Gate-Flux Historie (Atlantic oder Pacific).

**Query Parameters**:
- `side` (required) - `ATL` (Atlantic) oder `PAC` (Pacific)
- `range_days` (int, default: 90, max: 365) - Tage Historie

**Response**:
```json
[
  {
    "date": "2025-10-28",
    "side": "ATL",
    "gate_id": "GATE_PANAMA_ATL_10NM",
    "total_flux": 45
  }
]
```

#### `GET /api/open_sea/panama/sis_history`
SIS (Stress Index Score) Historie [0-1].

**Query Parameters**:
- `range_days` (int, default: 30, max: 365) - Tage Historie

**Response**:
```json
[
  {
    "date": "2025-10-28",
    "sis": 0.35,
    "transit_nb": 840,
    "transit_sb": 820,
    "queue_atl": 12,
    "queue_pac": 8
  }
]
```

### 3. API Integration ✅

**Datei**: [`src/spvx/api_app.py`](spvx-lite/src/spvx/api_app.py:28-331)

Panama-Router ist im FastAPI-Server registriert:
```python
from spvx.api_panama import router as panama_router
app.include_router(panama_router)
```

API Server wird automatisch neu laden und die Endpoints sind sofort verfügbar!

## Nächste Schritte 📋

### Phase 2: Consumer & Datensammlung

1. **Starte den Consumer mit Panama-Gates**:
```bash
cd spvx-lite

# Kopiere/merge die Panama-Geometrien in eure bestehenden Files
# ODER nutze sie separat:
PYTHONPATH=src python -m spvx.cli open-sea-consume \
  --gates data/geo/panama_gates.geojson \
  --polygons data/geo/panama_polygons.geojson
```

2. **Warte auf erste Daten** (12-24h):
   - `gate_crossings` Tabelle sollte Einträge für `GATE_PANAMA_*` bekommen
   - `polygon_events` sollte Einträge für `ANCH_PANAMA_*` bekommen

3. **Checke die Datensammlung**:
```bash
source .venv/bin/activate
python3 << 'EOF'
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)

# Check Gates
gates = con.execute("""
    SELECT gate_id, COUNT(*) as crossings
    FROM gate_crossings
    WHERE gate_id LIKE 'GATE_PANAMA_%'
    GROUP BY gate_id
    ORDER BY gate_id
""").df()
print("Panama Gate Crossings:")
print(gates)

# Check Anchorages
anch = con.execute("""
    SELECT polygon_id, COUNT(*) as events
    FROM polygon_events
    WHERE polygon_id LIKE 'ANCH_PANAMA_%'
    GROUP BY polygon_id
""").df()
print("\nPanama Anchorage Events:")
print(anch)

con.close()
EOF
```

### Phase 3: Aggregation Pipeline (TODO)

Erstelle Modul `src/spvx/etl/panama_aggregation.py`:

**Features**:
1. **Gate Flux** - Stündlich/täglich aggregiert für ATL/PAC
2. **Transit Times** - Entry→Exit Zeit für NB/SB Richtung
3. **Queue Metrics** - Ankerfeld Counts & Dwell aus `polygon_events`
4. **Baselines** - 90-Tage Median & p95 für Normalwerte

**Tabelle**: `open_sea_panama_daily`

**Columns**:
```sql
CREATE TABLE open_sea_panama_daily (
    date DATE PRIMARY KEY,
    -- Flux (24h)
    flux_atl_24h INT,
    flux_pac_24h INT,
    -- Transit (minutes)
    transit_p50_nb_min FLOAT,
    transit_p95_nb_min FLOAT,
    transit_count_nb INT,
    transit_p50_sb_min FLOAT,
    transit_p95_sb_min FLOAT,
    transit_count_sb INT,
    -- Queues
    queue_atl_count INT,
    queue_atl_dwell_sum_min FLOAT,
    queue_pac_count INT,
    queue_pac_dwell_sum_min FLOAT,
    -- SIS
    sis_panama FLOAT,
    -- Metadata
    updated_at TIMESTAMP
);
```

**Cron**:
```bash
*/15 * * * * cd /path/to/spvx-lite && python -m spvx.cli open-sea-aggregate --corridor PANAMA
```

### Phase 4: SIS Signal (TODO)

**Formel**:
```python
# Z-Scores berechnen
z_transit_nb = (current_transit_nb - baseline_p50) / baseline_std
z_transit_sb = (current_transit_sb - baseline_p50) / baseline_std
z_queue_atl = (current_queue - baseline_p50) / baseline_std
z_queue_pac = (current_queue - baseline_p50) / baseline_std
z_flux_drop = -(flux_24h - flux_30d_mean) / flux_30d_std

# Gewichtete Summe
sis_raw = (
    0.25 * z_transit_nb +
    0.25 * z_transit_sb +
    0.20 * z_queue_atl +
    0.20 * z_queue_pac +
    0.10 * z_flux_drop
)

# Logistic Clipping [0-1]
sis_panama = 1 / (1 + exp(-sis_raw))
```

**Optional**: Hydro-Layer (Gatún-Seespiegel, Niederschlag) als zusätzlicher Faktor.

### Phase 5: Dashboard Integration (TODO)

**React Component**: `dashboard/src/components/PanamaCanalPanel.tsx`

**Features**:
- **Summary Card**: SIS Badge (Normal/Alert), Transit NB/SB, Queue ATL/PAC, Flux Δ%
- **Map Overlay**: Gates + Ankerfelder mit Tooltips (aktuelle Counts)
- **Charts**:
  - Transit Time Trends (7/30/90 Tage)
  - Queue Length Time Series
  - Flux Comparison ATL vs PAC
- **Alerts**: Hohe Queue + niedriger Flux → "Slot-Restriktion wahrscheinlich"

**API Integration**:
```typescript
// dashboard/src/api/panama.ts
export async function fetchPanamaSummary(rangeDays = 7) {
  const response = await fetch(`/api/open_sea/panama/summary?range_days=${rangeDays}`);
  return response.json();
}

export async function fetchPanamaQueues(rangeHours = 24) {
  const response = await fetch(`/api/open_sea/panama/queues?range_hours=${rangeHours}`);
  return response.json();
}
```

### Phase 6: Prometheus Metrics (TODO)

**Metrics**:
```python
panama_flux_total = Counter(
    "panama_flux_total",
    "Panama Canal gate flux",
    ["side"]  # ATL, PAC
)

panama_transit_minutes_p50 = Gauge(
    "panama_transit_minutes_p50",
    "Panama Canal median transit time",
    ["direction"]  # NB, SB
)

panama_queue_count = Gauge(
    "panama_queue_count",
    "Panama anchorage vessel count",
    ["side"]  # ATL, PAC
)

panama_sis = Gauge(
    "panama_sis",
    "Panama Canal Stress Index Score [0-1]"
)
```

**Alerts** (Prometheus AlertManager):
```yaml
groups:
  - name: panama_canal
    rules:
      - alert: PanamaTransitDelayed
        expr: panama_transit_minutes_p50 > panama_transit_baseline_p95
        for: 6h
        labels:
          severity: warning
        annotations:
          summary: "Panama transit time above p95 baseline"

      - alert: PanamaFluxDrop
        expr: rate(panama_flux_total[24h]) == 0
        for: 2h
        labels:
          severity: critical
        annotations:
          summary: "No flux detected for 2h (watchdog)"

      - alert: PanamaQueueHigh
        expr: panama_queue_count > panama_queue_baseline_p95
        for: 6h
        labels:
          severity: warning
        annotations:
          summary: "Panama anchorage queue above p95"
```

### Phase 7: Tests (TODO)

**Datei**: `tests/test_panama.py`

**Test Cases**:
1. **Geometry Validation**:
   - Gates haben korrekte Koordinaten
   - Polygone sind valide GeoJSON

2. **Engine Tests**:
   - Gate Direction Detection (NB/SB) funktioniert
   - Hysterese & TTL greifen korrekt
   - Exit erst nach 2. Fix außerhalb

3. **Aggregation Tests**:
   - Transit-Rekonstruktion aus Entry/Exit korrekt
   - Queue-Metriken korrekt berechnet
   - Idempotent (mehrfaches Ausführen = gleiches Ergebnis)

4. **API Tests**:
   - `/panama/summary` liefert fallback bei No-Data
   - Alle Endpoints geben valide JSON zurück
   - Error Handling (400/404/500)

## API Testing 🧪

Sobald Daten vorhanden sind:

```bash
# Summary
curl "http://localhost:8000/api/open_sea/panama/summary?range_days=7" | jq

# Queues (last 24h)
curl "http://localhost:8000/api/open_sea/panama/queues?range_hours=24" | jq

# Transit times Northbound (last 90 days)
curl "http://localhost:8000/api/open_sea/panama/transit?direction=NB&range_days=90" | jq

# Flux Atlantic side
curl "http://localhost:8000/api/open_sea/panama/flux?side=ATL&range_days=90" | jq

# SIS history
curl "http://localhost:8000/api/open_sea/panama/sis_history?range_days=30" | jq
```

## Geometrie-Tuning 📐

Die aktuellen Koordinaten sind **praktikable Defaults**. Bitte visuell prüfen:

1. **Öffne QGIS/GeoJSON.io**:
```bash
open https://geojson.io
# Upload data/geo/panama_gates.geojson
```

2. **Checke**:
   - Gates treffen die Anmarschlinien
   - Ankerfelder überdecken die Wartezonen
   - Lock-Gates liegen an den Schleusen

3. **Feintuning**:
   - Verschiebe Punkte wenn nötig
   - Exportiere als GeoJSON
   - Ersetze `data/geo/panama_gates.geojson`

## Notizen 📝

### Warum 4 Distanzen (10/25/50/100nm)?

- **10nm**: Unmittelbare Ankunft, Slot-Confirmation
- **25nm**: Final Approach, Pilot Boarding Area
- **50nm**: Mid-Range Approach, Schedule Adjustments
- **100nm**: Early Detection, Planning Horizon

### Warum Atlantic & Pacific separat?

- **Unterschiedliche Patterns**: Asien→US vs US→Asien Traffic
- **Queue-Management**: Separate Warteflächen
- **Operational Independence**: Unterschiedliche Hafenbehörden

### Lock-Gates vs Approach-Gates?

- **Lock-Gates**: Messen direkte Schleusen-Durchfahrt (Micro-Transit)
- **Approach-Gates**: Messen gesamte Kanal-Annäherung (Macro-Transit)
- **Kombination**: Gibt vollständiges Bild Entry→Lock→Exit

## Definition of Done ✅

Phase 1 (FERTIG):
- ✅ Gates & Polygone im Repo (`data/geo/panama_*.geojson`)
- ✅ API Endpoints implementiert (`api_panama.py`)
- ✅ API Server integriert (`api_app.py`)
- ✅ Dokumentation (`PANAMA_CANAL_IMPLEMENTATION.md`)

Phase 2-7 (TODO):
- ⏳ Consumer sammelt Daten (≥ 48h)
- ⏳ Aggregation Pipeline (`etl/panama_aggregation.py`)
- ⏳ `open_sea_panama_daily` Tabelle gefüllt
- ⏳ SIS-Signal berechnet und in `signals.json`
- ⏳ Dashboard zeigt Panama-Kachel
- ⏳ Prometheus-Metriken sichtbar
- ⏳ Unit-/Integrations-Tests grün

## Kontakt & Support

Bei Fragen oder Problemen:
1. Check die Logs: `tail -f spvx-lite/logs/*.log`
2. Datenbank-Check: Siehe "Phase 2: Datensammlung" oben
3. GitHub Issue: https://github.com/your-repo/issues

---

**Implementation Date**: 2025-10-28
**Status**: Phase 1 Complete - API Ready
**Next**: Start Consumer with Panama gates, wait for data (12-24h)
