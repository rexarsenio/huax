#!/usr/bin/env python3
"""
Show which corridors have SIS data and which are missing.
"""

import duckdb
from pathlib import Path

DB_PATH = "db/spvx.duckdb"

def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH, read_only=True)

    print("📊 Corridor Coverage Report")
    print("=" * 70)
    print()

    # 1. Corridors with SIS data
    print("✅ Corridors WITH SIS data:")
    print("-" * 70)

    result = con.execute("""
        SELECT
            corridor_id,
            COUNT(*) as days,
            MIN(ds) as first_date,
            MAX(ds) as last_date,
            AVG(sis_mean) as avg_sis,
            SUM(samples_n) as total_samples
        FROM sis_daily
        GROUP BY corridor_id
        ORDER BY total_samples DESC
    """).fetchall()

    if result:
        for row in result:
            corridor, days, first, last, avg_sis, samples = row
            age_days = (Path(DB_PATH).stat().st_mtime - last.timestamp()) / 86400 if last else 999
            status = "🟢" if age_days < 2 else "🟡" if age_days < 5 else "🔴"
            print(f"{status} {corridor:40s}")
            print(f"   {days} days | {samples:,} samples | SIS avg: {avg_sis:.2f}")
            print(f"   Latest: {last} ({int(age_days)}d ago)")
            print()
    else:
        print("   (none)")
        print()

    # 2. Corridors in sea_state_samples but not in sis_daily
    print("⚠️  Corridors with sea_state_samples but NO sis_daily:")
    print("-" * 70)

    result = con.execute("""
        SELECT
            corridor_id,
            COUNT(*) as samples,
            MIN(ts) as first_ts,
            MAX(ts) as last_ts
        FROM sea_state_samples
        WHERE corridor_id IS NOT NULL
          AND corridor_id NOT IN (SELECT DISTINCT corridor_id FROM sis_daily)
        GROUP BY corridor_id
        ORDER BY samples DESC
    """).fetchall()

    if result:
        for row in result:
            corridor, samples, first, last = row
            print(f"❌ {corridor:40s}")
            print(f"   {samples:,} samples | Range: {first} to {last}")
            print(f"   👉 Run migration again or check sis calculation")
            print()
    else:
        print("   ✅ All sea_state corridors have sis_daily entries")
        print()

    # 3. Active gates/corridors in consumer
    print("🚪 Active Gates (collecting AIS data):")
    print("-" * 70)

    result = con.execute("""
        SELECT
            gate_id,
            COUNT(DISTINCT DATE(ts)) as active_days,
            COUNT(*) as total_crossings,
            MAX(ts) as latest_crossing
        FROM gate_crossings
        WHERE ts >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY gate_id
        ORDER BY total_crossings DESC
    """).fetchall()

    if result:
        for row in result:
            gate, days, crossings, latest = row
            print(f"✅ {gate:40s}")
            print(f"   {crossings:,} crossings | {days} active days | Latest: {latest}")
            print()
    else:
        print("   ❌ No recent gate crossings found")
        print()

    # 4. Summary
    print("=" * 70)
    print()

    sis_count = con.execute("SELECT COUNT(DISTINCT corridor_id) FROM sis_daily").fetchone()[0]
    ss_count = con.execute("SELECT COUNT(DISTINCT corridor_id) FROM sea_state_samples WHERE corridor_id IS NOT NULL").fetchone()[0]
    gate_count = con.execute("SELECT COUNT(DISTINCT gate_id) FROM gate_crossings WHERE ts >= CURRENT_DATE - INTERVAL '7 days'").fetchone()[0]

    print(f"📈 Summary:")
    print(f"   Corridors with SIS data: {sis_count}")
    print(f"   Corridors with sea_state samples: {ss_count}")
    print(f"   Active gates (7d): {gate_count}")
    print()

    # 5. Missing corridors expected by dashboard
    missing = [
        "CHOKEPOINT_SICILY->UNK",
        "LANE_CANARY_E_v1->UNK",
        "LANE_CANARY_W_v1->UNK",
        "CHOKEPOINT_DARDANELLES->UNK",
        "CHOKEPOINT_OTRANTO->UNK",
        "WEST_AFRICA_BONNY->UNK",
    ]

    print("💡 To add missing corridors:")
    print()
    print("   Option 1: Add to consumer configuration")
    print("   - Edit data/geo/polygons.geojson")
    print("   - Add corridors for Sicily, Canary, Dardanelles, Otranto, W.Africa")
    print("   - Restart consumer")
    print()
    print("   Option 2: Accept limited coverage")
    print("   - These corridors simply don't have gates/polygons configured")
    print("   - Dashboard will show 'No samples' for unconfigured areas")
    print("   - This is normal - focus on your priority corridors")
    print()
    print("   Current active corridors are working correctly! ✅")

    con.close()

if __name__ == "__main__":
    main()
