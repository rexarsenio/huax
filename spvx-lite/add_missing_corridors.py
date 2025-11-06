#!/usr/bin/env python3
"""
Add missing gates and polygons for Sicily, Canary, Dardanelles, Otranto, W.Africa.
"""

import json
from pathlib import Path
from datetime import datetime

def create_gate_feature(gate_id, name, lat, lon, bearing, width_nm=2.0):
    """Create a gate feature (simple point with bearing)."""
    return {
        "type": "Feature",
        "properties": {
            "id": gate_id,
            "name": name,
            "kind": "GATE",
            "bearing_deg": bearing,
            "half_width_nm": width_nm,
            "created": datetime.utcnow().isoformat() + "Z"
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat]
        }
    }

def create_polygon_feature(poly_id, name, coords):
    """Create a polygon feature."""
    return {
        "type": "Feature",
        "properties": {
            "id": poly_id,
            "name": name,
            "kind": "CORRIDOR",
            "created": datetime.utcnow().isoformat() + "Z"
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords]
        }
    }

def add_missing_corridors():
    """Add missing gates and polygons."""

    print("🚀 Adding Missing Corridors")
    print("=" * 70)
    print()

    gates_file = Path("data/geo/gates.geojson")
    polygons_file = Path("data/geo/polygons.geojson")

    # Load existing files
    if gates_file.exists():
        with open(gates_file) as f:
            gates_data = json.load(f)
    else:
        gates_data = {"type": "FeatureCollection", "features": []}

    if polygons_file.exists():
        with open(polygons_file) as f:
            polygons_data = json.load(f)
    else:
        polygons_data = {"type": "FeatureCollection", "features": []}

    existing_gate_ids = {f['properties']['id'] for f in gates_data['features']}
    existing_poly_ids = {f['properties']['id'] for f in polygons_data['features']}

    # New gates to add
    new_gates = [
        # Sicily Strait
        {
            "id": "GATE_SICILY_v1",
            "name": "Strait of Sicily",
            "lat": 36.5,
            "lon": 12.5,
            "bearing": 0,  # North-South
            "width": 50.0
        },
        # Canary Islands
        {
            "id": "GATE_CANARY_E_v1",
            "name": "Canary Islands East",
            "lat": 28.5,
            "lon": -15.5,
            "bearing": 0,
            "width": 30.0
        },
        {
            "id": "GATE_CANARY_W_v1",
            "name": "Canary Islands West",
            "lat": 28.5,
            "lon": -18.0,
            "bearing": 0,
            "width": 30.0
        },
        # Dardanelles
        {
            "id": "GATE_DARDANELLES_v1",
            "name": "Dardanelles Strait",
            "lat": 40.2,
            "lon": 26.4,
            "bearing": 45,  # NE-SW
            "width": 2.0
        },
        # Otranto
        {
            "id": "GATE_OTRANTO_v1",
            "name": "Strait of Otranto",
            "lat": 40.0,
            "lon": 19.0,
            "bearing": 0,
            "width": 20.0
        },
        # West Africa - Bonny
        {
            "id": "GATE_BONNY_v1",
            "name": "Bonny Terminal Nigeria",
            "lat": 4.4,
            "lon": 7.2,
            "bearing": 90,  # E-W
            "width": 10.0
        }
    ]

    # Add gates
    print("1️⃣  Adding Gates:")
    print("-" * 70)
    added_gates = 0
    for gate in new_gates:
        if gate['id'] not in existing_gate_ids:
            feature = create_gate_feature(
                gate['id'],
                gate['name'],
                gate['lat'],
                gate['lon'],
                gate['bearing'],
                gate['width']
            )
            gates_data['features'].append(feature)
            print(f"   ✅ {gate['id']:30s} - {gate['name']}")
            added_gates += 1
        else:
            print(f"   ⏭️  {gate['id']:30s} - Already exists")

    if added_gates > 0:
        with open(gates_file, 'w') as f:
            json.dump(gates_data, f, indent=2)
        print(f"\n   💾 Saved {added_gates} new gates to {gates_file}")
    else:
        print("\n   ℹ️  No new gates to add")

    print()

    # New polygons (simple rectangular corridors)
    new_polygons = [
        # Sicily Strait corridor
        {
            "id": "CORRIDOR_SICILY_v1",
            "name": "Sicily Strait Corridor",
            "coords": [
                [12.0, 37.0],  # NW
                [13.0, 37.0],  # NE
                [13.0, 36.0],  # SE
                [12.0, 36.0],  # SW
                [12.0, 37.0]   # Close polygon
            ]
        },
        # Canary East corridor
        {
            "id": "CORRIDOR_CANARY_E_v1",
            "name": "Canary East Corridor",
            "coords": [
                [-15.0, 29.0],
                [-14.0, 29.0],
                [-14.0, 27.5],
                [-15.0, 27.5],
                [-15.0, 29.0]
            ]
        },
        # Canary West corridor
        {
            "id": "CORRIDOR_CANARY_W_v1",
            "name": "Canary West Corridor",
            "coords": [
                [-18.5, 29.0],
                [-17.5, 29.0],
                [-17.5, 27.5],
                [-18.5, 27.5],
                [-18.5, 29.0]
            ]
        },
        # Dardanelles corridor
        {
            "id": "CORRIDOR_DARDANELLES_v1",
            "name": "Dardanelles Corridor",
            "coords": [
                [26.0, 40.5],
                [26.8, 40.5],
                [26.8, 39.9],
                [26.0, 39.9],
                [26.0, 40.5]
            ]
        },
        # Otranto corridor
        {
            "id": "CORRIDOR_OTRANTO_v1",
            "name": "Otranto Corridor",
            "coords": [
                [18.5, 40.5],
                [19.5, 40.5],
                [19.5, 39.5],
                [18.5, 39.5],
                [18.5, 40.5]
            ]
        },
        # Bonny offshore area
        {
            "id": "AREA_BONNY_v1",
            "name": "Bonny Offshore Area",
            "coords": [
                [7.0, 4.6],
                [7.4, 4.6],
                [7.4, 4.2],
                [7.0, 4.2],
                [7.0, 4.6]
            ]
        }
    ]

    # Add polygons
    print("2️⃣  Adding Polygons/Corridors:")
    print("-" * 70)
    added_polygons = 0
    for poly in new_polygons:
        if poly['id'] not in existing_poly_ids:
            feature = create_polygon_feature(
                poly['id'],
                poly['name'],
                poly['coords']
            )
            polygons_data['features'].append(feature)
            print(f"   ✅ {poly['id']:30s} - {poly['name']}")
            added_polygons += 1
        else:
            print(f"   ⏭️  {poly['id']:30s} - Already exists")

    if added_polygons > 0:
        with open(polygons_file, 'w') as f:
            json.dump(polygons_data, f, indent=2)
        print(f"\n   💾 Saved {added_polygons} new polygons to {polygons_file}")
    else:
        print("\n   ℹ️  No new polygons to add")

    print()
    print("=" * 70)
    print()

    if added_gates > 0 or added_polygons > 0:
        print("✅ Corridors added successfully!")
        print()
        print("📋 Next steps:")
        print()
        print("   1. Verify the new gates/polygons:")
        print("      python3 check_geo_config.py")
        print()
        print("   2. Stop the consumer:")
        print("      ./stop_consumer.sh")
        print()
        print("   3. Restart with new configuration:")
        print("      ./start_consumer.sh")
        print()
        print("   4. Monitor data collection:")
        print("      tail -f logs/open_sea_consumer.log")
        print()
        print("   5. Wait 2-4 hours for data to accumulate")
        print()
        print("   6. Check corridor coverage:")
        print("      python3 check_corridor_coverage.py")
        print()
        print("⏰ Note: It takes time for ships to cross new gates!")
        print("   Sicily, Canary: Active shipping lanes (should see data quickly)")
        print("   Dardanelles, Otranto: Moderate traffic")
        print("   Bonny: Specialized oil terminal traffic")
    else:
        print("ℹ️  All corridors already configured")

if __name__ == "__main__":
    add_missing_corridors()
