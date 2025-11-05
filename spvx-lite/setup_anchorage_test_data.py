#!/usr/bin/env python3
"""
Quick setup script to create test anchorage data for TH-4 API testing.

This creates minimal test data in the required tables so the API endpoints work.
For production, use TH-1, TH-2, TH-3 pipeline.
"""
import duckdb
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = "db/spvx.duckdb"

# Shandong anchorages + OPL Singapore
ANCHORAGES = [
    {"id": "ANCH_QINGDAO", "name": "Qingdao Anchorage", "lat": 36.07, "lon": 120.33},
    {"id": "ANCH_RIZHAO", "name": "Rizhao Anchorage", "lat": 35.43, "lon": 119.53},
    {"id": "ANCH_YANTAI", "name": "Yantai Anchorage", "lat": 37.53, "lon": 121.39},
    {"id": "ANCH_LONGKOU", "name": "Longkou Anchorage", "lat": 37.65, "lon": 120.33},
    {"id": "ANCH_LANSHAN", "name": "Lanshan Anchorage", "lat": 35.07, "lon": 119.35},
    {"id": "ANCH_OPL_SIN", "name": "OPL Singapore", "lat": 1.20, "lon": 103.75},
]

def main():
    print("🔧 Setting up anchorage test data...")

    con = duckdb.connect(DB_PATH)

    try:
        # 1. Create anchorage_polygons table
        print("\n1️⃣  Creating anchorage_polygons table...")
        con.execute("""
            CREATE TABLE IF NOT EXISTS anchorage_polygons (
                anchorage_id VARCHAR PRIMARY KEY,
                anchorage_name VARCHAR,
                kind VARCHAR DEFAULT 'ANCHORAGE',
                centroid_lat DOUBLE,
                centroid_lon DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert anchorages
        for anch in ANCHORAGES:
            con.execute("""
                INSERT OR REPLACE INTO anchorage_polygons (anchorage_id, anchorage_name, centroid_lat, centroid_lon)
                VALUES (?, ?, ?, ?)
            """, [anch["id"], anch["name"], anch["lat"], anch["lon"]])

        print(f"  ✓ Inserted {len(ANCHORAGES)} anchorage definitions")

        # 2. Create anchorage_episodes table
        print("\n2️⃣  Creating anchorage_episodes table...")
        con.execute("""
            CREATE TABLE IF NOT EXISTS anchorage_episodes (
                episode_id VARCHAR PRIMARY KEY,
                anchorage_id VARCHAR,
                mmsi BIGINT,
                vessel_name VARCHAR,
                ts_entry TIMESTAMP,
                ts_exit TIMESTAMP,
                dwell_hours DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Generate sample episodes (last 14 days)
        episodes = []
        base_mmsi = 412000000  # China flag range

        for i, anch in enumerate(ANCHORAGES):
            # Generate 20-40 episodes per anchorage
            num_episodes = 25 + (i * 5)

            for j in range(num_episodes):
                days_ago = 14 - (j % 14)
                entry = datetime.now() - timedelta(days=days_ago, hours=(j % 24))
                dwell = 12 + (j % 48)  # 12-60 hours
                exit_time = entry + timedelta(hours=dwell)

                episodes.append({
                    "episode_id": f"EP_{anch['id']}_{j:04d}",
                    "anchorage_id": anch["id"],
                    "mmsi": base_mmsi + i * 1000 + j,
                    "vessel_name": f"TANKER_{j:03d}",
                    "ts_entry": entry,
                    "ts_exit": exit_time,
                    "dwell_hours": dwell,
                })

        # Insert episodes
        df_episodes = pd.DataFrame(episodes)
        con.execute("""
            INSERT OR REPLACE INTO anchorage_episodes
            (episode_id, anchorage_id, mmsi, vessel_name, ts_entry, ts_exit, dwell_hours)
            SELECT episode_id, anchorage_id, mmsi, vessel_name, ts_entry, ts_exit, dwell_hours
            FROM df_episodes
        """)
        print(f"  ✓ Inserted {len(episodes)} sample episodes")

        # 3. Create anchorage_daily_dwell table
        print("\n3️⃣  Creating anchorage_daily_dwell table...")
        con.execute("""
            CREATE TABLE IF NOT EXISTS anchorage_daily_dwell (
                ds DATE,
                anchorage_id VARCHAR,
                episode_count INTEGER,
                median_dwell_h DOUBLE,
                p90_dwell_h DOUBLE,
                coverage_ratio DOUBLE,
                baseline_median_h DOUBLE,
                baseline_std_h DOUBLE,
                z_dwell DOUBLE,
                anomaly_detected BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ds, anchorage_id)
            )
        """)

        # Generate daily aggregations with Z-scores
        daily_data = []

        for days_ago in range(14):
            date = (datetime.now() - timedelta(days=days_ago)).date()

            for i, anch in enumerate(ANCHORAGES):
                # Simulate varying congestion
                base_count = 15 + (i * 2)

                # Create an "anomaly" on day 3 for Qingdao
                if anch["id"] == "ANCH_QINGDAO" and days_ago == 3:
                    episode_count = 35  # High congestion!
                    median_dwell = 48.0
                    z_score = 2.8
                    anomaly = True
                else:
                    episode_count = base_count + (days_ago % 5)
                    median_dwell = 24.0 + (days_ago % 12)
                    # Normal Z-score
                    z_score = -0.5 + (days_ago % 3) * 0.5
                    anomaly = z_score > 2.0

                daily_data.append({
                    "ds": date,
                    "anchorage_id": anch["id"],
                    "episode_count": episode_count,
                    "median_dwell_h": median_dwell,
                    "p90_dwell_h": median_dwell * 1.5,
                    "coverage_ratio": 0.85 + (days_ago % 10) * 0.01,
                    "baseline_median_h": 24.0,
                    "baseline_std_h": 8.0,
                    "z_dwell": z_score,
                    "anomaly_detected": anomaly,
                })

        # Insert daily data
        df_daily = pd.DataFrame(daily_data)
        con.execute("""
            INSERT OR REPLACE INTO anchorage_daily_dwell
            (ds, anchorage_id, episode_count, median_dwell_h, p90_dwell_h,
             coverage_ratio, baseline_median_h, baseline_std_h, z_dwell, anomaly_detected)
            SELECT ds, anchorage_id, episode_count, median_dwell_h, p90_dwell_h,
                   coverage_ratio, baseline_median_h, baseline_std_h, z_dwell, anomaly_detected
            FROM df_daily
        """)
        print(f"  ✓ Inserted {len(daily_data)} daily aggregation rows")

        # 4. Show summary
        print("\n📊 Data Summary:")
        print("=" * 60)

        for anch in ANCHORAGES:
            count = con.execute("""
                SELECT COUNT(*) FROM anchorage_episodes WHERE anchorage_id = ?
            """, [anch["id"]]).fetchone()[0]

            latest = con.execute("""
                SELECT episode_count, median_dwell_h, z_dwell
                FROM anchorage_daily_dwell
                WHERE anchorage_id = ?
                ORDER BY ds DESC
                LIMIT 1
            """, [anch["id"]]).fetchone()

            print(f"\n{anch['name']} ({anch['id']}):")
            print(f"  Episodes (14d): {count}")
            if latest:
                print(f"  Latest daily: {latest[0]} episodes, {latest[1]:.1f}h median, Z={latest[2]:.2f}")

        con.commit()
        print("\n✅ Test data setup complete!")
        print("\n💡 Next steps:")
        print("   1. Start API: python -m uvicorn spvx.api_app:app --port 8000 --reload")
        print("   2. Test: curl 'http://localhost:8000/api/anchorage/summary?anchorage_ids=ANCH_QINGDAO&window=d7'")

    finally:
        con.close()

if __name__ == "__main__":
    main()
