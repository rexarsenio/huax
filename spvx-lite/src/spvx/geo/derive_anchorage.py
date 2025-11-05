"""
Utility helpers to derive anchorage polygons from AIS dwell points.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
from shapely.geometry import MultiPoint, Point, Polygon, mapping
from shapely.ops import transform
from sklearn.cluster import DBSCAN

try:
    import pyproj
except ImportError as exc:  # pragma: no cover - dependency guaranteed in main project
    raise RuntimeError("pyproj is required for anchorage derivation") from exc


EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class DeriveParams:
    """
    Parameter bundle for the anchorage derivation routine.
    """

    center_lat: float = 28.13
    center_lon: float = -15.42
    radius_km: float = 22.0
    days_lookback: int = 14
    sog_max_kn: float = 0.5
    eps_m: float = 350.0
    min_samples: int = 30
    buffer_m: float = 120.0
    simplify_m: float = 30.0
    feature_name: str = "Las Palmas Anchorage"


def _bbox(params: DeriveParams) -> tuple[float, float, float, float]:
    lat_delta = params.radius_km / 111.0
    lon_scale = max(0.2, math.cos(math.radians(params.center_lat)))
    lon_delta = params.radius_km / (111.0 * lon_scale)
    return (
        params.center_lat - lat_delta,
        params.center_lon - lon_delta,
        params.center_lat + lat_delta,
        params.center_lon + lon_delta,
    )


def _fetch_fixes(db_path: Path, params: DeriveParams) -> np.ndarray:
    since_ts = dt.datetime.utcnow() - dt.timedelta(days=max(1, params.days_lookback))
    lat_min, lon_min, lat_max, lon_max = _bbox(params)
    query = """
        SELECT lat, lon
        FROM open_sea_fixes
        WHERE ts >= ?
          AND lat BETWEEN ? AND ?
          AND lon BETWEEN ? AND ?
          AND sog <= ?
          AND lat IS NOT NULL
          AND lon IS NOT NULL
    """
    with duckdb.connect(str(db_path), read_only=True) as con:
        try:
            rows = con.execute(
                query,
                [
                    since_ts,
                    lat_min,
                    lat_max,
                    lon_min,
                    lon_max,
                    params.sog_max_kn,
                ],
            ).fetchall()
        except duckdb.Error as exc:
            raise RuntimeError(f"Failed to query open_sea_fixes: {exc}") from exc

    if not rows:
        return np.empty((0, 2), dtype=float)

    points = np.array(rows, dtype=float)
    return points


def _cluster_points(points_latlon: np.ndarray, params: DeriveParams) -> Optional[np.ndarray]:
    if points_latlon.size == 0:
        return None
    points_rad = np.radians(points_latlon)
    eps_rad = params.eps_m / EARTH_RADIUS_M
    clustering = DBSCAN(eps=eps_rad, min_samples=params.min_samples, metric="haversine").fit(points_rad)
    labels = clustering.labels_
    mask = labels >= 0
    if not np.any(mask):
        return None
    labels_filtered = labels[mask]
    points_filtered = points_latlon[mask]
    largest_label = labels_filtered[np.argmax(np.bincount(labels_filtered))]
    cluster = points_latlon[labels == largest_label]
    if cluster.shape[0] < params.min_samples:
        return None
    return cluster


_TO_METERS = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
_TO_DEGREES = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform


def _to_polygon(cluster: np.ndarray, params: DeriveParams) -> Polygon:
    points = [Point(float(lon), float(lat)) for lat, lon in cluster]
    multi = MultiPoint(points)
    hull = multi.convex_hull
    if hull.is_empty:
        raise RuntimeError("Convex hull of cluster is empty")
    metric_geom = transform(_TO_METERS, hull)
    buffered = metric_geom.buffer(params.buffer_m)
    simplified = buffered.simplify(params.simplify_m)
    polygon = transform(_TO_DEGREES, simplified)
    if not isinstance(polygon, Polygon):
        polygon = polygon.convex_hull
    return polygon


def _upsert_feature(geojson_path: Path, feature: dict, feature_id: str) -> None:
    if geojson_path.exists():
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
    else:
        data = {"type": "FeatureCollection", "features": []}
    features = [item for item in data.get("features", []) if item.get("properties", {}).get("id") != feature_id]
    features.append(feature)
    data["features"] = features
    geojson_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_anchorage(db_path: str, polygons_path: str, params: Optional[DeriveParams] = None, fid: str = "ANCH_LAS_PALMAS") -> dict:
    params = params or DeriveParams()
    cluster = _cluster_points(_fetch_fixes(Path(db_path), params), params)
    if cluster is None:
        raise RuntimeError("Insufficient dwell points to derive anchorage polygon")
    polygon = _to_polygon(cluster, params)
    feature = {
        "type": "Feature",
        "geometry": mapping(polygon),
        "properties": {
            "id": fid,
            "name": params.feature_name,
            "kind": "ANCHORAGE",
            "source": "derived_dbscan",
            "created_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "metadata": {
                "center": [params.center_lat, params.center_lon],
                "radius_km": params.radius_km,
                "days_lookback": params.days_lookback,
                "sog_max_kn": params.sog_max_kn,
                "eps_m": params.eps_m,
                "min_samples": params.min_samples,
                "buffer_m": params.buffer_m,
                "simplify_m": params.simplify_m,
                "cluster_points": int(cluster.shape[0]),
            },
        },
    }
    _upsert_feature(Path(polygons_path), feature, fid)
    return feature

