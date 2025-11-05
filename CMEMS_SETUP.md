# 🌊 CMEMS Setup für Gate Weather System

## Warum CMEMS?

Dein System nutzt **CMEMS (Copernicus Marine Environment Monitoring Service)** - nicht NOAA!

**Vorteile:**
- ✅ Globale Abdeckung
- ✅ Hohe Genauigkeit
- ✅ 3-stündige Updates (Wellen)
- ✅ 6-stündige Updates (Strömungen)
- ✅ EU-finanziert, zuverlässig

## 📝 CMEMS Account erstellen (KOSTENLOS)

### 1. Registrieren

Gehe zu: **https://data.marine.copernicus.eu/register**

- Name, Email, Land angeben
- Account wird sofort freigeschaltet
- **100% kostenlos** für Forschung & Entwicklung

### 2. Credentials notieren

Nach Registrierung hast du:
- `CMEMS_USERNAME`: Deine Email oder Username
- `CMEMS_PASSWORD`: Dein Passwort

## ⚙️ Setup auf deinem System

### Option 1: .env Datei (empfohlen)

```bash
cd spvx-lite

# Erstelle .env Datei
cat > .env << 'EOF'
CMEMS_USERNAME=deine_email@example.com
CMEMS_PASSWORD=dein_passwort
EOF

# Sicherheit: Nur du kannst lesen
chmod 600 .env
```

### Option 2: Environment Variables

```bash
# In deiner Shell (.bashrc oder .zshrc)
export CMEMS_USERNAME="deine_email@example.com"
export CMEMS_PASSWORD="dein_passwort"
```

## 🚀 Wetterdaten sammeln

### Erste Sammlung

```bash
cd spvx-lite

# Mit CMEMS (neu, korrekt)
./COLLECT_GATE_WEATHER_CMEMS.sh
```

**Das dauert 5-10 Minuten** beim ersten Mal:
- Lädt ~2 Tage Wellendaten (CMEMS WW3 Modell)
- Lädt ~2 Tage Strömungsdaten (CMEMS Physik-Modell)
- Extrahiert Features für 11 Gates
- Speichert in DuckDB

### Was du sehen solltest:

```
🌊 Starting Gate Weather Collection (CMEMS)...
=====================================
Fetching CMEMS data for GATE_HORMUZ (Strait of Hormuz)...
  📥 Downloading wave data...
  [CMEMS WAVES] Found 8 existing files, downloading 0 missing
  📥 Downloading current data...
  [CMEMS CURRENTS] All files already cached
  📊 Extracting features...
  ✅ Extracted 16 records
     Waves: 2.15m
     Current: 1.44kn

Fetching CMEMS data for GATE_WEST_AFRICA_BONNY...
  ✅ Extracted 16 records
     Waves: 1.92m
     Current: 1.04kn

...

✅ Inserted/updated 176 gate weather records
```

## 📊 Verwendete Datasets

### Wellen
```
Dataset: cmems_mod_glo_wav_anfc_0.083deg_PT3H-i
Beschreibung: Global Wave Analysis and Forecast
Auflösung: ~9km
Update: Alle 3 Stunden
Parameter: Wellenhöhe (hs), Periode (tp), Richtung (dp)
```

### Strömungen
```
Dataset: cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i
Beschreibung: Global Ocean Physics Analysis and Forecast
Auflösung: ~9km
Update: Alle 6 Stunden
Parameter: u/v Strömungen, Geschwindigkeit
```

## 🔄 Automatische Updates

### Cron Job Setup

```bash
# Crontab bearbeiten
crontab -e

# Alle 6 Stunden sammeln (nach CMEMS Updates)
30 */6 * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./COLLECT_GATE_WEATHER_CMEMS.sh >> logs/gate_weather_cmems.log 2>&1

# ODER: 2x täglich (Morgens + Abends)
0 6,18 * * * cd /Users/alongo/Desktop/huax/spvx-lite && ./COLLECT_GATE_WEATHER_CMEMS.sh >> logs/gate_weather_cmems.log 2>&1
```

## 📍 Daten-Cache

CMEMS lädt Dateien nach:
```
spvx-lite/data/sea_state/*.nc
```

**Beim ersten Mal:** ~500MB Download
**Danach:** Nur neue Dateien (inkrementell)

**Cache-Management:**
```bash
# Alte Dateien löschen (>7 Tage)
find data/sea_state -name "*.nc" -mtime +7 -delete

# Speicherplatz prüfen
du -sh data/sea_state
```

## 🐛 Troubleshooting

### Problem: "CMEMS credentials not set"

**Lösung:**
```bash
cd spvx-lite
cat > .env << 'EOF'
CMEMS_USERNAME=deine_email
CMEMS_PASSWORD=dein_passwort
EOF
```

### Problem: "Authentication failed"

**Ursachen:**
- Falscher Username/Passwort
- Account noch nicht aktiviert (Check Email)
- Account gesperrt (zu viele Downloads)

**Lösung:**
1. Login testen: https://data.marine.copernicus.eu
2. Passwort zurücksetzen falls nötig
3. Neuen Account erstellen (mit anderer Email)

### Problem: "No data files downloaded"

**Ursachen:**
- CMEMS Server offline (selten)
- Netzwerkprobleme
- Quota überschritten

**Lösung:**
```bash
# Status prüfen: https://marine.copernicus.eu/services-portfolio/news/
# Später nochmal versuchen (1-2 Stunden)
```

### Problem: "Slow downloads"

**CMEMS kann langsam sein!**
- Erste Download: 5-10 Minuten normal
- Danach: 1-2 Minuten (nur neue Dateien)

**Geduld haben!** ⏰

## 🆚 CMEMS vs. NOAA

| Feature | CMEMS | NOAA (alt) |
|---------|-------|------------|
| **Coverage** | Global ✅ | Global ✅ |
| **Resolution** | 9km ✅ | 13km |
| **Updates** | 3-6h ✅ | 6-12h |
| **Reliability** | Sehr gut ✅ | Mittel ⚠️ |
| **Auth Required** | Ja (kostenlos) | Nein |
| **Your System** | ✅ **IN USE** | ❌ Falsch |

## 📚 Weitere Infos

**CMEMS Docs:**
- https://help.marine.copernicus.eu/
- https://data.marine.copernicus.eu/products

**Python Package:**
```bash
pip install copernicusmarine
```

**Support:**
- servicedesk.cmems@mercator-ocean.eu

---

## ✅ Quick Start Checklist

- [ ] CMEMS Account erstellen
- [ ] .env Datei mit Credentials erstellen
- [ ] `./COLLECT_GATE_WEATHER_CMEMS.sh` ausführen
- [ ] Browser neu laden (F5)
- [ ] Wetterdaten im Dashboard sehen!

---

**Erstellt:** 2025-11-05
**System:** CMEMS (Copernicus Marine)
**Status:** ✅ Produktionsbereit
