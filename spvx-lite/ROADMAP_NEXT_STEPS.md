# 🚀 SPVX-Lite Roadmap - Nächste Schritte

## ✅ Was funktioniert bereits PERFEKT

### 1. AIS Data Collection
- ✅ 14,424 AIS Fixes gesammelt
- ✅ 13,601 Polygon Events (enter/exit)
- ✅ Consumer läuft stabil (PID: 21879)
- ✅ 160 Tanker in MALACCA, 154 in SINGAPORE_STRAIT

### 2. Tracklet Generation
- ✅ 4,134 echte Tracklets aus Schiffsbewegungen
- ✅ Script: `generate_tracklets_from_events.py`
- ✅ Funktioniert einwandfrei

### 3. Sea State Integration
- ✅ 286 Sea State Samples mit CMEMS verknüpft
- ✅ 5 SIS Daily Records (2 Tage Daten)
- ✅ Point-Sampling Methode ultraschnell
- ✅ Script: `join_tracklets_cmems_fast.py`

### 4. API & Dashboard
- ✅ API läuft auf Port 8000
- ✅ API Snapshot aktualisiert
- ✅ Dashboard zeigt Occupancy, Flux, etc.

---

## 🎯 NÄCHSTE SCHRITTE - Priorität

### Option 1: Dashboard Sea State Integration ⭐⭐⭐
**Was:** Weather Impact Badges im Dashboard anzeigen

**Warum:** Die SIS-Daten sind fertig, aber nicht im UI sichtbar

**Tasks:**
1. Frontend: SIS-Daten vom API holen
2. Weather Impact Badge komponente erstellen
3. Auf Corridor/Chokepoint Cards anzeigen
4. Color-Coding: Grün (0-0.5), Gelb (0.5-0.7), Rot (0.7-1.0)

**Dateien:**
- `dashboard/src/api/openSea.ts` - API calls hinzufügen
- `dashboard/src/components/SeaStateChip.tsx` - Bereits vorhanden! ✅
- `dashboard/src/pages/MapPage.tsx` - Badges auf Map anzeigen
- `dashboard/src/pages/OperationsPage.tsx` - Badges in Ops View

**Aufwand:** 2-3 Stunden

---

### Option 2: Automatisierung (Cron Jobs) ⭐⭐
**Was:** Daily automated pipeline

**Tasks:**
1. Cron Job für Tracklet-Generierung (täglich 6 Uhr)
2. Cron Job für CMEMS-Join (täglich 7 Uhr)
3. Cron Job für SIS-Berechnung (täglich 8 Uhr)
4. Cron Job für API Snapshot (täglich 9 Uhr)

**Script erstellen:** `DAILY_UPDATE.sh`

```bash
#!/bin/bash
# Daily pipeline: Run at 6 AM

cd /path/to/spvx-lite
source .venv/bin/activate

# 1. Generate tracklets
python generate_tracklets_from_events.py

# 2. CMEMS join (all tracklets from last 24h)
python join_tracklets_cmems_fast.py

# 3. SIS computation
python -m spvx.cli sea-state-join

# 4. Update API snapshot
./UPDATE_API_SNAPSHOT.sh

# 5. Metrics
python << EOF
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)
print(f"Tracklets: {con.execute('SELECT COUNT(*) FROM tracklets WHERE tracklet_id < 1000000').fetchone()[0]:,}")
print(f"SIS Records: {con.execute('SELECT COUNT(*) FROM sea_state_daily').fetchone()[0]:,}")
con.close()
EOF
```

**Crontab:**
```bash
0 6 * * * cd /path/to/spvx-lite && ./DAILY_UPDATE.sh >> logs/daily_update.log 2>&1
```

**Aufwand:** 1 Stunde

---

### Option 3: Mehr CMEMS-Daten (Wind & Currents) ⭐⭐
**Was:** Vollständige Sea State Daten (nicht nur Waves)

**Warum:** Aktuell nur Wave-Daten (VHM0), Wind & Currents sind 0

**Tasks:**
1. CMEMS Currents Dataset runterladen
2. CMEMS Wind Dataset runterladen
3. `join_tracklets_cmems_fast.py` erweitern für multiple NetCDF files
4. Head-Current & Head-Wind richtig berechnen

**CMEMS Datasets:**
- Waves: `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i` ✅ Haben wir
- Currents: `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m` ❌ Fehlt
- Wind: Im Wave-Dataset manchmal enthalten

**Aufwand:** 3-4 Stunden (inkl. Download)

---

### Option 4: More Tracklets verarbeiten ⭐
**Was:** Alle 4,134 Tracklets mit CMEMS verknüpfen (nicht nur 100)

**Warum:** Aktuell limit=100 für Demo

**Task:**
Ändere in `join_tracklets_cmems_fast.py`:
```python
# Zeile 38
tracklets = load_tracklets(limit=4134)  # Statt 100
```

**Aufwand:** 5 Minuten + 30 Min Runtime

**Result:** ~12,000 samples statt 286

---

### Option 5: Historical Analysis Dashboard ⭐⭐
**Was:** Timeline Chart für SIS-Trends

**Features:**
- Line Chart: SIS Score über Zeit
- Vergleich verschiedener Corridors
- Seasonal Patterns erkennen
- Alerts bei hohen SIS-Werten

**Aufwand:** 3-4 Stunden

---

### Option 6: Alerting System ⭐⭐
**Was:** Email/Slack notifications bei hohen SIS-Werten

**Trigger:**
- SIS > 0.7 (high impact conditions)
- Dwell time > threshold
- Anomalien in Transit times

**Aufwand:** 2-3 Stunden

---

### Option 7: Panama Canal Integration ⭐⭐⭐
**Was:** Panama Canal als neuen Corridor hinzufügen

**Status:** PANAMA_CANAL_IMPLEMENTATION.md existiert schon!

**Tasks:**
1. Gates definieren (Pacific side, Atlantic side)
2. Corridor config hinzufügen
3. Testen mit echten Daten

**Aufwand:** 2-3 Stunden

---

### Option 8: Ship Registry Full Integration ⭐
**Was:** Ship details (type, size, age) zu Tracklets hinzufügen

**Why:** Bessere Analytics (z.B. unterschiedlicher SIS impact für verschiedene Schiffstypen)

**Status:** Registry infrastructure existiert bereits!

**Files:**
- `src/spvx/registry/` - Vorhanden
- `migrate_ship_registry.py` - Vorhanden

**Aufwand:** 2 Stunden

---

## 🏃‍♂️ SCHNELLE WINS (< 1 Stunde)

### 1. Consumer als Service (systemd/launchd)
Damit Consumer automatisch startet nach Reboot.

### 2. Monitoring Dashboard
Grafana + Prometheus für System Metrics (bereits vorbereitet!)

### 3. Database Backup Script
```bash
#!/bin/bash
cp db/spvx.duckdb backups/spvx_$(date +%Y%m%d).duckdb
```

### 4. API Documentation
Swagger/OpenAPI docs für alle Endpoints.

### 5. README Update
Komplette Dokumentation des aktuellen Status.

---

## 📊 EMPFOHLENE REIHENFOLGE

Für maximalen Impact in kürzester Zeit:

1. **Option 4** (5 Min) - Alle Tracklets verarbeiten → Sofort mehr Daten
2. **Option 2** (1h) - Automatisierung → Läuft dann automatisch
3. **Option 1** (2-3h) - Dashboard Integration → User sehen Weather Impact
4. **Option 7** (2-3h) - Panama Canal → Mehr Corridors
5. **Option 3** (3-4h) - Wind & Currents → Bessere SIS Scores
6. **Option 5** (3-4h) - Historical Analysis → Insights gewinnen

---

## 🎯 WELCHE OPTION WILLST DU ZUERST?

Sag mir einfach eine Nummer (1-8) oder einen der Quick Wins!

**Meine Empfehlung:**
- **Quick Win jetzt:** Option 4 (alle Tracklets verarbeiten - 5 Min)
- **Dann:** Option 1 (Dashboard Sea State Badges - direkter User Impact)
- **Danach:** Option 2 (Automatisierung - läuft dann alleine)

Was meinst du? 🚀
