"""
FastAPI router exposing consolidated latest index metrics for the dashboard hero.
"""

from __future__ import annotations

import datetime as dt
import math
from copy import deepcopy
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Tuple

import duckdb
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status

from spvx.analytics.relative_stress import compute_relative_stress
from spvx.config import AppSettings

router = APIRouter(prefix="/api/index", tags=["index"])

_CACHE_TTL_SECONDS = 60.0
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _connect() -> duckdb.DuckDBPyConnection:
    """
    Prefer an API snapshot database if available to avoid locking the primary DuckDB.
    """
    settings = AppSettings()
    db_path = Path(settings.duckdb_path)
    api_db_path = db_path.parent / "spvx_api.duckdb"
    if api_db_path.exists():
        return duckdb.connect(str(api_db_path), read_only=True)
    return duckdb.connect(str(db_path), read_only=True)


def _clean_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _percentile_of_score(window: np.ndarray, value: float) -> float | None:
    finite = window[np.isfinite(window)]
    if finite.size == 0:
        return None
    less = np.sum(finite < value)
    equal = np.sum(np.isclose(finite, value))
    percentile = ((less + 0.5 * equal) / finite.size) * 100.0
    return float(percentile)


def _build_snapshot(scope: str) -> Dict[str, Any]:
    scope_normalised = scope.lower()
    if scope_normalised != "global":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "invalid_scope", "scope": scope},
        )

    try:
        with _connect() as con:
            df = con.execute(
                """
                SELECT d, spvx_global
                FROM spvx_global_daily
                WHERE spvx_global IS NOT NULL
                ORDER BY d
                """
            ).df()
    except Exception as e:
        # Handle case where table doesn't exist (data collection in progress)
        if "does not exist" in str(e) or "Catalog Error" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "unavailable", "reason": "table_not_ready"},
            )
        raise

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "reason": "no_index_data"},
        )

    df["d"] = pd.to_datetime(df["d"])
    df = df.sort_values("d").reset_index(drop=True)
    df = df.dropna(subset=["spvx_global"])
    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "reason": "no_index_data"},
        )

    latest_row = df.iloc[-1]
    latest_ts = pd.Timestamp(latest_row["d"]).to_pydatetime()
    latest_value = _clean_number(latest_row["spvx_global"])

    if latest_value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "reason": "latest_value_missing"},
        )

    delta_points = None
    delta_pct = None
    if len(df) >= 2:
        prev_value = _clean_number(df.iloc[-2]["spvx_global"])
        if prev_value is not None:
            delta_points = latest_value - prev_value
            if prev_value != 0:
                delta_pct = (delta_points / prev_value) * 100.0

    frame = df.rename(columns={"d": "date", "spvx_global": "value"})
    result, enriched = compute_relative_stress(frame, value_col="value", date_col="date", lookback_days=365)

    seasonal_mean = _clean_number(getattr(result, "seasonal_mean", None)) if result else None
    deviation_pct = _clean_number(getattr(result, "deviation_pct", None)) if result else None
    zscore = _clean_number(getattr(result, "z_score", None)) if result else None
    classification = result.classification.to_dict() if result else None

    percentile_70d = None
    if not enriched.empty:
        values = enriched["value"].astype(float).to_numpy()
        window = min(70, values.size)
        if window > 0:
            window_values = values[-window:]
            percentile_70d = _clean_number(_percentile_of_score(window_values, window_values[-1]))

    payload: Dict[str, Any] = {
        "scope": scope_normalised,
        "ts": latest_ts,
        "spvx": latest_value,
        "seasonal_baseline": seasonal_mean,
        "deviation_pct": deviation_pct,
        "zscore": zscore,
        "percentile_70d": percentile_70d,
        "delta_day_points": _clean_number(delta_points),
        "delta_day_pct": _clean_number(delta_pct),
    }

    if classification:
        payload["classification"] = classification

    return payload


def _get_snapshot(scope: str) -> Dict[str, Any]:
    now = monotonic()
    cached = _CACHE.get(scope)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return deepcopy(cached[1])

    snapshot = _build_snapshot(scope)
    _CACHE[scope] = (now, deepcopy(snapshot))
    return snapshot


@router.get("/latest")
def latest_index(scope: str = Query("global", min_length=1)) -> Dict[str, Any]:
    """
    Return the latest SPVX index snapshot for the requested scope.
    """
    snapshot = _get_snapshot(scope.lower())
    payload = deepcopy(snapshot)
    ts = payload.get("ts")
    if isinstance(ts, (dt.datetime, pd.Timestamp)):
        payload["ts"] = pd.Timestamp(ts).to_pydatetime().isoformat()
    return payload
