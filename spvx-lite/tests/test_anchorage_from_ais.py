# spvx-lite/tests/test_anchorage_from_ais.py
from pathlib import Path
import json
import pytest
from shapely.geometry import Point, Polygon

from spvx.open_sea.tools.anchorage_from_ais import (
    points_to_polygon,
    build_dwell_query,
    DwellConfig,
    AnchorageConfig,
    save_anchorages,
    CORRIDOR_ANCHORAGES,
)


def test_points_to_polygon_alpha_shape():
    """Test alpha-shape polygon generation from point cloud."""
    # Create a circular cluster of points
    points = []
    import math
    for i in range(20):
        angle = 2 * math.pi * i / 20
        x = 10.0 + 0.5 * math.cos(angle)
        y = 20.0 + 0.5 * math.sin(angle)
        points.append((x, y))

    config = AnchorageConfig(alpha=None, buffer_meters=100, min_points=10)
    polygon = points_to_polygon(points, config)

    assert polygon is not None
    assert isinstance(polygon, Polygon)
    assert polygon.is_valid
    assert polygon.area > 0


def test_points_to_polygon_convex_hull_fallback():
    """Test convex hull fallback when alpha-shape fails."""
    # Simple 3-point triangle
    points = [(0, 0), (1, 0), (0.5, 1)]

    config = AnchorageConfig(
        alpha=None,
        buffer_meters=0,
        min_points=3,
        use_convex_hull_fallback=True,
    )
    polygon = points_to_polygon(points, config)

    assert polygon is not None
    assert isinstance(polygon, Polygon)
    assert polygon.is_valid


def test_points_to_polygon_insufficient_points():
    """Test that insufficient points return None."""
    points = [(0, 0), (1, 0)]  # Only 2 points

    config = AnchorageConfig(min_points=10)
    polygon = points_to_polygon(points, config)

    assert polygon is None


def test_points_to_polygon_with_buffer():
    """Test that buffer is applied correctly."""
    points = [(0, 0), (1, 0), (1, 1), (0, 1)]  # Square

    # Without buffer
    config_no_buffer = AnchorageConfig(buffer_meters=0, min_points=3)
    polygon_no_buffer = points_to_polygon(points, config_no_buffer)

    # With buffer
    config_with_buffer = AnchorageConfig(buffer_meters=500, min_points=3)
    polygon_with_buffer = points_to_polygon(points, config_with_buffer)

    assert polygon_with_buffer.area > polygon_no_buffer.area


def test_build_dwell_query_basic():
    """Test SQL query generation with basic parameters."""
    config = DwellConfig(sog_max=0.5, dwell_min_minutes=60, lookback_days=30)
    query, params = build_dwell_query("open_sea_fixes", config=config)

    assert "SELECT" in query
    assert "FROM open_sea_fixes" in query
    assert "sog <= ?" in query
    assert "dwell_min >= ?" in query
    assert len(params) == 2
    assert params[0] == 0.5
    assert params[1] == 60


def test_build_dwell_query_with_bbox():
    """Test SQL query with bounding box filter."""
    bbox = (32.0, 31.0, 33.0, 32.0)  # lon_min, lat_min, lon_max, lat_max
    query, params = build_dwell_query("open_sea_fixes", bbox=bbox)

    assert "lon BETWEEN ? AND ?" in query
    assert "lat BETWEEN ? AND ?" in query
    assert 32.0 in params
    assert 31.0 in params
    assert 33.0 in params
    assert 32.0 in params


def test_build_dwell_query_with_polygon_id():
    """Test SQL query with polygon ID filter."""
    query, params = build_dwell_query("open_sea_fixes", polygon_id="ANCH_PORT_SAID")

    assert "polygon_id = ?" in query
    assert "ANCH_PORT_SAID" in params


def test_save_anchorages(tmp_path: Path):
    """Test saving anchorages to GeoJSON file."""
    features = [
        {
            "type": "Feature",
            "properties": {"id": "ANCH_TEST_1", "kind": "ANCHORAGE_AIS"},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        },
        {
            "type": "Feature",
            "properties": {"id": "ANCH_TEST_2", "kind": "ANCHORAGE_AIS"},
            "geometry": {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]]},
        },
    ]

    out_path = tmp_path / "anchorages.geojson"
    save_anchorages(features, out_path)

    assert out_path.exists()

    # Verify content
    data = json.loads(out_path.read_text())
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2
    assert data["features"][0]["properties"]["id"] == "ANCH_TEST_1"


def test_corridor_anchorages_definitions():
    """Test that corridor anchorage definitions are valid."""
    assert "suez" in CORRIDOR_ANCHORAGES
    assert "gibraltar" in CORRIDOR_ANCHORAGES
    assert "bosporus" in CORRIDOR_ANCHORAGES

    for corridor, definitions in CORRIDOR_ANCHORAGES.items():
        assert isinstance(definitions, list)
        assert len(definitions) > 0

        for defn in definitions:
            assert "id" in defn
            assert "bbox" in defn
            bbox = defn["bbox"]
            assert len(bbox) == 4  # (lon_min, lat_min, lon_max, lat_max)
            assert bbox[0] < bbox[2]  # lon_min < lon_max
            assert bbox[1] < bbox[3]  # lat_min < lat_max


def test_dwell_config_defaults():
    """Test DwellConfig default values."""
    config = DwellConfig()

    assert config.sog_max == 0.5
    assert config.dwell_min_minutes == 60
    assert config.lookback_days == 60


def test_anchorage_config_defaults():
    """Test AnchorageConfig default values."""
    config = AnchorageConfig()

    assert config.alpha is None  # Auto-optimize
    assert config.buffer_meters == 200.0
    assert config.min_points == 10
    assert config.use_convex_hull_fallback is True


def test_points_to_polygon_simplify():
    """Test polygon simplification."""
    # Create many points in a circle
    import math
    points = []
    for i in range(100):
        angle = 2 * math.pi * i / 100
        x = 10.0 + 0.5 * math.cos(angle)
        y = 20.0 + 0.5 * math.sin(angle)
        points.append((x, y))

    # With simplification
    config_simple = AnchorageConfig(simplify_tolerance=0.01, min_points=10)
    polygon_simple = points_to_polygon(points, config_simple)

    # Without simplification
    config_no_simple = AnchorageConfig(simplify_tolerance=0.0, min_points=10)
    polygon_no_simple = points_to_polygon(points, config_no_simple)

    # Simplified polygon should have fewer vertices
    assert len(polygon_simple.exterior.coords) < len(polygon_no_simple.exterior.coords)
