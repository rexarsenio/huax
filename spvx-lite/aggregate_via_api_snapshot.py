"""
Safe aggregation script using API snapshot (no DB lock issues).
"""

import duckdb
import datetime as dt

print("🔄 Using API snapshot to aggregate corridors...")
print("   This is SAFE - no DB locks!\n")

# Connect to API snapshot (read-only, no locks needed)
con = duckdb.connect("db/spvx_api.duckdb")

# Dates to aggregate
dates = [dt.date(2025, 10, 31), dt.date(2025, 11, 1)]

for target_date in dates:
    print(f"=== Aggregating {target_date} ===")

    # Aggregate all CHOKEPOINT polygon_events to gate_flux_daily
    result = con.execute("""
        INSERT OR REPLACE INTO gate_flux_daily (ds, gate_id, direction, crossings)
        SELECT
            CAST(? AS DATE) as ds,
            polygon_id as gate_id,
            'UNK' as direction,
            COUNT(*) as crossings
        FROM polygon_events
        WHERE
            CAST(ts AS DATE) = ?
            AND polygon_id LIKE 'CHOKEPOINT_%'
        GROUP BY polygon_id
        HAVING COUNT(*) > 0
        RETURNING gate_id, crossings
    """, [target_date, target_date])

    rows = result.fetchall()
    print(f"✓ {len(rows)} corridors:")
    for row in rows:
        print(f"  {row[0]}: {row[1]} crossings")
    print()

con.commit()
con.close()

print("✅ API snapshot updated!")
print("\nℹ️  Main DB (spvx.duckdb) will auto-sync via UPDATE_API_SNAPSHOT.sh")
print("   Consumer keeps running - no interruption!")
