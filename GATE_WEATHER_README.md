# 🌊 Gate Weather System - Unabhängige Wetterdaten

## Überblick

Das Gate Weather System sammelt Wetterdaten (Wellen, Strömungen, Wind) für alle definierten Checkpoints/Gates **unabhängig von Schiffsbewegungen**.

### Problem gelöst ✅

**Vorher:**
- Wetterdaten wurden nur gesammelt, wenn Schiffe durch Gates fuhren (tracklet-basiert)
- Keine Daten sichtbar, wenn keine Schiffe durchfuhren
- Dashboard zeigte "No sea state coverage available"

**Jetzt:**
- Wetterdaten werden regelmäßig für alle Gates gesammelt
- Unabhängig von Schiffsbewegungen
- Immer aktuelle Bedingungen sichtbar

## Architektur

```
┌──────────────────────────────────────────┐
│  NOAA RTOFS (Currents) + WW3 (Waves)   │
│  https://nomads.ncep.noaa.gov/dods/     │
└────────────────┬─────────────────────────┘
                 │
                 │ Fetch every 3-6h
                 ▼
┌──────────────────────────────────────────┐
│  ingest_gate_weather.py                  │
│  - Fetches for all 11 gates             │
│  - Stores in gate_weather_standalone     │
└────────────────┬─────────────────────────┘
                 │
                 │ DuckDB
                 ▼
┌──────────────────────────────────────────┐
│  API: /api/open_sea/gate_weather        │
│  - Returns latest + statistics           │
│  - Filter by gate_ids, time window       │
└────────────────┬─────────────────────────┘
                 │
                 │ REST API
                 ▼
┌──────────────────────────────────────────┐
│  Dashboard: GateWeatherPanel            │
│  - Shows waves (height, period)          │
│  - Shows currents (speed, direction)     │
│  - Auto-refreshes every 30 min           │
└──────────────────────────────────────────┘
```

## Monitored Gates

Das System überwacht folgende 11 Gates/Checkpoints:

1. **GATE_HORMUZ** - Strait of Hormuz (Iran Öl)
2. **GATE_SUEZ_N** - Suez Canal North (Port Said)
3. **GATE_SUEZ_S** - Suez Canal South (Port of Suez)
4. **GATE_BAB_EL_MANDEB** - Bab el-Mandeb Strait
5. **GATE_GIBRALTAR** - Strait of Gibraltar
6. **GATE_BOSPORUS** - Bosporus Strait (Istanbul)
7. **GATE_MALACCA** - Singapore & Malacca Strait
8. **GATE_PANAMA** - Panama Canal
9. **GATE_YUCATAN** - Yucatan Channel (Gulf of Mexico)
10. **GATE_WEST_AFRICA_BONNY** - Bonny Terminal (Nigeria)
11. **GATE_WEST_AFRICA_ESCRAVOS** - Escravos Terminal (Nigeria)

## Installation & Setup

### 1. Datenbank-Tabelle wird automatisch erstellt

Die Tabelle `gate_weather_standalone` wird beim ersten Lauf automatisch erstellt.

### 2. Erste Datensammlung starten

```bash
cd /home/user/huax/spvx-lite

# Manuell starten
./COLLECT_GATE_WEATHER.sh
```

**Erste Sammlung dauert ca. 2-5 Minuten** (lädt Daten von NOAA für 11 Gates)

### 3. Automatische Sammlung (Cron Job)

Empfohlen: Alle 3-6 Stunden ausführen

```bash
# Crontab bearbeiten
crontab -e

# Alle 3 Stunden um :15 ausführen
15 */3 * * * cd /home/user/huax/spvx-lite && ./COLLECT_GATE_WEATHER.sh >> logs/gate_weather.log 2>&1

# ODER: Alle 6 Stunden
0 */6 * * * cd /home/user/huax/spvx-lite && ./COLLECT_GATE_WEATHER.sh >> logs/gate_weather.log 2>&1
```

## Verwendung

### API Endpoints

#### 1. Alle Gates abrufen (24h)

```bash
curl http://localhost:8000/api/open_sea/gate_weather?window=h24
```

#### 2. Spezifische Gates filtern

```bash
curl http://localhost:8000/api/open_sea/gate_weather?window=h24&gate_ids=GATE_HORMUZ,GATE_SUEZ_N
```

#### 3. Längere Zeitfenster

```bash
# Letzte 7 Tage
curl http://localhost:8000/api/open_sea/gate_weather?window=d7

# Letzte 48 Stunden
curl http://localhost:8000/api/open_sea/gate_weather?window=h48
```

### Dashboard

Die Wetterdaten werden angezeigt auf:

**Operations Page:** `http://localhost:5173/operations`

Zeigt:
- 🌊 **Wellen:** Höhe (m), Periode (s), Richtung (°)
- 🌀 **Strömungen:** Geschwindigkeit (kn), U/V-Komponenten
- ⚠️ **Severity Flags:** High/Moderate/Normal
- 📊 **Statistiken:** Mean, P90, Sample Count

Auto-Refresh: Alle 30 Minuten

## Datenstruktur

### Tabelle: `gate_weather_standalone`

```sql
CREATE TABLE gate_weather_standalone (
    gate_id VARCHAR NOT NULL,           -- GATE_HORMUZ, GATE_SUEZ_N, etc.
    gate_name VARCHAR,                  -- "Strait of Hormuz", etc.
    observed_at TIMESTAMP NOT NULL,     -- Observation time (UTC)
    basin VARCHAR,                      -- APAC, MED, NAM, AFRICA

    -- Wave data (from NOAA WW3)
    hs_m DOUBLE,                        -- Significant wave height (meters)
    tp_s DOUBLE,                        -- Wave period (seconds)
    dp_deg DOUBLE,                      -- Wave direction (degrees)
    wave_flag INTEGER,                  -- 1 = high waves (>3.5m)

    -- Current data (from NOAA RTOFS)
    u_knots DOUBLE,                     -- Current u-component (knots)
    v_knots DOUBLE,                     -- Current v-component (knots)
    speed_knots DOUBLE,                 -- Current speed (knots)
    current_flag INTEGER,               -- 1 = strong current (>3.0kn)

    -- Sources
    wave_source VARCHAR,                -- NOAA WW3 URL
    current_source VARCHAR,             -- NOAA RTOFS URL

    collected_at TIMESTAMP,             -- When data was collected

    PRIMARY KEY (gate_id, observed_at)
)
```

### API Response Format

```json
{
  "window": "h24",
  "start": "2025-11-04T11:48:00+00:00",
  "end": "2025-11-05T11:48:00+00:00",
  "gates": [
    {
      "gate_id": "GATE_HORMUZ",
      "gate_name": "Strait of Hormuz",
      "basin": "APAC",
      "latest_observation": {
        "observed_at": "2025-11-05T09:00:00",
        "waves": {
          "height_m": 2.15,
          "period_s": 8.2,
          "direction_deg": 245.0,
          "flag": 0,
          "severity": "normal"
        },
        "currents": {
          "u_knots": 1.2,
          "v_knots": 0.8,
          "speed_knots": 1.44,
          "flag": 0,
          "severity": "normal"
        }
      },
      "statistics": {
        "samples_count": 8,
        "waves": {
          "mean_height_m": 2.05,
          "max_height_m": 2.45,
          "p90_height_m": 2.38
        },
        "currents": {
          "mean_speed_kn": 1.35,
          "max_speed_kn": 1.82,
          "p90_speed_kn": 1.75
        }
      }
    }
  ]
}
```

## Severity Thresholds

### Wellen
- **Normal:** < 2.0m
- **Moderate:** 2.0 - 3.5m
- **High:** > 3.5m (Flag = 1)

### Strömungen
- **Normal:** < 2.0 kn
- **Moderate:** 2.0 - 3.0 kn
- **High:** > 3.0 kn (Flag = 1)

## Monitoring & Debugging

### Status prüfen

```bash
cd /home/user/huax/spvx-lite

# Letzte Sammlung ansehen
tail -50 logs/gate_weather.log

# Datenbank prüfen
python3 -c "
import duckdb
con = duckdb.connect('db/spvx.duckdb', read_only=True)
print('Total records:', con.sql('SELECT COUNT(*) FROM gate_weather_standalone').fetchone()[0])
print('Latest observations:')
for row in con.sql('''
    SELECT gate_id, observed_at, ROUND(hs_m,2) as waves_m, ROUND(speed_knots,2) as current_kn
    FROM gate_weather_standalone
    ORDER BY observed_at DESC
    LIMIT 10
''').fetchall():
    print(f'  {row[0]:<25} | {row[1]} | Waves: {row[2]}m | Current: {row[3]}kn')
con.close()
"
```

### Logs ansehen

```bash
# Collection logs
tail -f logs/gate_weather.log

# API logs (wenn API läuft)
tail -f /tmp/api_server.log | grep gate_weather
```

### Troubleshooting

#### Problem: "No gate weather data available"

**Lösung:**
```bash
# Erste Sammlung starten
./COLLECT_GATE_WEATHER.sh

# Prüfen ob Daten in DB sind
python3 -c "import duckdb; con = duckdb.connect('db/spvx.duckdb'); print(con.sql('SELECT COUNT(*) FROM gate_weather_standalone').fetchone())"
```

#### Problem: NOAA Server nicht erreichbar

**Symptome:**
```
⚠️  Failed to fetch currents: Could not resolve dataset
```

**Lösung:**
- NOAA Server manchmal offline oder langsam
- Warte 30 Minuten und versuche erneut
- Alte Daten bleiben in der Datenbank

#### Problem: Keine aktuellen Daten im Dashboard

**Prüfen:**
1. Läuft die API? `curl http://localhost:8000/health`
2. Sind Daten in DB? (siehe oben)
3. Browser Console (F12) für Errors checken

## Vorteile vs. Tracklet-basierte Daten

| Aspekt | Alte Methode (Tracklets) | Neue Methode (Standalone) |
|--------|---------------------------|---------------------------|
| **Datensammlung** | Nur wenn Schiffe durchfahren | Unabhängig, regelmäßig |
| **Verfügbarkeit** | Lücken bei wenig Traffic | Kontinuierlich |
| **Latenz** | Real-time mit Schiffen | 3-6h Intervalle |
| **Coverage** | Nur aktive Schiffsrouten | Alle definierten Gates |
| **Anzeige** | "No data" bei 0 Schiffen | Immer verfügbar |

## Nächste Schritte

### Optional: Wind-Daten hinzufügen

Das System sammelt aktuell:
- ✅ Wellen (WW3)
- ✅ Strömungen (RTOFS)
- ⚠️  Wind (u10/v10 in WW3, noch nicht extrahiert)

Für Wind-Daten: siehe `src/spvx/weather/sea_state.py` und erweitere `fetch_ww3_waves()`.

### Optional: Mehr Gates hinzufügen

Bearbeite `ingest_gate_weather.py`, füge zu `GATE_WEATHER_REGIONS` hinzu:

```python
"GATE_NEW_CHECKPOINT": {
    "bbox": {"lat_min": X, "lat_max": Y, "lon_min": A, "lon_max": B},
    "name": "Name of Checkpoint",
    "basin": "REGION",
},
```

## Dateien & Komponenten

### Backend (spvx-lite/)
- `ingest_gate_weather.py` - Hauptsammler
- `COLLECT_GATE_WEATHER.sh` - Wrapper-Skript
- `src/spvx/api_open_sea.py:1398` - API Endpoint
- `src/spvx/weather/sea_state.py` - NOAA Fetchers

### Frontend (dashboard/)
- `src/api/openSea.ts:200` - API Client
- `src/components/GateWeatherPanel.tsx` - React Component
- `src/pages/OperationsPage.tsx:38` - Integration

## Support

Bei Fragen oder Problemen:
1. Logs prüfen: `logs/gate_weather.log`
2. Datenbank Status: siehe "Monitoring" oben
3. API Status: `curl http://localhost:8000/api/open_sea/gate_weather`

---

**Erstellt:** 2025-11-05
**Version:** 1.0
**Status:** ✅ Produktionsbereit
