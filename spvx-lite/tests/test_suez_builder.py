# spvx-lite/tests/test_suez_builder.py
from pathlib import Path
from spvx.open_sea.tools.suez_builder import build_suez
import json


def test_build_suez_offline(tmp_path: Path):
    """Test Suez builder in offline mode (no Overpass API calls)."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    res = build_suez(out_gates=g, out_polys=p, use_overpass=False)

    assert g.exists() and p.exists()
    assert res["gates"] == 10  # 5 Distanzen * 2 Seiten (North + South)
    assert res["polys"] == 2  # Port Said + Great Bitter Lake

    # Verify GeoJSON structure
    gates_data = json.loads(g.read_text())
    assert gates_data["type"] == "FeatureCollection"
    assert len(gates_data["features"]) == 10

    # Check that gate IDs are correct
    gate_ids = [f["properties"]["id"] for f in gates_data["features"]]
    assert "GATE_SUEZ_N_10NM" in gate_ids
    assert "GATE_SUEZ_N_150NM" in gate_ids
    assert "GATE_SUEZ_S_10NM" in gate_ids
    assert "GATE_SUEZ_S_150NM" in gate_ids


def test_build_suez_with_width_map(tmp_path: Path):
    """Test Suez builder with custom width mapping."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    # Custom widths: 10nm -> 1.0nm half-width, 25nm -> 1.5nm half-width, etc.
    width_map = {10: 1.0, 25: 1.5, 50: 2.0, 100: 2.5, 150: 3.0}

    res = build_suez(
        out_gates=g,
        out_polys=p,
        distances_nm=[10, 25, 50, 100, 150],
        width_map_half_nm=width_map,
        use_overpass=False,
    )

    assert res["gates"] == 10

    # Verify widths in generated gates
    gates_data = json.loads(g.read_text())
    for feature in gates_data["features"]:
        dist = feature["properties"]["distance_nm"]
        half_width = feature["properties"]["half_width_nm"]
        total_width = feature["properties"]["width_nm"]

        # Check that width matches our mapping
        assert half_width == width_map[dist]
        assert total_width == 2 * width_map[dist]


def test_build_suez_polygons(tmp_path: Path):
    """Test that anchorage polygons are generated correctly."""
    g = tmp_path / "gates.geojson"
    p = tmp_path / "polygons.geojson"

    res = build_suez(out_gates=g, out_polys=p, use_overpass=False)

    assert res["polys"] == 2

    # Verify polygon structure
    polys_data = json.loads(p.read_text())
    assert polys_data["type"] == "FeatureCollection"
    assert len(polys_data["features"]) == 2

    # Check polygon IDs
    poly_ids = [f["properties"]["id"] for f in polys_data["features"]]
    assert "ANCH_PORT_SAID" in poly_ids
    assert "ANCH_GREAT_BITTER_LAKE" in poly_ids

    # Check polygon kinds
    for feature in polys_data["features"]:
        assert "kind" in feature["properties"]
        assert feature["properties"]["kind"] in ["ANCHORAGE", "ANCHORAGE_INLAND"]
