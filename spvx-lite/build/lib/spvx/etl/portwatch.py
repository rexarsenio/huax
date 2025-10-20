"""
PortWatch (ArcGIS) ETL helpers.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

import duckdb
import requests

from spvx.db import ensure_core_tables

LOG = logging.getLogger(__name__)

BASE_URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Trade_Data/FeatureServer/0/query"


@dataclass(frozen=True)
class PortWatchRow:
    date: dt.date
    portname: str
    iso3: str
    movements: Optional[float]
    departures: Optional[float] = None
    arrivals: Optional[float] = None
    shiptype: str = "tanker"
    source: str = "portwatch"

    @property
    def port_code(self) -> str:
        return slugify(self.portname)


def slugify(name: str) -> str:
    token = name.strip().lower()
    replacements = {
        "&": " and ",
        "/": " ",
        "-": " ",
        ".": " ",
    }
    for old, new in replacements.items():
        token = token.replace(old, new)
    return "_".join(t for t in token.split() if t)


def fetch_portwatch_daily(
    *,
    iso3: str,
    port_like: str,
    fields: Sequence[str] | None = None,
    order: str = "date ASC",
    timeout: int = 30,
) -> List[PortWatchRow]:
    params = {
        "where": f"ISO3='{iso3}' AND UPPER(portname) LIKE '%{port_like.upper()}%'",
        "outFields": ",".join(fields or ["date", "portname", "portcalls_tanker", "export_tanker", "import_tanker"]),
        "orderByFields": order,
        "f": "json",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        LOG.warning("PortWatch fetch failed for %s/%s: %s", iso3, port_like, exc)
        return []

    payload = resp.json()
    features = payload.get("features", [])
    rows: List[PortWatchRow] = []

    for feature in features:
        attrs = feature.get("attributes") or {}
        raw_date = attrs.get("date")
        if raw_date is None:
            continue
        try:
            date = dt.datetime.utcfromtimestamp(raw_date / 1000.0).date()
        except Exception:
            continue
        movements = attrs.get("portcalls_tanker")
        departures = attrs.get("export_tanker")
        arrivals = attrs.get("import_tanker")
        rows.append(
            PortWatchRow(
                date=date,
                portname=str(attrs.get("portname", port_like)).strip(),
                iso3=iso3,
                movements=float(movements) if movements is not None else None,
                departures=float(departures) if departures is not None else None,
                arrivals=float(arrivals) if arrivals is not None else None,
            )
        )
    return rows


def upsert_portwatch_rows(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[PortWatchRow],
) -> int:
    ensure_core_tables(con)
    payload = []
    for row in rows:
        payload.append(
            (
                row.date,
                row.portname,
                row.port_code,
                row.iso3,
                row.shiptype,
                row.departures,
                row.arrivals,
                row.movements,
                row.source,
            )
        )

    if not payload:
        return 0

    con.executemany(
        """
        INSERT INTO portwatch_daily (
            d,
            portname,
            port_code,
            iso3,
            shiptype,
            departures,
            arrivals,
            movements,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (d, port_code, shiptype, source) DO UPDATE SET
            portname = excluded.portname,
            iso3 = excluded.iso3,
            departures = excluded.departures,
            arrivals = excluded.arrivals,
            movements = excluded.movements
        """,
        payload,
    )
    LOG.info("Upserted %s PortWatch rows.", len(payload))
    return len(payload)
