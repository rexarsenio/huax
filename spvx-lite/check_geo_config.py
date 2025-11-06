#!/usr/bin/env python3
"""
Check existing gates and polygons, then add missing corridors.
"""

import json
from pathlib import Path

def check_existing():
    """Check what gates/polygons already exist."""

    print("🔍 Checking existing configuration...")
    print("=" * 70)
    print()

    gates_file = Path("data/geo/gates.geojson")
    polygons_file = Path("data/geo/polygons.geojson")

    # Check gates
    print("📍 Existing Gates:")
    if gates_file.exists():
        with open(gates_file) as f:
            gates = json.load(f)
        gate_ids = [f.get('properties', {}).get('id', 'NO_ID') for f in gates.get('features', [])]
        print(f"   Found {len(gate_ids)} gates:")
        for gid in sorted(gate_ids):
            print(f"   - {gid}")
    else:
        print("   ❌ gates.geojson not found")
        gate_ids = []

    print()

    # Check polygons
    print("📐 Existing Polygons:")
    if polygons_file.exists():
        with open(polygons_file) as f:
            polygons = json.load(f)
        poly_ids = [f.get('properties', {}).get('id', 'NO_ID') for f in polygons.get('features', [])]
        print(f"   Found {len(poly_ids)} polygons:")
        for pid in sorted(poly_ids):
            print(f"   - {pid}")
    else:
        print("   ❌ polygons.geojson not found")
        poly_ids = []

    print()
    print("=" * 70)
    print()

    # Missing corridors
    missing = {
        'CHOKEPOINT_SICILY': {
            'name': 'Strait of Sicily',
            'center': (36.5, 12.5),
            'description': 'Between Sicily and Tunisia'
        },
        'LANE_CANARY_E': {
            'name': 'Canary Islands Eastern Lane',
            'center': (28.5, -15.5),
            'description': 'East of Canary Islands'
        },
        'LANE_CANARY_W': {
            'name': 'Canary Islands Western Lane',
            'center': (28.5, -18.0),
            'description': 'West of Canary Islands'
        },
        'CHOKEPOINT_DARDANELLES': {
            'name': 'Dardanelles Strait',
            'center': (40.2, 26.4),
            'description': 'Between Aegean and Marmara Sea'
        },
        'CHOKEPOINT_OTRANTO': {
            'name': 'Strait of Otranto',
            'center': (40.0, 19.0),
            'description': 'Between Italy and Albania'
        },
        'WEST_AFRICA_BONNY': {
            'name': 'Bonny Terminal Nigeria',
            'center': (4.4, 7.2),
            'description': 'Major oil export terminal'
        }
    }

    print("⚠️  Missing Corridors:")
    for key, info in missing.items():
        print(f"   ❌ {key:30s} - {info['name']}")
        print(f"      Location: {info['center']}")
        print(f"      {info['description']}")
        print()

    return gate_ids, poly_ids, missing

if __name__ == "__main__":
    check_existing()
