#!/usr/bin/env python3
"""
Quick setup for Malacca → OPL → Shandong supply chain.
Creates all necessary tables and base configuration.
"""

import duckdb
import json
from pathlib import Path
from datetime import datetime

DB_PATH = "db/spvx.duckdb"
GATES_FILE = "data/geo/gates.geojson"
POLYGONS_FILE = "data/geo/polygons.geojson"

def setup_database_tables():
    """Create anchorage tables if they don't exist."""
    print("1️⃣  Creating database tables...")
    print("-" * 70)

    con = duckdb.connect(DB_PATH)

    # Create anchorage_polygons
    con.execute("""
        CREATE TABLE IF NOT EXISTS anchorage_polygons (
            anchorage_id VARCHAR PRIMARY KEY,
            anchorage_name VARCHAR,
            kind VARCHAR DEFAULT 'ANCHORAGE',
            centroid_lat DOUBLE,
            centroid_lon DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ anchorage_polygons")

    # Create anchorage_episodes
    con.execute("""
        CREATE TABLE IF NOT EXISTS anchorage_episodes (
            episode_id VARCHAR PRIMARY KEY,
            anchorage_id VARCHAR,
            mmsi BIGINT,
            vessel_name VARCHAR,
            ts_entry TIMESTAMP,
            ts_exit TIMESTAMP,
            dwell_hours DOUBLE,
            t_in TIMESTAMP,
            t_out TIMESTAMP,
            dwell_h DOUBLE,
            fixes_n INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ anchorage_episodes")

    # Create anchorage_daily_dwell
    con.execute("""
        CREATE TABLE IF NOT EXISTS anchorage_daily_dwell (
            ds DATE,
            anchorage_id VARCHAR,
            episode_count INTEGER,
            median_dwell_h DOUBLE,
            p90_dwell_h DOUBLE,
            coverage_ratio DOUBLE,
            baseline_median_h DOUBLE,
            baseline_std_h DOUBLE,
            z_dwell DOUBLE,
            anomaly_detected BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ds, anchorage_id)
        )
    """)
    print("   ✅ anchorage_daily_dwell")

    # Create anchorage_daily view (for API compatibility)
    con.execute("""
        CREATE OR REPLACE VIEW anchorage_daily AS
        SELECT
            ds,
            anchorage_id,
            episode_count as episodes,
            episode_count as active_vessels,
            median_dwell_h as dwell_median_h,
            p90_dwell_h as dwell_p90_h,
            coverage_ratio,
            z_dwell,
            (baseline_median_h IS NULL OR baseline_std_h IS NULL) as baseline_insufficient,
            NULL as tanker_share
        FROM anchorage_daily_dwell
    """)
    print("   ✅ anchorage_daily (view)")

    con.commit()
    con.close()
    print()

def setup_anchorage_definitions():
    """Add OPL and Shandong anchorage definitions."""
    print("2️⃣  Adding anchorage definitions...")
    print("-" * 70)

    con = duckdb.connect(DB_PATH)

    anchorages = [
        # OPL Singapore
        {"id": "ANCH_OPL_SIN", "name": "OPL Singapore", "lat": 1.20, "lon": 103.75},
        # Shandong ports
        {"id": "ANCH_QINGDAO", "name": "Qingdao Anchorage", "lat": 36.07, "lon": 120.33},
        {"id": "ANCH_RIZHAO", "name": "Rizhao Anchorage", "lat": 35.43, "lon": 119.53},
        {"id": "ANCH_YANTAI", "name": "Yantai Anchorage", "lat": 37.53, "lon": 121.39},
        {"id": "ANCH_LONGKOU", "name": "Longkou Anchorage", "lat": 37.65, "lon": 120.33},
        {"id": "ANCH_LANSHAN", "name": "Lanshan Anchorage", "lat": 35.07, "lon": 119.35},
    ]

    for anch in anchorages:
        con.execute("""
            INSERT OR REPLACE INTO anchorage_polygons
            (anchorage_id, anchorage_name, centroid_lat, centroid_lon)
            VALUES (?, ?, ?, ?)
        """, [anch["id"], anch["name"], anch["lat"], anch["lon"]])
        print(f"   ✅ {anch['id']:20s} - {anch['name']}")

    con.commit()
    con.close()
    print()

def setup_malacca_gates():
    """Add Malacca gates to gates.geojson."""
    print("3️⃣  Adding Malacca gates...")
    print("-" * 70)

    gates_path = Path(GATES_FILE)

    if gates_path.exists():
        with open(gates_path) as f:
            gates_data = json.load(f)
    else:
        gates_data = {"type": "FeatureCollection", "features": []}

    existing_ids = {f['properties']['id'] for f in gates_data['features']}

    # Malacca gates
    malacca_gates = [
        {
            "id": "GATE_MALACCA_v1",
            "name": "Strait of Malacca",
            "lat": 1.45,
            "lon": 102.9,
            "bearing": 135,  # NW-SE
            "width": 7.5  # 15 NM total = 28km (strait is 2.8km at narrowest)
        }
    ]

    added = 0
    for gate in malacca_gates:
        if gate['id'] not in existing_ids:
            feature = {
                "type": "Feature",
                "properties": {
                    "id": gate['id'],
                    "name": gate['name'],
                    "kind": "GATE",
                    "bearing_deg": gate['bearing'],
                    "half_width_nm": gate['width'],
                    "created": datetime.utcnow().isoformat() + "Z"
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [gate['lon'], gate['lat']]
                }
            }
            gates_data['features'].append(feature)
            print(f"   ✅ {gate['id']:30s} - {gate['name']}")
            added += 1
        else:
            print(f"   ⏭️  {gate['id']:30s} - Already exists")

    if added > 0:
        # Ensure directory exists
        gates_path.parent.mkdir(parents=True, exist_ok=True)
        with open(gates_path, 'w') as f:
            json.dump(gates_data, f, indent=2)
        print(f"\n   💾 Saved to {gates_path}")

    print()

def main():
    print("🚀 Malacca → OPL → Shandong Supply Chain Setup")
    print("=" * 80)
    print()

    # 1. Create database tables
    setup_database_tables()

    # 2. Add anchorage definitions
    setup_anchorage_definitions()

    # 3. Add Malacca gates
    setup_malacca_gates()

    print("=" * 80)
    print("✅ Supply chain setup complete!")
    print()
    print("📋 Next steps:")
    print()
    print("   1. Restart consumer to start collecting Malacca crossings:")
    print("      ./stop_consumer.sh")
    print("      ./start_consumer.sh")
    print()
    print("   2. Wait 2-4 hours for data to accumulate")
    print()
    print("   3. Check supply chain coverage:")
    print("      python3 diagnose_supply_chain.py")
    print()
    print("   4. Once you have AIS data, collect sea-state:")
    print("      source .venv/bin/activate")
    print("      PYTHONPATH=src python -m spvx.cli ingest-sea-state --provider auto --lookback-days 3")
    print()
    print("   5. Migrate/compute SIS:")
    print("      python3 migrate_sea_state.py")
    print()
    print("   6. Update API snapshot:")
    print("      ./UPDATE_API_SNAPSHOT.sh")
    print()
    print("⏰ Note: Full supply chain needs 24-48 hours to populate!")
    print("   - Malacca gate crossings: 1-2 hours")
    print("   - OPL episodes: Requires episode detection engine")
    print("   - Shandong episodes: Requires episode detection engine")
    print()
    print("💡 To enable episode detection, you'll need to implement TH-1, TH-2, TH-3")
    print("   For now, you can use the test data script:")
    print("   python3 setup_anchorage_test_data.py")

if __name__ == "__main__":
    main()
