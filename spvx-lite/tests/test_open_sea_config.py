from __future__ import annotations

import json
from pathlib import Path

import yaml

from spvx.open_sea.config import OpenSeaConfig, get_open_sea_config
from shapely.geometry import LineString

from spvx.open_sea.geo import load_gates, load_polygons


def _write_geojson(path: Path, features: list[dict]) -> None:
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_get_open_sea_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "open_sea": {
                    "downsample_secs": 120,
                    "hysteresis_hits": 3,
                    "ttl_min": {"moving": 20, "anchorage": 45},
                    "sog_thresholds": {"dwell_max_kn": 0.9},
                    "gates": {"width_nm_default": 1.2},
                    "cmems": {"enabled": True, "features": ["hs", "u10"]},
                    "sis": {
                        "weights": {"wave": 0.5, "head_current": 0.3, "head_wind": 0.2},
                        "high_impact_p": 0.6,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = get_open_sea_config(str(cfg_path))
    assert isinstance(cfg, OpenSeaConfig)
    assert cfg.downsample_secs == 120
    assert cfg.ttl_min.anchorage == 45
    assert cfg.cmems.enabled is True
    assert cfg.cmems.features == ("hs", "u10")
    assert cfg.sis.weights.wave == 0.5
    assert cfg.sis.high_impact_p == 0.6


def test_load_polygons_and_gates(tmp_path: Path) -> None:
    polygons_path = tmp_path / "polygons.geojson"
    gates_path = tmp_path / "gates.geojson"

    _write_geojson(
        polygons_path,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                "properties": {"id": "TEST_POLY", "kind": "ANCHORAGE", "buffer_m": 200.0, "notes": "demo"},
            }
        ],
    )
    _write_geojson(
        gates_path,
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                "properties": {"id": "TEST_GATE", "width_nm": 0.5, "dir_hint": "A_TO_B"},
            }
        ],
    )

    polygons = load_polygons(polygons_path)
    gates = load_gates(gates_path)

    assert len(polygons) == 1
    poly = polygons[0]
    assert poly.feature_id == "TEST_POLY"
    assert poly.kind == "ANCHORAGE"
    assert poly.buffer_m == 200.0
    assert poly.notes == "demo"
    assert poly.prepared_buffer.contains(poly.geom_mercator.representative_point())
    assert isinstance(poly.bbox_lonlat, tuple)

    assert len(gates) == 1
    gate = gates[0]
    assert gate.feature_id == "TEST_GATE"
    assert gate.width_nm == 0.5
    assert gate.dir_hint == "A_TO_B"
    assert isinstance(gate.line_mercator, LineString)
    assert isinstance(gate.bbox_lonlat, tuple)
