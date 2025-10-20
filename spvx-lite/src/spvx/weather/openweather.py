"""OpenWeather ingestion for SPVX weather flags."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import duckdb
import requests

from spvx.db import ensure_core_tables
from chokepoints import CHOKEPOINTS

LOG = logging.getLogger("spvx.weather.openweather")

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_USER_AGENT = "spvx-lite-openweather/0.1 (+https://huax.ai)"
KNOTS_PER_MS = 1.943844

# Map chokepoint regions to basins used downstream.
BASIN_BY_REGION = {
    "singapore_malacca": "APAC",
    "hormuz": "APAC",
    "panama_n": "NAM",
    "panama_s": "SAM",
}


@dataclass
class WeatherSample:
    observed_at: dt.datetime
    region: str
    basin: str
    wind_speed_kn: Optional[float]
    wind_gust_kn: Optional[float]
    wave_height_m: Optional[float]
    weather_flag: int
    raw_payload: str


def _centroid(box: Iterable[float]) -> tuple[float, float]:
    lon_min, lat_min, lon_max, lat_max = box
    return (lat_min + lat_max) / 2.0, (lon_min + lon_max) / 2.0


def _ms_to_kn(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * KNOTS_PER_MS, 3)


def _compute_flag(wind_kn: Optional[float], gust_kn: Optional[float], wave_m: Optional[float]) -> int:
    thresholds = []
    if wind_kn is not None:
        thresholds.append(wind_kn >= 25.0)
    if gust_kn is not None:
        thresholds.append(gust_kn >= 25.0)
    if wave_m is not None:
        thresholds.append(wave_m >= 3.5)
    return int(any(thresholds)) if thresholds else 0


def fetch_openweather(region: str, *, api_key: str, session: Optional[requests.Session] = None) -> WeatherSample:
    if region not in CHOKEPOINTS:
        raise ValueError(f"Unknown chokepoint region '{region}'")
    lat, lon = _centroid(CHOKEPOINTS[region])
    basin = BASIN_BY_REGION.get(region, "GLOBAL")
    session = session or requests.Session()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}

    LOG.info("[OPENWEATHER] Request region=%s lat=%.3f lon=%.3f", region, lat, lon)
    response = session.get(OPENWEATHER_URL, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    payload = response.json()

    wind = payload.get("wind", {})
    water = payload.get("waves") or {}
    wind_speed_kn = _ms_to_kn(wind.get("speed"))
    wind_gust_kn = _ms_to_kn(wind.get("gust"))
    wave_height = water.get("height")
    observed_ts = payload.get("dt") or dt.datetime.utcnow().timestamp()
    observed_at = dt.datetime.fromtimestamp(observed_ts, tz=dt.timezone.utc)

    flag = _compute_flag(wind_speed_kn, wind_gust_kn, wave_height)

    return WeatherSample(
        observed_at=observed_at,
        region=region,
        basin=basin,
        wind_speed_kn=wind_speed_kn,
        wind_gust_kn=wind_gust_kn,
        wave_height_m=wave_height,
        weather_flag=flag,
        raw_payload=json.dumps(payload),
    )


def upsert_weather_samples(con: duckdb.DuckDBPyConnection, samples: Iterable[WeatherSample]) -> int:
    ensure_core_tables(con)
    rows = [
        (
            sample.observed_at,
            sample.region,
            sample.basin,
            sample.wind_speed_kn,
            sample.wind_gust_kn,
            sample.wave_height_m,
            sample.weather_flag,
            sample.raw_payload,
        )
        for sample in samples
    ]
    if not rows:
        return 0
    con.executemany(
        """
        INSERT INTO weather_observations (
            observed_at,
            region,
            basin,
            wind_speed_kn,
            wind_gust_kn,
            wave_height_m,
            weather_flag,
            raw_payload
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (observed_at, region, source) DO UPDATE SET
            wind_speed_kn = excluded.wind_speed_kn,
            wind_gust_kn = excluded.wind_gust_kn,
            wave_height_m = excluded.wave_height_m,
            weather_flag = excluded.weather_flag,
            raw_payload = excluded.raw_payload
        """,
        rows,
    )
    return len(rows)


def run(regions: Optional[Iterable[str]] = None) -> int:
    """Fetch OpenWeather observations for the configured regions."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        LOG.info("OPENWEATHER_API_KEY not configured; skipping weather ingest.")
        return 0

    target_regions: Iterable[str]
    if regions:
        target_regions = list(regions)
    else:
        target_regions = BASIN_BY_REGION.keys()

    samples = []
    session = requests.Session()
    for region in target_regions:
        try:
            sample = fetch_openweather(region, api_key=api_key, session=session)
            samples.append(sample)
        except Exception as exc:  # pragma: no cover - network failures
            LOG.warning("[OPENWEATHER] Failed for %s: %s", region, exc)
    session.close()

    if not samples:
        LOG.info("[OPENWEATHER] No weather samples collected.")
        return 0

    con = duckdb.connect(os.getenv("DUCKDB_PATH", "db/spvx.duckdb"))
    try:
        upserted = upsert_weather_samples(con, samples)
    finally:
        con.close()

    LOG.info("[OPENWEATHER] Upserted %s weather observations.", upserted)
    return upserted
