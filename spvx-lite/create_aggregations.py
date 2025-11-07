#!/usr/bin/env python3
"""
Create missing aggregation tables from collected AIS data.
Run this after the consumer has collected data.
"""

import duckdb
from pathlib import Path
from datetime import datetime

DB_PATH = "db/spvx.duckdb"

def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH)

    print("🔧 Creating Missing Aggregation Tables")
    print("=" * 70)
    print()

    # 1. Create gate_flux table from gate_crossings
    print("1️⃣  Creating gate_flux from gate_crossings...")
    try:
        # Check if gate_crossings exists
        count = con.execute("SELECT COUNT(*) FROM gate_crossings").fetchone()[0]
        print(f"   Found {count:,} gate crossings")

        # Create gate_flux table
        con.execute("""
            CREATE TABLE IF NOT EXISTS gate_flux (
                gate_id VARCHAR,
                window_start TIMESTAMP,
                window_end TIMESTAMP,
                crossings_n BIGINT,
                crossings_s BIGINT,
                net_flux INTEGER,
                PRIMARY KEY (gate_id, window_start)
            )
        """)

        # Populate gate_flux with 1-hour windows
        con.execute("""
            INSERT OR REPLACE INTO gate_flux
            SELECT
                gate_id,
                time_bucket(INTERVAL '1 hour', ts) as window_start,
                time_bucket(INTERVAL '1 hour', ts) + INTERVAL '1 hour' as window_end,
                SUM(CASE WHEN direction = 'N' THEN 1 ELSE 0 END) as crossings_n,
                SUM(CASE WHEN direction = 'S' THEN 1 ELSE 0 END) as crossings_s,
                SUM(CASE WHEN direction = 'N' THEN 1 WHEN direction = 'S' THEN -1 ELSE 0 END) as net_flux
            FROM gate_crossings
            GROUP BY gate_id, time_bucket(INTERVAL '1 hour', ts)
        """)

        flux_count = con.execute("SELECT COUNT(*) FROM gate_flux").fetchone()[0]
        print(f"   ✅ Created gate_flux: {flux_count:,} windows")

    except Exception as e:
        print(f"   ❌ Error creating gate_flux: {e}")

    print()

    # 2. Create sis_daily table if sea_state_samples exists
    print("2️⃣  Creating sis_daily from sea_state_samples...")
    try:
        # Check if sea_state_samples exists
        ss_count = con.execute("SELECT COUNT(*) FROM sea_state_samples").fetchone()[0]
        print(f"   Found {ss_count:,} sea state samples")

        # Create sis_daily table
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

        # Populate sis_daily
        con.execute("""
            INSERT OR REPLACE INTO sis_daily
            SELECT
                DATE(ts) as ds,
                corridor_id,
                AVG(sis) as sis_mean,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY sis) as sis_p90,
                COUNT(*) as samples_n,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY current_head_ms) as head_current_p90,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY wind_head_ms) as head_wind_p90,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY wave_encounter_m) as wave_encounter_p90
            FROM sea_state_samples
            WHERE sis IS NOT NULL
            GROUP BY DATE(ts), corridor_id
        """)

        sis_count = con.execute("SELECT COUNT(*) FROM sis_daily").fetchone()[0]
        print(f"   ✅ Created sis_daily: {sis_count:,} corridor-days")

    except Exception as e:
        print(f"   ⚠️  Could not create sis_daily: {e}")
        print(f"   This is normal if sea state data hasn't been ingested yet")

    print()

    con.commit()
    con.close()

    print("=" * 70)
    print("✅ Aggregation tables created!")
    print()
    print("Next steps:")
    print("  1. Run diagnose_data.py to verify")
    print("  2. Update API snapshot: ./UPDATE_API_SNAPSHOT.sh")
    print("  3. Restart dashboard")

if __name__ == "__main__":
    main()
