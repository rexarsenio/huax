# spvx-lite/src/spvx/open_sea/tools/suez_builder.py
from __future__ import annotations
import json, math, datetime as dt
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import requests
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import linemerge
from pyproj import Geod

GEOD = Geod(ellps="WGS84")

# --- Overpass (OSM/Seamarks) -------------------------------------------------
NORTH_BBOX = (31.10, 31.80, 31.60, 32.60)  # (south, west, north, east)
SOUTH_BBOX = (29.20, 32.20, 30.40, 33.80)

def overpass_fetch(bbox: Tuple[float,float,float,float]) -> dict:
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

# --- Geodätik -----------------------------------------------------------------
def geod_fwd(lon: float, lat: float, az_deg: float, dist_nm: float) -> Tuple[float,float]:
    """Forward geodesic calculation: from point, bearing, distance -> new point."""
    lon1, lat1, _ = GEOD.fwd(lon, lat, az_deg, dist_nm * 1852.0)
    return lon1, lat1

def azimuth(p0: Tuple[float,float], p1: Tuple[float,float]) -> float:
    """Calculate azimuth from p0 to p1."""
    lon0, lat0 = p0; lon1, lat1 = p1
    az12, _, _ = GEOD.inv(lon0, lat0, lon1, lat1)
    return az12

def orthogonal_transect(center: Tuple[float,float], axis_az_deg: float, half_width_nm: float):
    """Create orthogonal transect (left, right) perpendicular to axis."""
    left  = geod_fwd(center[0], center[1], axis_az_deg - 90.0, half_width_nm)
    right = geod_fwd(center[0], center[1], axis_az_deg + 90.0, half_width_nm)
    return left, right

def sample_axis_points(axis: LineString, start_lonlat: Tuple[float,float], distances_nm: List[float]) -> List[Tuple[float,float,float]]:
    """Sample points along axis at specified distances from start, return (lon, lat, azimuth)."""
    coords = list(axis.coords)
    if len(coords) < 2:
        raise RuntimeError("Axis too short")

    # Find nearest axis point to start
    start_idx = min(range(len(coords)), key=lambda i: Point(coords[i]).distance(Point(start_lonlat)))

    # Cumulative geodesic distance per vertex
    cum = [0.0]
    for i in range(1, len(coords)):
        _, _, d = GEOD.inv(*coords[i-1], *coords[i])
        cum.append(cum[-1] + d)

    # Base azimuth for direction
    base_az = azimuth(coords[max(0, start_idx-1)], coords[min(len(coords)-1, start_idx+1)])

    out = []
    for nm in distances_nm:
        target = cum[start_idx] + nm*1852.0
        # Find point with cumulative distance closest to target
        best_j = start_idx
        best = 1e18
        for j in range(start_idx, len(coords)):
            diff = abs(cum[j] - target)
            if diff < best:
                best = diff
                best_j = j
        j0 = max(0, min(len(coords)-2, best_j-1))
        j1 = j0+1
        az = azimuth(coords[j0], coords[j1])
        out.append((coords[best_j][0], coords[best_j][1], az if not math.isnan(az) else base_az))
    return out

# --- Defaults (Entries & Fallback-Achsen) ------------------------------------
PORT_SAID_ENTRY = (32.301, 31.265)
PORT_SUEZ_ENTRY = (32.566, 29.966)

NORTH_AXIS_FALLBACK = LineString([
    (32.60, 31.55), (32.40, 31.35), (32.30, 31.26), (32.15, 31.05)
])
SOUTH_AXIS_FALLBACK = LineString([
    (33.40, 29.10), (33.00, 29.55), (32.80, 29.80), (32.56, 29.97)
])

# --- Builder ------------------------------------------------------------------
def build_suez(
    out_gates: Path,
    out_polys: Path,
    distances_nm: List[float] = [10,25,50,100,150],
    half_width_nm: Optional[float] = None,
    width_map_half_nm: Optional[Dict[float,float]] = None,  # e.g. {10:1.0, 25:1.5, ...}
    auto_width_from_tss: bool = False,
    auto_margin_nm: float = 0.3,
    use_overpass: bool = True,
    north_entry: Tuple[float,float] = PORT_SAID_ENTRY,
    south_entry: Tuple[float,float] = PORT_SUEZ_ENTRY,
) -> Dict[str,int]:
    """
    Build Suez Canal approach gates and anchorage polygons.

    Args:
        out_gates: Output path for gates GeoJSON
        out_polys: Output path for polygons GeoJSON
        distances_nm: List of distances from entry points for gates
        half_width_nm: Default half-width for gates (if no width_map provided)
        width_map_half_nm: Dict mapping distance to half-width (overrides half_width_nm)
        auto_width_from_tss: Attempt to derive width from TSS data
        auto_margin_nm: Additional margin when using auto_width_from_tss
        use_overpass: Whether to fetch OSM seamark data from Overpass
        north_entry: (lon, lat) for Port Said entry
        south_entry: (lon, lat) for Port of Suez entry

    Returns:
        Dict with counts of generated features
    """
    if use_overpass:
        try:
            north_osm = overpass_fetch(NORTH_BBOX)
            south_osm = overpass_fetch(SOUTH_BBOX)
            north_axis = lines_to_axis(osm_to_lines(north_osm), NORTH_AXIS_FALLBACK)
            south_axis = lines_to_axis(osm_to_lines(south_osm), SOUTH_AXIS_FALLBACK)
        except Exception:
            north_axis, south_axis = NORTH_AXIS_FALLBACK, SOUTH_AXIS_FALLBACK
    else:
        north_axis, south_axis = NORTH_AXIS_FALLBACK, SOUTH_AXIS_FALLBACK

    n_pts = sample_axis_points(north_axis, north_entry, distances_nm)
    s_pts = sample_axis_points(south_axis, south_entry, distances_nm)

    def tss_span_half_nm(axis: LineString, center_lonlat: Tuple[float,float]) -> Optional[float]:
        """
        Optional: Derive gate width from TSS boundaries.
        Currently returns None (stub) - can be enhanced with actual TSS data.
        """
        # Stub: TSS data not always available → None triggers fallback
        return None

    gates = []

    # North gates
    for d, (lon, lat, az) in zip(distances_nm, n_pts):
        hw = (width_map_half_nm or {}).get(d, None)
        if hw is None:
            if auto_width_from_tss:
                hw = tss_span_half_nm(north_axis, (lon, lat))
                if hw is not None:
                    hw = hw + auto_margin_nm
        if hw is None:
            hw = half_width_nm if half_width_nm is not None else 1.0  # Default 1.0 nm (→ 2.0 nm total)

        pL, pR = orthogonal_transect((lon, lat), az, hw)
        gates.append({
            "type": "Feature",
            "properties": {
                "id": f"GATE_SUEZ_N_{int(d)}NM",
                "width_nm": round(2*hw, 2),
                "half_width_nm": round(hw, 2),
                "distance_nm": int(d),
                "dir_hint": "BIDIR",
                "kind": "APPROACH_GATE",
                "corridor": "SUEZ_N"
            },
            "geometry": mapping(LineString([pL, pR]))
        })

    # South gates
    for d, (lon, lat, az) in zip(distances_nm, s_pts):
        hw = (width_map_half_nm or {}).get(d, None)
        if hw is None:
            if auto_width_from_tss:
                hw = tss_span_half_nm(south_axis, (lon, lat))
                if hw is not None:
                    hw = hw + auto_margin_nm
        if hw is None:
            hw = half_width_nm if half_width_nm is not None else 1.0

        pL, pR = orthogonal_transect((lon, lat), az, hw)
        gates.append({
            "type": "Feature",
            "properties": {
                "id": f"GATE_SUEZ_S_{int(d)}NM",
                "width_nm": round(2*hw, 2),
                "half_width_nm": round(hw, 2),
                "distance_nm": int(d),
                "dir_hint": "BIDIR",
                "kind": "APPROACH_GATE",
                "corridor": "SUEZ_S"
            },
            "geometry": mapping(LineString([pL, pR]))
        })

    gates_fc = {"type": "FeatureCollection", "features": gates}
    out_gates.parent.mkdir(parents=True, exist_ok=True)
    out_gates.write_text(json.dumps(gates_fc, ensure_ascii=False, indent=2))

    # Anchorage polygons - improved boundaries (wider, more realistic)
    # Port Said Anchorage: expanded west/east by 0.1°
    port_said = Polygon([
        (32.12, 31.34), (32.56, 31.34), (32.56, 31.54), (32.12, 31.54), (32.12, 31.34)
    ])

    # Great Bitter Lake: narrower, with shore margin
    bitter_lake = Polygon([
        (32.35, 30.26), (32.42, 30.26), (32.42, 30.50), (32.35, 30.50), (32.35, 30.26)
    ])

    polys_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "ANCH_PORT_SAID",
                    "kind": "ANCHORAGE",
                    "name": "Port Said Anchorage"
                },
                "geometry": mapping(port_said)
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "ANCH_GREAT_BITTER_LAKE",
                    "kind": "ANCHORAGE_INLAND",
                    "name": "Great Bitter Lake Anchorage"
                },
                "geometry": mapping(bitter_lake)
            },
        ]
    }
    out_polys.parent.mkdir(parents=True, exist_ok=True)
    out_polys.write_text(json.dumps(polys_fc, ensure_ascii=False, indent=2))

    return {"gates": len(gates), "polys": 2}

# --- Convoy Windows from gate_crossings (optional) ---------------------------
def derive_convoy_windows(db_path: str, gate_ids: List[str], days: int = 30) -> Dict[str, List[Dict]]:
    """
    Derive convoy time windows from historical gate_crossings data.

    Analyzes crossing patterns to identify peak traffic hours (90th percentile).

    Args:
        db_path: Path to DuckDB database
        gate_ids: List of gate IDs to analyze
        days: Number of days of history to analyze

    Returns:
        Dict mapping gate_id to list of time windows (start/end hours)
    """
    import duckdb
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()

    q = """
    WITH x AS (
      SELECT gate_id, date_trunc('hour', ts) AS hr, count(*) AS c
      FROM gate_crossings
      WHERE ts >= ?
        AND gate_id IN ({})
      GROUP BY 1,2
    ),
    agg AS (
      SELECT gate_id, EXTRACT(hour FROM hr) AS hod, sum(c) AS crossings
      FROM x GROUP BY 1,2
    ),
    pct AS (
      SELECT gate_id, hod, crossings,
             crossings / NULLIF(sum(crossings) OVER (PARTITION BY gate_id),0) AS share
      FROM agg
    ),
    th AS (
      SELECT gate_id, percentile_cont(0.90) WITHIN GROUP (ORDER BY share)
      OVER (PARTITION BY gate_id) AS p90
      FROM pct LIMIT 1
    )
    SELECT p.gate_id, p.hod, p.share
    FROM pct p, th
    WHERE p.share >= th.p90
    ORDER BY 1,2;
    """.format(",".join(["?"]*len(gate_ids)))

    args = [since] + gate_ids
    with duckdb.connect(db_path, read_only=True) as con:
        rows = con.execute(q, args).fetchall()

    # Build 2h windows from peaks
    out: Dict[str, List[Dict]] = {}
    for gid, hod, _ in rows:
        block = {
            "start": f"{int(hod):02d}:00",
            "end": f"{(int(hod)+2)%24:02d}:00"
        }
        out.setdefault(gid, []).append(block)
    return out
