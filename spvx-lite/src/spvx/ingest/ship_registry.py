"""
Ship Registry: Cache for vessel static data (AIS Message Type 5).

This module provides a persistent cache of vessel metadata (ship type, name,
dimensions, etc.) extracted from AIS Static Data Reports (Message Type 5).
Position reports (Message Types 1,2,3) don't include this info, so we need
to cache it and look it up by MMSI.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, Optional

import duckdb

LOG = logging.getLogger(__name__)


def create_ship_registry_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create ship_registry table if it doesn't exist."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ship_registry (
            mmsi TEXT PRIMARY KEY,
            ship_name TEXT,
            callsign TEXT,
            imo_number TEXT,
            shiptype_num INTEGER,
            shiptype_str TEXT,
            dimension_a INTEGER,  -- Bow to reference position (m)
            dimension_b INTEGER,  -- Stern to reference position (m)
            dimension_c INTEGER,  -- Port to reference position (m)
            dimension_d INTEGER,  -- Starboard to reference position (m)
            eta TEXT,            -- Estimated time of arrival
            draught DOUBLE,      -- Maximum present static draught (m)
            destination TEXT,
            first_seen TIMESTAMP,
            last_updated TIMESTAMP,
            update_count INTEGER DEFAULT 1
        )
        """
    )
    LOG.info("Ship registry table created/verified")


def extract_ship_static_data(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract ship static data from AIS Message Type 5 payload.

    Args:
        payload: Raw AIS message from stream

    Returns:
        Dict with ship static data or None if not a Type 5 message
    """
    message = payload.get("Message") or {}
    msg_type = message.get("MessageType") or message.get("msgType")

    # Type 5 = Ship Static and Voyage Related Data
    if msg_type != 5:
        return None

    static_data = message.get("ShipStaticData") or message.get("StaticData") or {}
    metadata = payload.get("MetaData") or payload.get("metadata") or {}

    # Extract MMSI
    mmsi = (
        payload.get("MMSI")
        or metadata.get("MMSI")
        or static_data.get("UserID")
        or static_data.get("MMSI")
    )
    if mmsi is None:
        return None

    try:
        mmsi_str = str(int(mmsi)).zfill(9)
    except (TypeError, ValueError):
        return None

    if len(mmsi_str) != 9:
        return None

    # Extract ship type
    shiptype_num = None
    for key in ("Type", "ShipType", "shipType", "ShipTypeCode"):
        value = static_data.get(key) or message.get(key)
        if value is not None:
            try:
                shiptype_num = int(value)
                break
            except (TypeError, ValueError):
                continue

    # Shiptype string representation
    shiptype_str = None
    if shiptype_num is not None:
        shiptype_str = _shiptype_name(shiptype_num)
    else:
        # Try to get string directly
        shiptype_str = (
            static_data.get("ShipTypeName")
            or metadata.get("ShipType")
            or metadata.get("shipType")
        )
        if shiptype_str:
            shiptype_str = str(shiptype_str)

    # Extract dimensions
    dim_a = _safe_int(static_data.get("DimensionA") or static_data.get("Dimension", {}).get("A"))
    dim_b = _safe_int(static_data.get("DimensionB") or static_data.get("Dimension", {}).get("B"))
    dim_c = _safe_int(static_data.get("DimensionC") or static_data.get("Dimension", {}).get("C"))
    dim_d = _safe_int(static_data.get("DimensionD") or static_data.get("Dimension", {}).get("D"))

    # Extract other fields
    ship_name = static_data.get("Name") or static_data.get("ShipName")
    if ship_name:
        ship_name = str(ship_name).strip()

    callsign = static_data.get("CallSign") or static_data.get("Callsign")
    if callsign:
        callsign = str(callsign).strip()

    imo_number = static_data.get("ImoNumber") or static_data.get("IMO")
    if imo_number:
        imo_number = str(imo_number).strip()

    destination = static_data.get("Destination")
    if destination:
        destination = str(destination).strip()

    eta = static_data.get("Eta") or static_data.get("ETA")
    if eta:
        eta = str(eta)

    draught = _safe_float(static_data.get("Draught") or static_data.get("MaximumStaticDraught"))

    now = dt.datetime.now(dt.timezone.utc)

    return {
        "mmsi": mmsi_str,
        "ship_name": ship_name,
        "callsign": callsign,
        "imo_number": imo_number,
        "shiptype_num": shiptype_num,
        "shiptype_str": shiptype_str,
        "dimension_a": dim_a,
        "dimension_b": dim_b,
        "dimension_c": dim_c,
        "dimension_d": dim_d,
        "eta": eta,
        "draught": draught,
        "destination": destination,
        "first_seen": now,
        "last_updated": now,
    }


def upsert_ship_registry(
    con: duckdb.DuckDBPyConnection,
    ship_data: Dict[str, Any]
) -> None:
    """
    Insert or update ship registry entry.

    Args:
        con: DuckDB connection
        ship_data: Ship static data dict from extract_ship_static_data()
    """
    # Check if exists
    existing = con.execute(
        "SELECT mmsi, update_count FROM ship_registry WHERE mmsi = ?",
        [ship_data["mmsi"]]
    ).fetchone()

    if existing:
        # Update existing record
        con.execute(
            """
            UPDATE ship_registry
            SET ship_name = ?,
                callsign = ?,
                imo_number = ?,
                shiptype_num = ?,
                shiptype_str = ?,
                dimension_a = ?,
                dimension_b = ?,
                dimension_c = ?,
                dimension_d = ?,
                eta = ?,
                draught = ?,
                destination = ?,
                last_updated = ?,
                update_count = update_count + 1
            WHERE mmsi = ?
            """,
            [
                ship_data.get("ship_name"),
                ship_data.get("callsign"),
                ship_data.get("imo_number"),
                ship_data.get("shiptype_num"),
                ship_data.get("shiptype_str"),
                ship_data.get("dimension_a"),
                ship_data.get("dimension_b"),
                ship_data.get("dimension_c"),
                ship_data.get("dimension_d"),
                ship_data.get("eta"),
                ship_data.get("draught"),
                ship_data.get("destination"),
                ship_data["last_updated"],
                ship_data["mmsi"],
            ]
        )
    else:
        # Insert new record
        con.execute(
            """
            INSERT INTO ship_registry (
                mmsi, ship_name, callsign, imo_number,
                shiptype_num, shiptype_str,
                dimension_a, dimension_b, dimension_c, dimension_d,
                eta, draught, destination,
                first_seen, last_updated, update_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            [
                ship_data["mmsi"],
                ship_data.get("ship_name"),
                ship_data.get("callsign"),
                ship_data.get("imo_number"),
                ship_data.get("shiptype_num"),
                ship_data.get("shiptype_str"),
                ship_data.get("dimension_a"),
                ship_data.get("dimension_b"),
                ship_data.get("dimension_c"),
                ship_data.get("dimension_d"),
                ship_data.get("eta"),
                ship_data.get("draught"),
                ship_data.get("destination"),
                ship_data["first_seen"],
                ship_data["last_updated"],
            ]
        )


def lookup_ship_info(
    con: duckdb.DuckDBPyConnection,
    mmsi: str
) -> Optional[Dict[str, Any]]:
    """
    Look up ship information from registry by MMSI.

    Args:
        con: DuckDB connection
        mmsi: MMSI to look up (9-digit string)

    Returns:
        Dict with ship info or None if not found
    """
    row = con.execute(
        """
        SELECT mmsi, ship_name, shiptype_num, shiptype_str,
               callsign, imo_number, destination
        FROM ship_registry
        WHERE mmsi = ?
        """,
        [mmsi]
    ).fetchone()

    if row is None:
        return None

    return {
        "mmsi": row[0],
        "ship_name": row[1],
        "shiptype_num": row[2],
        "shiptype_str": row[3],
        "callsign": row[4],
        "imo_number": row[5],
        "destination": row[6],
    }


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert value to int."""
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert value to float."""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _shiptype_name(shiptype_num: int) -> str:
    """Get human-readable ship type name from AIS code."""
    # AIS ship type codes (simplified)
    types = {
        # 20-29: Wing in ground
        20: "WIG",
        # 30-39: Fishing
        30: "Fishing",
        # 40-49: Towing
        40: "Towing",
        # 50-59: Pilot, Search & Rescue, etc
        50: "Pilot Vessel",
        51: "Search and Rescue",
        52: "Tug",
        53: "Port Tender",
        54: "Anti-pollution",
        55: "Law Enforcement",
        58: "Medical Transport",
        59: "Non-combatant ship",
        # 60-69: Passenger
        60: "Passenger",
        61: "Passenger (Hazardous A)",
        62: "Passenger (Hazardous B)",
        63: "Passenger (Hazardous C)",
        64: "Passenger (Hazardous D)",
        69: "Passenger (No additional info)",
        # 70-79: Cargo
        70: "Cargo",
        71: "Cargo (Hazardous A)",
        72: "Cargo (Hazardous B)",
        73: "Cargo (Hazardous C)",
        74: "Cargo (Hazardous D)",
        79: "Cargo (No additional info)",
        # 80-89: Tanker (IMPORTANT!)
        80: "Tanker",
        81: "Tanker (Hazardous A)",
        82: "Tanker (Hazardous B)",
        83: "Tanker (Hazardous C)",
        84: "Tanker (Hazardous D)",
        89: "Tanker (No additional info)",
        # 90-99: Other
        90: "Other",
        91: "Other (Hazardous A)",
        92: "Other (Hazardous B)",
        93: "Other (Hazardous C)",
        94: "Other (Hazardous D)",
        99: "Other (No additional info)",
    }
    return types.get(shiptype_num, f"Type {shiptype_num}")
