# spvx-lite/tests/test_corridor_builder.py
from pathlib import Path
from spvx.open_sea.tools.corridor_builder import build_corridor, CORRIDORS
import json
import pytest


@pytest.mark.parametrize(
    "corridor,expected_gates,expected_polys",
    [
        ("suez", 10, 2),  # 5 distances * 2 approaches
        ("gibraltar", 10, 2),  # 5 distances * 2 approaches
        ("bosporus", 6, 2),  # 3 distances * 2 approaches
    ],
)
def test_build_corridor_offline(tmp_path: Path, corridor: str, expected_gates: int, expected_polys: int):
    """Test corridor builder in offline mode for all corridors."""
    g = tmp_path / f"{corridor}_gates.geojson"
    p = tmp_path / f"{corridor}_polygons.geojson"

    # Use corridor-specific defaults
    default_distances = {
        "suez": [10, 25, 50, 100, 150],
        "gibraltar": [10, 25, 50, 100, 150],
        "bosporus": [10, 25, 50],
    }

    res = build_corridor(
        corridor=corridor,
        out_gates=g,
        out_polys=p,
        distances_nm=default_distances[corridor],
        use_overpass=False,
    )

    assert g.exists() and p.exists()
    assert res["gates"] == expected_gates
    assert res["polys"] == expected_polys

    # Verify GeoJSON structure
    gates_data = json.loads(g.read_text())
    assert gates_data["type"] == "FeatureCollection"
    assert len(gates_data["features"]) == expected_gates

    polys_data = json.loads(p.read_text())
    assert polys_data["type"] == "FeatureCollection"
    assert len(polys_data["features"]) == expected_polys


def test_suez_gate_ids(tmp_path: Path):
    """Test that Suez gates have correct IDs."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    build_corridor(
        corridor="suez",
        out_gates=g,
        out_polys=p,
        distances_nm=[10, 25, 50, 100, 150],
        use_overpass=False,
    )

    gates_data = json.loads(g.read_text())
    gate_ids = [f["properties"]["id"] for f in gates_data["features"]]

    assert "GATE_SUEZ_N_10NM" in gate_ids
    assert "GATE_SUEZ_N_150NM" in gate_ids
    assert "GATE_SUEZ_S_10NM" in gate_ids
    assert "GATE_SUEZ_S_150NM" in gate_ids


def test_gibraltar_gate_ids(tmp_path: Path):
    """Test that Gibraltar gates have correct IDs."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    build_corridor(
        corridor="gibraltar",
        out_gates=g,
        out_polys=p,
        distances_nm=[10, 25, 50, 100, 150],
        use_overpass=False,
    )

    gates_data = json.loads(g.read_text())
    gate_ids = [f["properties"]["id"] for f in gates_data["features"]]

    assert "GATE_GIBRALTAR_W_10NM" in gate_ids
    assert "GATE_GIBRALTAR_W_150NM" in gate_ids
    assert "GATE_GIBRALTAR_E_10NM" in gate_ids
    assert "GATE_GIBRALTAR_E_150NM" in gate_ids


def test_bosporus_gate_ids(tmp_path: Path):
    """Test that Bosporus gates have correct IDs."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    build_corridor(
        corridor="bosporus",
        out_gates=g,
        out_polys=p,
        distances_nm=[10, 25, 50],
        use_overpass=False,
    )

    gates_data = json.loads(g.read_text())
    gate_ids = [f["properties"]["id"] for f in gates_data["features"]]

    assert "GATE_BOSPORUS_N_10NM" in gate_ids
    assert "GATE_BOSPORUS_N_50NM" in gate_ids
    assert "GATE_BOSPORUS_S_10NM" in gate_ids
    assert "GATE_BOSPORUS_S_50NM" in gate_ids


def test_corridor_width_map(tmp_path: Path):
    """Test corridor builder with custom width mapping."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    width_map = {10: 1.5, 25: 2.0, 50: 2.5, 100: 3.0, 150: 3.5}

    build_corridor(
        corridor="gibraltar",
        out_gates=g,
        out_polys=p,
        distances_nm=[10, 25, 50, 100, 150],
        width_map_half_nm=width_map,
        use_overpass=False,
    )

    gates_data = json.loads(g.read_text())

    for feature in gates_data["features"]:
        dist = feature["properties"]["distance_nm"]
        half_width = feature["properties"]["half_width_nm"]
        total_width = feature["properties"]["width_nm"]

        # Check that width matches our mapping
        assert half_width == width_map[dist]
        assert total_width == 2 * width_map[dist]


def test_corridor_anchorages(tmp_path: Path):
    """Test that anchorage polygons are generated correctly for all corridors."""
    for corridor in ["suez", "gibraltar", "bosporus"]:
        g = tmp_path / f"{corridor}_gates.geojson"
        p = tmp_path / f"{corridor}_polygons.geojson"

        build_corridor(
            corridor=corridor, out_gates=g, out_polys=p, distances_nm=[10, 25], use_overpass=False
        )

        polys_data = json.loads(p.read_text())
        assert polys_data["type"] == "FeatureCollection"
        assert len(polys_data["features"]) == 2

        # Check that all anchorages have required properties
        for feature in polys_data["features"]:
            assert "id" in feature["properties"]
            assert "kind" in feature["properties"]
            assert "name" in feature["properties"]
            assert feature["properties"]["kind"] in ["ANCHORAGE", "ANCHORAGE_INLAND"]


def test_corridor_configs_exist():
    """Test that all predefined corridor configurations are valid."""
    assert "suez" in CORRIDORS
    assert "gibraltar" in CORRIDORS
    assert "bosporus" in CORRIDORS

    for corridor_name, config in CORRIDORS.items():
        assert config.name is not None
        assert len(config.approaches) == 2  # All corridors have 2 approaches
        assert len(config.anchorages) == 2  # All corridors have 2 anchorages

        for approach in config.approaches:
            assert approach.id is not None
            assert len(approach.entry_point) == 2
            assert approach.fallback_axis is not None


def test_invalid_corridor_name(tmp_path: Path):
    """Test that invalid corridor name raises error."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    with pytest.raises(ValueError, match="Unknown corridor"):
        build_corridor(corridor="invalid_corridor", out_gates=g, out_polys=p, distances_nm=[10])
