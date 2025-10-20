"""Sea-state ingestion (currents + waves) via RTOFS/WW3."""

from __future__ import annotations

import datetime as dt
import logging
import math
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

import duckdb
import numpy as np
import xarray as xr

from chokepoints import CHOKEPOINTS
from spvx.db import ensure_core_tables

LOG = logging.getLogger("spvx.weather.sea_state")

KNOTS_PER_MS = 1.943844
CURRENT_FLAG_THRESHOLD_KN = float(os.getenv("SEA_CURRENT_FLAG_KN", "3.0"))
WAVE_FLAG_THRESHOLD_M = float(os.getenv("SEA_WAVE_FLAG_M", "3.5"))

# Default dataset templates (see NOMADS documentation)
RTOFS_URL_TEMPLATE = (
    "https://nomads.ncep.noaa.gov/dods/rtofs/rtofs_global{run_date}/"
    "rtofs_glo_2ds_forecast_3hrly_prog"
)
RTOFS_DATASET_NAMES: Sequence[str] = ("u", "v", "time", "lon", "lat")

WW3_URL_TEMPLATE = (
    "https://nomads.ncep.noaa.gov/dods/wave/nww3/nww3_global{run_date}/"
    "nww3hsfc_00z"
)
WW3_VARIABLE_CANDIDATES = {
    "hs": ["hs", "htsgwsfc", "swh"],
    "tp": ["tp", "ptp", "perpw", "wvper"],
    "dp": ["dp", "dirpw", "wvdir"],
}

BASIN_BY_REGION = {
    "singapore_malacca": "APAC",
    "hormuz": "APAC",
    "panama_n": "NAM",
    "panama_s": "SAM",
}


@dataclass
class CurrentSample:
    observed_at: dt.datetime
    region: str
    basin: str
    u_ms: float
    v_ms: float
    speed_kn: float
    flag: int
    source_url: str

    def as_row(self) -> Tuple:
        return (
            self.observed_at,
            self.region,
            self.basin,
            float(self.u_ms * KNOTS_PER_MS),
            float(self.v_ms * KNOTS_PER_MS),
            float(self.speed_kn),
            int(self.flag),
            self.source_url,
        )


@dataclass
class WaveSample:
    observed_at: dt.datetime
    region: str
    basin: str
    hs_m: float
    tp_s: Optional[float]
    dp_deg: Optional[float]
    flag: int
    source_url: str

    def as_row(self) -> Tuple:
        return (
            self.observed_at,
            self.region,
            self.basin,
            float(self.hs_m),
            float(self.tp_s) if self.tp_s is not None else None,
            float(self.dp_deg) if self.dp_deg is not None else None,
            int(self.flag),
            self.source_url,
        )


def _candidate_run_dates(days: int = 3) -> Iterable[dt.date]:
    today = dt.datetime.utcnow().date()
    for delta in range(days):
        yield today - dt.timedelta(days=delta)


def _pick_coord(ds: xr.Dataset, candidates: Sequence[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in ds.variables}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _normalize_lon(lon: float) -> float:
    # Convert to 0-360 range for datasets using that convention.
    if lon < 0:
        return lon % 360
    return lon


def _select_box(ds: xr.Dataset, region: str) -> xr.Dataset:
    lon_min, lat_min, lon_max, lat_max = CHOKEPOINTS[region]
    lat_name = _pick_coord(ds, ["lat", "latitude", "y", "Lat"])
    lon_name = _pick_coord(ds, ["lon", "longitude", "x", "Lon"])
    if not lat_name or not lon_name:
        raise KeyError("Dataset missing lat/lon coordinates")

    lon_values = ds[lon_name].values
    lon_min_adj, lon_max_adj = lon_min, lon_max
    if lon_values.min() >= 0 and lon_values.max() > 180:
        lon_min_adj = _normalize_lon(lon_min)
        lon_max_adj = _normalize_lon(lon_max)

    lat_slice = slice(min(lat_min, lat_max), max(lat_min, lat_max))
    lon_slice = slice(min(lon_min_adj, lon_max_adj), max(lon_min_adj, lon_max_adj))

    return ds.sel({lat_name: lat_slice, lon_name: lon_slice})


def _resolve_dataset(url_template: str, *, days: int = 3) -> Tuple[str, xr.Dataset]:
    for run_date in _candidate_run_dates(days):
        url = url_template.format(run_date=run_date.strftime("%Y%m%d"))
        try:
            ds = xr.open_dataset(url)
            return url, ds
        except Exception as exc:  # pragma: no cover - network dependent
            LOG.debug("[SEA-STATE] Failed dataset %s: %s", url, exc)
            continue
    raise RuntimeError(f"Could not resolve dataset for template {url_template}")


def fetch_rtofs_currents(region: str) -> Optional[CurrentSample]:
    basin = BASIN_BY_REGION.get(region, "GLOBAL")
    try:
        url, ds = _resolve_dataset(RTOFS_URL_TEMPLATE)
    except RuntimeError as exc:
        LOG.warning("[RTOFS] No dataset available: %s", exc)
        return None

    try:
        time_name = _pick_coord(ds, ["time", "Time"])
        if not time_name:
            raise KeyError("No time coordinate")
        time_index = 1 if ds.dims.get(time_name, 0) > 1 else 0
        subset = _select_box(ds.isel({time_name: time_index}), region)

        u_var = _pick_coord(subset, ["u", "water_u", "uo", "ucurr", "ucur"])
        v_var = _pick_coord(subset, ["v", "water_v", "vo", "vcurr", "vcur"])
        if not u_var or not v_var:
            raise KeyError("U/V current variables not found in RTOFS dataset")

        u = subset[u_var].mean().item()
        v = subset[v_var].mean().item()
        speed_ms = math.sqrt(u ** 2 + v ** 2)
        speed_kn = speed_ms * KNOTS_PER_MS
        flag = int(speed_kn >= CURRENT_FLAG_THRESHOLD_KN)

        observed_ts = subset[time_name].item()
        if isinstance(observed_ts, (np.datetime64, dt.datetime)):
            observed_at = np.datetime64(observed_ts).astype("datetime64[ns]").astype(dt.datetime)
        else:
            observed_at = dt.datetime.utcnow().replace(tzinfo=None)

        return CurrentSample(
            observed_at=observed_at,
            region=region,
            basin=basin,
            u_ms=float(u),
            v_ms=float(v),
            speed_kn=float(speed_kn),
            flag=flag,
            source_url=url,
        )
    finally:
        ds.close()


def fetch_ww3_waves(region: str) -> Optional[WaveSample]:
    basin = BASIN_BY_REGION.get(region, "GLOBAL")
    try:
        url, ds = _resolve_dataset(WW3_URL_TEMPLATE)
    except RuntimeError as exc:
        LOG.warning("[WW3] No dataset available: %s", exc)
        return None

    try:
        time_name = _pick_coord(ds, ["time", "Time"])
        if not time_name:
            raise KeyError("No time coordinate for WW3")
        time_index = 0
        subset = _select_box(ds.isel({time_name: time_index}), region)

        def _pick_var(candidates: Sequence[str]) -> Optional[str]:
            return _pick_coord(subset, candidates)

        hs_var = _pick_var(WW3_VARIABLE_CANDIDATES["hs"])
        tp_var = _pick_var(WW3_VARIABLE_CANDIDATES["tp"])
        dp_var = _pick_var(WW3_VARIABLE_CANDIDATES["dp"])
        if not hs_var:
            raise KeyError("WW3 significant wave height variable not found")

        hs = subset[hs_var].mean().item()
        tp = subset[tp_var].mean().item() if tp_var else None
        dp = subset[dp_var].mean().item() if dp_var else None
        flag = int(hs >= WAVE_FLAG_THRESHOLD_M)

        observed_ts = subset[time_name].item()
        if isinstance(observed_ts, (np.datetime64, dt.datetime)):
            observed_at = np.datetime64(observed_ts).astype("datetime64[ns]").astype(dt.datetime)
        else:
            observed_at = dt.datetime.utcnow().replace(tzinfo=None)

        return WaveSample(
            observed_at=observed_at,
            region=region,
            basin=basin,
            hs_m=float(hs),
            tp_s=float(tp) if tp is not None else None,
            dp_deg=float(dp) if dp is not None else None,
            flag=flag,
            source_url=url,
        )
    finally:
        ds.close()


def upsert_current_samples(con: duckdb.DuckDBPyConnection, samples: Iterable[CurrentSample]) -> int:
    rows = [sample.as_row() for sample in samples]
    if not rows:
        return 0
    ensure_core_tables(con)
    con.executemany(
        """
        INSERT INTO sea_currents_daily (
            observed_at,
            region,
            basin,
            u_knots,
            v_knots,
            speed_knots,
            weather_flag,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (observed_at, region, source) DO UPDATE SET
            u_knots = excluded.u_knots,
            v_knots = excluded.v_knots,
            speed_knots = excluded.speed_knots,
            weather_flag = excluded.weather_flag
        """,
        rows,
    )
    return len(rows)


def upsert_wave_samples(con: duckdb.DuckDBPyConnection, samples: Iterable[WaveSample]) -> int:
    rows = [sample.as_row() for sample in samples]
    if not rows:
        return 0
    ensure_core_tables(con)
    con.executemany(
        """
        INSERT INTO sea_waves_daily (
            observed_at,
            region,
            basin,
            hs_m,
            tp_s,
            dp_deg,
            weather_flag,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (observed_at, region, source) DO UPDATE SET
            hs_m = excluded.hs_m,
            tp_s = excluded.tp_s,
            dp_deg = excluded.dp_deg,
            weather_flag = excluded.weather_flag
        """,
        rows,
    )
    return len(rows)


def run(regions: Optional[Iterable[str]] = None) -> Tuple[int, int]:
    """Fetch sea-state measurements (currents + waves) and persist them."""
    target_regions = list(regions) if regions else list(BASIN_BY_REGION.keys())
    current_samples = []
    wave_samples = []

    for region in target_regions:
        try:
            current = fetch_rtofs_currents(region)
            if current:
                current_samples.append(current)
        except Exception as exc:  # pragma: no cover - depends on remote
            LOG.warning("[SEA-STATE] Currents failed for %s: %s", region, exc)

        try:
            wave = fetch_ww3_waves(region)
            if wave:
                wave_samples.append(wave)
        except Exception as exc:  # pragma: no cover - depends on remote
            LOG.warning("[SEA-STATE] Waves failed for %s: %s", region, exc)

    if not current_samples and not wave_samples:
        LOG.info("[SEA-STATE] No observations collected.")
        return (0, 0)

    con = duckdb.connect(os.getenv("DUCKDB_PATH", "db/spvx.duckdb"))
    try:
        currents = upsert_current_samples(con, current_samples)
        waves = upsert_wave_samples(con, wave_samples)
    finally:
        con.close()

    LOG.info("[SEA-STATE] Upserted %s current rows and %s wave rows.", currents, waves)
    return currents, waves
