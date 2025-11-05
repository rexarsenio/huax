# 🚀 HUAX Platform - Startup Guide

## 📋 ÜBERSICHT: MOCK vs. PRODUCTION

### **GARANTIERT GETRENNT!**

| Modus | Datenbank | Verwendung | Daten überschreiben? |
|-------|-----------|------------|---------------------|
| **Mock** | `db/spvx_MOCK.duckdb` | Testing, Development, Mediterranean Basin testen | ❌ NEIN - separate DB |
| **Production** | `db/spvx.duckdb` | Echte Daten, Live-Betrieb | ❌ NEIN - separate DB |

**✅ SICHER:** Mock-Daten können NIEMALS echte Produktionsdaten überschreiben!

---

## 🧪 OPTION 1: MOCK-MODUS (Empfohlen zum Testen)

### Wann nutzen?
- ✅ Mediterranean Basin Features testen
- ✅ Entwicklung ohne echte API-Keys
- ✅ Schnelles Prototyping
- ✅ Frontend-Entwicklung

### Starten:

**Terminal 1 - Backend (Mock):**
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
./START_MOCK.sh
```

**Terminal 2 - Frontend:**
```bash
cd /Users/alongo/Desktop/huax/dashboard
./START_DASHBOARD.sh
```

**Was passiert:**
1. Generiert 420 Tage Mock-Daten in `db/spvx_MOCK.duckdb`
2. Berechnet alle Komponenten inkl. **Mediterranean (NEU!)**
3. Startet API auf `http://localhost:8080`
4. Frontend öffnet `http://localhost:5173`

**Testen:**
- Öffne Browser: `http://localhost:5173`
- Klicke auf **"Mediterranean"** Tab
- Komponenten sichtbar: CQ_SUEZ, CQ_GIBRALTAR, PORT_MED
- Sprache wechseln: EN → ES → IT → PT

---

## 🚀 OPTION 2: PRODUCTION-MODUS (Echte Daten)

### Wann nutzen?
- ✅ Live-Betrieb mit echten AIS-Daten
- ✅ Echte Port-APIs (NxtPort, Rotterdam, etc.)
- ✅ CMEMS Wetterdaten
- ✅ Production Deployment

### Voraussetzungen:
1. Alle API-Keys in `.env` konfiguriert ✅ (bereits erledigt!)
2. Echte Daten bereits ingested (siehe unten)

### Starten:

**Terminal 1 - Backend (Production):**
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
./START_PRODUCTION.sh
```

**Terminal 2 - Frontend:**
```bash
cd /Users/alongo/Desktop/huax/dashboard
./START_DASHBOARD.sh
```

### Echte Daten ingestieren (einmalig):
```bash
cd /Users/alongo/Desktop/huax/spvx-lite

# Live AIS-Daten + Port-APIs abrufen
python -m spvx.cli ingest --mode live

# Komponenten berechnen
python -m spvx.cli compute-components

# Indizes berechnen
python -m spvx.cli compute-index
```

---

## 📊 DATENBANK-ÜBERSICHT

### Wo liegen die Daten?

```
spvx-lite/db/
├── spvx.duckdb          ← PRODUCTION (echte Daten)
└── spvx_MOCK.duckdb     ← MOCK (Test-Daten)
```

### Datenbanken prüfen:

**Mock-DB überprüfen:**
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
python -c "
import duckdb
con = duckdb.connect('db/spvx_MOCK.duckdb')
print('Mock DB - Basins:', con.execute('SELECT DISTINCT basin FROM components_daily').fetchall())
print('Mock DB - Rows:', con.execute('SELECT COUNT(*) FROM components_daily').fetchone()[0])
con.close()
"
```

**Production-DB überprüfen:**
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
python -c "
import duckdb
con = duckdb.connect('db/spvx.duckdb')
print('Production DB - Basins:', con.execute('SELECT DISTINCT basin FROM components_daily').fetchall())
print('Production DB - Rows:', con.execute('SELECT COUNT(*) FROM components_daily').fetchone()[0])
con.close()
"
```

---

## 🧹 DATENBANKEN LÖSCHEN (falls nötig)

### Mock-DB zurücksetzen:
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
rm db/spvx_MOCK.duckdb
./START_MOCK.sh  # Generiert neue Mock-Daten
```

### Production-DB zurücksetzen (VORSICHT!):
```bash
cd /Users/alongo/Desktop/huax/spvx-lite
rm db/spvx.duckdb
# Dann echte Daten neu ingestieren
python -m spvx.cli ingest --mode live
```

---

## 🔍 API-ENDPUNKTE TESTEN

### Nach Backend-Start testen:

```bash
# Health-Check
curl http://localhost:8080/health

# Mediterranean Index (NEU!)
curl http://localhost:8080/api/index/MED?range=90d | jq

# Mediterranean Komponenten (NEU!)
curl http://localhost:8080/api/components/MED?range=30d | jq

# Global Index (inkl. MED)
curl http://localhost:8080/api/index/global?range=90d | jq

# Meta-Daten (inkl. MED-Driver)
curl http://localhost:8080/meta | jq '.drivers[] | select(.id | contains("SUEZ"))'
```

---

## 🌍 MEDITERRANEAN BASIN FEATURES TESTEN

### Checklist:

**Backend (API):**
- [ ] `/api/index/MED` gibt Daten zurück
- [ ] `/api/components/MED` zeigt 3 Komponenten: CQ_SUEZ, CQ_GIBRALTAR, PORT_MED
- [ ] `/meta` enthält MED-Treiber

**Frontend (Dashboard):**
- [ ] "Mediterranean" Tab ist sichtbar
- [ ] Index-Wert wird angezeigt
- [ ] 3 Komponenten-Cards vorhanden
- [ ] Zeitreihen-Chart funktioniert
- [ ] Saisonale Gauge funktioniert

**i18n (Mehrsprachigkeit):**
- [ ] Englisch: "Suez Canal", "Strait of Gibraltar", "Mediterranean Ports"
- [ ] Spanisch: "Canal de Suez", "Estrecho de Gibraltar", "Puertos Mediterráneos"
- [ ] Italienisch: "Canale di Suez", "Stretto di Gibilterra", "Porti Mediterranei"
- [ ] Portugiesisch: "Canal de Suez", "Estreito de Gibraltar", "Portos Mediterrâneos"

---

## ⚠️ TROUBLESHOOTING

### Backend startet nicht:
```bash
# Port 8080 bereits belegt?
lsof -ti:8080 | xargs kill -9

# Python-Dependencies fehlen?
cd /Users/alongo/Desktop/huax/spvx-lite
pip install -e .
```

### Frontend startet nicht:
```bash
# Port 5173 bereits belegt?
lsof -ti:5173 | xargs kill -9

# Dependencies fehlen?
cd /Users/alongo/Desktop/huax/dashboard
pnpm install
```

### Mock-Daten Generation schlägt fehl:
```bash
# Datenbank löschen und neu generieren
cd /Users/alongo/Desktop/huax/spvx-lite
rm -f db/spvx_MOCK.duckdb
RUN_MODE=mock DUCKDB_PATH=db/spvx_MOCK.duckdb python -m spvx.cli ingest --mode mock
```

---

## 📝 SCHNELLREFERENZ

### Mock-Modus starten:
```bash
# Terminal 1
cd /Users/alongo/Desktop/huax/spvx-lite && ./START_MOCK.sh

# Terminal 2
cd /Users/alongo/Desktop/huax/dashboard && ./START_DASHBOARD.sh
```

### Production-Modus starten:
```bash
# Terminal 1
cd /Users/alongo/Desktop/huax/spvx-lite && ./START_PRODUCTION.sh

# Terminal 2
cd /Users/alongo/Desktop/huax/dashboard && ./START_DASHBOARD.sh
```

### URLs:
- Backend API: `http://localhost:8080`
- Frontend Dashboard: `http://localhost:5173`
- Mediterranean Index: `http://localhost:8080/api/index/MED`
- API Docs: `http://localhost:8080/docs` (FastAPI auto-docs)

---

## ✅ ZUSAMMENFASSUNG

**Deine Sorge war berechtigt, aber:**

✅ Mock-Daten: `db/spvx_MOCK.duckdb` (separate Datei!)
✅ Echte Daten: `db/spvx.duckdb` (separate Datei!)
✅ Startup-Scripts: Stellen sicher, dass richtige DB verwendet wird
✅ Kann nicht verwechselt werden: Explizite Umgebungsvariablen

**Du bist 100% sicher!** 🔒
