"""
GeoJSON helpers for open-sea polygons and gates with metric-aware buffering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform
from shapely.prepared import PreparedGeometry, prep


class GeoJSONLoadError(RuntimeError):
    """Raised when a GeoJSON artefact fails validation."""


@lru_cache(maxsize=2)
def _transformers() -> tuple[Transformer, Transformer]:
    forward = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    inverse = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    return forward, inverse


def _to_mercator(geom):
    forward, _ = _transformers()
    return transform(forward.transform, geom)


def _buffer_polygon_meters(geometry, buffer_m: float):
    geom_merc = _to_mercator(geometry)
    buffered = geom_merc.buffer(buffer_m)
    return geom_merc, buffered


def point_from_latlon(lat: float, lon: float) -> Point:
    forward, _ = _transformers()
    x, y = forward.transform(lon, lat)
    return Point(x, y)


@dataclass(frozen=True)
class PolygonFeature:
    feature_id: str
    kind: str
    buffer_m: float
    notes: str | None
    geom_mercator: object
    buffered_mercator: object
    prepared_buffer: PreparedGeometry
    bbox_lonlat: tuple[float, float, float, float]

    def contains_point(self, point: Point) -> bool:
        return self.prepared_buffer.contains(point)


@dataclass(frozen=True)
class GateFeature:
    feature_id: str
    width_nm: float
    dir_hint: str | None
    line_mercator: LineString
    buffer_mercator: object
    prepared_buffer: PreparedGeometry
    normal_unit: tuple[float, float]
    bbox_lonlat: tuple[float, float, float, float]


def _load_geojson(path: Path) -> Mapping[str, object]:
    if not path.exists():
        raise GeoJSONLoadError(f"GeoJSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise GeoJSONLoadError(f"GeoJSON root must be an object: {path}")
    if data.get("type") != "FeatureCollection":
        raise GeoJSONLoadError(f"GeoJSON root must be a FeatureCollection: {path}")
    return data


def _require_properties(feature: Mapping[str, object], required: Sequence[str], path: Path) -> Mapping[str, object]:
    props = feature.get("properties")
    if not isinstance(props, Mapping):
        raise GeoJSONLoadError(f"Feature missing properties in {path}")
    for key in required:
        if key not in props:
            raise GeoJSONLoadError(f"Feature missing '{key}' property in {path}")
    return props


def _prepare_polygon_feature(geometry, props: Mapping[str, object]) -> PolygonFeature:
    polygon = shape(geometry)
    geom_merc, buffered = _buffer_polygon_meters(polygon, float(props.get("buffer_m", 150.0)))
    return PolygonFeature(
        feature_id=str(props["id"]),
        kind=str(props["kind"]),
        buffer_m=float(props.get("buffer_m", 150.0)),
        notes=str(props["notes"]) if props.get("notes") is not None else None,
        geom_mercator=geom_merc,
        buffered_mercator=buffered,
        prepared_buffer=prep(buffered),
        bbox_lonlat=polygon.bounds,
    )


def load_polygons(path: Path) -> List[PolygonFeature]:
    data = _load_geojson(path)
    features = data.get("features")
    if not isinstance(features, Sequence):
        raise GeoJSONLoadError(f"'features' must be an array in {path}")
    results: List[PolygonFeature] = []
    for raw in features:
        if not isinstance(raw, Mapping):
            raise GeoJSONLoadError(f"Invalid feature entry in {path}")
        geometry = raw.get("geometry")
        if not isinstance(geometry, Mapping):
            raise GeoJSONLoadError(f"Feature missing geometry in {path}")
        props = _require_properties(raw, ("id", "kind"), path)
        results.append(_prepare_polygon_feature(geometry, props))
    return results


def _gate_normal(line_mercator: LineString) -> tuple[float, float]:
    x1, y1 = line_mercator.coords[0]
    x2, y2 = line_mercator.coords[-1]
    dx = x2 - x1
    dy = y2 - y1
    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        return 0.0, 0.0
    return (-dy / length, dx / length)


def load_gates(path: Path) -> List[GateFeature]:
    data = _load_geojson(path)
    features = data.get("features")
    if not isinstance(features, Iterable):
        raise GeoJSONLoadError(f"'features' must be an array in {path}")
    results: List[GateFeature] = []
    for raw in features:
        if not isinstance(raw, Mapping):
            raise GeoJSONLoadError(f"Invalid feature entry in {path}")
        geometry = raw.get("geometry")
        if not isinstance(geometry, Mapping):
            raise GeoJSONLoadError(f"Feature missing geometry in {path}")
        props = _require_properties(raw, ("id",), path)
        line = shape(geometry)
        if not isinstance(line, LineString):
            raise GeoJSONLoadError(f"Gate geometry must be a LineString in {path}")
        line_merc = _to_mercator(line)
        width_nm = float(props.get("width_nm", 0.8))
        width_m = width_nm * 1852.0
        buffer_merc = line_merc.buffer(width_m / 2.0, cap_style=2)
        results.append(
            GateFeature(
                feature_id=str(props["id"]),
                width_nm=width_nm,
                dir_hint=str(props.get("dir_hint")) if props.get("dir_hint") is not None else None,
                line_mercator=line_merc,
                buffer_mercator=buffer_merc,
                prepared_buffer=prep(buffer_merc),
                normal_unit=_gate_normal(line_merc),
                bbox_lonlat=line.bounds,
            )
        )
    return results
