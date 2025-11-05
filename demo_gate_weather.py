#!/usr/bin/env python3
"""
Demo script to test Gate Weather collection without full system
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "spvx-lite", "src"))

print("=" * 70)
print("🌊 GATE WEATHER DEMO - Minimal Test")
print("=" * 70)
print()

# Test 1: Can we import the modules?
print("1️⃣  Testing imports...")
try:
    import duckdb
    print("   ✅ duckdb imported")
except ImportError:
    print("   ❌ duckdb not found - install with: pip3 install duckdb")
    sys.exit(1)

try:
    import xarray
    import netCDF4
    print("   ✅ xarray/netCDF4 imported")
except ImportError:
    print("   ⚠️  xarray/netCDF4 not found - install with: pip3 install xarray netCDF4")
    print("   (Only needed for actual data collection)")

print()

# Test 2: Create database and table
print("2️⃣  Creating test database...")
db_path = "spvx-lite/db/spvx.duckdb"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

con = duckdb.connect(db_path)
print(f"   ✅ Database created/opened: {db_path}")

# Create the table
con.execute("""
    CREATE TABLE IF NOT EXISTS gate_weather_standalone (
        gate_id VARCHAR NOT NULL,
        gate_name VARCHAR,
        observed_at TIMESTAMP NOT NULL,
        basin VARCHAR,
        hs_m DOUBLE,
        tp_s DOUBLE,
        dp_deg DOUBLE,
        wave_flag INTEGER,
        u_knots DOUBLE,
        v_knots DOUBLE,
        speed_knots DOUBLE,
        current_flag INTEGER,
        wave_source VARCHAR,
        current_source VARCHAR,
        collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (gate_id, observed_at)
    )
""")
print("   ✅ Table 'gate_weather_standalone' ready")
print()

# Test 3: Insert demo data
print("3️⃣  Inserting demo weather data...")
from datetime import datetime, timedelta

now = datetime.utcnow()
demo_data = [
    ("GATE_HORMUZ", "Strait of Hormuz", now, "APAC", 2.15, 8.2, 245.0, 0, 1.2, 0.8, 1.44, 0, "DEMO", "DEMO"),
    ("GATE_SUEZ_N", "Suez Canal North", now - timedelta(hours=1), "MED", 1.85, 7.5, 180.0, 0, 0.9, 1.1, 1.42, 0, "DEMO", "DEMO"),
    ("GATE_GIBRALTAR", "Strait of Gibraltar", now - timedelta(hours=2), "MED", 3.2, 9.1, 270.0, 0, 2.1, 1.5, 2.58, 0, "DEMO", "DEMO"),
]

for data in demo_data:
    con.execute("""
        INSERT INTO gate_weather_standalone 
        (gate_id, gate_name, observed_at, basin, hs_m, tp_s, dp_deg, wave_flag, 
         u_knots, v_knots, speed_knots, current_flag, wave_source, current_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
    """, data)

print(f"   ✅ Inserted {len(demo_data)} demo records")
print()

# Test 4: Query the data
print("4️⃣  Querying demo data...")
result = con.execute("""
    SELECT 
        gate_id,
        gate_name,
        ROUND(hs_m, 2) as wave_height_m,
        ROUND(speed_knots, 2) as current_kn,
        observed_at
    FROM gate_weather_standalone
    ORDER BY observed_at DESC
""").fetchall()

print(f"   ✅ Found {len(result)} records:")
print()
print("   Gate ID                    | Gate Name                  | Waves  | Current | Observed At")
print("   " + "-" * 95)
for row in result:
    gate_id, gate_name, wave, current, obs = row
    print(f"   {gate_id:<26} | {gate_name:<26} | {wave:>5}m | {current:>6}kn | {obs}")

con.close()
print()

# Test 5: Simulate API response
print("5️⃣  Simulating API response format...")
print()
print("   📋 API Response (JSON-like):")
print("   {")
print('     "window": "h24",')
print('     "gates": [')
for i, row in enumerate(result[:2]):  # Show first 2
    gate_id, gate_name, wave, current, obs = row
    print('       {')
    print(f'         "gate_id": "{gate_id}",')
    print(f'         "gate_name": "{gate_name}",')
    print('         "latest_observation": {')
    print(f'           "waves": {{ "height_m": {wave} }},')
    print(f'           "currents": {{ "speed_knots": {current} }}')
    print('         }')
    print('       }' + (',' if i == 0 else ''))
print('     ]')
print('   }')
print()

print("=" * 70)
print("✅ DEMO COMPLETE!")
print("=" * 70)
print()
print("📌 Next steps:")
print("   1. To collect REAL weather data:")
print("      cd spvx-lite && ./COLLECT_GATE_WEATHER.sh")
print()
print("   2. To test with full system (API + Dashboard):")
print("      See QUICK_START_GATE_WEATHER.md")
print()
print("   3. Database location:")
print(f"      {os.path.abspath(db_path)}")
print()
