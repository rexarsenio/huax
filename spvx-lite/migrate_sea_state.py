#!/usr/bin/env python3
"""
Migrate old sea_state_samples to new schema with corridor_id and SIS.
"""

import duckdb
from pathlib import Path

DB_PATH = "db/spvx.duckdb"

def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH)

    print("🔄 Migrating sea_state_samples to new schema")
    print("=" * 70)
    print()

    # 1. Check current schema
    print("1️⃣  Checking current schema...")
    columns = con.execute("DESCRIBE sea_state_samples").fetchall()
    col_names = [row[0] for row in columns]
    print(f"   Current columns: {', '.join(col_names)}")

    has_corridor = 'corridor_id' in col_names
    has_sis = 'sis' in col_names
    has_tracklet = 'tracklet_id' in col_names

    if has_corridor and has_sis:
        print("   ✅ Schema is already up to date!")
        con.close()
        return

    print(f"   Missing: {[] if has_corridor else ['corridor_id']} {[] if has_sis else ['sis']}")
    print()

    # 2. Extract corridor from tracklet_id if needed
    if has_tracklet and not has_corridor:
        print("2️⃣  Adding corridor_id column from tracklet_id...")
        try:
            # Add column
            con.execute("ALTER TABLE sea_state_samples ADD COLUMN IF NOT EXISTS corridor_id VARCHAR")

            # Extract corridor from tracklet format: "CHOKEPOINT_MALACCA->UNK:412345678:20251103"
            con.execute("""
                UPDATE sea_state_samples
                SET corridor_id = SPLIT_PART(tracklet_id, ':', 1)
                WHERE corridor_id IS NULL AND tracklet_id IS NOT NULL
            """)

            count = con.execute("SELECT COUNT(*) FROM sea_state_samples WHERE corridor_id IS NOT NULL").fetchone()[0]
            print(f"   ✅ Set corridor_id for {count:,} rows")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            con.close()
            return

    print()

    # 3. Calculate SIS (Sea Impact Score)
    if not has_sis:
        print("3️⃣  Calculating SIS (Sea Impact Score)...")
        try:
            # Add column
            con.execute("ALTER TABLE sea_state_samples ADD COLUMN IF NOT EXISTS sis DOUBLE")

            # Calculate SIS from components
            # SIS = normalized combination of wave height, head current, head wind
            # Simple formula: SIS = (Hs/4 + |head_current|/2 + |head_wind|/10) / 3
            con.execute("""
                UPDATE sea_state_samples
                SET sis = (
                    COALESCE(hs, 0.0) / 4.0 +
                    COALESCE(ABS(head_current_kn * 0.514444), 0.0) / 2.0 +  -- Convert knots to m/s
                    COALESCE(ABS(head_wind_ms), 0.0) / 10.0
                ) / 3.0
                WHERE sis IS NULL
            """)

            count = con.execute("SELECT COUNT(*) FROM sea_state_samples WHERE sis IS NOT NULL").fetchone()[0]
            avg_sis = con.execute("SELECT AVG(sis) FROM sea_state_samples WHERE sis IS NOT NULL").fetchone()[0]
            print(f"   ✅ Calculated SIS for {count:,} rows (avg: {avg_sis:.3f})")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            con.close()
            return

    print()

    # 4. Create/update sis_daily
    print("4️⃣  Creating sis_daily from migrated data...")
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS sis_daily (
                ds DATE,
                corridor_id VARCHAR,
                sis_mean DOUBLE,
                sis_p90 DOUBLE,
                samples_n INTEGER,
                head_current_p90 DOUBLE,
                head_wind_p90 DOUBLE,
                wave_encounter_p90 DOUBLE,
                PRIMARY KEY (ds, corridor_id)
            )
        """)

        con.execute("""
            INSERT OR REPLACE INTO sis_daily
            SELECT
                DATE(ts) as ds,
                corridor_id,
                AVG(sis) as sis_mean,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY sis) as sis_p90,
                COUNT(*) as samples_n,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY ABS(head_current_kn)) as head_current_p90,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY ABS(head_wind_ms)) as head_wind_p90,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY wave_encounter_m) as wave_encounter_p90
            FROM sea_state_samples
            WHERE sis IS NOT NULL
              AND corridor_id IS NOT NULL
            GROUP BY DATE(ts), corridor_id
        """)

        count = con.execute("SELECT COUNT(*) FROM sis_daily").fetchone()[0]
        latest = con.execute("SELECT MAX(ds) FROM sis_daily").fetchone()[0]
        print(f"   ✅ Created sis_daily: {count:,} corridor-days (latest: {latest})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        con.close()
        return

    print()

    con.commit()
    con.close()

    print("=" * 70)
    print("✅ Migration complete!")
    print()
    print("Next steps:")
    print("  1. Update API snapshot: ./UPDATE_API_SNAPSHOT.sh")
    print("  2. Restart dashboard to see SIS data")
    print("  3. Run diagnose_data.py to verify")

if __name__ == "__main__":
    main()
