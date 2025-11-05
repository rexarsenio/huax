from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from spvx.open_sea.config import OpenSeaConfig
from spvx.open_sea.engine import Observation, OpenSeaEngine
from spvx.open_sea.geo import load_gates, load_polygons


def _write_geojson(path: Path, features: list[dict]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def test_engine_generates_polygon_and_gate_events(tmp_path: Path) -> None:
    cfg = OpenSeaConfig.from_mapping(
        {
            "downsample_secs": 60,
            "hysteresis_hits": 2,
            "ttl_min": {"moving": 30, "anchorage": 90},
            "sog_thresholds": {"dwell_max_kn": 1.0},
            "gates": {"width_nm_default": 0.8},
            "cmems": {"enabled": False, "features": []},
            "sis": {"weights": {"wave": 0.5, "head_current": 0.35, "head_wind": 0.15}, "high_impact_p": 0.7},
        }
    )

    polygons_path = tmp_path / "polygons.geojson"
    gates_path = tmp_path / "gates.geojson"
    _write_geojson(
        polygons_path,
        [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-0.01, 0.0], [0.01, 0.0], [0.01, 0.02], [-0.01, 0.02], [-0.01, 0.0]]],
                },
                "properties": {"id": "TEST_POLY", "kind": "ANCHORAGE", "buffer_m": 50},
            }
        ],
    )
    _write_geojson(
        gates_path,
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[-0.02, 0.01], [0.02, 0.01]]},
                "properties": {"id": "TEST_GATE", "width_nm": 0.5, "dir_hint": "A_TO_B"},
            }
        ],
    )

    polygons = load_polygons(polygons_path)
    gates = load_gates(gates_path)
    engine = OpenSeaEngine(cfg, polygons, gates)

    base_ts = dt.datetime(2024, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    obs_inside = Observation(
        ts=base_ts,
        lat=0.01,
        lon=0.0,
        sog=0.4,
        cog=90.0,
        shiptype_num=80,
        is_tanker=True,
    )
    # First hit triggers sampling but no enter event yet
    result1 = engine.process_observation(123456789, obs_inside)
    assert not result1.polygon_events
    assert not result1.gate_crossings

    # Second hit -> enter event
    obs_inside2 = Observation(
        ts=base_ts + dt.timedelta(minutes=1),
        lat=0.011,
        lon=0.001,
        sog=0.3,
        cog=95.0,
        shiptype_num=None,
        is_tanker=True,
    )
    result2 = engine.process_observation(123456789, obs_inside2)
    assert any(evt.event == "enter" for evt in result2.polygon_events)

    # Move out crossing gate -> gate crossing
    obs_outside = Observation(
        ts=base_ts + dt.timedelta(minutes=2),
        lat=0.005,
        lon=0.03,
        sog=12.0,
        cog=90.0,
        shiptype_num=None,
        is_tanker=True,
    )
    result3 = engine.process_observation(123456789, obs_outside)
    assert result3.gate_crossings, "Expected gate crossing event"

    # Next fix outside should trigger exit (hysteresis satisfied)
    obs_outside2 = Observation(
        ts=base_ts + dt.timedelta(minutes=3),
        lat=0.004,
        lon=0.04,
        sog=12.0,
        cog=90.0,
        shiptype_num=None,
        is_tanker=True,
    )
    result4 = engine.process_observation(123456789, obs_outside2)
    assert any(evt.event == "exit" for evt in result4.polygon_events)
