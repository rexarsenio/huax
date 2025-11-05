#!/usr/bin/env python3
"""
Ingest OpenWeather wind data and write to CSV (for later DB import).
Workaround for DB lock issues.
"""

import datetime as dt
from pathlib import Path

import pandas as pd

from spvx.weather.openweather import fetch_weather_samples


# Mapping OpenWeather regions to corridor IDs
REGION_TO_CORRIDOR = {
    "singapore_malacca": "CHOKEPOINT_MALACCA->UNK",
    "singapore": "CHOKEPOINT_SINGAPORE_STRAIT->UNK",
    "suez": "CHOKEPOINT_SUEZ_NORTH->UNK",
    "gibraltar": "CHOKEPOINT_GIBRALTAR->UNK",
    "bosporus": "CHOKEPOINT_BOSPORUS->UNK",
}


def ingest_weather_to_csv(output_csv: str = "data/processed/regional_wind.csv"):
    """
    Fetch OpenWeather data and write to CSV.

    This avoids DB lock issues by writing to CSV first.
    """

    print("🌬️  Fetching OpenWeather wind data...\n")

    # Fetch weather samples
    samples = fetch_weather_samples(regions=None)  # None = all regions

    if not samples:
        print("⚠️  No weather data collected!")
        return

    print(f"✅ Collected {len(samples)} weather samples")

    # Convert to DataFrame
    rows = []
    for sample in samples:
        # Check if this is one of our 5 corridors
        corridor_id = REGION_TO_CORRIDOR.get(sample.region)
        if not corridor_id:
            continue

        rows.append({
            "ds": sample.observed_at.date(),
            "corridor_id": corridor_id,
            "wind_speed_kn": sample.wind_speed_kn,
            "wind_gust_kn": sample.wind_gust_kn,
            "weather_flag": sample.weather_flag,
            "observed_at": sample.observed_at,
        })

    if not rows:
        print("\n⚠️  No data for the 5 main corridors!")
        return

    df = pd.DataFrame(rows)

    # Aggregate by day (in case multiple samples per day)
    daily = df.groupby(["ds", "corridor_id"]).agg({
        "wind_speed_kn": "mean",  # p90 would be better but we have few samples
        "wind_gust_kn": "max",
        "weather_flag": "max",
    }).reset_index()

    # Rename to match schema
    daily = daily.rename(columns={
        "wind_speed_kn": "hw_p90_ms",  # Actually using mean, but naming for schema compatibility
    })

    # Convert knots to m/s for database (1 kn = 0.514444 m/s)
    daily["hw_p90_ms"] = daily["hw_p90_ms"] * 0.514444

    print(f"\n📦 Total records: {len(daily)}")
    print(f"   Corridors: {daily['corridor_id'].nunique()}")
    print(f"   Avg wind speed: {daily['hw_p90_ms'].mean():.2f} m/s ({daily['hw_p90_ms'].mean() / 0.514444:.2f} kn)")

    # Write to CSV
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_csv, index=False)
    print(f"\n💾 Wrote data to {output_csv}")

    print("\n📋 Summary by corridor:")
    summary = daily.groupby("corridor_id").agg({
        "hw_p90_ms": "mean",
        "ds": "count"
    }).round(2)
    summary.columns = ["Avg Wind (m/s)", "Records"]
    # Add knots column
    summary["Avg Wind (kn)"] = (summary["Avg Wind (m/s)"] / 0.514444).round(2)
    print(summary[["Avg Wind (kn)", "Avg Wind (m/s)", "Records"]].to_string())

    print("\n✅ Done!")
    print(f"\n💡 To import into database when ready:")
    print(f"   duckdb db/spvx.duckdb")
    print(f"   >> CREATE TEMP TABLE wind_temp AS SELECT * FROM read_csv_auto('{output_csv}');")
    print(f"   >> UPDATE sea_state_daily SET hw_p90_ms = t.hw_p90_ms")
    print(f"   >> FROM wind_temp t WHERE sea_state_daily.ds = t.ds AND sea_state_daily.corridor_id = t.corridor_id;")


if __name__ == "__main__":
    ingest_weather_to_csv()
