import duckdb
import pytest
from fastapi.testclient import TestClient

from spvx.api_app import app


@pytest.fixture(scope="module")
def api_client(prepared_db):
    with TestClient(app) as client:
        yield client


def test_components_daily_contains_new_basins(prepared_db):
    con = duckdb.connect(prepared_db)
    try:
        basins = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT basin
                FROM components_daily
                """
            ).fetchall()
        }
        assert {"APAC", "NAM", "SAM", "MED"}.issubset(basins)

        comps = con.execute(
            """
            SELECT basin, comp
            FROM components_daily
            WHERE d >= (SELECT max(d) FROM components_daily) - 7
            """
        ).fetchall()
        combo = {(row[0], row[1]) for row in comps}
        assert ("NAM", "CQ_PAN") in combo
        assert ("NAM", "PORT_US") in combo
        assert ("SAM", "CQ_PAN_S") in combo
        assert ("SAM", "PORT_BR") in combo
        assert ("MED", "CQ_SUEZ") in combo
        assert ("MED", "CQ_GIBRALTAR") in combo
        assert ("MED", "PORT_MED") in combo

        sample_flag = con.execute(
            "SELECT weather_flag FROM components_daily WHERE weather_flag IS NOT NULL LIMIT 1"
        ).fetchone()
        if sample_flag:
            assert sample_flag[0] in (0, 1)
    finally:
        con.close()


def test_spvx_basin_and_global_tables(prepared_db):
    con = duckdb.connect(prepared_db)
    try:
        basin_rows = con.execute("SELECT COUNT(*) FROM spvx_basin_daily").fetchone()[0]
        global_rows = con.execute("SELECT COUNT(*) FROM spvx_global_daily").fetchone()[0]
        assert basin_rows > 0
        assert global_rows > 0
        latest_global_row = con.execute(
            "SELECT spvx_global, weather_flag FROM spvx_global_daily ORDER BY d DESC LIMIT 1"
        ).fetchone()
        latest_global = latest_global_row[0]
        if latest_global is not None and not (isinstance(latest_global, float) and latest_global != latest_global):
            assert latest_global >= 0
        if latest_global_row[1] is not None:
            assert latest_global_row[1] in (0, 1)
    finally:
        con.close()


def test_api_basin_index(api_client):
    response = api_client.get("/api/index/APAC", params={"range": "30d"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["basin"] == "APAC"
    assert len(payload["series"]) > 0
    if payload["series"]:
        assert "weather_flag" in payload["series"][0]


def test_api_components(api_client):
    response = api_client.get("/api/components/NAM", params={"range": "14d"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["basin"] == "NAM"
    assert any(item["comp"] == "PORT_US" for item in payload["series"])
    if payload["series"]:
        assert all("weather_flag" in item for item in payload["series"])  # weather flag propagated


def test_api_mediterranean_basin(api_client):
    """Test Mediterranean basin index and components."""
    response = api_client.get("/api/index/MED", params={"range": "30d"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["basin"] == "MED"
    assert len(payload["series"]) > 0
    if payload["series"]:
        assert "weather_flag" in payload["series"][0]
        assert "spvx_basin" in payload["series"][0]

    # Test MED components
    comp_response = api_client.get("/api/components/MED", params={"range": "14d"})
    assert comp_response.status_code == 200
    comp_payload = comp_response.json()
    assert comp_payload["basin"] == "MED"
    components_present = {item["comp"] for item in comp_payload["series"]}
    assert "CQ_SUEZ" in components_present
    assert "CQ_GIBRALTAR" in components_present
    assert "PORT_MED" in components_present


def test_ops_health_endpoint(api_client):
    response = api_client.get("/ops/health")
    assert response.status_code == 200
    payload = response.json()
    assert "coverage_30d" in payload
    assert "components_present" in payload
    assert "weather_flags" in payload


def test_download_csv(api_client, tmp_path):
    response = api_client.get("/download/APAC.csv", params={"range": "30d"})
    assert response.status_code == 200
    csv_path = tmp_path / "apac.csv"
    csv_path.write_bytes(response.content)
    assert csv_path.exists()
    assert csv_path.read_text().startswith("date,value")
