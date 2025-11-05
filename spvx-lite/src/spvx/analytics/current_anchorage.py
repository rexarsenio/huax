"""
Current anchorage occupancy analysis.

Identifies vessels currently dwelling in anchorage areas.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import duckdb


@dataclass
class DwellingVessel:
    """Vessel currently dwelling in anchorage."""

    mmsi: str
    lat: float
    lon: float
    sog: float
    last_update: datetime
    is_tanker: bool
    shiptype_num: Optional[int]
    dwell_duration_hours: Optional[float] = None


def get_current_dwelling_vessels(
    db_path: str,
    bbox: Tuple[float, float, float, float],
    table_name: str = "ais_canon",
    timestamp_field: str = "msg_time",
    sog_threshold: float = 0.5,
    max_age_hours: float = 2.0,
) -> List[DwellingVessel]:
    """
    Get vessels currently dwelling in a bounding box.

    Args:
        db_path: Path to DuckDB database
        bbox: Bounding box (lon_min, lat_min, lon_max, lat_max)
        table_name: AIS fixes table name
        timestamp_field: Timestamp column name
        sog_threshold: Maximum SOG for dwelling (knots)
        max_age_hours: Maximum age of last fix (hours)

    Returns:
        List of DwellingVessel objects
    """
    lon_min, lat_min, lon_max, lat_max = bbox

    query = f"""
    WITH latest_fixes AS (
        SELECT
            mmsi,
            lat,
            lon,
            sog,
            {timestamp_field} as ts,
            is_tanker,
            COALESCE(shiptype_num, 0) as shiptype_num,
            ROW_NUMBER() OVER (PARTITION BY mmsi ORDER BY {timestamp_field} DESC) as rn
        FROM {table_name}
        WHERE lon BETWEEN ? AND ?
          AND lat BETWEEN ? AND ?
          AND {timestamp_field} >= current_timestamp - interval '{max_age_hours} hours'
    ),
    dwell_history AS (
        SELECT
            mmsi,
            MIN({timestamp_field}) as first_seen,
            MAX({timestamp_field}) as last_seen,
            EPOCH(MAX({timestamp_field}) - MIN({timestamp_field})) / 3600.0 as dwell_hours
        FROM {table_name}
        WHERE lon BETWEEN ? AND ?
          AND lat BETWEEN ? AND ?
          AND sog <= ?
          AND {timestamp_field} >= current_timestamp - interval '48 hours'
        GROUP BY mmsi
    )
    SELECT
        lf.mmsi,
        lf.lat,
        lf.lon,
        lf.sog,
        lf.ts,
        lf.is_tanker,
        lf.shiptype_num,
        dh.dwell_hours
    FROM latest_fixes lf
    LEFT JOIN dwell_history dh ON lf.mmsi = dh.mmsi
    WHERE lf.rn = 1
      AND lf.sog <= ?
    ORDER BY dh.dwell_hours DESC NULLS LAST, lf.ts DESC
    """

    params = [
        lon_min, lon_max, lat_min, lat_max,  # latest_fixes bbox
        lon_min, lon_max, lat_min, lat_max, sog_threshold,  # dwell_history
        sog_threshold,  # final filter
    ]

    with duckdb.connect(db_path, read_only=True) as conn:
        rows = conn.execute(query, params).fetchall()

    vessels = []
    for row in rows:
        mmsi, lat, lon, sog, ts, is_tanker, shiptype, dwell_hrs = row
        vessels.append(DwellingVessel(
            mmsi=str(mmsi),
            lat=lat,
            lon=lon,
            sog=sog,
            last_update=ts,
            is_tanker=is_tanker,
            shiptype_num=shiptype if shiptype != 0 else None,
            dwell_duration_hours=dwell_hrs,
        ))

    return vessels


def format_dwelling_vessels_table(vessels: List[DwellingVessel]) -> str:
    """Format dwelling vessels as ASCII table."""
    if not vessels:
        return "No dwelling vessels found."

    lines = [
        "MMSI         | Lat      | Lon      | SOG  | Dwell Time | Last Update",
        "-" * 80,
    ]

    for v in vessels:
        dwell_str = f"{v.dwell_duration_hours:.1f}h" if v.dwell_duration_hours else "---"
        ts_str = v.last_update.strftime("%H:%M:%S") if isinstance(v.last_update, datetime) else str(v.last_update)

        lines.append(
            f"{v.mmsi:12} | {v.lat:8.4f} | {v.lon:8.4f} | {v.sog:4.1f} | {dwell_str:10} | {ts_str}"
        )

    return "\n".join(lines)


def get_anchorage_statistics(
    vessels: List[DwellingVessel],
) -> Dict[str, any]:
    """
    Calculate statistics for dwelling vessels.

    Returns:
        Dict with keys: total_vessels, tankers, avg_dwell_hours, max_dwell_hours
    """
    tankers = [v for v in vessels if v.is_tanker]
    dwell_times = [v.dwell_duration_hours for v in vessels if v.dwell_duration_hours]

    return {
        "total_vessels": len(vessels),
        "tankers": len(tankers),
        "avg_dwell_hours": sum(dwell_times) / len(dwell_times) if dwell_times else 0,
        "max_dwell_hours": max(dwell_times) if dwell_times else 0,
        "vessels_with_dwell_data": len(dwell_times),
    }
