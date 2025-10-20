"""
NxtPort PortStays ingestion (UAT/PRD) with token caching and DuckDB persistence.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import duckdb
import requests
from dotenv import load_dotenv

from spvx.db import ensure_core_tables

LOG = logging.getLogger("spvx.portstays")

DEFAULT_TOKEN_URL = "https://login-uat.nxtport.com/connect/token"
DEFAULT_API_BASE = "https://api-uat.nxtport.com/portstays/v1"
DEFAULT_USER_AGENT = "spvx-lite-portstays/0.1 (+https://huax.ai)"

load_dotenv()


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _parse_iso(ts: str | None) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        token = ts.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(token)
    except ValueError:
        return None


def _slugify(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    token = name.strip().lower()
    for old, new in (("&", " and "), ("/", " "), ("-", " "), (".", " ")):
        token = token.replace(old, new)
    return "_".join(part for part in token.split() if part)


def _is_tanker(vessel_type: Optional[str]) -> bool:
    if not vessel_type:
        return False
    token = vessel_type.lower()
    return any(keyword in token for keyword in ("tank", "oil", "product", "chem"))


def _iter_stays(payload: object) -> Iterator[dict]:
    if isinstance(payload, dict):
        if isinstance(payload.get("stays"), list):
            yield from payload["stays"]  # type: ignore[index]
            return
        if isinstance(payload.get("items"), list):
            yield from payload["items"]  # type: ignore[index]
            return
    if isinstance(payload, list):
        yield from payload  # type: ignore[misc]


@dataclass
class PortStaySummary:
    date: dt.date
    port_code: str
    port_name: str
    depart: int = 0
    arrive: int = 0


def summarise_tanker_activity(payload: object) -> List[PortStaySummary]:
    counters: Dict[Tuple[str, dt.date], PortStaySummary] = {}
    for entry in _iter_stays(payload):
        if not isinstance(entry, dict):
            continue
        vessel = entry.get("vessel") or entry.get("ship") or entry
        vessel_type = (
            vessel.get("vesselType")
            or vessel.get("type")
            or vessel.get("ship_type")
            or entry.get("vessel_type")
            or entry.get("ship_type")
        )
        if not _is_tanker(vessel_type or ""):
            continue

        port_block = entry.get("port") or entry.get("portStay") or {}
        port_name = (
            port_block.get("name")
            or port_block.get("portName")
            or entry.get("portName")
            or entry.get("port")
        )
        port_code = (
            port_block.get("code")
            or port_block.get("portCode")
            or entry.get("portCode")
        )

        berth_identifier = entry.get("berth_at_arrival") or entry.get("berth_at_departure")
        if not port_name:
            if berth_identifier and berth_identifier.upper().startswith("BEANR"):
                port_name = "Antwerp"
            elif berth_identifier and berth_identifier.upper().startswith("BEZEE"):
                port_name = "Zeebrugge"
        if not port_code and port_name:
            port_code = port_name
        if not port_code and berth_identifier:
            port_code = berth_identifier
        if not port_code:
            port_code = "antwerp"

        port_code = _slugify(port_code or port_name)
        port_name = (port_name or port_code).strip()

        if not port_code:
            continue

        atd = entry.get("atd") or entry.get("actualDeparture") or entry.get("actualTimeOfDeparture")
        ata = entry.get("ata") or entry.get("actualArrival") or entry.get("actualTimeOfArrival")
        etd = entry.get("etd")
        stay_start = entry.get("stay_start")

        if atd:
            ts = _parse_iso(atd)
            if ts:
                key = (port_code, ts.date())
                summary = counters.setdefault(key, PortStaySummary(ts.date(), port_code, port_name))
                summary.depart += 1

        if etd:
            ts = _parse_iso(etd)
            if ts:
                key = (port_code, ts.date())
                summary = counters.setdefault(key, PortStaySummary(ts.date(), port_code, port_name))
                summary.depart += 1

        if ata:
            ts = _parse_iso(ata)
            if ts:
                key = (port_code, ts.date())
                summary = counters.setdefault(key, PortStaySummary(ts.date(), port_code, port_name))
                summary.arrive += 1
        elif stay_start:
            ts = _parse_iso(stay_start)
            if ts:
                key = (port_code, ts.date())
                summary = counters.setdefault(key, PortStaySummary(ts.date(), port_code, port_name))
                summary.arrive += 1

    return list(counters.values())


@dataclass
class PortStaysCredentials:
    subscription_key: str
    client_id: str
    client_secret: str
    scope: Optional[str]
    username: Optional[str]
    password: Optional[str]
    grant_type: str
    token_url: str
    api_base: str
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_env(cls) -> "PortStaysCredentials | None":
        subs = os.getenv("NXTPORT_SUBSCRIPTION_KEY")
        cid = os.getenv("NXTPORT_CLIENT_ID")
        secret = os.getenv("NXTPORT_CLIENT_SECRET")
        if not subs or not cid or not secret:
            return None
        username = os.getenv("NXTPORT_USERNAME")
        password = os.getenv("NXTPORT_PASSWORD")
        grant_type = os.getenv("NXTPORT_GRANT_TYPE")
        if not grant_type:
            grant_type = "password" if username and password else "client_credentials"
        return cls(
            subscription_key=subs,
            client_id=cid,
            client_secret=secret,
            scope=os.getenv("NXTPORT_SCOPE"),
            username=username,
            password=password,
            grant_type=grant_type,
            token_url=os.getenv("NXTPORT_TOKEN_URL", DEFAULT_TOKEN_URL),
            api_base=os.getenv("NXTPORT_API_BASE", DEFAULT_API_BASE),
            user_agent=os.getenv("NXTPORT_USER_AGENT", DEFAULT_USER_AGENT),
        )


class PortStaysClient:
    def __init__(self, creds: PortStaysCredentials, session: Optional[requests.Session] = None):
        self.creds = creds
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _ensure_token(self) -> str:
        if self._token and self._token_expiry - time.time() > 120:
            return self._token
        data = {
            "grant_type": self.creds.grant_type,
            "client_id": self.creds.client_id,
            "client_secret": self.creds.client_secret,
        }
        if self.creds.scope:
            data["scope"] = self.creds.scope
        if self.creds.grant_type == "password":
            if not self.creds.username or not self.creds.password:
                raise RuntimeError("Password grant selected but NXTPORT_USERNAME/PASSWORD not provided.")
            data["username"] = self.creds.username
            data["password"] = self.creds.password
        response = self.session.post(
            self.creds.token_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.creds.user_agent,
            },
            data=data,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("PortStays token response missing access_token")
        ttl = int(payload.get("expires_in", 3600))
        self._token = token
        self._token_expiry = time.time() + max(ttl - 120, 60)
        LOG.debug("Fetched new PortStays token (expires in %s seconds)", ttl)
        return token

    def fetch_stays(self, iso_dt: str) -> object:
        token = self._ensure_token()
        url = f"{self.creds.api_base}/stays"
        headers = {
            "Authorization": f"Bearer {token}",
            "Ocp-Apim-Subscription-Key": self.creds.subscription_key,
            "User-Agent": self.creds.user_agent,
        }
        params = {"date": iso_dt}
        response = self.session.get(url, params=params, headers=headers, timeout=30)
        if response.status_code in (429, 500, 502, 503, 504):
            wait_seconds = 3 if response.status_code == 429 else 5
            LOG.warning(
                "PortStays request returned %s; retrying after %ss",
                response.status_code,
                wait_seconds,
            )
            time.sleep(wait_seconds)
            response = self.session.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()


def _snapshot_rows(
    summaries: Iterable[PortStaySummary],
    snapshot_ts: dt.datetime,
    source: str = "portstays_uat",
) -> List[Tuple[dt.date, str, str, int, int, str, dt.datetime]]:
    rows: List[Tuple[dt.date, str, str, int, int, str, dt.datetime]] = []
    for summary in summaries:
        rows.append(
            (
                summary.date,
                summary.port_code,
                summary.port_name,
                summary.depart,
                summary.arrive,
                source,
                snapshot_ts,
            )
        )
    return rows


def _write_to_duckdb(
    con: duckdb.DuckDBPyConnection,
    *,
    request_date: dt.datetime,
    snapshot_ts: dt.datetime,
    payload: object,
    summaries: Iterable[PortStaySummary],
    source: str = "portstays_uat",
) -> None:
    ensure_core_tables(con)
    con.execute(
        """
        INSERT INTO portstays_snapshots (snapshot_ts, request_date, payload)
        VALUES (?, ?, ?)
        ON CONFLICT (snapshot_ts, request_date) DO UPDATE SET payload = excluded.payload
        """,
        [snapshot_ts, request_date, json.dumps(payload)],
    )
    rows = _snapshot_rows(summaries, snapshot_ts, source=source)
    if not rows:
        LOG.info("PortStays snapshot produced 0 tanker movements.")
        return
    con.executemany(
        """
        INSERT INTO portstays_daily (
            d,
            port_code,
            port_name,
            tanker_departures,
            tanker_arrivals,
            source,
            snapshot_ts
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (d, port_code, source) DO UPDATE SET
            tanker_departures = excluded.tanker_departures,
            tanker_arrivals = excluded.tanker_arrivals,
            snapshot_ts = excluded.snapshot_ts
        """,
        rows,
    )
    LOG.info("PortStays upserted %s daily rows.", len(rows))


def run(iso_datetime: Optional[str] = None) -> Optional[int]:
    """
    Fetch a PortStays snapshot for the requested ISO timestamp (UTC) and persist to DuckDB.

    Returns the number of aggregated rows written, or None if credentials are missing.
    """
    creds = PortStaysCredentials.from_env()
    if creds is None:
        LOG.info("NXTPORT credentials not configured; skipping PortStays ingestion.")
        return None

    target_ts = iso_datetime or _now_utc().isoformat().replace("+00:00", "Z")
    request_dt = _parse_iso(target_ts)
    if request_dt is None:
        raise ValueError(f"Invalid ISO datetime for PortStays request: {target_ts}")

    client = PortStaysClient(creds)
    payload = client.fetch_stays(target_ts)
    summaries = summarise_tanker_activity(payload)

    settings_path = os.getenv("DUCKDB_PATH", "db/spvx.duckdb")
    con = duckdb.connect(settings_path)
    try:
        snapshot_ts = _now_utc()
        _write_to_duckdb(
            con,
            request_date=request_dt,
            snapshot_ts=snapshot_ts,
            payload=payload,
            summaries=summaries,
            source="portstays_uat" if "uat" in creds.api_base.lower() else "portstays",
        )
    finally:
        con.close()

    return len(summaries)
