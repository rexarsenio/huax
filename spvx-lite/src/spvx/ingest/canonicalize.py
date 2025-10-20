"""
Helpers to normalize raw AIS messages before writing into DuckDB.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional


UTC = dt.timezone.utc


def _parse_timestamp(payload: Dict[str, Any]) -> dt.datetime:
    """
    Try to infer the message timestamp from the payload metadata.
    Falls back to current UTC when no usable value exists.
    """
    metadata = payload.get("MetaData") or payload.get("metadata") or {}
    message = payload.get("Message") or {}
    report = message.get("PositionReport") or {}

    candidates = [
        metadata.get("receivedTimestamp"),
        metadata.get("timestamp"),
        report.get("UtcSec"),
        report.get("Timestamp"),
    ]

    for value in candidates:
        if value is None:
            continue
        try:
            if isinstance(value, (int, float)):
                if value > 10**12:
                    return dt.datetime.fromtimestamp(value / 1000.0, UTC)
                if value > 10**9:
                    return dt.datetime.fromtimestamp(value, UTC)
                if 0 <= value < 60:
                    now = dt.datetime.now(UTC)
                    return now.replace(second=int(value), microsecond=0)
            if isinstance(value, str):
                return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            continue

    return dt.datetime.now(UTC)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_lat_lon(lat: Optional[float], lon: Optional[float]) -> bool:
    return lat is not None and lon is not None and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _shiptype_string(payload: Dict[str, Any]) -> Optional[str]:
    metadata = payload.get("MetaData") or payload.get("metadata") or {}
    shiptype = metadata.get("shipType") or metadata.get("ShipType")
    if shiptype:
        return str(shiptype)
    message = payload.get("Message") or {}
    report = message.get("PositionReport") or {}
    shiptype = report.get("ShipType")
    if shiptype:
        return str(shiptype)
    ship_static = message.get("ShipStaticData") or {}
    shiptype = ship_static.get("ShipType")
    if shiptype:
        return str(shiptype)
    return None


def tanker_flag(shiptype_num: Optional[int], shiptype_str: Optional[str]) -> bool:
    if shiptype_num is not None and 80 <= shiptype_num <= 89:
        return True
    if shiptype_str:
        token = shiptype_str.lower()
        keywords = ("tanker", "crude", "product", "oil", "chem", "lng", "lpg")
        if any(word in token for word in keywords):
            return True
    return False


def canonicalize(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize the incoming AIS payload. Returns a dict to insert into `ais_canon`
    or None if the message is invalid.
    """
    message = payload.get("Message") or {}
    report = message.get("PositionReport") or {}

    mmsi = payload.get("MMSI") or payload.get("MetaData", {}).get("MMSI") or report.get("UserID")
    if mmsi is None:
        return None
    try:
        mmsi_str = str(int(mmsi)).zfill(9)
    except (TypeError, ValueError):
        return None
    if len(mmsi_str) != 9:
        return None

    msg_time = _parse_timestamp(payload)
    rx_time = dt.datetime.now(UTC)

    lat = _safe_float(report.get("Latitude"))
    lon = _safe_float(report.get("Longitude"))
    if not _valid_lat_lon(lat, lon):
        return None

    sog = _safe_float(report.get("Sog") or report.get("SOG"))
    if sog is None or sog < 0 or sog > 40:
        return None

    cog = _safe_float(report.get("Cog") or report.get("COG"))
    if cog is not None and (cog < 0 or cog > 360):
        cog = None

    shiptype_num = None
    for key in ("ShipType", "shipType", "ShipTypeCode"):
        value = report.get(key) or payload.get(key) or message.get(key)
        if value is None:
            continue
        try:
            shiptype_num = int(value)
            break
        except (TypeError, ValueError):
            continue

    shiptype_str = _shiptype_string(payload)
    is_tanker = tanker_flag(shiptype_num, shiptype_str)

    return {
        "mmsi": mmsi_str,
        "msg_time": msg_time,
        "rx_time": rx_time,
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "is_tanker": is_tanker,
        "shiptype_num": shiptype_num,
        "shiptype_str": shiptype_str,
    }
