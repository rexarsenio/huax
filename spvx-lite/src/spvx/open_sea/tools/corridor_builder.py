# spvx-lite/src/spvx/open_sea/tools/corridor_builder.py
"""
Generic corridor builder for maritime chokepoints with orthogonal approach gates.
Supports Suez Canal, Strait of Gibraltar, and Turkish Straits (Bosporus).
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

import requests
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import linemerge
from pyproj import Geod

GEOD = Geod(ellps="WGS84")


# ============================================================================
# Corridor Configurations
# ============================================================================

@dataclass
class CorridorConfig:
    """Configuration for a maritime corridor."""
    name: str
    approaches: List[ApproachConfig]
    anchorages: List[AnchorageConfig]
    overpass_bbox: Optional[Tuple[float, float, float, float]] = None  # (south, west, north, east)


@dataclass
class ApproachConfig:
    """Configuration for one approach direction of a corridor."""
    id: str  # e.g., "SUEZ_N", "GIBRALTAR_W"
    entry_point: Tuple[float, float]  # (lon, lat)
    fallback_axis: LineString
    overpass_bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class AnchorageConfig:
    """Configuration for an anchorage area."""
    id: str
    name: str
    kind: str  # "ANCHORAGE" or "ANCHORAGE_INLAND"
    polygon: Polygon


# ============================================================================
# Predefined Corridor Configurations
# ============================================================================

# --- SUEZ CANAL ---
SUEZ_CONFIG = CorridorConfig(
    name="SUEZ",
    approaches=[
        ApproachConfig(
            id="SUEZ_N",
            entry_point=(32.301, 31.265),  # Port Said
            fallback_axis=LineString([
                (32.60, 31.55), (32.40, 31.35), (32.30, 31.26), (32.15, 31.05)
            ]),
            overpass_bbox=(31.10, 31.80, 31.60, 32.60),
        ),
        ApproachConfig(
            id="SUEZ_S",
            entry_point=(32.566, 29.966),  # Port of Suez
            fallback_axis=LineString([
                (33.40, 29.10), (33.00, 29.55), (32.80, 29.80), (32.56, 29.97)
            ]),
            overpass_bbox=(29.20, 32.20, 30.40, 33.80),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_PORT_SAID",
            name="Port Said Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (32.12, 31.34), (32.56, 31.34), (32.56, 31.54), (32.12, 31.54), (32.12, 31.34)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_GREAT_BITTER_LAKE",
            name="Great Bitter Lake Anchorage",
            kind="ANCHORAGE_INLAND",
            polygon=Polygon([
                (32.35, 30.26), (32.42, 30.26), (32.42, 30.50), (32.35, 30.50), (32.35, 30.26)
            ]),
        ),
    ],
)

# --- STRAIT OF GIBRALTAR ---
GIBRALTAR_CONFIG = CorridorConfig(
    name="GIBRALTAR",
    approaches=[
        ApproachConfig(
            id="GIBRALTAR_W",
            entry_point=(-5.45, 35.95),  # West approach (Atlantic side)
            fallback_axis=LineString([
                (-6.50, 36.00), (-6.00, 36.00), (-5.45, 35.95), (-5.20, 35.90)
            ]),
            overpass_bbox=(35.70, -6.50, 36.30, -5.00),
        ),
        ApproachConfig(
            id="GIBRALTAR_E",
            entry_point=(-5.30, 35.88),  # East approach (Mediterranean side)
            fallback_axis=LineString([
                (-5.30, 35.88), (-4.80, 35.85), (-4.00, 35.80), (-3.50, 35.75)
            ]),
            overpass_bbox=(35.60, -5.50, 36.10, -3.00),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_GIBRALTAR_BAY",
            name="Gibraltar Bay Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-5.37, 36.10), (-5.33, 36.10), (-5.33, 36.14), (-5.37, 36.14), (-5.37, 36.10)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_ALGECIRAS",
            name="Algeciras Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-5.47, 36.10), (-5.40, 36.10), (-5.40, 36.16), (-5.47, 36.16), (-5.47, 36.10)
            ]),
        ),
    ],
)

# --- BOSPORUS (TURKISH STRAITS) ---
BOSPORUS_CONFIG = CorridorConfig(
    name="BOSPORUS",
    approaches=[
        ApproachConfig(
            id="BOSPORUS_N",
            entry_point=(29.08, 41.23),  # Black Sea approach
            fallback_axis=LineString([
                (29.08, 41.40), (29.08, 41.30), (29.08, 41.23), (29.05, 41.15)
            ]),
            overpass_bbox=(41.00, 28.90, 41.50, 29.20),
        ),
        ApproachConfig(
            id="BOSPORUS_S",
            entry_point=(29.00, 41.02),  # Marmara Sea approach
            fallback_axis=LineString([
                (29.00, 40.90), (29.00, 40.95), (29.00, 41.02), (29.03, 41.10)
            ]),
            overpass_bbox=(40.80, 28.80, 41.10, 29.10),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_BOSPORUS_N",
            name="Bosporus North Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (29.00, 41.25), (29.15, 41.25), (29.15, 41.35), (29.00, 41.35), (29.00, 41.25)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_BOSPORUS_S",
            name="Bosporus South Anchorage (Marmara)",
            kind="ANCHORAGE",
            polygon=Polygon([
                (28.90, 40.95), (29.05, 40.95), (29.05, 41.05), (28.90, 41.05), (28.90, 40.95)
            ]),
        ),
    ],
)

# --- VENEZUELA (Maracaibo/Jose Terminal) ---
VENEZUELA_CONFIG = CorridorConfig(
    name="VENEZUELA",
    approaches=[
        ApproachConfig(
            id="VENEZUELA_N",
            entry_point=(-70.60, 11.80),  # North approach (Caribbean)
            fallback_axis=LineString([
                (-70.60, 12.50), (-70.60, 12.00), (-70.60, 11.80), (-70.50, 11.50)
            ]),
        ),
        ApproachConfig(
            id="VENEZUELA_W",
            entry_point=(-71.50, 11.00),  # West approach (Maracaibo)
            fallback_axis=LineString([
                (-72.00, 11.00), (-71.70, 11.00), (-71.50, 11.00), (-71.20, 10.80)
            ]),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_JOSE_TERMINAL",
            name="Jose Terminal Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-70.70, 11.70), (-70.50, 11.70), (-70.50, 11.90), (-70.70, 11.90), (-70.70, 11.70)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_MARACAIBO",
            name="Lake Maracaibo Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-71.70, 10.60), (-71.50, 10.60), (-71.50, 10.80), (-71.70, 10.80), (-71.70, 10.60)
            ]),
        ),
    ],
)

# --- GULF OF MEXICO (Yucatan Channel) ---
GULF_MEXICO_CONFIG = CorridorConfig(
    name="GULF_MEXICO",
    approaches=[
        ApproachConfig(
            id="YUCATAN_N",
            entry_point=(-86.00, 22.00),  # North approach (Gulf side)
            fallback_axis=LineString([
                (-86.00, 23.00), (-86.00, 22.50), (-86.00, 22.00), (-85.80, 21.50)
            ]),
        ),
        ApproachConfig(
            id="YUCATAN_S",
            entry_point=(-86.50, 21.00),  # South approach (Caribbean side)
            fallback_axis=LineString([
                (-87.00, 20.50), (-86.70, 20.70), (-86.50, 21.00), (-86.20, 21.30)
            ]),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_YUCATAN_N",
            name="Yucatan Channel North Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-86.20, 21.80), (-85.80, 21.80), (-85.80, 22.20), (-86.20, 22.20), (-86.20, 21.80)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_YUCATAN_S",
            name="Yucatan Channel South Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-86.80, 20.80), (-86.40, 20.80), (-86.40, 21.20), (-86.80, 21.20), (-86.80, 20.80)
            ]),
        ),
    ],
)

# --- HOUSTON/TEXAS PORTS ---
HOUSTON_CONFIG = CorridorConfig(
    name="HOUSTON",
    approaches=[
        ApproachConfig(
            id="HOUSTON_SE",
            entry_point=(-94.50, 28.50),  # Southeast approach
            fallback_axis=LineString([
                (-94.50, 27.50), (-94.50, 28.00), (-94.50, 28.50), (-94.70, 29.00)
            ]),
        ),
        ApproachConfig(
            id="HOUSTON_S",
            entry_point=(-95.00, 28.00),  # South approach
            fallback_axis=LineString([
                (-95.00, 27.00), (-95.00, 27.50), (-95.00, 28.00), (-95.00, 28.50)
            ]),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_GALVESTON",
            name="Galveston Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-94.90, 29.20), (-94.70, 29.20), (-94.70, 29.40), (-94.90, 29.40), (-94.90, 29.20)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_HOUSTON_SHIP_CHANNEL",
            name="Houston Ship Channel Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-95.10, 29.60), (-94.90, 29.60), (-94.90, 29.80), (-95.10, 29.80), (-95.10, 29.60)
            ]),
        ),
    ],
)

# --- SANTOS/RIO (BRAZIL) ---
BRAZIL_PORTS_CONFIG = CorridorConfig(
    name="BRAZIL_PORTS",
    approaches=[
        ApproachConfig(
            id="SANTOS_E",
            entry_point=(-45.80, -24.00),  # East approach (Santos)
            fallback_axis=LineString([
                (-45.00, -24.00), (-45.40, -24.00), (-45.80, -24.00), (-46.20, -23.90)
            ]),
        ),
        ApproachConfig(
            id="RIO_SE",
            entry_point=(-42.80, -23.20),  # Southeast approach (Rio)
            fallback_axis=LineString([
                (-42.00, -23.50), (-42.40, -23.30), (-42.80, -23.20), (-43.10, -23.00)
            ]),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_SANTOS",
            name="Santos Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-46.40, -24.10), (-46.20, -24.10), (-46.20, -23.90), (-46.40, -23.90), (-46.40, -24.10)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_RIO_DE_JANEIRO",
            name="Rio de Janeiro Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-43.30, -23.10), (-43.10, -23.10), (-43.10, -22.90), (-43.30, -22.90), (-43.30, -23.10)
            ]),
        ),
    ],
)

# --- LAS PALMAS (GRAN CANARIA) - Major Bunkering Hub ---
LAS_PALMAS_CONFIG = CorridorConfig(
    name="LAS_PALMAS",
    approaches=[
        ApproachConfig(
            id="LAS_PALMAS_N",
            entry_point=(-15.40, 28.50),  # North approach
            fallback_axis=LineString([
                (-15.40, 29.00), (-15.40, 28.70), (-15.40, 28.50), (-15.35, 28.20)
            ]),
        ),
        ApproachConfig(
            id="LAS_PALMAS_E",
            entry_point=(-15.20, 28.10),  # East approach
            fallback_axis=LineString([
                (-14.80, 28.10), (-15.00, 28.10), (-15.20, 28.10), (-15.40, 28.05)
            ]),
        ),
    ],
    anchorages=[
        AnchorageConfig(
            id="ANCH_LAS_PALMAS_BAY",
            name="Las Palmas Bay Anchorage",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-15.45, 28.10), (-15.40, 28.10), (-15.40, 28.15), (-15.45, 28.15), (-15.45, 28.10)
            ]),
        ),
        AnchorageConfig(
            id="ANCH_LAS_PALMAS_BUNKERING",
            name="Las Palmas Bunkering Area",
            kind="ANCHORAGE",
            polygon=Polygon([
                (-15.48, 28.05), (-15.43, 28.05), (-15.43, 28.12), (-15.48, 28.12), (-15.48, 28.05)
            ]),
        ),
    ],
)

CORRIDORS: Dict[str, CorridorConfig] = {
    "suez": SUEZ_CONFIG,
    "gibraltar": GIBRALTAR_CONFIG,
    "bosporus": BOSPORUS_CONFIG,
    "venezuela": VENEZUELA_CONFIG,
    "gulf_mexico": GULF_MEXICO_CONFIG,
    "houston": HOUSTON_CONFIG,
    "brazil_ports": BRAZIL_PORTS_CONFIG,
    "las_palmas": LAS_PALMAS_CONFIG,
}


# ============================================================================
# Geodesic Utilities
# ============================================================================

def geod_fwd(lon: float, lat: float, az_deg: float, dist_nm: float) -> Tuple[float, float]:
    """Forward geodesic calculation: from point, bearing, distance -> new point."""
    lon1, lat1, _ = GEOD.fwd(lon, lat, az_deg, dist_nm * 1852.0)
    return lon1, lat1


def azimuth(p0: Tuple[float, float], p1: Tuple[float, float]) -> float:
    """Calculate azimuth from p0 to p1."""
    lon0, lat0 = p0
    lon1, lat1 = p1
    az12, _, _ = GEOD.inv(lon0, lat0, lon1, lat1)
    return az12


def orthogonal_transect(center: Tuple[float, float], axis_az_deg: float, half_width_nm: float):
    """Create orthogonal transect (left, right) perpendicular to axis."""
    left = geod_fwd(center[0], center[1], axis_az_deg - 90.0, half_width_nm)
    right = geod_fwd(center[0], center[1], axis_az_deg + 90.0, half_width_nm)
    return left, right


def sample_axis_points(
    axis: LineString, start_lonlat: Tuple[float, float], distances_nm: List[float]
) -> List[Tuple[float, float, float]]:
    """Sample points along axis at specified distances from start, return (lon, lat, azimuth)."""
    coords = list(axis.coords)
    if len(coords) < 2:
        raise RuntimeError("Axis too short")

    # Find nearest axis point to start
    start_idx = min(range(len(coords)), key=lambda i: Point(coords[i]).distance(Point(start_lonlat)))

    # Cumulative geodesic distance per vertex
    cum = [0.0]
    for i in range(1, len(coords)):
        _, _, d = GEOD.inv(*coords[i - 1], *coords[i])
        cum.append(cum[-1] + d)

    # Base azimuth for direction
    base_az = azimuth(coords[max(0, start_idx - 1)], coords[min(len(coords) - 1, start_idx + 1)])

    out = []
    for nm in distances_nm:
        target = cum[start_idx] + nm * 1852.0
        # Find point with cumulative distance closest to target
        best_j = start_idx
        best = 1e18
        for j in range(start_idx, len(coords)):
            diff = abs(cum[j] - target)
            if diff < best:
                best = diff
                best_j = j
        j0 = max(0, min(len(coords) - 2, best_j - 1))
        j1 = j0 + 1
        az = azimuth(coords[j0], coords[j1])
        out.append((coords[best_j][0], coords[best_j][1], az if not math.isnan(az) else base_az))
    return out


# ============================================================================
# OSM Overpass Integration
# ============================================================================

def overpass_fetch(bbox: Tuple[float, float, float, float]) -> dict:
    """Fetch OSM seamark separation lines/zones from Overpass API."""
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:60];
    (
      way["seamark:type"~"separation_(line|boundary|zone)"]({s},{w},{n},{e});
      rel["seamark:type"~"separation_(line|boundary|zone)"]({s},{w},{n},{e});
    );
    out geom;
    """
    r = requests.get("https://overpass-api.de/api/interpreter", params={"data": q}, timeout=60)
    r.raise_for_status()
    return r.json()


def osm_to_lines(osm_json: dict) -> List[LineString]:
    """Convert OSM JSON elements to shapely LineStrings."""
    lines = []
    for el in osm_json.get("elements", []):
        if "geometry" in el:
            coords = [(n["lon"], n["lat"]) for n in el["geometry"]]
            if len(coords) >= 2:
                lines.append(LineString(coords))
    return lines


def lines_to_axis(lines: List[LineString], fallback: LineString) -> LineString:
    """Merge OSM lines into single axis, or use fallback."""
    if not lines:
        return fallback
    try:
        merged = linemerge(lines)
        if merged.geom_type == "MultiLineString":
            merged = max(list(merged.geoms), key=lambda g: g.length)
        return merged
    except Exception:
        return fallback


# ============================================================================
# Main Builder
# ============================================================================

def build_corridor(
    corridor: str,
    out_gates: Path,
    out_polys: Path,
    distances_nm: List[float],
    width_map_half_nm: Optional[Dict[float, float]] = None,
    use_overpass: bool = True,
) -> Dict[str, int]:
    """
    Build approach gates and anchorage polygons for a maritime corridor.

    Args:
        corridor: Corridor name ("suez", "gibraltar", "bosporus")
        out_gates: Output path for gates GeoJSON
        out_polys: Output path for polygons GeoJSON
        distances_nm: List of distances from entry points for gates
        width_map_half_nm: Dict mapping distance to half-width
        use_overpass: Whether to fetch OSM seamark data from Overpass

    Returns:
        Dict with counts of generated features
    """
    if corridor not in CORRIDORS:
        raise ValueError(f"Unknown corridor: {corridor}. Must be one of: {list(CORRIDORS.keys())}")

    config = CORRIDORS[corridor]
    gates = []

    # Process each approach
    for approach in config.approaches:
        # Determine axis (OSM or fallback)
        if use_overpass and approach.overpass_bbox:
            try:
                osm_data = overpass_fetch(approach.overpass_bbox)
                axis = lines_to_axis(osm_to_lines(osm_data), approach.fallback_axis)
            except Exception:
                axis = approach.fallback_axis
        else:
            axis = approach.fallback_axis

        # Sample points along axis
        points = sample_axis_points(axis, approach.entry_point, distances_nm)

        # Create gates
        for d, (lon, lat, az) in zip(distances_nm, points):
            hw = (width_map_half_nm or {}).get(d, 1.0)  # Default 1.0 nm if not specified

            pL, pR = orthogonal_transect((lon, lat), az, hw)
            gates.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": f"GATE_{approach.id}_{int(d)}NM",
                        "width_nm": round(2 * hw, 2),
                        "half_width_nm": round(hw, 2),
                        "distance_nm": int(d),
                        "dir_hint": "BIDIR",
                        "kind": "APPROACH_GATE",
                        "corridor": approach.id,
                    },
                    "geometry": mapping(LineString([pL, pR])),
                }
            )

    # Write gates
    gates_fc = {"type": "FeatureCollection", "features": gates}
    out_gates.parent.mkdir(parents=True, exist_ok=True)
    out_gates.write_text(json.dumps(gates_fc, ensure_ascii=False, indent=2))

    # Write anchorage polygons
    polys_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": anch.id, "kind": anch.kind, "name": anch.name},
                "geometry": mapping(anch.polygon),
            }
            for anch in config.anchorages
        ],
    }
    out_polys.parent.mkdir(parents=True, exist_ok=True)
    out_polys.write_text(json.dumps(polys_fc, ensure_ascii=False, indent=2))

    return {"gates": len(gates), "polys": len(config.anchorages)}
