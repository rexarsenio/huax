#!/usr/bin/env python
"""Test script for full polygon detection pipeline."""
import sys
sys.path.insert(0, '/Users/alongo/Desktop/huax/spvx-lite/src')

import duckdb
from datetime import datetime
from spvx.open_sea.polygon_detect import PolygonDetector, PolygonConfig

def main():
    db_path = 'db/spvx_POLYGON_TEST.duckdb'
    terminals_path = 'data/geo/oil_terminals.geojson'
    sts_path = 'data/geo/sts_zones.geojson'

    print("=" * 70)
    print("POLYGON DETECTION PIPELINE TEST")
    print("=" * 70)

    con = duckdb.connect(db_path)

    try:
        # Step 1: Initialize detector
        print("\n[1/4] Initializing polygon detector...")
        config = PolygonConfig()
        detector = PolygonDetector(con, terminals_path, sts_path, config)
        print(f"  ✓ Loaded {len(detector.polygons)} polygons")
        print(f"  ✓ {len(detector.open_sessions)} open sessions recovered")

        # Step 2: Query sample of AIS fixes (last 7 days)
        print("\n[2/4] Querying AIS fixes (last 7 days)...")
        result = con.execute("""
            SELECT mmsi, msg_time, lon, lat, sog
            FROM ais_canon
            WHERE msg_time >= NOW() - INTERVAL '7 days'
            ORDER BY msg_time ASC
            LIMIT 100000
        """)

        fixes = result.fetchall()
        print(f"  ✓ Loaded {len(fixes):,} fixes")

        # Step 3: Process fixes
        print("\n[3/4] Processing fixes through detector...")
        total_events = 0
        for i, (mmsi, ts, lon, lat, sog) in enumerate(fixes):
            events = detector.handle_fix(mmsi, ts, lon, lat, sog)
            total_events += len(events)

            if (i + 1) % 10000 == 0:
                print(f"  Processed {i+1:,}/{len(fixes):,} fixes, {total_events} events so far...")

        # Step 4: Finalize
        print("\n[4/4] Finalizing detector...")
        final_events = detector.finalize(datetime.now())
        total_events += len(final_events)

        con.commit()

        print(f"\n{'=' * 70}")
        print("✓ POLYGON DETECTION COMPLETE")
        print(f"{'=' * 70}")
        print(f"  Fixes processed: {len(fixes):,}")
        print(f"  Events generated: {total_events:,}")

        # Show summary
        print("\n[SUMMARY] Event breakdown:")
        summary = con.execute("""
            SELECT kind, COUNT(*) as events, SUM(dwell_min) as total_dwell_min,
                   MIN(dwell_min) as min_dwell, MAX(dwell_min) as max_dwell
            FROM polygon_events
            GROUP BY kind
        """).fetchall()

        if summary:
            for kind, events, total_dwell, min_dwell, max_dwell in summary:
                print(f"  {kind}:")
                print(f"    Events: {events:,}")
                print(f"    Total dwell: {total_dwell:,} min ({total_dwell/60:.1f} hours)")
                print(f"    Dwell range: {min_dwell}-{max_dwell} min")
        else:
            print("  No events generated yet (vessels may still be dwelling)")

        # Show top polygons
        print("\n[TOP POLYGONS] Most active terminals/zones:")
        top = con.execute("""
            SELECT polygon_id, kind, COUNT(*) as visits, SUM(dwell_min) as total_dwell
            FROM polygon_events
            GROUP BY polygon_id, kind
            ORDER BY visits DESC
            LIMIT 10
        """).fetchall()

        if top:
            for polygon_id, kind, visits, total_dwell in top:
                print(f"  {polygon_id} ({kind}): {visits} visits, {total_dwell} min")
        else:
            print("  No polygon events yet")

    finally:
        con.close()

if __name__ == "__main__":
    main()
