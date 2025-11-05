import datetime as dt

import duckdb
import pandas as pd

from spvx.sources.mpa_sg import _normalise_move, _upsert_moves
from spvx.sources.rotterdam import _normalise_event, _upsert_calls


def test_rotterdam_normalise_event_handles_multiple_fields():
    now = dt.datetime(2024, 5, 1, 12, 30)
    payload = {
        "eventTime": now.isoformat(),
        "eventType": "Departure",
        "shipCount": "3",
        "cargoType": "Crude Tanker",
    }
    normalised = _normalise_event(payload)
    assert normalised is not None
    assert normalised["ts"] == now
    assert normalised["event"] == "departure"
    assert normalised["vessels"] == 3
    assert normalised["is_tanker"] is True


def test_mpa_normalise_move_filters_timestamp_and_counts():
    now = dt.datetime(2024, 5, 2, 8, 15)
    payload = {
        "timestamp": now.isoformat(),
        "movement": "Arrival",
        "vesselType": "Oil Tanker",
        "count": "5",
    }
    normalised = _normalise_move(payload)
    assert normalised is not None
    assert normalised["ts"] == now
    assert normalised["movement"] == "arrival"
    assert normalised["vessel_type"] == "oil tanker"
    assert normalised["vessels"] == 5


def test_upsert_helpers_replace_existing_rows(tmp_path):
    con = duckdb.connect(str(tmp_path / "test.duckdb"))
    con.execute(
        """
        CREATE TABLE rotterdam_calls (
            ts TIMESTAMP,
            event TEXT,
            vessels INTEGER,
            is_tanker BOOLEAN,
            PRIMARY KEY (ts, event)
        )
        """
    )
    rows = [
        {"ts": dt.datetime(2024, 5, 1, 12), "event": "departure", "vessels": 1, "is_tanker": True},
        {"ts": dt.datetime(2024, 5, 1, 13), "event": "arrival", "vessels": 2, "is_tanker": False},
    ]
    inserted = _upsert_calls(con, rows)
    assert inserted == 2
    updated = _upsert_calls(
        con,
        [{"ts": dt.datetime(2024, 5, 1, 12), "event": "departure", "vessels": 4, "is_tanker": True}],
    )
    assert updated == 1
    df = con.execute("SELECT * FROM rotterdam_calls ORDER BY ts").df()
    assert df.loc[0, "vessels"] == 4

    con.execute(
        """
        CREATE TABLE mpa_moves (
            ts TIMESTAMP,
            vessel_type TEXT,
            movement TEXT,
            vessels INTEGER,
            PRIMARY KEY (ts, vessel_type, movement)
        )
        """
    )
    moves = [
        {"ts": dt.datetime(2024, 5, 2, 8), "vessel_type": "oil tanker", "movement": "arrival", "vessels": 3},
    ]
    count = _upsert_moves(con, moves)
    assert count == 1
    moves_df = con.execute("SELECT * FROM mpa_moves").df()
    assert isinstance(moves_df, pd.DataFrame)
    assert moves_df.loc[0, "vessels"] == 3
