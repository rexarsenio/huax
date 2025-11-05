# 📦 Gate Weather System - Python Dependencies

## Required Python Packages

Das Gate Weather System benötigt folgende Python-Pakete:

### Core Dependencies

```bash
pip3 install duckdb pandas copernicusmarine
```

**Details:**
- `duckdb` - Datenbank für Speicherung
- `pandas` - Datenverarbeitung und Timestamp-Merging
- `copernicusmarine` - CMEMS Data Access API

### Data Processing Dependencies

Diese werden automatisch mit `copernicusmarine` installiert:
- `xarray` - Multi-dimensionale Array-Verarbeitung
- `netCDF4` - NetCDF File Reading
- `requests` - HTTP Requests

### Optional (für Geodaten)
```bash
pip3 install shapely pyproj
```

---

## Dependency Check

### Automatischer Check beim Start

Das Skript `ingest_gate_weather_final.py` prüft automatisch:

```python
try:
    import copernicusmarine
except ImportError:
    print("❌ copernicusmarine not installed!")
    print("   Install with: pip install copernicusmarine")
    sys.exit(1)
```

### Manueller Check

Prüfe ob alle Pakete installiert sind:

```bash
python3 << 'EOF'
import sys

packages = [
    'duckdb',
    'pandas',
    'copernicusmarine',
    'xarray',
    'netCDF4'
]

print("Checking Python dependencies...")
print("-" * 50)

missing = []
for pkg in packages:
    try:
        __import__(pkg)
        print(f"✅ {pkg:<20} installed")
    except ImportError:
        print(f"❌ {pkg:<20} MISSING")
        missing.append(pkg)

print("-" * 50)

if missing:
    print(f"\n❌ Missing {len(missing)} package(s):")
    print(f"   pip3 install {' '.join(missing)}")
    sys.exit(1)
else:
    print("\n✅ All dependencies installed!")
    sys.exit(0)
EOF
```

---

## Installation

### Option 1: Einzeln installieren

```bash
pip3 install duckdb
pip3 install pandas
pip3 install copernicusmarine
```

### Option 2: Alle zusammen

```bash
pip3 install duckdb pandas copernicusmarine
```

### Option 3: Mit Virtual Environment

```bash
cd /home/user/huax/spvx-lite

# Virtual Environment erstellen (falls nicht vorhanden)
python3 -m venv .venv

# Aktivieren
source .venv/bin/activate

# Dependencies installieren
pip3 install duckdb pandas copernicusmarine

# Testen
python3 ingest_gate_weather_final.py
```

---

## Package Versionen

Getestete Versionen (empfohlen):

```
duckdb >= 0.9.0
pandas >= 2.0.0
copernicusmarine >= 1.0.0
xarray >= 2023.0.0
netCDF4 >= 1.6.0
```

---

## Troubleshooting

### Problem: "No module named 'copernicusmarine'"

**Lösung:**
```bash
pip3 install copernicusmarine
```

### Problem: "No module named 'duckdb'"

**Lösung:**
```bash
pip3 install duckdb
```

### Problem: "No module named 'netCDF4'"

**Lösung:**
```bash
pip3 install netCDF4
```

Oder mit conda:
```bash
conda install -c conda-forge netcdf4
```

### Problem: Permission Denied

**Lösung:** User install verwenden:
```bash
pip3 install --user duckdb pandas copernicusmarine
```

### Problem: Alte Python Version

**Requirement:** Python >= 3.8

**Check:**
```bash
python3 --version
```

Sollte mindestens `Python 3.8.x` ausgeben.

---

## System Dependencies (Linux)

Falls Installation von netCDF4 fehlschlägt, System-Pakete installieren:

### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install libnetcdf-dev libhdf5-dev
pip3 install netCDF4
```

### CentOS/RHEL:
```bash
sudo yum install netcdf-devel hdf5-devel
pip3 install netCDF4
```

### macOS:
```bash
brew install netcdf hdf5
pip3 install netCDF4
```

---

## Verification Script

Führe dieses Skript aus, um alles zu prüfen:

```bash
cd /home/user/huax

python3 << 'EOF'
print("=" * 60)
print("🔍 GATE WEATHER DEPENDENCIES CHECK")
print("=" * 60)
print()

import sys
import importlib.metadata

packages = {
    'duckdb': 'Database',
    'pandas': 'Data Processing',
    'copernicusmarine': 'CMEMS API',
    'xarray': 'Array Processing',
    'netCDF4': 'NetCDF Reader',
}

print("📦 Checking packages...")
print("-" * 60)

all_ok = True
for pkg, desc in packages.items():
    try:
        mod = __import__(pkg)
        try:
            version = importlib.metadata.version(pkg)
        except:
            version = getattr(mod, '__version__', 'unknown')
        print(f"✅ {pkg:<20} {version:<12} ({desc})")
    except ImportError:
        print(f"❌ {pkg:<20} MISSING       ({desc})")
        all_ok = False

print("-" * 60)
print()

if all_ok:
    print("✅ ALL DEPENDENCIES OK!")
    print()
    print("Ready to run:")
    print("  cd spvx-lite && ./COLLECT_GATE_WEATHER.sh")
else:
    print("❌ MISSING DEPENDENCIES!")
    print()
    print("Install with:")
    print("  pip3 install duckdb pandas copernicusmarine")

print()
print("=" * 60)
EOF
```

Erwartete Ausgabe wenn alles OK:

```
============================================================
🔍 GATE WEATHER DEPENDENCIES CHECK
============================================================

📦 Checking packages...
------------------------------------------------------------
✅ duckdb              0.9.2        (Database)
✅ pandas              2.1.3        (Data Processing)
✅ copernicusmarine    1.0.2        (CMEMS API)
✅ xarray              2023.12.0    (Array Processing)
✅ netCDF4             1.6.5        (NetCDF Reader)
------------------------------------------------------------

✅ ALL DEPENDENCIES OK!

Ready to run:
  cd spvx-lite && ./COLLECT_GATE_WEATHER.sh

============================================================
```

---

## Quick Install Script

```bash
#!/bin/bash
# Quick install script for Gate Weather dependencies

echo "Installing Gate Weather System dependencies..."
echo ""

pip3 install --upgrade pip

echo "Installing core packages..."
pip3 install duckdb pandas copernicusmarine

echo ""
echo "Verifying installation..."
python3 -c "
try:
    import duckdb, pandas, copernicusmarine
    print('✅ All core dependencies installed!')
except ImportError as e:
    print(f'❌ Error: {e}')
"

echo ""
echo "Done! Ready to run:"
echo "  cd spvx-lite && ./COLLECT_GATE_WEATHER.sh"
```

Speichere als `install_dependencies.sh` und führe aus:
```bash
chmod +x install_dependencies.sh
./install_dependencies.sh
```

---

**Erstellt:** 2025-11-05
**Status:** Dokumentiert
