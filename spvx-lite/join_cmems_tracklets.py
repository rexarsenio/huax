#!/usr/bin/env python
"""
Spatial-temporal join of CMEMS grid data with vessel tracklets.

This script:
1. Generates mock tracklets (or reads from DB if available)
2. Loads CMEMS parquet files
3. Performs nearest-neighbor spatial-temporal join
4. Computes head components (wind, current)
5. Writes to sea_state_samples table
"""

import numpy as np
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timedelta, timezone
from scipy.spatial import cKDTree
import logging

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def generate_mock_tracklets(n_tracklets=20):
    """Generate realistic mock tracklets for chokepoints."""

    # Define realistic chokepoint routes
    routes = [
        # Strait of Hormuz
        {"from": "AG", "to": "HORMUZ", "lat_start": 26.0, "lon_start": 56.2, "lat_end": 26.5, "lon_end": 56.8, "cog": 60},
        {"from": "HORMUZ", "to": "MALACCA", "lat_start": 26.5, "lon_start": 56.8, "lat_end": 1.3, "lon_end": 103.8, "cog": 110},

        # Malacca Strait
        {"from": "MALACCA", "to": "SINGAPORE", "lat_start": 2.0, "lon_start": 100.5, "lat_end": 1.25, "lon_end": 103.8, "cog": 120},
        {"from": "SINGAPORE", "to": "PACIFIC", "lat_start": 1.25, "lon_start": 103.8, "lat_end": 1.2, "lon_end": 104.2, "cog": 95},

        # Suez Canal
        {"from": "RED_SEA", "to": "SUEZ_S", "lat_start": 29.9, "lon_start": 32.5, "lat_end": 30.0, "lon_end": 32.55, "cog": 0},
        {"from": "SUEZ_N", "to": "MED", "lat_start": 31.3, "lon_start": 32.3, "lat_end": 31.5, "lon_end": 32.4, "cog": 340},

        # Gibraltar
        {"from": "ATLANTIC", "to": "GIBRALTAR", "lat_start": 35.9, "lon_start": -5.5, "lat_end": 36.0, "lon_end": -5.35, "cog": 80},
        {"from": "GIBRALTAR", "to": "MED", "lat_start": 36.0, "lon_start": -5.35, "lat_end": 36.1, "lon_end": -5.2, "cog": 85},
    ]

    tracklets = []
    base_time = datetime.now(timezone.utc) - timedelta(days=3)

    for i in range(n_tracklets):
        route = routes[i % len(routes)]

        # Random start time within last 3 days
        start_offset = np.random.randint(0, 72) * 3600  # 0-72 hours
        start_ts = base_time + timedelta(seconds=start_offset)

        # Transit time: 2-8 hours
        transit_hours = np.random.uniform(2, 8)
        end_ts = start_ts + timedelta(hours=transit_hours)

        # Random MMSI (tanker range)
        mmsi = 200000000 + np.random.randint(1000000, 9999999)

        # Average speed and course
        mean_sog = np.random.uniform(10, 15)  # knots
        mean_cog = route["cog"] + np.random.uniform(-10, 10)  # degrees

        # Number of AIS fixes during transit
        n_points = int(transit_hours * 6)  # ~6 fixes per hour

        tracklet = {
            "tracklet_id": 1000000 + i,  # BIGINT
            "mmsi": mmsi,
            "poly_from_id": route["from"],
            "poly_to_id": route["to"],
            "start_ts": start_ts,
            "end_ts": end_ts,
            "mean_sog": mean_sog,
            "mean_cog": np.radians(mean_cog),  # Convert to radians
            "n_fixes": n_points,
            "status": "completed",
            # Route geometry
            "lat_start": route["lat_start"],
            "lon_start": route["lon_start"],
            "lat_end": route["lat_end"],
            "lon_end": route["lon_end"],
        }
        tracklets.append(tracklet)

    return pd.DataFrame(tracklets)


def load_cmems_data(region="CQ_SG"):
    """Load CMEMS parquet data for a region."""
    parquet_path = Path(f"data/processed/sea_state_{region}.parquet")

    if not parquet_path.exists():
        LOG.warning(f"No CMEMS data for {region} at {parquet_path}")
        return None

    df = pd.read_parquet(parquet_path)
    LOG.info(f"Loaded {len(df)} CMEMS samples for {region}")
    return df


def interpolate_tracklet_positions(tracklet, n_samples=10):
    """Generate positions along tracklet path."""
    positions = []

    for i in range(n_samples):
        fraction = i / (n_samples - 1)

        lat = tracklet["lat_start"] + fraction * (tracklet["lat_end"] - tracklet["lat_start"])
        lon = tracklet["lon_start"] + fraction * (tracklet["lon_end"] - tracklet["lon_start"])

        ts = tracklet["start_ts"] + fraction * (tracklet["end_ts"] - tracklet["start_ts"])

        positions.append({
            "tracklet_id": tracklet["tracklet_id"],
            "ts": ts,
            "lat": lat,
            "lon": lon,
            "mean_cog": tracklet["mean_cog"],
        })

    return positions


def spatial_temporal_join(tracklet_positions, cmems_df, max_distance_km=50, max_time_hours=3):
    """
    Perform nearest-neighbor spatial-temporal join.

    Args:
        tracklet_positions: List of tracklet position dicts
        cmems_df: DataFrame with columns [time, lat, lon, hs, u10, v10, uo, vo, sst_anom]
        max_distance_km: Maximum spatial distance for match
        max_time_hours: Maximum temporal distance for match

    Returns:
        DataFrame with joined sea state samples
    """
    if cmems_df is None or cmems_df.empty:
        return pd.DataFrame()

    tracklet_df = pd.DataFrame(tracklet_positions)

    # Ensure datetime types
    tracklet_df["ts"] = pd.to_datetime(tracklet_df["ts"], utc=True)
    cmems_df["time"] = pd.to_datetime(cmems_df["time"], utc=True)

    results = []

    # Build spatial index for CMEMS points
    cmems_coords = cmems_df[["lat", "lon"]].values
    tree = cKDTree(cmems_coords)

    for _, tracklet_pos in tracklet_df.iterrows():
        # Find nearest CMEMS points spatially
        distances, indices = tree.query([tracklet_pos["lat"], tracklet_pos["lon"]], k=5)

        # Check temporal distance
        tracklet_time = tracklet_pos["ts"]

        best_match = None
        best_score = float("inf")

        for dist_km, idx in zip(distances * 111, indices):  # Convert degrees to km
            if dist_km > max_distance_km:
                continue

            cmems_time = cmems_df.iloc[idx]["time"]
            time_diff_hours = abs((tracklet_time - cmems_time).total_seconds()) / 3600

            if time_diff_hours > max_time_hours:
                continue

            # Combined score: spatial + temporal
            score = dist_km + time_diff_hours * 10  # Weight temporal by 10 km/hour

            if score < best_score:
                best_score = score
                best_match = idx

        if best_match is not None:
            cmems_row = cmems_df.iloc[best_match]

            # Compute head components
            cog_rad = tracklet_pos["mean_cog"]
            cos_cog = np.cos(cog_rad)
            sin_cog = np.sin(cog_rad)

            # Head current (opposing flow)
            head_current_ms = -(cmems_row["uo"] * cos_cog + cmems_row["vo"] * sin_cog)
            head_current_kn = head_current_ms * 1.94384  # m/s to knots

            # Head wind (opposing)
            head_wind_ms = -(cmems_row["u10"] * cos_cog + cmems_row["v10"] * sin_cog)

            # Wave encounter (just wave height for simplicity)
            wave_encounter_m = cmems_row["hs"]

            result = {
                "tracklet_id": tracklet_pos["tracklet_id"],
                "ts": tracklet_pos["ts"],
                "lat": tracklet_pos["lat"],
                "lon": tracklet_pos["lon"],
                "hs": cmems_row["hs"],
                "u10": cmems_row["u10"],
                "v10": cmems_row["v10"],
                "uo": cmems_row["uo"] if "uo" in cmems_row else 0.0,
                "vo": cmems_row["vo"] if "vo" in cmems_row else 0.0,
                "sst_anom": cmems_row.get("sst_anom", 0.0),
                "head_current_kn": head_current_kn,
                "head_wind_ms": head_wind_ms,
                "wave_encounter_m": wave_encounter_m,
            }
            results.append(result)

    return pd.DataFrame(results)


def write_to_db(samples_df, db_path="db/spvx.duckdb"):
    """Write sea state samples to database."""
    if samples_df.empty:
        LOG.warning("No samples to write")
        return 0

    con = duckdb.connect(db_path)

    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sea_state_samples (
                tracklet_id TEXT,
                ts TIMESTAMP,
                lat DOUBLE,
                lon DOUBLE,
                hs DOUBLE,
                u10 DOUBLE,
                v10 DOUBLE,
                uo DOUBLE,
                vo DOUBLE,
                sst_anom DOUBLE,
                head_current_kn DOUBLE,
                head_wind_ms DOUBLE,
                wave_encounter_m DOUBLE
            )
            """
        )

        samples_df = samples_df.copy()
        samples_df["ts"] = pd.to_datetime(samples_df["ts"], utc=True)
        min_ts = samples_df["ts"].min()
        max_ts = samples_df["ts"].max()
        LOG.info(
            "Deleting existing samples between %s and %s",
            min_ts.isoformat(),
            max_ts.isoformat(),
        )
        con.execute(
            "DELETE FROM sea_state_samples WHERE ts BETWEEN ? AND ?",
            [min_ts.to_pydatetime(), max_ts.to_pydatetime()],
        )

        rows = [tuple(row) for row in samples_df.values.tolist()]
        con.executemany(
            """
            INSERT INTO sea_state_samples
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        con.commit()
        count = len(samples_df)
        LOG.info("✓ Wrote %s samples to sea_state_samples", count)
        return count
    finally:
        con.close()


def main():
    LOG.info("=== CMEMS-Tracklet Join Script ===")

    # Step 1: Generate mock tracklets
    LOG.info("Step 1: Generating mock tracklets...")
    tracklets = generate_mock_tracklets(n_tracklets=20)
    LOG.info(f"✓ Generated {len(tracklets)} mock tracklets")

    # Step 2: Write tracklets to DB
    LOG.info("Step 2: Writing tracklets to database...")
    con = duckdb.connect("db/spvx.duckdb")
    con.execute("DELETE FROM tracklets")  # Clear old

    for _, tracklet in tracklets.iterrows():
        con.execute("""
            INSERT INTO tracklets
            (tracklet_id, mmsi, poly_from_id, poly_to_id, start_ts, end_ts, mean_sog, mean_cog, n_fixes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            int(tracklet["tracklet_id"]),
            int(tracklet["mmsi"]),
            tracklet["poly_from_id"],
            tracklet["poly_to_id"],
            tracklet["start_ts"],
            tracklet["end_ts"],
            tracklet["mean_sog"],
            tracklet["mean_cog"],
            int(tracklet["n_fixes"]),
            tracklet["status"],
        ])
    con.commit()
    con.close()
    LOG.info(f"✓ Wrote {len(tracklets)} tracklets to database")

    # Step 3: Load CMEMS data
    LOG.info("Step 3: Loading CMEMS data...")
    regions = ["CQ_SG", "CQ_TR", "PORT_EU", "CQ_SUEZ", "CQ_GIBRALTAR"]
    cmems_data = {}

    for region in regions:
        df = load_cmems_data(region)
        if df is not None and not df.empty:
            cmems_data[region] = df

    if not cmems_data:
        LOG.error("No CMEMS data found! Run: python process_existing_sea_state.py")
        return

    # Step 4: Generate tracklet positions
    LOG.info("Step 4: Generating tracklet positions...")
    all_positions = []
    for _, tracklet in tracklets.iterrows():
        positions = interpolate_tracklet_positions(tracklet, n_samples=10)
        all_positions.extend(positions)
    LOG.info(f"✓ Generated {len(all_positions)} tracklet positions")

    # Step 5: Spatial-temporal join
    LOG.info("Step 5: Performing spatial-temporal join...")
    # Use first available CMEMS dataset for demo
    first_region = list(cmems_data.keys())[0]
    cmems_df = cmems_data[first_region]

    samples = spatial_temporal_join(all_positions, cmems_df, max_distance_km=100, max_time_hours=6)
    LOG.info(f"✓ Matched {len(samples)} samples (from {len(all_positions)} positions)")

    # Step 6: Write to database
    LOG.info("Step 6: Writing to database...")
    count = write_to_db(samples)

    LOG.info(f"\n=== Summary ===")
    LOG.info(f"Mock tracklets:      {len(tracklets)}")
    LOG.info(f"Tracklet positions:  {len(all_positions)}")
    LOG.info(f"CMEMS regions:       {len(cmems_data)}")
    LOG.info(f"Matched samples:     {len(samples)}")
    LOG.info(f"Written to DB:       {count}")
    LOG.info(f"\n✓ Done! Ready to run: python -m spvx.cli sea-state-join")


if __name__ == "__main__":
    main()
