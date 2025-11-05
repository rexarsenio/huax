#!/usr/bin/env python3
"""
Test script to demonstrate ship registry functionality.

This script simulates processing AIS Message Type 5 (Ship Static Data)
and shows how the ship registry enriches position reports with ship type info.
"""

import json
from datetime import datetime, timezone

import duckdb

from spvx.ingest.canonicalize import canonicalize
from spvx.ingest.ship_registry import (
    create_ship_registry_table,
    extract_ship_static_data,
    upsert_ship_registry,
    lookup_ship_info,
)

# Simulated AIS Message Type 5 for a tanker
MSG_TYPE_5_TANKER = {
    "MessageType": "StaticDataReport",
    "MetaData": {
        "MMSI": "477123456",
        "ShipName": "OCEAN TANKER",
        "time_utc": "2025-10-26 18:00:00",
    },
    "Message": {
        "MessageType": 5,
        "ShipStaticData": {
            "UserID": 477123456,
            "Type": 80,  # Oil Tanker
            "Name": "OCEAN TANKER",
            "CallSign": "ABCD",
            "DimensionA": 150,
            "DimensionB": 50,
            "DimensionC": 15,
            "DimensionD": 15,
            "Destination": "ROTTERDAM",
            "Draught": 12.5,
        },
    },
}

# Simulated AIS Position Report (without ship type info)
POSITION_REPORT_TANKER = {
    "MessageType": "PositionReport",
    "MetaData": {
        "MMSI": "477123456",
        "time_utc": "2025-10-26 18:05:00",
    },
    "Message": {
        "PositionReport": {
            "UserID": 477123456,
            "Latitude": 40.95,
            "Longitude": 28.87,
            "Sog": 0.3,
            "Cog": 120.5,
        },
    },
}


def main():
    print("=" * 80)
    print("Ship Registry Test - Demonstrating Tanker Detection")
    print("=" * 80)
    print()

    # Create in-memory database
    con = duckdb.connect(":memory:")
    create_ship_registry_table(con)
    print("✓ Created ship_registry table")
    print()

    # Step 1: Process Message Type 5 (Ship Static Data)
    print("Step 1: Processing AIS Message Type 5 (Ship Static Data)")
    print("-" * 80)
    ship_data = extract_ship_static_data(MSG_TYPE_5_TANKER)
    if ship_data:
        print(f"  MMSI: {ship_data['mmsi']}")
        print(f"  Name: {ship_data['ship_name']}")
        print(f"  Type: {ship_data['shiptype_num']} ({ship_data['shiptype_str']})")
        print(f"  Callsign: {ship_data['callsign']}")
        print(f"  Destination: {ship_data['destination']}")
        print(f"  Dimensions: {ship_data['dimension_a']+ship_data['dimension_b']}m x {ship_data['dimension_c']+ship_data['dimension_d']}m")
        print()

        upsert_ship_registry(con, ship_data)
        print("  ✓ Ship data stored in registry")
    print()

    # Step 2: Process Position Report WITHOUT ship registry
    print("Step 2: Processing Position Report WITHOUT ship registry lookup")
    print("-" * 80)
    canonical_without = canonicalize(POSITION_REPORT_TANKER, db_conn=None)
    print(f"  MMSI: {canonical_without['mmsi']}")
    print(f"  Position: {canonical_without['lat']}, {canonical_without['lon']}")
    print(f"  SOG: {canonical_without['sog']} kn")
    print(f"  ShipType: {canonical_without['shiptype_num']}")
    print(f"  Is Tanker: {canonical_without['is_tanker']} ❌")
    print()

    # Step 3: Process Position Report WITH ship registry
    print("Step 3: Processing Position Report WITH ship registry lookup")
    print("-" * 80)
    canonical_with = canonicalize(POSITION_REPORT_TANKER, db_conn=con)
    print(f"  MMSI: {canonical_with['mmsi']}")
    print(f"  Position: {canonical_with['lat']}, {canonical_with['lon']}")
    print(f"  SOG: {canonical_with['sog']} kn")
    print(f"  ShipType: {canonical_with['shiptype_num']} ({canonical_with['shiptype_str']})")
    print(f"  Is Tanker: {canonical_with['is_tanker']} ✅")
    print()

    # Step 4: Direct registry lookup
    print("Step 4: Direct ship registry lookup")
    print("-" * 80)
    ship_info = lookup_ship_info(con, "477123456")
    print(f"  {json.dumps(ship_info, indent=2, default=str)}")
    print()

    # Statistics
    registry_size = con.execute("SELECT COUNT(*) FROM ship_registry").fetchone()[0]
    print("=" * 80)
    print(f"Ship Registry Size: {registry_size} vessel(s)")
    print("=" * 80)
    print()
    print("Summary:")
    print("  • Message Type 5 (Ship Static Data) populates the ship registry")
    print("  • Message Type 1/2/3 (Position Reports) are enriched with registry data")
    print("  • Tanker detection now works even when position reports lack ship type")
    print("  • This enables accurate tanker tracking in anchorages!")
    print()

    con.close()


if __name__ == "__main__":
    main()
