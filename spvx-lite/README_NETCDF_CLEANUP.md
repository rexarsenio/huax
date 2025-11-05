# NetCDF Auto-Cleanup

## Problem
CMEMS NetCDF-Dateien sind sehr groß (1.8 GB pro Datei). Sie stapeln sich und füllen den Speicher!

## Lösung
Auto-Cleanup Script das nur die 2 neuesten Dateien behält.

## Manuell ausführen
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
./CLEANUP_NETCDF.sh
```

## Automatisch täglich ausführen (Empfohlen!)

### Option 1: Cron Job (läuft automatisch jeden Tag um 2 Uhr nachts)
```bash
# Crontab öffnen
crontab -e

# Diese Zeile hinzufügen:
0 2 * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./CLEANUP_NETCDF.sh >> logs/cleanup.log 2>&1
```

### Option 2: Manuell wenn nötig
Wenn der Ordner zu groß wird (>10 GB), einfach das Script ausführen!

## Was macht das Script?
- Behält die 2 neuesten NetCDF-Dateien in `data/sea_state/waves/`
- Behält die 2 neuesten NetCDF-Dateien in `data/sea_state/currents/`
- Löscht alle älteren Dateien
- Spart ~20-25 GB Speicherplatz!

## Warum ist das sicher?
Die historischen Wetter-Daten sind **in der Datenbank** gespeichert (`sea_state_daily` table).
Die NetCDF-Dateien sind nur temporär zum Processing!

## Monitoring
```bash
# Ordnergröße checken
du -sh /Users/alongo/Desktop/huax/spvx-lite/data/sea_state

# Cleanup Log ansehen
tail -f /Users/alongo/Desktop/huax/spvx-lite/logs/cleanup.log
```
