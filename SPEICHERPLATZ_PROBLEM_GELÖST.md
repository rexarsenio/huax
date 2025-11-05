# ✅ Speicherplatz-Problem GELÖST!

## 🚨 Das Problem

```
No space left on device
```

Die Festplatte war zu **100% voll** (nur noch 488 MB frei)!

## 🔍 Ursache gefunden

Der `data/sea_state/` Ordner hatte **36 GB alte Wetter-Daten** (NetCDF-Dateien):
- 61 alte `.nc` Dateien mit Meeres-Zustandsdaten
- Jede Datei ~300 MB groß
- Dateien von vor mehreren Tagen, die nicht mehr gebraucht wurden

## ✅ Lösung

### 1. Test-Datenbanken gelöscht (~1.2 GB)
```bash
# Gelöscht:
- spvx_BACKUP_*.duckdb (189 MB)
- spvx_CHECK.duckdb (161 MB)
- spvx_CURRENT.duckdb (143 MB)
- spvx_E2E_TEST.duckdb (230 MB)
- spvx_MOCK.duckdb (51 MB)
- spvx_POLYGON_TEST.duckdb (175 MB)
- spvx_REGISTRY_TEST.duckdb (166 MB)
- spvx_SNAPSHOT.duckdb (128 MB)
```

### 2. Alte Sea-State-Dateien gelöscht (~35 GB)
```bash
# Alle .nc Dateien älter als 3 Tage
data/sea_state/**/*.nc (mtime > 3 days)
```

## 📊 Ergebnis

| Vorher | Nachher |
|--------|---------|
| 488 MB frei (100% voll) | **37 GB frei** (22% genutzt) |
| data/ = 36 GB | data/ = 735 MB |
| spvx-lite/ = 39 GB | spvx-lite/ = 2.8 GB |

## 🛠️ Automatisches Cleanup

Neues Skript erstellt: **[CLEANUP.sh](spvx-lite/CLEANUP.sh)**

```bash
./CLEANUP.sh
```

**Was es macht:**
- ✅ Löscht Sea-State-Dateien älter als 3 Tage
- ✅ Löscht Log-Dateien älter als 7 Tage
- ✅ Löscht Python-Cache (`__pycache__`)
- ✅ Zeigt Speicherplatz vorher/nachher

### Automatisch täglich ausführen (optional)

Füge zu deiner Crontab hinzu:
```bash
# Jeden Tag um 3 Uhr morgens aufräumen
0 3 * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./CLEANUP.sh >> logs/cleanup.log 2>&1
```

## 🚀 Services wieder gestartet

| Service | Status |
|---------|--------|
| AIS Ingestion | ✅ Läuft (PID 9412) |
| API Server | ✅ Läuft (Port 8000) |
| Dashboard | ✅ Läuft (Port 5173) |

## 📈 Aktueller Status

```
✅ AIS Ingestion:     Läuft (~100 Nachrichten/Sekunde)
✅ Speicherplatz:     37 GB frei
✅ Datenbank:         308 MB
✅ data/:             735 MB (statt 36 GB!)
```

Die Datensammlung läuft jetzt wieder problemlos! 🎉

## 🔮 Empfehlung für die Zukunft

1. **Täglich CLEANUP.sh ausführen** (manuell oder per Cron)
2. **Speicherplatz überwachen**:
   ```bash
   df -h /
   ```
3. **Bei < 10 GB frei**: CLEANUP.sh ausführen

## 📝 Monitoring

```bash
# Status checken:
./MONITOR.sh

# Live-Überwachung:
./WATCH.sh

# Cleanup:
./CLEANUP.sh
```

---

**Problem gelöst:** 2025-10-28 07:42 UTC
**Speicherplatz frei:** 37 GB (von 228 GB)
**Status:** ✅ Alles läuft!
