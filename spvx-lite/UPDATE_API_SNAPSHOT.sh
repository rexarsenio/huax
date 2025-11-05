#!/bin/bash
#
# UPDATE_API_SNAPSHOT.sh
#
# Creates/updates the API snapshot database (spvx_api.duckdb) from the production database.
# This avoids read locks on the main database while the ingestion pipeline is running.
#
# Usage:
#   ./UPDATE_API_SNAPSHOT.sh
#
# Run this periodically (e.g., every 5-10 minutes) to refresh the API with latest data.
#

set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate

echo "🔄 Updating API snapshot database..."

python3 << 'EOF'
import duckdb
from pathlib import Path
import sys
import time

src_db = Path("db/spvx.duckdb")
dst_db = Path("db/spvx_api.duckdb")

if not src_db.exists():
    print(f"❌ ERROR: Source database {src_db} does not exist")
    sys.exit(1)

# DuckDB doesn't allow read-only access while a write lock is held.
# We'll use the ATTACH DATABASE feature to copy tables between connections.

try:
    print(f"📖 Attempting to read from {src_db}...")
    print("   ℹ️  If ingestion is running, this will fail due to write lock.")
    print("   ℹ️  Stop ingestion temporarily or wait for it to release the lock.")
    print()

    # Try to connect read-only with a timeout
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            src = duckdb.connect(str(src_db), read_only=True)
            print("✅ Successfully opened source database")
            break
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"⏳ Attempt {attempt + 1}/{max_attempts} failed, retrying in 2s...")
                time.sleep(2)
            else:
                print()
                print("❌ Cannot access source database - it's locked by ingestion process")
                print()
                print("Solutions:")
                print("  1. Temporarily stop ingestion: pkill -f ingest_aisstream.py")
                print("  2. Run this script, then restart ingestion")
                print("  3. Or use the mock data for testing (START_MOCK.sh)")
                print()
                sys.exit(1)

    # Export critical tables
    tables_to_copy = [
        'polygon_events',
        'tanker_presence',
        'gate_crossings',
        'tanker_occupancy_intraday',
        'gate_flux_hourly',
        'gate_flux_daily',
        'gate_flux_daily_deduplicated',
        'gate_paired_transits_daily',
        'transit_times_daily',
        'sea_state_daily',
        'sea_state_region_metrics',
        'open_sea_alerts',
        'spvx_global_daily',
        'spvx_basin_daily',
        'components_daily'
    ]

    # Create a temporary database for the snapshot
    tmp_db = dst_db.with_suffix('.duckdb.tmp')
    if tmp_db.exists():
        tmp_db.unlink()

    dst = duckdb.connect(str(tmp_db))

    # Use ATTACH DATABASE to copy tables
    dst.execute(f"ATTACH '{src_db}' AS src (READ_ONLY)")

    for table in tables_to_copy:
        try:
            # Check if table exists in source by trying to query it
            try:
                dst.execute(f"SELECT 1 FROM src.{table} LIMIT 1").fetchone()
                table_exists = True
            except:
                table_exists = False

            if table_exists:
                print(f"  📋 Copying {table}...")
                # Copy table structure and data
                dst.execute(f"CREATE TABLE {table} AS SELECT * FROM src.{table}")
                row_count = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"     ✅ {row_count:,} rows")
            else:
                print(f"  ⏭️  Skipping {table} (not found in source)")
        except Exception as e:
            print(f"  ⚠️  Warning: Could not copy {table}: {e}")

    dst.execute("DETACH src")
    dst.close()
    src.close()

    # Atomic swap
    if dst_db.exists():
        old_db = dst_db.with_suffix('.duckdb.old')
        dst_db.rename(old_db)
        tmp_db.rename(dst_db)
        old_db.unlink()
    else:
        tmp_db.rename(dst_db)

    print()
    print(f"✅ API snapshot updated at {dst_db}")
    print()
    print("🚀 API server will now serve fresh data from the snapshot")
    print("   (no restart needed with --reload)")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

echo ""
echo "✅ Done!"
