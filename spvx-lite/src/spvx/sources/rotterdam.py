"""
Live ingestion for Port of Rotterdam vessel call statistics.

The production API requires either an API key header or OAuth2 client credentials.
We keep the client deliberately defensive: anything that looks like a call record
is normalised into the minimal structure the rest of the pipeline expects.

Environment variables (all optional unless noted):
    ROTTERDAM_API_BASE        Base URL for the calls API
    ROTTERDAM_TOKEN_URL       OAuth2 token endpoint (if using client credentials)
    ROTTERDAM_CLIENT_ID       OAuth2 client id
    ROTTERDAM_CLIENT_SECRET   OAuth2 client secret
    ROTTERDAM_SCOPE           Optional OAuth2 scope value
    ROTTERDAM_API_KEY         Subscription key header (Ocp-Apim-Subscription-Key)
    ROTTERDAM_USER_AGENT      HTTP user-agent header
    ROTTERDAM_PAGE_SIZE       Override page size (default: 500)
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

LOG = logging.getLogger("spvx.rotterdam")

DEFAULT_API_BASE = "https://api.portofrotterdam.com/calls/v1"
DEFAULT_TOKEN_URL = "https://identity.portofrotterdam.com/connect/token"
DEFAULT_USER_AGENT = "spvx-lite-rotterdam/0.1 (+https://huax.ai)"
DEFAULT_PAGE_SIZE = int(os.getenv("ROTTERDAM_PAGE_SIZE", "500") or 500)


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


def _normalise_event(payload: dict) -> Optional[dict[str, object]]:
    ts = (
        _parse_iso(payload.get("eventTime"))
        or _parse_iso(payload.get("reportedAt"))
        or _parse_iso(payload.get("timestamp"))
        or _parse_iso(payload.get("ts"))
    )
    if ts is None:
        return None

    event = (
        (payload.get("event") or payload.get("eventType") or payload.get("type") or "unknown")
        .strip()
        .lower()
    )
    vessels = payload.get("vessels") or payload.get("shipCount") or payload.get("count") or payload.get("value")
    try:
        vessels_int = int(vessels)
    except (TypeError, ValueError):
        vessels_int = 1

    cargo_type = (
        str(payload.get("cargoType") or payload.get("segment") or payload.get("tankerFlag") or "")
        .strip()
        .lower()
    )
    ship_type = str(payload.get("shipType") or payload.get("vesselType") or "").strip().lower()
    is_tanker = "tank" in cargo_type or "tank" in ship_type or payload.get("is_tanker") is True

    return {
        "ts": ts.replace(tzinfo=None),
        "event": event,
        "vessels": vessels_int,
        "is_tanker": bool(is_tanker),
    }


def _extract_items(payload: object) -> Iterable[dict]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "entries", "calls"):
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
class RotterdamCredentials:
    api_base: str = DEFAULT_API_BASE
    token_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None
    api_key: Optional[str] = None
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_env(cls) -> Optional["RotterdamCredentials"]:
        api_base = os.getenv("ROTTERDAM_API_BASE", DEFAULT_API_BASE)
        token_url = os.getenv("ROTTERDAM_TOKEN_URL", DEFAULT_TOKEN_URL)
        client_id = os.getenv("ROTTERDAM_CLIENT_ID")
        client_secret = os.getenv("ROTTERDAM_CLIENT_SECRET")
        scope = os.getenv("ROTTERDAM_SCOPE")
        api_key = os.getenv("ROTTERDAM_API_KEY")
        if not api_key and not (client_id and client_secret):
            LOG.warning(
                "Rotterdam credentials missing (ROTTERDAM_API_KEY or client credentials required)."
            )
            return None
        return cls(
            api_base=api_base.rstrip("/"),
            token_url=token_url if client_id and client_secret else None,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            api_key=api_key,
            user_agent=os.getenv("ROTTERDAM_USER_AGENT", DEFAULT_USER_AGENT),
        )


class RotterdamClient:
    def __init__(self, creds: RotterdamCredentials, session: Optional[requests.Session] = None):
        self.creds = creds
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": self.creds.user_agent}
        if self.creds.api_key:
            headers["Ocp-Apim-Subscription-Key"] = self.creds.api_key
        if self.creds.client_id and self.creds.client_secret and self.creds.token_url:
            token = self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _ensure_token(self) -> str:
        now = dt.datetime.utcnow().timestamp()
        if self._token and self._token_expiry - now > 60:
            return self._token
        data = {
            "grant_type": "client_credentials",
            "client_id": self.creds.client_id,
            "client_secret": self.creds.client_secret,
        }
        if self.creds.scope:
            data["scope"] = self.creds.scope
        response = self.session.post(self.creds.token_url, data=data, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Rotterdam token request failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Rotterdam token response missing 'access_token'.")
        expires_in = int(payload.get("expires_in") or 1200)
        self._token = token
        self._token_expiry = now + expires_in
        return token

    def fetch_calls(self, start: dt.datetime, end: dt.datetime, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[dict]:
        params = {
            "from": start.isoformat(timespec="seconds"),
            "to": end.isoformat(timespec="seconds"),
            "limit": page_size,
        }
        url = f"{self.creds.api_base}/calls"
        headers = self._auth_headers()
        next_url: Optional[str] = None
        while True:
            request_url = next_url or url
            response = self.session.get(request_url, params=None if next_url else params, headers=headers, timeout=30)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Rotterdam API error ({response.status_code}): {response.text}"
                )
            payload = response.json()
            items = list(_extract_items(payload))
            LOG.debug("Rotterdam fetched %s items from %s", len(items), request_url)
            for item in items:
                normalised = _normalise_event(item)
                if normalised:
                    yield normalised

            links = payload.get("links") if isinstance(payload, dict) else None
            next_url = None
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
        CREATE TABLE IF NOT EXISTS rotterdam_calls (
            ts TIMESTAMP,
            event TEXT,
            vessels INTEGER,
            is_tanker BOOLEAN,
            PRIMARY KEY (ts, event)
        )
        """
    )
    return con


def _upsert_calls(con: duckdb.DuckDBPyConnection, rows: Iterable[dict[str, object]]) -> int:
    df = pd.DataFrame(rows)
    if df.empty:
        return 0
    df = df.sort_values("ts")
    con.register("rotterdam_calls_ingest", df)
    con.execute(
        """
        INSERT INTO rotterdam_calls AS tgt
        SELECT ts, event, vessels, is_tanker
        FROM rotterdam_calls_ingest
        ON CONFLICT (ts, event) DO UPDATE SET
            vessels = EXCLUDED.vessels,
            is_tanker = EXCLUDED.is_tanker
        """
    )
    con.unregister("rotterdam_calls_ingest")
    return len(df)


def run(*, days: int = 400) -> int:
    """
    Pull vessel call events from the Rotterdam API and persist them in DuckDB.
    Returns the number of upserted rows.
    """
    creds = RotterdamCredentials.from_env()
    if creds is None:
        raise RuntimeError("Rotterdam credentials missing; check ROTTERDAM_* environment variables.")

    end = dt.datetime.utcnow().replace(microsecond=0)
    start = end - dt.timedelta(days=days)

    client = RotterdamClient(creds)
    rows = list(client.fetch_calls(start, end))
    if not rows:
        LOG.warning("Rotterdam API returned no call records for %s days.", days)
        return 0

    con = _connect_db()
    try:
        con.execute("BEGIN")
        try:
            count = _upsert_calls(con, rows)
            cutoff = start - dt.timedelta(days=5)
            con.execute("DELETE FROM rotterdam_calls WHERE ts < ?", [cutoff])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()

    LOG.info("Persisted %s Rotterdam call rows (%s → %s).", count, rows[0]["ts"], rows[-1]["ts"])
    return count


__all__ = ["run", "RotterdamClient", "RotterdamCredentials"]
