#!/usr/bin/env python3
"""
Real-time monitor for Port Said tankers.
Checks every 60 seconds and alerts when first Suez data appears.

Usage:
    python watch_port_said.py

Stop with: Ctrl+C
"""

import duckdb
from pathlib import Path
import time
import sys
from datetime import datetime

# Port Said bounding box
LON_MIN, LON_MAX = 32.50893236223425, 32.58842670653189
LAT_MIN, LAT_MAX = 29.911469982654836, 29.957396076891925

CHECK_INTERVAL = 60  # seconds
FOUND_SUEZ = False
FOUND_PORT_SAID = False

def clear_line():
    """Clear current line in terminal."""
    sys.stdout.write('\r\033[K')
    sys.stdout.flush()

def try_check():
    """Try to check DB (returns None if locked)."""
    db_path = Path('db/spvx.duckdb')

    if not db_path.exists():
        return None

    try:
        con = duckdb.connect(str(db_path), read_only=True)

        # Quick stats
        total = con.execute('SELECT COUNT(*), COUNT(DISTINCT mmsi) FROM ais_raw').fetchone()

        # Region breakdown
        regions = con.execute('''
            SELECT region, COUNT(*), COUNT(DISTINCT mmsi)
            FROM ais_raw
            GROUP BY region
            ORDER BY COUNT(*) DESC
        ''').fetchall()

        # Suez check
        suez = con.execute("SELECT COUNT(*), COUNT(DISTINCT mmsi) FROM ais_raw WHERE region = 'suez'").fetchone()

        # Port Said box check
        port_said = con.execute(f'''
            SELECT COUNT(*), COUNT(DISTINCT mmsi), MAX(ts)
            FROM ais_raw
            WHERE lat BETWEEN {LAT_MIN} AND {LAT_MAX}
              AND lon BETWEEN {LON_MIN} AND {LON_MAX}
        ''').fetchone()

        con.close()

        return {
            'total_pos': total[0],
            'total_vessels': total[1],
            'regions': regions,
            'suez_pos': suez[0],
            'suez_vessels': suez[1],
            'port_said_pos': port_said[0],
            'port_said_vessels': port_said[1],
            'port_said_latest': port_said[2],
        }
    except Exception as e:
        return None

def format_time(seconds):
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def main():
    global FOUND_SUEZ, FOUND_PORT_SAID

    print("=" * 80)
    print("🔍 PORT SAID TANKER MONITOR - Real-time Watcher")
    print("=" * 80)
    print(f"   Checking every {CHECK_INTERVAL} seconds...")
    print(f"   Press Ctrl+C to stop")
    print("=" * 80)
    print()

    check_count = 0
    start_time = time.time()

    try:
        while True:
            check_count += 1
            elapsed = time.time() - start_time

            # Show waiting message
            clear_line()
            sys.stdout.write(f"⏳ Checking... (attempt #{check_count}, running {format_time(elapsed)})")
            sys.stdout.flush()

            result = try_check()

            if result is None:
                clear_line()
                print(f"⚠️  [{datetime.now().strftime('%H:%M:%S')}] DB locked (stream writing) - will retry in {CHECK_INTERVAL}s...")
            else:
                clear_line()
                timestamp = datetime.now().strftime('%H:%M:%S')

                print(f"📊 [{timestamp}] Total: {result['total_pos']:,} pos, {result['total_vessels']} vessels")

                # Show regions
                for region, cnt, vessels in result['regions']:
                    print(f"   • {region:<20} {cnt:>5,} pos, {vessels:>3} vessels")

                # Check Suez
                if result['suez_pos'] > 0:
                    if not FOUND_SUEZ:
                        print()
                        print("🎉" * 30)
                        print(f"   ✅ FIRST SUEZ DATA DETECTED!")
                        print(f"   📍 {result['suez_pos']} positions, {result['suez_vessels']} tankers")
                        print("🎉" * 30)
                        print()
                        FOUND_SUEZ = True
                    else:
                        print(f"   ✅ Suez: {result['suez_pos']:,} pos, {result['suez_vessels']} vessels")

                    # Check Port Said box
                    if result['port_said_pos'] > 0:
                        if not FOUND_PORT_SAID:
                            print()
                            print("🎯" * 30)
                            print(f"   ✅✅ FIRST PORT SAID TANKER DETECTED! ✅✅")
                            print(f"   📦 {result['port_said_pos']} positions in your box")
                            print(f"   🚢 {result['port_said_vessels']} unique tankers")
                            print(f"   🕒 Latest: {result['port_said_latest']}")
                            print("🎯" * 30)
                            print()
                            print("💡 Run: python check_port_said_tankers.py for details!")
                            print()
                            FOUND_PORT_SAID = True
                        else:
                            print(f"   🎯 Port Said Box: {result['port_said_pos']} pos, {result['port_said_vessels']} vessels (latest: {str(result['port_said_latest'])[:19]})")
                else:
                    print(f"   ⏳ Suez: Waiting for first tanker...")

                print()

            # Wait for next check
            for i in range(CHECK_INTERVAL, 0, -1):
                clear_line()
                sys.stdout.write(f"⏱️  Next check in {i:2d}s... (Press Ctrl+C to stop)")
                sys.stdout.flush()
                time.sleep(1)

            clear_line()
            print()

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 80)
        print("👋 Monitoring stopped by user")
        print(f"   Total runtime: {format_time(time.time() - start_time)}")
        print(f"   Checks performed: {check_count}")
        if FOUND_SUEZ:
            print("   ✅ Suez data was detected!")
        if FOUND_PORT_SAID:
            print("   ✅ Port Said tankers were detected!")
        print("=" * 80)
        sys.exit(0)

if __name__ == "__main__":
    main()
