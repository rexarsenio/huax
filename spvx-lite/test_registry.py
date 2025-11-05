#!/usr/bin/env python
"""Test script for ship registry commands."""
import sys
sys.path.insert(0, '/Users/alongo/Desktop/huax/spvx-lite/src')

import duckdb
from spvx.registry.schema import create_ship_registry_schema, bootstrap_unknown_mmsi, get_registry_stats

def main():
    db_path = 'db/spvx_REGISTRY_TEST.duckdb'

    print("=" * 60)
    print("SHIP REGISTRY TEST")
    print("=" * 60)

    con = duckdb.connect(db_path)

    try:
        # Step 1: Create schema
        print("\n[1/3] Creating ship_registry schema...")
        create_ship_registry_schema(con)
        print("✓ Schema created")

        # Step 2: Bootstrap unknown MMSIs
        print("\n[2/3] Bootstrapping unknown vessels (last 7 days)...")
        count = bootstrap_unknown_mmsi(con, since_days=7)
        print(f"✓ Bootstrapped {count:,} MMSIs")

        # Step 3: Show stats
        print("\n[3/3] Registry statistics:")
        stats = get_registry_stats(con)
        print(f"  Total vessels: {stats['total']:,}")
        print(f"  Tankers: {stats['tankers']:,}")
        print(f"  Unknown (24h): {stats['unknown_24h']:,}")
        print(f"  Avg confidence: {stats['avg_confidence']:.2f}")

        print("\n" + "=" * 60)
        print("✓ TEST COMPLETE")
        print("=" * 60)

    finally:
        con.close()

if __name__ == "__main__":
    main()
