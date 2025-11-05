import tempfile
import datetime as dt
from importlib import reload
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_database(path: Path, values: list[float]) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE spvx_global_daily (
                d DATE PRIMARY KEY,
                spvx_global DOUBLE
            )
            """
        )
        for idx, value in enumerate(values):
            current_date = (dt.date(2024, 1, 1) + dt.timedelta(days=idx)).isoformat()
            con.execute(
                "INSERT INTO spvx_global_daily (d, spvx_global) VALUES (?, ?)",
                (current_date, float(value)),
            )
    finally:
        con.close()


def test_latest_index_endpoint(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "spvx.duckdb"
        values = [100.0 + idx * 0.5 for idx in range(120)]
        _build_database(db_path, values)

        monkeypatch.setenv("DUCKDB_PATH", str(db_path))

        import spvx.api_index as api_index

        reload(api_index)
        api_index._CACHE.clear()

        app = FastAPI()
        app.include_router(api_index.router)

        client = TestClient(app)

        response = client.get("/api/index/latest")
        assert response.status_code == 200
        payload = response.json()

        assert payload["scope"] == "global"
        assert pytest.approx(payload["spvx"], rel=1e-6) == values[-1]
        assert pytest.approx(payload["delta_day_points"], rel=1e-6) == values[-1] - values[-2]
        classification = payload.get("classification")
        assert classification is not None
        assert "status" in classification

        # Remove data to confirm cached response is served
        con = duckdb.connect(str(db_path))
        try:
            con.execute("DELETE FROM spvx_global_daily")
        finally:
            con.close()

        cached = client.get("/api/index/latest")
        assert cached.status_code == 200
        assert pytest.approx(cached.json()["spvx"], rel=1e-6) == values[-1]


def test_latest_index_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "spvx.duckdb"
        con = duckdb.connect(str(db_path))
        try:
            con.execute(
                """
                CREATE TABLE spvx_global_daily (
                    d DATE PRIMARY KEY,
                    spvx_global DOUBLE
                )
                """
            )
        finally:
            con.close()

        monkeypatch.setenv("DUCKDB_PATH", str(db_path))

        import spvx.api_index as api_index

        reload(api_index)
        api_index._CACHE.clear()

        app = FastAPI()
        app.include_router(api_index.router)
        client = TestClient(app)

        response = client.get("/api/index/latest")
        assert response.status_code == 503
        detail = response.json()
        assert detail["detail"]["reason"] == "no_index_data"
