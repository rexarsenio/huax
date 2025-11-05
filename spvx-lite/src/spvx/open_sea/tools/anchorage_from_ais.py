# spvx-lite/src/spvx/open_sea/tools/anchorage_from_ais.py
"""
Generate anchorage polygons from AIS dwell data using alpha-shapes or convex hulls.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

import duckdb
import numpy as np
from shapely.geometry import Point, Polygon, MultiPoint, mapping
from shapely.ops import unary_union
import alphashape


@dataclass
class DwellConfig:
    """Configuration for dwell point extraction."""
    sog_max: float = 0.5  # knots
    position_delta_max: float = 100.0  # meters
    dwell_min_minutes: int = 60  # 1 hour
    lookback_days: int = 60


@dataclass
class AnchorageConfig:
    """Configuration for anchorage polygon generation."""
    alpha: Optional[float] = None  # Alpha value for alpha-shape (None = auto)
    buffer_meters: float = 200.0  # Buffer around points
    min_points: int = 10  # Minimum points to generate polygon
    simplify_tolerance: float = 0.0001  # Simplify polygon (degrees)
    use_convex_hull_fallback: bool = True  # Use convex hull if alpha-shape fails


# ============================================================================
# SQL Queries
# ============================================================================

def build_dwell_query(
    table_name: str,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    polygon_id: Optional[str] = None,
    config: DwellConfig = DwellConfig(),
    timestamp_field: str = "ts",
) -> Tuple[str, List]:
    """
    Build SQL query to extract dwell points from AIS data.

    Computes dwell duration from consecutive low-SOG fixes using window functions.
    Works with both open_sea_fixes (ts field) and ais_canon (msg_time field).

    Args:
        table_name: Name of AIS fixes table (e.g., 'open_sea_fixes', 'ais_canon')
        bbox: Optional bounding box (lon_min, lat_min, lon_max, lat_max)
        polygon_id: Optional polygon ID to filter by
        config: Dwell extraction configuration
        timestamp_field: Name of timestamp column ('ts' or 'msg_time')

    Returns:
        Tuple of (query_string, parameters)
    """
    lookback_timestamp = f"current_timestamp - interval '{config.lookback_days} days'"

    # Base filter for low-SOG fixes
    base_where = [f"{timestamp_field} >= {lookback_timestamp}", "sog <= ?"]
    params = [config.sog_max]

    if bbox:
        lon_min, lat_min, lon_max, lat_max = bbox
        base_where.extend([
            "lon BETWEEN ? AND ?",
            "lat BETWEEN ? AND ?",
        ])
        params.extend([lon_min, lon_max, lat_min, lat_max])

    if polygon_id:
        base_where.append("polygon_id = ?")
        params.append(polygon_id)

    base_where_sql = " AND ".join(base_where)

    # Compute dwell duration from consecutive low-SOG fixes
    # Group fixes by mmsi and session, calculate duration
    query = f"""
    WITH low_sog_fixes AS (
        SELECT
            mmsi,
            {timestamp_field} AS ts,
            lon,
            lat,
            LAG({timestamp_field}) OVER (PARTITION BY mmsi ORDER BY {timestamp_field}) AS prev_ts
        FROM {table_name}
        WHERE {base_where_sql}
    ),
    dwell_sessions AS (
        SELECT
            mmsi,
            ts,
            lon,
            lat,
            -- Create session groups: new session if gap > 2 hours
            SUM(CASE
                WHEN prev_ts IS NULL OR EPOCH(ts - prev_ts) > 7200
                THEN 1
                ELSE 0
            END) OVER (PARTITION BY mmsi ORDER BY ts) AS session_id
        FROM low_sog_fixes
    ),
    dwell_aggregated AS (
        SELECT
            mmsi,
            session_id,
            AVG(lon) AS lon,
            AVG(lat) AS lat,
            MIN(ts) AS start_ts,
            MAX(ts) AS end_ts,
            EPOCH(MAX(ts) - MIN(ts)) / 60.0 AS dwell_minutes,
            COUNT(*) AS fix_count
        FROM dwell_sessions
        GROUP BY mmsi, session_id
        HAVING dwell_minutes >= ?
    )
    SELECT DISTINCT
        lon,
        lat,
        mmsi,
        start_ts AS ts
    FROM dwell_aggregated
    ORDER BY start_ts DESC
    """

    params.append(config.dwell_min_minutes)

    return query, params


# ============================================================================
# Alpha-Shape Generation
# ============================================================================

def points_to_polygon(
    points: List[Tuple[float, float]],
    config: AnchorageConfig = AnchorageConfig(),
) -> Optional[Polygon]:
    """
    Generate polygon from point cloud using alpha-shape or convex hull.

    Args:
        points: List of (lon, lat) tuples
        config: Anchorage generation configuration

    Returns:
        Shapely Polygon or None if insufficient points
    """
    if len(points) < config.min_points:
        return None

    # Convert to shapely MultiPoint
    multi_point = MultiPoint(points)

    try:
        # Try alpha-shape first
        if config.alpha is None:
            # Auto-optimize alpha
            alpha_shape = alphashape.alphashape(points)
        else:
            alpha_shape = alphashape.alphashape(points, config.alpha)

        # Ensure it's a Polygon (not MultiPolygon)
        if alpha_shape.geom_type == "Polygon":
            polygon = alpha_shape
        elif alpha_shape.geom_type == "MultiPolygon":
            # Take largest polygon
            polygon = max(alpha_shape.geoms, key=lambda p: p.area)
        else:
            raise ValueError(f"Unexpected geometry type: {alpha_shape.geom_type}")

    except Exception as e:
        # Fallback to convex hull if alpha-shape fails
        if config.use_convex_hull_fallback:
            polygon = multi_point.convex_hull
        else:
            raise RuntimeError(f"Alpha-shape failed and fallback disabled: {e}") from e

    # Apply buffer (convert meters to approximate degrees)
    # Rough approximation: 1 degree ≈ 111km at equator
    buffer_degrees = config.buffer_meters / 111_320.0
    polygon = polygon.buffer(buffer_degrees)

    # Simplify to reduce vertex count
    if config.simplify_tolerance > 0:
        polygon = polygon.simplify(config.simplify_tolerance, preserve_topology=True)

    return polygon


# ============================================================================
# Main Extraction Functions
# ============================================================================

def extract_dwell_points(
    db_path: str,
    table_name: str = "open_sea_fixes",
    bbox: Optional[Tuple[float, float, float, float]] = None,
    polygon_id: Optional[str] = None,
    dwell_config: DwellConfig = DwellConfig(),
    timestamp_field: str = "ts",
) -> List[Tuple[float, float]]:
    """
    Extract dwell points from AIS database.

    Args:
        db_path: Path to DuckDB database
        table_name: Name of AIS fixes table
        bbox: Optional bounding box filter
        polygon_id: Optional polygon ID filter
        dwell_config: Dwell extraction configuration
        timestamp_field: Name of timestamp column ('ts' or 'msg_time')

    Returns:
        List of (lon, lat) tuples
    """
    query, params = build_dwell_query(table_name, bbox, polygon_id, dwell_config, timestamp_field)

    with duckdb.connect(db_path, read_only=True) as con:
        try:
            rows = con.execute(query, params).fetchall()
        except Exception as e:
            # Table might not exist yet
            print(f"Warning: Could not query {table_name}: {e}")
            return []

    # Extract unique positions (deduplicate by rounding)
    unique_points = set()
    for row in rows:
        lon, lat = row[0], row[1]
        # Round to ~11m precision (5 decimal places)
        unique_points.add((round(lon, 5), round(lat, 5)))

    return list(unique_points)


def generate_anchorage_from_ais(
    db_path: str,
    anchorage_id: str,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    polygon_id: Optional[str] = None,
    dwell_config: DwellConfig = DwellConfig(),
    anchorage_config: AnchorageConfig = AnchorageConfig(),
    table_name: str = "open_sea_fixes",
    timestamp_field: str = "ts",
) -> Optional[Dict]:
    """
    Generate anchorage polygon from AIS dwell data.

    Args:
        db_path: Path to DuckDB database
        anchorage_id: ID for the generated anchorage
        bbox: Optional bounding box filter
        polygon_id: Optional polygon ID filter
        dwell_config: Dwell extraction configuration
        anchorage_config: Anchorage generation configuration
        table_name: Name of AIS fixes table
        timestamp_field: Name of timestamp column ('ts' or 'msg_time')

    Returns:
        GeoJSON Feature dict or None if insufficient data
    """
    # Extract dwell points
    points = extract_dwell_points(
        db_path=db_path,
        table_name=table_name,
        bbox=bbox,
        polygon_id=polygon_id,
        dwell_config=dwell_config,
        timestamp_field=timestamp_field,
    )

    if len(points) < anchorage_config.min_points:
        print(
            f"Warning: Insufficient dwell points for {anchorage_id} "
            f"({len(points)} < {anchorage_config.min_points})"
        )
        return None

    # Generate polygon
    polygon = points_to_polygon(points, anchorage_config)

    if polygon is None:
        return None

    # Create GeoJSON feature
    feature = {
        "type": "Feature",
        "properties": {
            "id": anchorage_id,
            "kind": "ANCHORAGE_AIS",
            "source": "ais_dwell",
            "point_count": len(points),
            "lookback_days": dwell_config.lookback_days,
            "sog_max": dwell_config.sog_max,
            "dwell_min_minutes": dwell_config.dwell_min_minutes,
        },
        "geometry": mapping(polygon),
    }

    return feature


def generate_anchorages_for_corridor(
    db_path: str,
    corridor: str,
    anchorage_definitions: List[Dict],
    dwell_config: DwellConfig = DwellConfig(),
    anchorage_config: AnchorageConfig = AnchorageConfig(),
    table_name: str = "open_sea_fixes",
    timestamp_field: str = "ts",
) -> List[Dict]:
    """
    Generate multiple anchorages for a corridor.

    Args:
        db_path: Path to DuckDB database
        corridor: Corridor name (e.g., "suez")
        anchorage_definitions: List of dicts with keys: id, bbox, polygon_id (optional)
        dwell_config: Dwell extraction configuration
        anchorage_config: Anchorage generation configuration
        table_name: Name of AIS fixes table
        timestamp_field: Name of timestamp column ('ts' or 'msg_time')

    Returns:
        List of GeoJSON Feature dicts
    """
    features = []

    for defn in anchorage_definitions:
        anchorage_id = defn["id"]
        bbox = defn.get("bbox")
        polygon_id = defn.get("polygon_id")

        feature = generate_anchorage_from_ais(
            db_path=db_path,
            anchorage_id=anchorage_id,
            bbox=bbox,
            polygon_id=polygon_id,
            dwell_config=dwell_config,
            anchorage_config=anchorage_config,
            table_name=table_name,
            timestamp_field=timestamp_field,
        )

        if feature:
            features.append(feature)

    return features


def save_anchorages(features: List[Dict], out_path: Path) -> None:
    """Save anchorage features to GeoJSON file."""
    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2))


# ============================================================================
# Preset Anchorage Definitions
# ============================================================================

# Suez Canal anchorage regions
SUEZ_ANCHORAGES = [
    {
        "id": "ANCH_PORT_SAID_AIS",
        "bbox": (32.10, 31.30, 32.60, 31.60),  # Extended Port Said area
    },
    {
        "id": "ANCH_GREAT_BITTER_LAKE_AIS",
        "bbox": (32.30, 30.20, 32.50, 30.55),  # Great Bitter Lake
    },
]

# Gibraltar anchorage regions
GIBRALTAR_ANCHORAGES = [
    {
        "id": "ANCH_GIBRALTAR_BAY_AIS",
        "bbox": (-5.40, 36.08, -5.30, 36.16),  # Gibraltar Bay
    },
    {
        "id": "ANCH_ALGECIRAS_AIS",
        "bbox": (-5.50, 36.08, -5.38, 36.18),  # Algeciras area
    },
]

# Bosporus anchorage regions
BOSPORUS_ANCHORAGES = [
    {
        "id": "ANCH_BOSPORUS_N_AIS",
        "bbox": (28.95, 41.20, 29.20, 41.40),  # Black Sea approach
    },
    {
        "id": "ANCH_BOSPORUS_S_AIS",
        "bbox": (28.85, 40.90, 29.10, 41.10),  # Marmara Sea approach
    },
]

# Venezuela anchorage regions
VENEZUELA_ANCHORAGES = [
    {
        "id": "ANCH_JOSE_TERMINAL_AIS",
        "bbox": (-70.80, 11.60, -70.40, 12.00),  # Jose Terminal area
    },
    {
        "id": "ANCH_MARACAIBO_AIS",
        "bbox": (-71.80, 10.50, -71.40, 10.90),  # Maracaibo area
    },
]

# Gulf of Mexico / Yucatan Channel anchorage regions
GULF_MEXICO_ANCHORAGES = [
    {
        "id": "ANCH_YUCATAN_N_AIS",
        "bbox": (-86.30, 21.70, -85.70, 22.30),  # North side
    },
    {
        "id": "ANCH_YUCATAN_S_AIS",
        "bbox": (-87.00, 20.70, -86.30, 21.30),  # South side
    },
]

# Houston / Texas ports anchorage regions
HOUSTON_ANCHORAGES = [
    {
        "id": "ANCH_GALVESTON_AIS",
        "bbox": (-95.00, 29.10, -94.60, 29.50),  # Galveston
    },
    {
        "id": "ANCH_HOUSTON_SHIP_CHANNEL_AIS",
        "bbox": (-95.20, 29.50, -94.80, 29.90),  # Houston Ship Channel
    },
]

# Brazil ports anchorage regions
BRAZIL_PORTS_ANCHORAGES = [
    {
        "id": "ANCH_SANTOS_AIS",
        "bbox": (-46.50, -24.20, -46.10, -23.80),  # Santos
    },
    {
        "id": "ANCH_RIO_DE_JANEIRO_AIS",
        "bbox": (-43.40, -23.20, -43.00, -22.80),  # Rio de Janeiro
    },
]

# Las Palmas (Gran Canaria) anchorage regions
LAS_PALMAS_ANCHORAGES = [
    {
        "id": "ANCH_LAS_PALMAS_BAY_AIS",
        "bbox": (-15.50, 28.00, -15.35, 28.20),  # Bay area
    },
    {
        "id": "ANCH_LAS_PALMAS_BUNKERING_AIS",
        "bbox": (-15.50, 28.00, -15.40, 28.15),  # Bunkering zone
    },
]

CORRIDOR_ANCHORAGES = {
    "suez": SUEZ_ANCHORAGES,
    "gibraltar": GIBRALTAR_ANCHORAGES,
    "bosporus": BOSPORUS_ANCHORAGES,
    "venezuela": VENEZUELA_ANCHORAGES,
    "gulf_mexico": GULF_MEXICO_ANCHORAGES,
    "houston": HOUSTON_ANCHORAGES,
    "brazil_ports": BRAZIL_PORTS_ANCHORAGES,
    "las_palmas": LAS_PALMAS_ANCHORAGES,
}
