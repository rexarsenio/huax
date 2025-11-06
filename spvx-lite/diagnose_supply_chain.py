#!/usr/bin/env python3
"""
Diagnose coverage of the Malacca → OPL → Shandong supply chain.
This is the critical teapot market intelligence chain.
"""

import duckdb
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = "db/spvx.duckdb"

def check_supply_chain():
    """Check coverage of Malacca → OPL → Shandong chain."""

    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH, read_only=True)

    print("🔍 Malacca → OPL → Shandong Supply Chain Coverage")
    print("=" * 80)
    print()

    # 1. MALACCA PULSE - Gate crossings
    print("1️⃣  MALACCA PULSE (Strait Entry/Exit)")
    print("-" * 80)

    try:
        # Check for Malacca gates
        malacca_gates = con.execute("""
            SELECT
                gate_id,
                COUNT(*) as crossings_7d,
                MIN(ts) as first_crossing,
                MAX(ts) as last_crossing,
                COUNT(DISTINCT DATE(ts)) as active_days
            FROM gate_crossings
            WHERE gate_id LIKE '%MALACCA%'
              AND ts >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY gate_id
        """).fetchall()

        if malacca_gates:
            for gate, crossings, first, last, days in malacca_gates:
                age = datetime.now() - last.replace(tzinfo=None)
                status = "✅" if age < timedelta(hours=2) else "⚠️"
                print(f"{status} {gate}")
                print(f"   Crossings (7d): {crossings:,}")
                print(f"   Active days: {days}/7")
                print(f"   Latest: {last} ({age.seconds//60}min ago)")
                print()
        else:
            print("   ❌ No Malacca gate crossings found in last 7 days")
            print("   👉 Check if GATE_MALACCA_* exists in gates.geojson")
            print()

        # Check SIS data for Malacca corridor
        malacca_sis = con.execute("""
            SELECT
                corridor_id,
                COUNT(*) as days,
                MAX(ds) as latest,
                AVG(sis_mean) as avg_sis,
                SUM(samples_n) as total_samples
            FROM sis_daily
            WHERE corridor_id LIKE '%MALACCA%'
            GROUP BY corridor_id
        """).fetchall()

        if malacca_sis:
            print("   📊 SIS Data (Sea State):")
            for corridor, days, latest, avg_sis, samples in malacca_sis:
                age = (datetime.now().date() - latest).days if latest else 999
                status = "✅" if age < 2 else "⚠️"
                print(f"   {status} {corridor}")
                print(f"      {days} days | SIS avg: {avg_sis:.2f} | Latest: {latest}")
                print()
        else:
            print("   ❌ No SIS data for Malacca corridor")
            print()

    except Exception as e:
        print(f"   ❌ Error: {e}")
        print()

    # 2. OPL SINGAPORE DWELL - Anchorage episodes
    print("2️⃣  OPL SINGAPORE DWELL (Offshore Anchorage)")
    print("-" * 80)

    try:
        # Check for OPL anchorage definition
        opl_anch = con.execute("""
            SELECT anchorage_id, anchorage_name, centroid_lat, centroid_lon
            FROM anchorage_polygons
            WHERE anchorage_id LIKE '%OPL%' OR anchorage_id LIKE '%SINGAPORE%'
        """).fetchall()

        if opl_anch:
            for anch_id, name, lat, lon in opl_anch:
                print(f"   ✅ {anch_id} - {name}")
                print(f"      Location: {lat:.2f}°N, {lon:.2f}°E")
                print()

                # Check episodes
                episodes = con.execute("""
                    SELECT
                        COUNT(*) as total_episodes,
                        COUNT(DISTINCT mmsi) as unique_vessels,
                        AVG(dwell_hours) as avg_dwell_h,
                        MAX(ts_exit) as latest_exit
                    FROM anchorage_episodes
                    WHERE anchorage_id = ?
                      AND ts_entry >= CURRENT_DATE - INTERVAL '7 days'
                """, [anch_id]).fetchone()

                if episodes and episodes[0] > 0:
                    total, vessels, avg_dwell, latest = episodes
                    print(f"   📊 Episodes (7d):")
                    print(f"      Total episodes: {total}")
                    print(f"      Unique vessels: {vessels}")
                    print(f"      Avg dwell: {avg_dwell:.1f}h")
                    print(f"      Latest exit: {latest}")
                    print()
                else:
                    print(f"   ❌ No episodes recorded in last 7 days")
                    print()

                # Check daily metrics
                daily = con.execute("""
                    SELECT
                        ds,
                        episode_count,
                        median_dwell_h,
                        z_dwell,
                        anomaly_detected
                    FROM anchorage_daily_dwell
                    WHERE anchorage_id = ?
                    ORDER BY ds DESC
                    LIMIT 3
                """, [anch_id]).fetchall()

                if daily:
                    print(f"   📈 Daily Metrics (last 3 days):")
                    for ds, episodes, dwell, z, anomaly in daily:
                        status = "🔴" if anomaly else "✅"
                        print(f"      {status} {ds}: {episodes} episodes, {dwell:.1f}h median, Z={z:.2f}")
                    print()
                else:
                    print(f"   ⚠️  No daily aggregations")
                    print()

        else:
            print("   ❌ No OPL Singapore anchorage defined")
            print("   👉 Check anchorage_polygons table")
            print()

    except Exception as e:
        print(f"   ❌ Error: {e}")
        print()

    # 3. SHANDONG ANCHORAGES - Final destination
    print("3️⃣  SHANDONG ANCHORAGES (Final Destination)")
    print("-" * 80)

    shandong_anchorages = [
        'ANCH_QINGDAO',
        'ANCH_RIZHAO',
        'ANCH_YANTAI',
        'ANCH_LONGKOU',
        'ANCH_LANSHAN'
    ]

    try:
        for anch_id in shandong_anchorages:
            # Check if anchorage exists
            exists = con.execute("""
                SELECT anchorage_name, centroid_lat, centroid_lon
                FROM anchorage_polygons
                WHERE anchorage_id = ?
            """, [anch_id]).fetchone()

            if not exists:
                print(f"   ⚠️  {anch_id} - Not defined")
                continue

            name, lat, lon = exists
            print(f"   ✅ {anch_id} - {name}")
            print(f"      Location: {lat:.2f}°N, {lon:.2f}°E")

            # Check episodes (7d)
            episodes = con.execute("""
                SELECT
                    COUNT(*) as total_episodes,
                    COUNT(DISTINCT mmsi) as unique_vessels,
                    AVG(dwell_hours) as avg_dwell_h,
                    MAX(ts_exit) as latest_exit
                FROM anchorage_episodes
                WHERE anchorage_id = ?
                  AND ts_entry >= CURRENT_DATE - INTERVAL '7 days'
            """, [anch_id]).fetchone()

            if episodes and episodes[0] > 0:
                total, vessels, avg_dwell, latest = episodes
                print(f"      Episodes (7d): {total} | Vessels: {vessels} | Avg dwell: {avg_dwell:.1f}h")
            else:
                print(f"      Episodes (7d): 0 (no data)")

            # Check latest daily metric
            daily = con.execute("""
                SELECT ds, episode_count, median_dwell_h, z_dwell, anomaly_detected
                FROM anchorage_daily_dwell
                WHERE anchorage_id = ?
                ORDER BY ds DESC
                LIMIT 1
            """, [anch_id]).fetchone()

            if daily:
                ds, eps, dwell, z, anomaly = daily
                status = "🔴" if anomaly else "✅"
                print(f"      Latest: {ds} | {eps} episodes | {dwell:.1f}h median | Z={z:.2f} {status}")
            else:
                print(f"      Latest: No daily data")

            print()

    except Exception as e:
        print(f"   ❌ Error: {e}")
        print()

    # 4. CHAIN COMPLETENESS
    print("4️⃣  SUPPLY CHAIN COMPLETENESS")
    print("-" * 80)

    has_malacca_gate = len(malacca_gates) > 0 if 'malacca_gates' in locals() else False
    has_malacca_sis = len(malacca_sis) > 0 if 'malacca_sis' in locals() else False
    has_opl = len(opl_anch) > 0 if 'opl_anch' in locals() else False

    # Count Shandong anchorages with data
    shandong_with_data = 0
    for anch_id in shandong_anchorages:
        count = con.execute("""
            SELECT COUNT(*) FROM anchorage_daily_dwell
            WHERE anchorage_id = ?
        """, [anch_id]).fetchone()[0]
        if count > 0:
            shandong_with_data += 1

    has_shandong = shandong_with_data > 0

    print(f"   Malacca Gate Crossings:  {'✅' if has_malacca_gate else '❌'}")
    print(f"   Malacca Sea State (SIS): {'✅' if has_malacca_sis else '❌'}")
    print(f"   OPL Singapore Anchorage: {'✅' if has_opl else '❌'}")
    print(f"   Shandong Anchorages:     {'✅' if has_shandong else '❌'} ({shandong_with_data}/{len(shandong_anchorages)} with data)")
    print()

    if all([has_malacca_gate, has_opl, has_shandong]):
        print("   🎉 SUPPLY CHAIN COMPLETE!")
        print("   You can track: Malacca flux → OPL dwell → Shandong congestion")
        print()
        print("   📊 TH-4 API Endpoints:")
        print("      GET /api/anchorage/summary?anchorage_ids=ANCH_OPL_SIN,ANCH_QINGDAO&window=d7")
        print("      GET /api/anchorage/daily?anchorage_ids=ANCH_QINGDAO&start=2025-11-01")
        print("      GET /api/anchorage/episodes?anchorage_id=ANCH_OPL_SIN&limit=20")
    else:
        print("   ⚠️  SUPPLY CHAIN INCOMPLETE")
        print()
        print("   Missing components:")
        if not has_malacca_gate:
            print("      ❌ Malacca gate crossings - Add GATE_MALACCA to gates.geojson")
        if not has_malacca_sis:
            print("      ❌ Malacca SIS data - Run: PYTHONPATH=src python -m spvx.cli ingest-sea-state")
        if not has_opl:
            print("      ❌ OPL Singapore anchorage - Run: python3 setup_anchorage_test_data.py")
        if not has_shandong:
            print(f"      ❌ Shandong anchorages - Only {shandong_with_data}/{len(shandong_anchorages)} have data")

    print()
    print("=" * 80)

    con.close()

if __name__ == "__main__":
    check_supply_chain()
