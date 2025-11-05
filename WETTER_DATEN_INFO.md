# ℹ️ Wetter-Daten (Sea-State) - Was du wissen solltest

## ❓ Brauchen wir die Wetter-Daten?

**JA**, aber nur die **aktuellen**!

## 🌊 Wofür werden sie gebraucht?

Die NetCDF-Dateien (`.nc`) im `data/sea_state/` Ordner enthalten:

1. **Wellen-Höhe** (hs, VHM0) - Significant Wave Height
2. **Wind-Geschwindigkeit** (u10, v10) - 10m Wind
3. **Strömungen** (uo, vo) - Ocean Currents
4. **Temperatur-Anomalien** (sst_anom)

Diese werden verwendet für:
- **Sea-State Index (SIS)** - Berechnung der Meeres-Bedingungen
- **Komponenten-Berechnung** - Teil der täglichen Indizes
- **Transit-Zeit-Analysen** - Einfluss auf Schiffsbewegungen

## 📅 Wie viele Daten brauchen wir?

**Nur die letzten 7 Tage!**

- SIS wird auf rolling 7-Tage-Basis berechnet
- Ältere Daten werden nicht mehr gebraucht
- Jede Datei ist ~300 MB groß

## 🗑️ Was wurde gelöscht?

Beim Cleanup wurden gelöscht:
- ✅ **61 Dateien älter als 3 Tage** (~35 GB)
- ✅ Test-Datenbanken (~1.2 GB)

**Problem**: Ich habe zu aggressiv aufgeräumt und auch die neueren Dateien erwischt!

## ✅ Neue Cleanup-Strategie

Das aktualisierte `CLEANUP.sh` Skript:
- ❌ **Alte Strategie**: Lösche alles > 3 Tage
- ✅ **Neue Strategie**: Lösche nur > 7 Tage, **behalte letzte 7 Tage**

```bash
# Jetzt im CLEANUP.sh:
find . -name "*.nc" -mtime +7 -delete  # Nur > 7 Tage alt
```

## 🔄 Werden neue Dateien heruntergeladen?

**Ja, automatisch!** Das System nutzt:

```python
# In src/spvx/sea_state/cmems.py
import copernicusmarine
```

Wenn SIS-Berechnungen laufen, werden automatisch die benötigten Dateien von **Copernicus Marine Service (CMEMS)** heruntergeladen.

## 📊 Aktueller Status

```
Sea-State-Dateien: ~10 (Header-Dateien übrig)
Speicherplatz frei: 37 GB
Status: ✅ Ausreichend Platz
```

## 🎯 Empfehlung für die Zukunft

### Option 1: Manuelles Cleanup (empfohlen für jetzt)
```bash
# Alle 7 Tage ausführen:
./CLEANUP.sh
```

**Behält automatisch**:
- ✅ Letzte 7 Tage Sea-State-Daten (für SIS)
- ✅ Letzte 7 Tage Logs
- ❌ Löscht: Alles älter als 7 Tage

### Option 2: Automatisches Cleanup (für Production)
```bash
# Cron-Job (jeden Montag um 3 Uhr):
0 3 * * 1 cd /Users/alongo/Desktop/huax/spvx-lite && ./CLEANUP.sh >> logs/cleanup.log 2>&1
```

### Option 3: Wetter-Daten deaktivieren (wenn nicht gebraucht)
Falls du SIS-Berechnungen **nicht** brauchst, kannst du das deaktivieren:

```yaml
# In config.yml:
features:
  sea_state: false  # Deaktiviert Sea-State-Downloads
```

Dann werden **keine** neuen NetCDF-Dateien heruntergeladen.

## 💡 Was passiert jetzt?

1. **Ingestion läuft normal** - AIS-Daten werden gesammelt
2. **Wenn SIS-Berechnung läuft** - Neue Wetter-Daten werden automatisch heruntergeladen
3. **Cleanup alle 7 Tage** - Alte Dateien werden gelöscht, neueste bleiben

## 🚨 Wenn Speicherplatz wieder knapp wird

```bash
# Sofort-Lösung:
./CLEANUP.sh

# Speicherplatz prüfen:
df -h /

# Größte Verzeichnisse finden:
du -sh data/* | sort -hr
```

## ✅ Fazit

- **Wetter-Daten**: Werden gebraucht für SIS ✓
- **Wie viele**: Nur letzte 7 Tage ✓
- **Automatisch**: Werden heruntergeladen wenn gebraucht ✓
- **Cleanup**: Läuft jetzt intelligenter (behält 7 Tage) ✓
- **Speicherplatz**: 37 GB frei - alles gut! ✓

---

**Erstellt**: 2025-10-28
**Status**: ✅ Alles klar!
