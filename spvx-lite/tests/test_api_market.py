import os
import tempfile
from importlib import reload

from fastapi.testclient import TestClient

from fastapi import FastAPI
import duckdb
import spvx.api_market as market


def test_api_market_oil_endpoint(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "market.duckdb")
        con = duckdb.connect(db_path)
        try:
            con.execute(
                """
                CREATE TABLE oil_daily (
                    ds DATE NOT NULL,
                    series TEXT NOT NULL,
                    value DOUBLE,
                    source TEXT,
                    PRIMARY KEY (ds, series)
                )
                """
            )
            con.execute(
                """
                INSERT INTO oil_daily (ds, series, value, source) VALUES
                ('2024-10-21', 'RBRTE', 85.0, 'MOCK'),
                ('2024-10-22', 'RBRTE', 86.0, 'MOCK'),
                ('2024-10-21', 'RWTC', 77.0, 'MOCK'),
                ('2024-10-22', 'RWTC', 78.0, 'MOCK')
                """
            )
        finally:
            con.close()

        monkeypatch.setenv("DUCKDB_PATH", db_path)
        reload(market)
        app = FastAPI()
        app.include_router(market.router)
        client = TestClient(app)

        response = client.get("/api/market/oil?series=RBRTE,RWTC&range=400d")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["series"]) == 2
        latest = payload["latest"]
        assert latest["RBRTE"]["ds"].startswith("2024-10-22")
