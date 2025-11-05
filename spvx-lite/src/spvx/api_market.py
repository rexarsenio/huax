"""
Market context API endpoints (oil prices).
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Sequence

import duckdb
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/market", tags=["market"])

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")


def _parse_series(series: str) -> list[str]:
    tokens = [token.strip() for token in series.split(",")]
    return [token for token in tokens if token]


def _parse_range(range_token: str) -> int:
    token = range_token.strip().lower()
    if token.endswith("d"):
        token = token[:-1]
    days = int(token)
    if days <= 0:
        raise ValueError("range must be > 0")
    return days


@router.get("/oil")
def get_oil(series: str = "RBRTE,RWTC", range: str = "180d"):
    series_list = _parse_series(series)
    if not series_list:
        raise HTTPException(status_code=400, detail="series parameter required")
    try:
        days = _parse_range(range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    since_date = (dt.date.today() - dt.timedelta(days=days)).isoformat()

    placeholders = ",".join("?" for _ in series_list)
    query = f"""
        SELECT ds, series, value
        FROM oil_daily
        WHERE ds >= ? AND series IN ({placeholders})
        ORDER BY ds, series
    """

    with duckdb.connect(DUCKDB_PATH, read_only=True) as con:
        rows = con.execute(query, [since_date, *series_list]).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="no market data")

    points: dict[str, list[dict[str, float | str]]] = {sid: [] for sid in series_list}
    latest: dict[str, dict[str, float | str] | None] = {sid: None for sid in series_list}

    for ds, sid, value in rows:
        record = {"ds": ds.isoformat() if hasattr(ds, "isoformat") else str(ds), "value": float(value)}
        points.setdefault(sid, []).append(record)
        latest[sid] = record

    series_payload = [{"id": sid, "points": points.get(sid, [])} for sid in series_list]
    return {"series": series_payload, "latest": latest}


__all__ = ["router"]
