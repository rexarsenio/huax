"""
Market data ingestion (EIA/FRED oil prices).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

import duckdb
import requests
from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()

EIA_BASE = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES_MAP: dict[str, dict[str, str]] = {
    "RBRTE": {"fred": "DCOILBRENTEU"},  # Brent
    "RWTC": {"fred": "DCOILWTICO"},  # WTI
}


@dataclass(slots=True)
class OilRow:
    ds: str
    series: str
    value: float
    source: str


def ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS oil_daily (
            ds DATE NOT NULL,
            series TEXT NOT NULL,
            value DOUBLE,
            source TEXT,
            PRIMARY KEY (ds, series)
        )
        """
    )


def _insert_oil(con: duckdb.DuckDBPyConnection, rows: Iterable[OilRow]) -> int:
    batch = [(r.ds, r.series, r.value, r.source) for r in rows]
    if not batch:
        return 0
    con.executemany(
        "INSERT OR REPLACE INTO oil_daily (ds, series, value, source) VALUES (?, ?, ?, ?)",
        batch,
    )
    return len(batch)


def fetch_eia(series: Sequence[str], since_days: int = 365) -> list[OilRow]:
    key = os.getenv("EIA_API_KEY")
    if not key:
        raise RuntimeError("EIA_API_KEY missing")

    start = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    params: dict[str, object] = {
        "api_key": key,
        "start": start,
        "frequency": "daily",
        "data[0]": "value",
    }

    # Build multi-value parameter for series facets
    series_params = [(f"facets[series][]", s) for s in series]

    response = requests.get(EIA_BASE, params={**params, **dict(series_params)}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or []

    rows: list[OilRow] = []
    for entry in data:
        ds = entry.get("period")
        sid = entry.get("series")
        value = entry.get("value")
        if not ds or not sid or value in (None, "", "."):
            continue
        try:
            rows.append(OilRow(ds=str(ds), series=str(sid), value=float(value), source="EIA"))
        except (TypeError, ValueError):
            continue
    return rows


def fetch_fred(series_map: dict[str, str], since_days: int = 365) -> list[OilRow]:
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY missing")

    start = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    rows: list[OilRow] = []

    for target_series, fred_id in series_map.items():
        params = {
            "series_id": fred_id,
            "api_key": key,
            "file_type": "json",
            "observation_start": start,
        }
        response = requests.get(FRED_BASE, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        observations = payload.get("observations") or []
        for obs in observations:
            value = obs.get("value")
            if value in (None, "", "."):
                continue
            date_token = obs.get("date")
            if not date_token:
                continue
            try:
                rows.append(OilRow(ds=str(date_token), series=target_series, value=float(value), source="FRED"))
            except (TypeError, ValueError):
                continue
    return rows


def ingest_oil(
    con: duckdb.DuckDBPyConnection,
    *,
    since_days: int = 365,
    use_mock: bool = False,
) -> int:
    ensure_tables(con)

    if use_mock:
        base = dt.date.today() - dt.timedelta(days=180)
        rows: list[OilRow] = []
        for offset in range(180):
            ds = (base + dt.timedelta(days=offset)).isoformat()
            rows.append(OilRow(ds=ds, series="RBRTE", value=70.0 + 0.02 * offset, source="MOCK"))
            rows.append(OilRow(ds=ds, series="RWTC", value=65.0 + 0.01 * offset, source="MOCK"))
        return _insert_oil(con, rows)

    # Use FRED as primary source (more reliable, free API)
    # Fall back to EIA if FRED fails
    rows: list[OilRow]
    try:
        rows = fetch_fred({sid: mapping["fred"] for sid, mapping in SERIES_MAP.items()}, since_days)
    except Exception as e:
        print(f"FRED fetch failed: {e}, trying EIA...")
        rows = fetch_eia(["RBRTE", "RWTC"], since_days)

    return _insert_oil(con, rows)


__all__ = ["ingest_oil", "ensure_tables"]
