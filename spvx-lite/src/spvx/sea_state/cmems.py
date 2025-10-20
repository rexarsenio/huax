"""
Copernicus Marine Service (CMEMS) provider for sea-state features.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import math
import os
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

try:  # pragma: no cover - optional dependency
    import copernicusmarine

    HAS_CMEMS = True
except ImportError:  # pragma: no cover - executed in environments without CMEMS SDK
    HAS_CMEMS = False

LOG = logging.getLogger("spvx.sea_state.cmems")

DEFAULT_FEATURES: list[dict[str, object]] = [
    {
        "id": "hs",
        "dataset": "waves",
        "type": "scalar",
        "variables": ["VHM0", "hs", "swh", "significant_wave_height"],
        "stats": ["mean", "p95"],
    },
    {
        "id": "sst_anom",
        "dataset": "waves",
        "type": "scalar",
        "variables": ["sst_anom", "thetao_anomaly"],
        "stats": ["mean", "p90"],
    },
    {
        "id": "wind_speed",
        "dataset": "waves",
        "type": "vector_magnitude",
        "variables": ["u10", "v10"],
        "stats": ["p90"],
    },
    {
        "id": "current_speed",
        "dataset": "currents",
        "type": "vector_magnitude",
        "variables": ["uo", "vo"],
        "stats": ["p90"],
    },
    {
        "id": "opp_current",
        "dataset": "currents",
        "type": "opposing",
        "variables": ["uo", "vo"],
        "stats": ["mean"],
    },
]

SUPPORTED_STATS = {"mean", "p90", "p95"}


def _ensure_dir(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _list_days_yyyymmdd(lookback_days: int) -> list[str]:
    today = dt.datetime.now(dt.UTC).date()
    return [(today - dt.timedelta(days=k)).strftime("%Y%m%d") for k in range(lookback_days, -1, -1)]


def _expand_bbox(bbox: dict[str, float], buffer_km: float) -> dict[str, float]:
    if buffer_km <= 0:
        return dict(bbox)
    lat_buffer = buffer_km / 111.0
    lat_mid = (bbox["lat_min"] + bbox["lat_max"]) / 2.0
    lon_denom = max(math.cos(math.radians(lat_mid)), 0.1)
    lon_buffer = buffer_km / (111.0 * lon_denom)
    return {
        "lat_min": bbox["lat_min"] - lat_buffer,
        "lat_max": bbox["lat_max"] + lat_buffer,
        "lon_min": bbox["lon_min"] - lon_buffer,
        "lon_max": bbox["lon_max"] + lon_buffer,
    }


def _normalise_coords(ds: xr.Dataset) -> xr.Dataset:
    rename_map = {}
    if "lat" in ds.coords and "latitude" not in ds.coords:
        rename_map["lat"] = "latitude"
    if "lon" in ds.coords and "longitude" not in ds.coords:
        rename_map["lon"] = "longitude"
    if rename_map:
        ds = ds.rename(rename_map)
    return ds


def _open_dataset(nc_files: list[str]) -> xr.Dataset | None:
    if not nc_files:
        return None
    try:
        ds = xr.open_mfdataset(nc_files, combine="by_coords", engine="netcdf4")
        return _normalise_coords(ds)
    except Exception as exc:  # pragma: no cover - network/io errors
        LOG.warning("[CMEMS] Failed to open dataset: %s", exc)
        return None


def _clip_dataset(ds: xr.Dataset, bbox: dict[str, float]) -> xr.Dataset | None:
    if "latitude" not in ds.coords or "longitude" not in ds.coords:
        LOG.warning("[CMEMS] Dataset missing latitude/longitude coordinates.")
        return None
    try:
        return ds.sel(
            latitude=slice(bbox["lat_min"], bbox["lat_max"]),
            longitude=slice(bbox["lon_min"], bbox["lon_max"]),
        )
    except Exception as exc:  # pragma: no cover - guard clipping failures
        LOG.warning("[CMEMS] Failed to clip dataset: %s", exc)
        return None


def _select_first_variable(ds: xr.Dataset, candidates: Iterable[str]) -> str | None:
    for name in candidates:
        if name in ds.data_vars:
            return name
    return None


def _spatial_statistic(data: xr.DataArray, stat: str) -> xr.DataArray:
    dims = [dim for dim in ("latitude", "longitude") if dim in data.dims]
    if not dims:
        return data
    if stat == "mean":
        return data.mean(dim=dims, skipna=True)
    if stat.startswith("p"):
        quantile = float(stat[1:]) / 100.0
        q = data.quantile(quantile, dim=dims, skipna=True)
        if "quantile" in q.dims:
            q = q.sel(quantile=quantile, drop=True)
        return q
    raise ValueError(f"Unsupported stat '{stat}'")


def _dataarray_to_frame(data: xr.DataArray, column: str) -> pd.DataFrame:
    frame = data.to_dataframe(name=column).reset_index()
    if "time" in frame.columns:
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame[["time", column]].dropna()


def _vector_magnitude(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    return xr.apply_ufunc(
        np.hypot,
        u,
        v,
        dask="parallelized",
        output_dtypes=[float],
    )


def _opposing_component(u: xr.DataArray, v: xr.DataArray, bearing_deg: float) -> xr.DataArray:
    phi = np.deg2rad(bearing_deg)
    return -(u * np.cos(phi) + v * np.sin(phi))


def extract_region_features(
    waves_files: list[str],
    currents_files: list[str],
    features_cfg: Iterable[dict[str, object]],
    bbox: dict[str, float],
    bearing_deg: float,
    buffer_km: float = 0.0,
) -> pd.DataFrame:
    expanded_bbox = _expand_bbox(bbox, buffer_km)
    ds_cache = {
        "waves": _open_dataset(waves_files),
        "currents": _open_dataset(currents_files),
    }
    outputs: list[pd.DataFrame] = []

    try:
        for feature in features_cfg:
            feature_id = str(feature.get("id", "")).strip()
            if not feature_id:
                continue
            dataset_key = str(feature.get("dataset", "waves"))
            ds = ds_cache.get(dataset_key)
            if ds is None:
                LOG.debug("[CMEMS] Dataset '%s' not available for feature '%s'", dataset_key, feature_id)
                continue
            clipped = _clip_dataset(ds, expanded_bbox)
            if clipped is None:
                continue

            variables = feature.get("variables", [])
            stats = feature.get("stats", ["mean"])
            ftype = feature.get("type", "scalar")

            valid_stats = [stat for stat in stats if stat in SUPPORTED_STATS]
            if not valid_stats:
                LOG.debug("[CMEMS] Feature '%s' has no supported stats (%s)", feature_id, stats)
                continue

            if ftype == "scalar":
                var_name = _select_first_variable(clipped, variables)
                if var_name is None:
                    LOG.debug("[CMEMS] Feature '%s' variables %s not found", feature_id, variables)
                    continue
                data_var = clipped[var_name]
                for stat in valid_stats:
                    stat_da = _spatial_statistic(data_var, stat)
                    outputs.append(_dataarray_to_frame(stat_da, f"{feature_id}_{stat}"))

            elif ftype == "vector_magnitude":
                if len(variables) < 2:
                    LOG.warning("[CMEMS] Feature '%s' requires two variables for vector magnitude", feature_id)
                    continue
                u_name = _select_first_variable(clipped, [variables[0]])
                v_name = _select_first_variable(clipped, [variables[1]])
                if u_name is None or v_name is None:
                    LOG.debug("[CMEMS] Vector variables %s missing for '%s'", variables, feature_id)
                    continue
                speed = _vector_magnitude(clipped[u_name], clipped[v_name])
                for stat in valid_stats:
                    stat_da = _spatial_statistic(speed, stat)
                    outputs.append(_dataarray_to_frame(stat_da, f"{feature_id}_{stat}"))

            elif ftype == "opposing":
                if len(variables) < 2:
                    continue
                u_name = _select_first_variable(clipped, [variables[0]])
                v_name = _select_first_variable(clipped, [variables[1]])
                if u_name is None or v_name is None:
                    continue
                opp = _opposing_component(clipped[u_name], clipped[v_name], bearing_deg)
                opp_mean = _spatial_statistic(opp, "mean")
                outputs.append(_dataarray_to_frame(opp_mean, f"{feature_id}_mean"))

            else:  # pragma: no cover - guard for future extensions
                LOG.warning("[CMEMS] Unknown feature type '%s' for feature '%s'", ftype, feature_id)

    finally:
        for ds in ds_cache.values():
            with contextlib.suppress(Exception):
                if ds is not None:
                    ds.close()

    if not outputs:
        return pd.DataFrame(columns=["time"])

    merged = outputs[0]
    for frame in outputs[1:]:
        merged = merged.merge(frame, on="time", how="outer")
    return merged.sort_values("time").reset_index(drop=True)


def download_waves(
    dataset_id: str,
    out_dir: str,
    day_filters: list[str],
    username: str | None = None,
    password: str | None = None,
) -> list[str]:
    if not HAS_CMEMS:
        raise ImportError("copernicusmarine package not installed. Run: pip install copernicusmarine")

    _ensure_dir(out_dir)

    try:
        meta = copernicusmarine.get(
            dataset_id=dataset_id,
            dry_run=True,
            username=username,
            password=password,
        )
    except Exception as exc:  # pragma: no cover - network error path
        LOG.warning("[CMEMS WAVES] Failed to list files for %s: %s", dataset_id, exc)
        return []

    wanted = [f.file_path for f in meta.files if any(day in str(f.file_path) for day in day_filters)]
    if not wanted:
        LOG.info("[CMEMS WAVES] No files matched date filters")
        return []

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        for fp in wanted:
            tmp.write(str(fp) + "\n")
        file_list_path = tmp.name

    try:
        copernicusmarine.get(
            dataset_id=dataset_id,
            file_list=file_list_path,
            no_directories=True,
            output_directory=out_dir,
            username=username,
            password=password,
        )
    except Exception as exc:  # pragma: no cover
        LOG.error("[CMEMS WAVES] Download failed: %s", exc)
        return []
    finally:
        with contextlib.suppress(Exception):
            os.unlink(file_list_path)

    local_files = [os.path.join(out_dir, os.path.basename(fp)) for fp in wanted]
    return [f for f in local_files if os.path.exists(f)]


def download_currents(
    dataset_id: str,
    out_dir: str,
    day_filters: list[str],
    username: str | None = None,
    password: str | None = None,
) -> list[str]:
    if not HAS_CMEMS:
        raise ImportError("copernicusmarine package not installed. Run: pip install copernicusmarine")

    _ensure_dir(out_dir)

    try:
        meta = copernicusmarine.get(
            dataset_id=dataset_id,
            dry_run=True,
            username=username,
            password=password,
        )
    except Exception as exc:  # pragma: no cover
        LOG.warning("[CMEMS CURRENTS] Failed to list files for %s: %s", dataset_id, exc)
        return []

    wanted = [f.file_path for f in meta.files if any(day in str(f.file_path) for day in day_filters)]
    if not wanted:
        LOG.info("[CMEMS CURRENTS] No files matched date filters")
        return []

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        for fp in wanted:
            tmp.write(str(fp) + "\n")
        file_list_path = tmp.name

    try:
        copernicusmarine.get(
            dataset_id=dataset_id,
            file_list=file_list_path,
            no_directories=True,
            output_directory=out_dir,
            username=username,
            password=password,
        )
    except Exception as exc:  # pragma: no cover
        LOG.error("[CMEMS CURRENTS] Download failed: %s", exc)
        return []
    finally:
        with contextlib.suppress(Exception):
            os.unlink(file_list_path)

    local_files = [os.path.join(out_dir, os.path.basename(fp)) for fp in wanted]
    return [f for f in local_files if os.path.exists(f)]


# Backwards-compatible helpers -------------------------------------------------


def area_mean_waves(nc_files: list[str], bbox: dict[str, float]) -> pd.DataFrame:
    features = extract_region_features(
        waves_files=nc_files,
        currents_files=[],
        features_cfg=[
            {
                "id": "hs",
                "dataset": "waves",
                "type": "scalar",
                "variables": ["VHM0", "hs", "swh", "significant_wave_height"],
                "stats": ["mean"],
            }
        ],
        bbox=bbox,
        bearing_deg=0.0,
    )
    if features.empty or "hs_mean" not in features.columns:
        return pd.DataFrame(columns=["time", "hs"])
    return features.rename(columns={"hs_mean": "hs"})[["time", "hs"]]


def area_mean_opp_current(
    nc_files: list[str],
    bbox: dict[str, float],
    bearing_deg: float,
) -> pd.DataFrame:
    features = extract_region_features(
        waves_files=[],
        currents_files=nc_files,
        features_cfg=[
            {
                "id": "opp_current",
                "dataset": "currents",
                "type": "opposing",
                "variables": ["uo", "vo"],
                "stats": ["mean"],
            }
        ],
        bbox=bbox,
        bearing_deg=bearing_deg,
    )
    if features.empty or "opp_current_mean" not in features.columns:
        return pd.DataFrame(columns=["time", "opp_current"])
    return features.rename(columns={"opp_current_mean": "opp_current"})[["time", "opp_current"]]


__all__ = [
    "DEFAULT_FEATURES",
    "SUPPORTED_STATS",
    "_list_days_yyyymmdd",
    "download_waves",
    "download_currents",
    "extract_region_features",
    "area_mean_waves",
    "area_mean_opp_current",
]
