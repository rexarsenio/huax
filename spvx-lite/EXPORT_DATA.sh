#!/bin/bash
#
# EXPORT_DATA.sh - Export data from database to CSV files
#
# Exports:
# - Polygon events
# - Ship registry
# - Corridor statistics
#

cd "$(dirname "$0")"
source .venv/bin/activate

EXPORT_DIR="exports"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')

mkdir -p "$EXPORT_DIR"

echo "📊 SPVX-Lite Data Export"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Export directory: $EXPORT_DIR"
echo "Timestamp: $TIMESTAMP"
echo ""

# Use API snapshot to avoid locking main database
DB_PATH="db/spvx_api.duckdb"

if [ ! -f "$DB_PATH" ]; then
    echo "❌ Snapshot database not found: $DB_PATH"
    echo "   Run ./UPDATE_API_SNAPSHOT.sh first"
    exit 1
fi

python3 << EOF
import duckdb
import pandas as pd
from pathlib import Path

db_path = "$DB_PATH"
export_dir = Path("$EXPORT_DIR")
timestamp = "$TIMESTAMP"

print("🔌 Connecting to database...")
con = duckdb.connect(db_path, read_only=True)

# 1. Export polygon events
print("📦 Exporting polygon_events...")
try:
    df = con.execute("""
        SELECT
            mmsi,
            polygon_id,
            event,
            ts,
            centroid_lat as lat,
            centroid_lon as lon
        FROM polygon_events
        ORDER BY ts DESC
    """).df()

    output_file = export_dir / f"polygon_events_{timestamp}.csv"
    df.to_csv(output_file, index=False)
    print(f"   ✅ Exported {len(df):,} rows to {output_file}")
except Exception as e:
    print(f"   ⚠️  Error: {e}")

# 2. Export ship registry
print("📦 Exporting ship_registry...")
try:
    df = con.execute("""
        SELECT
            mmsi,
            imo,
            name,
            shiptype,
            callsign,
            flag,
            length,
            width,
            draught,
            last_updated
        FROM ship_registry
        ORDER BY last_updated DESC
    """).df()

    output_file = export_dir / f"ship_registry_{timestamp}.csv"
    df.to_csv(output_file, index=False)
    print(f"   ✅ Exported {len(df):,} rows to {output_file}")
except Exception as e:
    print(f"   ⚠️  Error: {e}")

# 3. Export corridor statistics
print("📦 Exporting corridor_statistics...")
try:
    df = con.execute("""
        SELECT
            polygon_id,
            COUNT(*) as total_events,
            COUNT(DISTINCT mmsi) as unique_vessels,
            MIN(ts_in) as first_event,
            MAX(ts_in) as last_event
        FROM polygon_events
        GROUP BY polygon_id
        ORDER BY total_events DESC
    """).df()

    output_file = export_dir / f"corridor_statistics_{timestamp}.csv"
    df.to_csv(output_file, index=False)
    print(f"   ✅ Exported {len(df):,} corridors to {output_file}")
except Exception as e:
    print(f"   ⚠️  Error: {e}")

# 4. Export daily summary
print("📦 Exporting daily_summary...")
try:
    df = con.execute("""
        SELECT
            DATE(ts_in) as date,
            polygon_id,
            COUNT(*) as events,
            COUNT(DISTINCT mmsi) as vessels
        FROM polygon_events
        WHERE ts_in >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(ts_in), polygon_id
        ORDER BY date DESC, events DESC
    """).df()

    output_file = export_dir / f"daily_summary_{timestamp}.csv"
    df.to_csv(output_file, index=False)
    print(f"   ✅ Exported {len(df):,} daily records to {output_file}")
except Exception as e:
    print(f"   ⚠️  Error: {e}")

con.close()

print("")
print(f"✅ Export complete! Files saved in: {export_dir}")
print("")
print("📁 Exported files:")
import os
for f in sorted(export_dir.glob(f"*_{timestamp}.csv")):
    size = os.path.getsize(f) / 1024 / 1024
    print(f"   • {f.name} ({size:.2f} MB)")

EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Done!"
