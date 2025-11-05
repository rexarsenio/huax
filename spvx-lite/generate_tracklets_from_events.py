#!/usr/bin/env python
"""
Generate tracklets from polygon_events (enter/exit pairs).

This script:
1. Finds enter+exit pairs for each vessel in each polygon
2. Fetches AIS fixes between enter/exit times
3. Computes mean SOG, mean COG, route geometry
4. Writes tracklets to the tracklets table
"""

import duckdb
import numpy as np
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def generate_tracklets(db_path="db/spvx.duckdb"):
    """Generate tracklets from polygon_events and open_sea_fixes."""

    # Try to connect - if locked, skip this run
    try:
        con = duckdb.connect(db_path)
    except Exception as e:
        LOG.error(f"Cannot connect to database (locked?): {e}")
        LOG.info("Skipping this iteration - will try again in 2 hours")
        return

    try:
        # Step 1: Find enter+exit pairs
        LOG.info("Step 1: Finding enter+exit pairs from polygon_events...")

        pairs = con.execute("""
            WITH enters AS (
                SELECT
                    mmsi,
                    polygon_id,
                    ts as enter_ts,
                    ROW_NUMBER() OVER (PARTITION BY mmsi, polygon_id ORDER BY ts) as enter_seq
                FROM polygon_events
                WHERE event = 'enter'
            ),
            exits AS (
                SELECT
                    mmsi,
                    polygon_id,
                    ts as exit_ts,
                    ROW_NUMBER() OVER (PARTITION BY mmsi, polygon_id ORDER BY ts) as exit_seq
                FROM polygon_events
                WHERE event = 'exit'
            )
            SELECT
                e1.mmsi,
                e1.polygon_id,
                e1.enter_ts,
                e2.exit_ts,
                EXTRACT(epoch FROM (e2.exit_ts - e1.enter_ts)) / 3600.0 as duration_hours
            FROM enters e1
            JOIN exits e2
                ON e1.mmsi = e2.mmsi
                AND e1.polygon_id = e2.polygon_id
                AND e1.enter_seq = e2.exit_seq
            WHERE e2.exit_ts > e1.enter_ts
            ORDER BY e1.enter_ts DESC
        """).fetchall()

        LOG.info(f"✓ Found {len(pairs)} enter+exit pairs")

        if not pairs:
            LOG.warning("No pairs found. Exiting.")
            return

        # Step 2: Clear existing real tracklets (keep mock ones for now)
        LOG.info("Step 2: Clearing existing real tracklets...")
        con.execute("DELETE FROM tracklets WHERE tracklet_id < 1000000")
        con.commit()

        # Step 3: Generate tracklets
        LOG.info("Step 3: Generating tracklets from AIS fixes...")

        tracklet_id = 1
        tracklets_created = 0

        for mmsi, polygon_id, enter_ts, exit_ts, duration_hours in pairs:
            # Get AIS fixes between enter and exit
            fixes = con.execute("""
                SELECT lat, lon, sog, cog, ts
                FROM open_sea_fixes
                WHERE mmsi = ?
                  AND ts BETWEEN ? AND ?
                ORDER BY ts
            """, [mmsi, enter_ts, exit_ts]).fetchall()

            if not fixes or len(fixes) < 2:
                continue

            # Compute statistics
            lats = [f[0] for f in fixes]
            lons = [f[1] for f in fixes]
            sogs = [f[2] for f in fixes if f[2] is not None]
            cogs = [f[3] for f in fixes if f[3] is not None]

            mean_sog = np.mean(sogs) if sogs else 0.0

            # Convert COG to radians for circular mean
            if cogs:
                cogs_rad = np.radians(cogs)
                mean_cog_rad = np.arctan2(np.mean(np.sin(cogs_rad)), np.mean(np.cos(cogs_rad)))
            else:
                mean_cog_rad = 0.0

            # Insert tracklet
            con.execute("""
                INSERT INTO tracklets
                (tracklet_id, mmsi, poly_from_id, poly_to_id, start_ts, end_ts,
                 mean_sog, mean_cog, n_fixes, status)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, 'completed')
            """, [
                tracklet_id,
                int(mmsi),
                polygon_id,
                enter_ts,
                exit_ts,
                float(mean_sog),
                float(mean_cog_rad),
                len(fixes),
            ])

            tracklet_id += 1
            tracklets_created += 1

            if tracklets_created % 100 == 0:
                LOG.info(f"  Created {tracklets_created} tracklets...")
                con.commit()

        con.commit()
        LOG.info(f"✓ Created {tracklets_created} tracklets")

        # Step 4: Summary
        LOG.info("\n=== Summary ===")

        real_count = con.execute(
            "SELECT COUNT(*) FROM tracklets WHERE tracklet_id < 1000000"
        ).fetchone()[0]

        mock_count = con.execute(
            "SELECT COUNT(*) FROM tracklets WHERE tracklet_id >= 1000000"
        ).fetchone()[0]

        LOG.info(f"Real tracklets:  {real_count}")
        LOG.info(f"Mock tracklets:  {mock_count}")
        LOG.info(f"Total tracklets: {real_count + mock_count}")

        # Sample
        sample = con.execute("""
            SELECT tracklet_id, mmsi, poly_from_id, start_ts, end_ts, mean_sog, n_fixes
            FROM tracklets
            WHERE tracklet_id < 1000000
            ORDER BY start_ts DESC
            LIMIT 5
        """).fetchall()

        LOG.info("\nRecent real tracklets:")
        for row in sample:
            tid, mmsi, poly, start, end, sog, fixes = row
            LOG.info(f"  Tracklet {tid}: MMSI {mmsi} in {poly}, {fixes} fixes, {sog:.1f} kn")

        LOG.info("\n✓ Done! Tracklets ready for sea state join.")

    finally:
        con.close()


if __name__ == "__main__":
    generate_tracklets()
