import json
from pathlib import Path

import duckdb
import pytest


def test_components_daily_has_sea_state_columns(prepared_db):
    con = duckdb.connect(prepared_db)
    try:
        columns = {
            row[1]
            for row in con.execute("PRAGMA table_info('components_daily')").fetchall()
        }
        assert {"sea_hs_z", "sea_opp_current", "sea_data_timestamp"}.issubset(columns)
    finally:
        con.close()


def test_basin_index_aggregates_sea_state(prepared_db):
    con = duckdb.connect(prepared_db)
    try:
        row = con.execute(
            """
            SELECT sea_hs_z_avg, sea_data_timestamp
            FROM spvx_basin_daily
            WHERE sea_hs_z_avg IS NOT NULL
               OR sea_data_timestamp IS NOT NULL
            ORDER BY d DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            pytest.skip("Sea-state aggregation not present in mock data run.")
        hs_z_avg, timestamp = row
        assert hs_z_avg is not None
        assert timestamp is not None
    finally:
        con.close()


def test_signals_json_contains_sea_state_drivers():
    path = Path("data/outputs/signals.json")
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    sea_state = payload.get("spread", {}).get("drivers", {}).get("sea_state")
    assert isinstance(sea_state, dict)
    assert "hs_z" in sea_state
    assert "as_of" in sea_state
