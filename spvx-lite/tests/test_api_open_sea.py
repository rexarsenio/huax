import datetime as dt
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

import sys
import types


if "email_validator" not in sys.modules:
    email_validator = types.ModuleType("email_validator")

    class EmailNotValidError(Exception):
        pass

    class _ValidationResult:
        def __init__(self, email: str):
            self.email = email

    def validate_email(email: str, *args, **kwargs):
        return _ValidationResult(email)

    email_validator.EmailNotValidError = EmailNotValidError
    email_validator.validate_email = validate_email
    sys.modules["email_validator"] = email_validator

from spvx.api_app import app


@pytest.fixture()
def open_sea_client(tmp_path, monkeypatch):
    db_path = tmp_path / "open_sea.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE tanker_occupancy_intraday (
                ts TIMESTAMP,
                polygon_id TEXT,
                count_now INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO tanker_occupancy_intraday VALUES
            ('2025-10-21 10:00:00', 'HORMUZ_CORRIDOR_v1', 5),
            ('2025-10-21 10:00:00', 'FUJAIRAH_ANCH_v1', 7)
            """
        )
        con.execute(
            """
            CREATE TABLE gate_flux_hourly (
                ts TIMESTAMP,
                gate_id TEXT,
                direction TEXT,
                crossings INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO gate_flux_hourly VALUES
            ('2025-10-21 09:00:00', 'GATE_HORMUZ_E_v1', 'AtoB', 12),
            ('2025-10-21 10:00:00', 'GATE_HORMUZ_E_v1', 'AtoB', 15)
            """
        )
        con.execute(
            """
            CREATE TABLE gate_flux_daily (
                ds DATE,
                gate_id TEXT,
                direction TEXT,
                crossings INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO gate_flux_daily VALUES
            ('2025-10-20', 'GATE_HORMUZ_E_v1', 'AtoB', 120),
            ('2025-10-21', 'GATE_HORMUZ_E_v1', 'AtoB', 135)
            """
        )
        con.execute(
            """
            CREATE TABLE transit_times_daily (
                ds DATE,
                corridor_id TEXT,
                from_id TEXT,
                to_id TEXT,
                median_h DOUBLE,
                mean_h DOUBLE,
                p90_h DOUBLE,
                n INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO transit_times_daily VALUES
            ('2025-10-21', 'HORMUZ_EASTBOUND', 'FUJAIRAH_ANCH_v1', 'HORMUZ_CORRIDOR_v1', 12.5, 12.8, 18.0, 9),
            ('2025-10-20', 'HORMUZ_EASTBOUND', 'FUJAIRAH_ANCH_v1', 'HORMUZ_CORRIDOR_v1', 13.1, 13.4, 19.2, 8)
            """
        )
        con.execute(
            """
            CREATE TABLE sea_state_daily (
                ds DATE,
                corridor_id TEXT,
                sis_mean DOUBLE,
                sis_p90 DOUBLE,
                pct_sis_gt_0_7 DOUBLE,
                hc_p90_kn DOUBLE,
                hw_p90_ms DOUBLE,
                we_p90_m DOUBLE,
                n_samples INTEGER
            )
            """
        )
        con.execute(
            """
            INSERT INTO sea_state_daily VALUES
            ('2025-10-21', 'ARABIAN_GULF->HORMUZ', 0.42, 0.73, 0.25, 1.8, 6.0, 2.1, 48),
            ('2025-10-20', 'ARABIAN_GULF->HORMUZ', 0.35, 0.66, 0.15, 1.2, 5.4, 1.9, 39)
            """
        )
        con.execute(
            """
            CREATE TABLE open_sea_alerts(
                ts TIMESTAMP,
                kind TEXT,
                corridor_id TEXT,
                payload JSON
            )
            """
        )
        con.execute(
            """
            INSERT INTO open_sea_alerts VALUES
            ('2025-10-21 11:00:00', 'TRANSIT_ANOMALY', 'AG->HORMUZ', '{"mmsi":123,"transit_hours":26.5}'),
            ('2025-10-21 09:30:00', 'FLOATING_STORAGE', 'FUJAIRAH_ANCH_v1', '{"count_vlcc":3}')
            """
        )
    finally:
        con.close()

    with TestClient(app) as client:
        yield client


def test_occupancy_now(open_sea_client):
    response = open_sea_client.get("/api/open_sea/occupancy_now")
    assert response.status_code == 200
    payload = response.json()
    assert "as_of" in payload
    assert len(payload["polygons"]) == 2

    response_single = open_sea_client.get("/api/open_sea/occupancy_now", params={"polygon_id": "FUJAIRAH_ANCH_v1"})
    assert response_single.status_code == 200
    data_single = response_single.json()
    assert len(data_single["polygons"]) == 1
    assert data_single["polygons"][0]["count_now"] == 7


def test_gate_flux(open_sea_client):
    resp_hourly = open_sea_client.get(
        "/api/open_sea/gate_flux",
        params={"gate_id": "GATE_HORMUZ_E_v1", "window": "h24", "direction": "AtoB"},
    )
    assert resp_hourly.status_code == 200
    hourly_payload = resp_hourly.json()
    assert hourly_payload["total_crossings"] == 27
    assert len(hourly_payload["series"]) == 2

    resp_daily = open_sea_client.get(
        "/api/open_sea/gate_flux",
        params={"gate_id": "GATE_HORMUZ_E_v1", "window": "d7"},
    )
    assert resp_daily.status_code == 200
    daily_payload = resp_daily.json()
    assert daily_payload["total_crossings"] == 255
    assert len(daily_payload["series"]) == 2


def test_transit(open_sea_client):
    resp = open_sea_client.get(
        "/api/open_sea/transit",
        params={
            "corridor": "HORMUZ_EASTBOUND",
            "from_id": "FUJAIRAH_ANCH_v1",
            "to": "HORMUZ_CORRIDOR_v1",
            "lookback": "30d",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["corridor"] == "HORMUZ_EASTBOUND"
    assert payload["from_id"] == "FUJAIRAH_ANCH_v1"
    assert payload["to_id"] == "HORMUZ_CORRIDOR_v1"
    assert payload["latest"]["median_h"] == 12.5
    assert payload["latest"]["mean_h"] == 12.8
    assert len(payload["series"]) == 2
    assert all(item["corridor_id"] == "HORMUZ_EASTBOUND" for item in payload["series"])


def test_sis(open_sea_client):
    resp = open_sea_client.get(
        "/api/open_sea/sis",
        params={"corridor": "ARABIAN_GULF->HORMUZ", "window": "d7"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["latest"]["sis_p90"] == 0.73
    assert len(payload["series"]) == 2


def test_alerts(open_sea_client):
    resp = open_sea_client.get(
        "/api/open_sea/alerts",
        params={"limit": 10},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 2
    assert payload[0]["kind"] in {"TRANSIT_ANOMALY", "FLOATING_STORAGE"}

    resp_filtered = open_sea_client.get(
        "/api/open_sea/alerts",
        params={"kind": "TRANSIT_ANOMALY"},
    )
    assert resp_filtered.status_code == 200
    filtered = resp_filtered.json()
    assert all(alert["kind"] == "TRANSIT_ANOMALY" for alert in filtered)


def test_chokepoint_summary(open_sea_client, monkeypatch):
    original_datetime = dt.datetime

    class _FrozenDateTime(dt.datetime):  # type: ignore[misc]
        @classmethod
        def utcnow(cls):
            return original_datetime(2025, 10, 21, 12, 0, 0)

    monkeypatch.setattr(dt, "datetime", _FrozenDateTime)

    resp = open_sea_client.get("/api/open_sea/summary")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["window"] == "h24"
    assert payload["as_of"].startswith("2025-10-21T12:00:00")
    assert isinstance(payload["corridors"], list)
    assert payload["corridors"], "Expected at least one chokepoint entry"
    first_entry = payload["corridors"][0]
    assert set(first_entry.keys()) >= {"gate_id", "flux", "delay_ratio", "flux_z", "sis_p90", "trend"}


def test_corridor_catalog(open_sea_client):
    resp = open_sea_client.get("/api/open_sea/corridors")
    assert resp.status_code == 200
    payload = resp.json()
    assert any(item["corridor_id"] == "SUEZ_SOUTHBOUND" for item in payload)
