#!/usr/bin/env python
"""Quick script to check open-sea data ingestion status."""

import sys
from pathlib import Path
from datetime import datetime, timezone

import duckdb

DB_PATH = "db/spvx.duckdb"


def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    con = duckdb.connect(DB_PATH, read_only=True)

    print("=" * 60)
    print("Open-Sea Data Ingestion Status")
    print("=" * 60)
    print(f"Checked at: {datetime.now(timezone.utc).isoformat()}")
    print()

    # Check tables exist
    tables = ["open_sea_fixes", "tracklets", "polygon_events", "gate_crossings"]

    for table in tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"✓ {table:25s}: {count:>10,} rows")

            # Get latest timestamp if available
            if count > 0 and table in ["open_sea_fixes", "tracklets"]:
                try:
                    latest = con.execute(f"SELECT MAX(ts) FROM {table}").fetchone()[0]
                    if latest:
                        age = (datetime.now(timezone.utc) - latest).total_seconds()
                        print(f"  └─ Latest entry: {latest} ({age:.0f}s ago)")
                except Exception:
                    pass

        except Exception as e:
            print(f"⚠ {table:25s}: Table not found or error - {e}")

    print()
    print("=" * 60)

    # Summary
    total_fixes = con.execute("SELECT COUNT(*) FROM open_sea_fixes").fetchone()[0]

    if total_fixes == 0:
        print("⚠️  NO DATA YET - Consumer may still be connecting...")
        print()
        print("Troubleshooting:")
        print("1. Check consumer is running (should see WebSocket connection)")
        print("2. Verify AISSTREAM_API_KEY is valid")
        print("3. Wait 1-2 minutes for initial data")
        print("4. Check bounding boxes cover active shipping areas")
    elif total_fixes < 100:
        print("⏳ INITIAL DATA - Consumer is working but needs more time")
        print(f"   Current: {total_fixes} fixes")
        print("   Expected: 100+ fixes within 5 minutes in busy areas")
    else:
        print("✅ INGESTION ACTIVE - Consumer is collecting data successfully!")

    print("=" * 60)

    con.close()


if __name__ == "__main__":
    main()
