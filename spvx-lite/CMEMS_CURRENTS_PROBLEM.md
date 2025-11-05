# CMEMS Strömungs-Daten Problem - Technische Beschreibung

## Zusammenfassung
Wir können CMEMS **Wellen-Daten** erfolgreich laden, aber **Strömungs-Daten (uo/vo) und Wind-Daten (u10/v10) laden NICHT**.

## Aktueller Status
- ✅ **Wellen**: Funktioniert perfekt (VHM0 wave height)
- ❌ **Strömungen**: Download hängt oder liefert falsches Dataset
- ❌ **Wind**: Nicht verfügbar in den Datasets die wir zugreifen können

## Technische Details

### Was funktioniert (Wellen):
```yaml
Dataset ID: cmems_mod_glo_wav_anfc_0.083deg_PT3H-i
Download: ✅ Erfolgreich (26 files in ~10 Min)
Variablen: VHM0 (significant wave height)
Dateiformat: NetCDF
Dateigröße: ~20-50 MB pro Datei
```

### Was NICHT funktioniert (Strömungen):

#### Versuch 1: Physics Daily Dataset
```yaml
Dataset ID: cmems_mod_glo_phy_anfc_0.083deg_P1D-m
Problem: Falsches Dataset!
Enthält: siconc (sea ice), sithick (ice thickness), zos (sea surface height)
Enthält NICHT: uo/vo (ocean currents)
Ergebnis: Download erfolgreich ABER falsche Variablen
```

#### Versuch 2: Physics 6-hourly Dataset
```yaml
Dataset ID: cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i
Problem: Download hängt bei 0/52 files
Verhalten:
  - Listing files: ✅ Funktioniert (findet 52 files)
  - Download start: ❌ Hängt ewig bei "Downloading files: 0%"
  - Keine Fehlermeldung, nur timeout/hang
Dateigröße: ~1.8 GB pro Datei (52 files = ~94 GB total!)
```

## Root Cause Analysis

### Mögliche Ursachen:

1. **Falsches Dataset-ID**
   - Die Dataset-IDs die wir haben enthalten KEINE ocean currents (uo/vo)
   - Oder sie sind zu groß (1.8 GB/file) und timeout

2. **Zugangsbeschränkungen**
   - CMEMS API Key hat evtl. keine Berechtigung für Physics-Datasets
   - Nur Zugriff auf Waves, nicht auf Physics/Atmosphere

3. **Download-Timeout**
   - 52 files à 1.8 GB = 94 GB ist zu viel
   - Netzwerk-Timeout oder Rate-Limiting

4. **Falsches Zeitfenster**
   - lookback-days=2 versucht zu viele files zu laden
   - Sollte nur 1-2 files brauchen für aktuelle Daten

## Was wir brauchen

### Variablen (CMEMS Standard Names):
```python
# Ocean Currents
uo  # eastward_sea_water_velocity (m/s)
vo  # northward_sea_water_velocity (m/s)

# Wind (Optional aber wichtig)
u10  # eastward_wind (m/s)
v10  # northward_wind (m/s)

# Aktuell haben wir
VHM0  # significant_wave_height (m) ✅
```

### Korrekte Dataset-IDs gesucht:
```
Wellen (funktioniert):
  cmems_mod_glo_wav_anfc_0.083deg_PT3H-i

Strömungen (gesucht):
  Dataset mit uo/vo Variablen
  Kleinere Files (<100 MB)
  Oder reduziertes räumliches Gebiet

Wind (optional):
  Dataset mit u10/v10 Variablen
```

## Unser Use Case

### Räumlicher Bereich:
Wir brauchen NICHT global! Nur diese Regionen:
- Strait of Malacca (1°-4°N, 100°-104°E)
- Strait of Gibraltar (35°-37°N, -6°--5°W)
- Suez Canal approaches (29°-32°N, 32°-34°E)
- Bosporus (41°N, 29°E)
- Singapore Strait (1°-2°N, 103°-104°E)

### Zeitliche Auflösung:
- Täglich oder 6-stündlich ist okay
- Brauchen nur letzte 2-3 Tage (nicht Monate!)

### Datenmenge:
- Aktuell: 26 wave files (~1 GB total) ✅
- Gewünscht: ~26 current files (~1-5 GB total) ❌ Aktuell 94 GB!

## Fragen an Kollegen

1. **Welches ist das RICHTIGE CMEMS Dataset-ID für ocean currents (uo/vo)?**
   - Mit kleineren Files (<100 MB)
   - Oder regional begrenzt auf Europa/Asien

2. **Haben wir die richtigen API-Zugriffsrechte?**
   - Können wir Physics-Datasets überhaupt zugreifen?
   - Oder nur Waves?

3. **Gibt es ein "Light" Physics-Dataset?**
   - Nur surface currents (nicht 3D)
   - Oder nur bestimmte Regionen

4. **Alternative Datenquellen?**
   - RTOFS (US Navy)?
   - HYCOM?
   - Andere operationale Modelle?

## Code/Config

### Aktuell verwendeter Code:
```python
# config.yml
sea_state:
  waves_dataset_id: "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"  # ✅ Funktioniert
  currents_dataset_id: "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"  # ❌ Hängt

# Download Command:
python -m spvx.cli ingest-sea-state --provider=cmems --lookback-days=2
```

### API Credentials:
```python
AISSTREAM_API_KEY=94a1eaf8b29a86e98576f8f9a842c51414988412  # AIS (funktioniert)
# CMEMS credentials? Wo sind diese?
```

## Gewünschtes Ergebnis

### In der Datenbank:
```sql
SELECT
  corridor_id,
  sis_mean,        -- Combined score (0-1)
  we_p90_m,        -- Wave height 90th percentile ✅ HAT WERTE
  hc_p90_kn,       -- Current speed 90th percentile ❌ IMMER 0!
  hw_p90_ms        -- Wind speed 90th percentile ❌ IMMER 0!
FROM sea_state_daily;
```

Aktuell:
- we_p90_m: 0.14-0.59m ✅
- hc_p90_kn: 0.0 ❌
- hw_p90_ms: 0.0 ❌

## Impact

**Warum das wichtig ist:**
Der SPVX Global Index v1.5 nutzt SIS (Sea Impact Score) als Komponente.

Aktuell:
```
SIS = 50% Wellen + 0% Strömungen + 0% Wind
```

Gewünscht:
```
SIS = 33% Wellen + 33% Strömungen + 33% Wind
```

**Ohne Strömungen & Wind ist der Index nur 33% komplett!**

Strömungen sind extrem wichtig weil:
- Schiffe müssen gegen Strömungen ankämpfen
- Verzögert Transit-Zeiten
- Erhöht Treibstoffverbrauch
- Kritisch in engen Straßen (Malacca, Gibraltar, Bosporus)

## Logs/Fehler

```
Downloading CMEMS currents...
INFO - Selected dataset version: "202406"
INFO - Listing files on remote server...
6it [00:01,  5.24it/s]  # ✅ Findet 52 files
INFO - Selected dataset version: "202406"
Downloading files:   0%| | 0/52 [00:00<?,  # ❌ HÄNGT HIER
```

Keine Error-Message, nur Hang/Timeout!

## Kontakt

Bei Fragen:
- Code: `/Users/alongo/Desktop/huax/spvx-lite/`
- Config: `config.yml`
- CLI: `python -m spvx.cli ingest-sea-state --help`
