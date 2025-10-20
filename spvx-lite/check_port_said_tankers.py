#!/usr/bin/env python3
"""
Quick script to check tankers in Port Said (Suez Canal) region.
Your specific coordinates: 32.51-32.59°E, 29.91-29.96°N

Usage:
    python check_port_said_tankers.py
"""

import duckdb
from pathlib import Path
import sys

# Port Said bounding box (from your GeoJSON)
LON_MIN, LON_MAX = 32.50893236223425, 32.58842670653189
LAT_MIN, LAT_MAX = 29.911469982654836, 29.957396076891925

def main():
    db_path = Path('db/spvx.duckdb')

    if not db_path.exists():
        print("❌ Database not found. Is the AIS stream running?")
        sys.exit(1)

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as e:
        print(f"⚠️  Cannot access DB (stream is using it): {e}")
        print("💡 Try: pkill -USR1 -f ingest_aisstream.py  # to trigger a checkpoint")
        sys.exit(1)

    print("🌍 Port Said Region - Tanker Tracker")
    print("=" * 80)
    print(f"   Bounding Box: [{LON_MIN:.6f}, {LAT_MIN:.6f}] → [{LON_MAX:.6f}, {LAT_MAX:.6f}]")
    print()

    # Total stats
    total = con.execute('SELECT COUNT(*), COUNT(DISTINCT mmsi) FROM ais_raw').fetchone()
    print(f"📊 Database Total:")
    print(f"   All Positions:     {total[0]:,}")
    print(f"   Unique Tankers:    {total[1]}")
    print()

    # Regions
    regions = con.execute('''
        SELECT region, COUNT(*) as cnt, COUNT(DISTINCT mmsi) as vessels
        FROM ais_raw
        GROUP BY region
        ORDER BY cnt DESC
    ''').fetchall()

    print("📍 By Region:")
    for region, cnt, vessels in regions:
        print(f"   {region:<25} {cnt:>6,} pos, {vessels:>4} vessels")
    print()

    # Port Said Box
    box = con.execute(f'''
        SELECT
            COUNT(*) as positions,
            COUNT(DISTINCT mmsi) as vessels,
            MIN(ts) as first,
            MAX(ts) as latest
        FROM ais_raw
        WHERE
            lat BETWEEN {LAT_MIN} AND {LAT_MAX}
            AND lon BETWEEN {LON_MIN} AND {LON_MAX}
    ''').fetchone()

    print(f"📦 Port Said Box (Your Coordinates):")
    print(f"   Total Positions: {box[0]:,}")
    print(f"   Unique Tankers:  {box[1]}")

    if box[0] > 0:
        print(f"   Time Range:      {box[2]} → {box[3]}")
        print()

        # Vessel details
        vessels = con.execute(f'''
            SELECT
                mmsi,
                COUNT(*) as pos_count,
                AVG(lat) as avg_lat,
                AVG(lon) as avg_lon,
                AVG(sog) as avg_sog,
                shiptype,
                MAX(ts) as last_seen
            FROM ais_raw
            WHERE
                lat BETWEEN {LAT_MIN} AND {LAT_MAX}
                AND lon BETWEEN {LON_MIN} AND {LON_MAX}
            GROUP BY mmsi, shiptype
            ORDER BY pos_count DESC, last_seen DESC
        ''').fetchall()

        print("🚢 Tanker Details:")
        print(f"{'MMSI':<12} {'Pos':<6} {'Avg Position':<22} {'SOG':<8} {'Type':<6} {'Last Seen':<20}")
        print("-" * 90)

        for mmsi, pos, lat, lon, sog, shiptype, last in vessels:
            pos_str = f"{lat:7.4f}°N, {lon:7.4f}°E"
            print(f"{mmsi:<12} {pos:<6} {pos_str:<22} {sog:5.1f}kt {shiptype or 'N/A':<6} {str(last)[:19]}")
    else:
        print("   ⏳ No data yet - stream is collecting...")
        print()
        print("💡 Tip: The AIS stream collects data for all chokepoints.")
        print("   Suez Canal data will appear when tankers pass through Port Said.")

    con.close()

if __name__ == "__main__":
    main()
