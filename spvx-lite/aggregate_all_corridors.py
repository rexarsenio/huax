"""
Quick script to aggregate gate_flux_daily for ALL chokepoints from polygon_events.
"""

import duckdb
import datetime as dt

# Connect to database
con = duckdb.connect("db/spvx.duckdb")

# Dates to aggregate
dates = [dt.date(2025, 10, 31), dt.date(2025, 11, 1)]

for target_date in dates:
    print(f"\n=== Aggregating {target_date} ===")

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
    print(f"✓ Inserted {len(rows)} corridors:")
    for row in rows:
        print(f"  {row[0]}: {row[1]} crossings")

con.commit()
con.close()

print("\n✅ gate_flux_daily aggregation complete!")
