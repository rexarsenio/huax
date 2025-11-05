"""
Live ingestion for the Maritime and Port Authority of Singapore vessel movements.

The API typically exposes REST endpoints with an API key header. We keep the
collector resilient to different payload shapes and only extract the signal we
need downstream: tanker movements per timestamp.

Environment variables:
    MPA_API_BASE          Base URL of the movements API (required)
    MPA_API_KEY           API key for X-API-Key header (required)
    MPA_USER_AGENT        Optional user-agent override
    MPA_PAGE_SIZE         Page size for pagination (default: 500)
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

import duckdb
import pandas as pd
import requests

from spvx.config import AppSettings
from spvx.db import ensure_core_tables

LOG = logging.getLogger("spvx.mpa")

DEFAULT_API_BASE = "https://api.mpa.gov.sg/vessels/v1"
DEFAULT_USER_AGENT = "spvx-lite-mpa/0.1 (+https://huax.ai)"
DEFAULT_PAGE_SIZE = int(os.getenv("MPA_PAGE_SIZE", "500") or 500)


def _parse_iso(value: object) -> Optional[dt.datetime]:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return None
        token = token.replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(token)
        except ValueError:
            pass
    return None


def _is_tanker(vessel_type: Optional[str]) -> bool:
    if not vessel_type:
        return False
    token = vessel_type.lower()
    return any(fragment in token for fragment in ("tank", "oil", "chem", "product"))


def _normalise_move(entry: dict) -> Optional[dict[str, object]]:
    ts = (
        _parse_iso(entry.get("ts"))
        or _parse_iso(entry.get("timestamp"))
        or _parse_iso(entry.get("eventTime"))
        or _parse_iso(entry.get("reportedAt"))
    )
    if ts is None:
        return None

    movement = (
        entry.get("movement")
        or entry.get("event")
        or entry.get("direction")
        or entry.get("status")
        or "unknown"
    )
    movement = str(movement).strip().lower()
    vessel_type = entry.get("vesselType") or entry.get("shipType") or entry.get("category")
    vessels = entry.get("vessels") or entry.get("count") or entry.get("value") or 1
    try:
        vessels_int = int(vessels)
    except (TypeError, ValueError):
        vessels_int = 1

    return {
        "ts": ts.replace(tzinfo=None),
        "vessel_type": (vessel_type or "unknown").strip().lower(),
        "movement": movement,
        "vessels": vessels_int,
    }


def _extract_items(payload: object) -> Iterable[dict]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "entries", "records"):
            block = payload.get(key)
            if isinstance(block, list):
                for item in block:
                    if isinstance(item, dict):
                        yield item
                return
        if all(isinstance(v, dict) for v in payload.values()):
            for item in payload.values():
                if isinstance(item, dict):
                    yield item


@dataclass
class MPACredentials:
    api_base: str
    api_key: str
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_env(cls) -> Optional["MPACredentials"]:
        api_key = os.getenv("MPA_API_KEY")
        api_base = os.getenv("MPA_API_BASE", DEFAULT_API_BASE)
        if not api_key:
            LOG.warning("MPA API key missing; set MPA_API_KEY to enable live ingestion.")
            return None
        return cls(api_base=api_base.rstrip("/"), api_key=api_key, user_agent=os.getenv("MPA_USER_AGENT", DEFAULT_USER_AGENT))


class MPAClient:
    def __init__(self, creds: MPACredentials, session: Optional[requests.Session] = None):
        self.creds = creds
        self.session = session or requests.Session()

    def fetch_moves(self, start: dt.datetime, end: dt.datetime, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[dict]:
        params = {
            "start": start.isoformat(timespec="seconds"),
            "end": end.isoformat(timespec="seconds"),
            "limit": page_size,
        }
        headers = {
            "X-API-Key": self.creds.api_key,
            "User-Agent": self.creds.user_agent,
        }
        base_url = f"{self.creds.api_base}/movements"
        next_url: Optional[str] = None
        while True:
            url = next_url or base_url
            resp = self.session.get(url, params=None if next_url else params, headers=headers, timeout=30)
            if resp.status_code >= 400:
                raise RuntimeError(f"MPA API error ({resp.status_code}): {resp.text}")
            payload = resp.json()
            items = list(_extract_items(payload))
            LOG.debug("MPA fetched %s items from %s", len(items), url)
            for item in items:
                normalised = _normalise_move(item)
                if normalised and _is_tanker(normalised.get("vessel_type")):
                    yield normalised

            next_url = None
            if isinstance(payload, dict):
                links = payload.get("links")
                if isinstance(links, dict):
                    nxt = links.get("next") or links.get("Next")
                    if isinstance(nxt, str) and nxt:
                        next_url = nxt
            if next_url:
                continue
            if len(items) < page_size:
                break
            params["offset"] = params.get("offset", 0) + page_size


def _connect_db() -> duckdb.DuckDBPyConnection:
    settings = AppSettings()
    path = Path(settings.duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    ensure_core_tables(con)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS mpa_moves (
            ts TIMESTAMP,
            vessel_type TEXT,
            movement TEXT,
            vessels INTEGER,
            PRIMARY KEY (ts, vessel_type, movement)
        )
        """
    )
    return con


def _upsert_moves(con: duckdb.DuckDBPyConnection, rows: Iterable[dict[str, object]]) -> int:
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df = df.sort_values("ts")
    con.register("mpa_moves_ingest", df)
    con.execute(
        """
        INSERT INTO mpa_moves AS tgt
        SELECT ts, vessel_type, movement, vessels
        FROM mpa_moves_ingest
        ON CONFLICT (ts, vessel_type, movement) DO UPDATE SET
            vessels = EXCLUDED.vessels
        """
    )
    con.unregister("mpa_moves_ingest")
    return len(df)


def run(*, days: int = 400) -> int:
    """
    Fetch tanker movements from the MPA API and persist them into DuckDB.
    Returns the number of upserted rows.
    """
    creds = MPACredentials.from_env()
    if creds is None:
        raise RuntimeError("MPA credentials missing; set MPA_API_KEY/MPA_API_BASE.")

    end = dt.datetime.utcnow().replace(microsecond=0)
    start = end - dt.timedelta(days=days)

    client = MPAClient(creds)
    rows = list(client.fetch_moves(start, end))
    if not rows:
        LOG.warning("MPA API returned no tanker movements for %s days.", days)
        return 0

    con = _connect_db()
    try:
        con.execute("BEGIN")
        try:
            count = _upsert_moves(con, rows)
            cutoff = start - dt.timedelta(days=5)
            con.execute("DELETE FROM mpa_moves WHERE ts < ?", [cutoff])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()

    LOG.info("Persisted %s MPA movement rows (%s → %s).", count, rows[0]["ts"], rows[-1]["ts"])
    return count


__all__ = ["run", "MPAClient", "MPACredentials"]
