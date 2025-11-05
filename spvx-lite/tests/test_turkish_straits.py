import datetime as dt
import importlib
import sys

import duckdb
import pytest


def test_turkish_straits_aggregation(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("TURKISH_CLOSURE_THRESHOLD", "5")
    monkeypatch.setenv("TURKISH_WAIT_HOURS_PER_SLOW", "1.0")

    module_name = "spvx.sources.turkish_straits"
    if module_name in sys.modules:
        turkish_straits = importlib.reload(sys.modules[module_name])
    else:
        turkish_straits = importlib.import_module(module_name)

    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE dwell_10m (
            window_start TIMESTAMP,
            region TEXT,
            slow_count BIGINT
        )
        """
    )
    base = dt.datetime(2024, 10, 10, 0, 0)
    rows = [
        (base, "bosporus", 6),
        (base + dt.timedelta(minutes=10), "bosporus", 2),
        (base + dt.timedelta(minutes=20), "bosporus", 7),
        (base + dt.timedelta(days=1), "bosporus", 1),
        (base + dt.timedelta(days=1, minutes=10), "bosporus", 5),
        (base + dt.timedelta(days=1, minutes=20), "singapore_malacca", 9),
    ]
    con.executemany("INSERT INTO dwell_10m VALUES (?, ?, ?)", rows)
    con.close()

    turkish_straits.run(days=5)

    con = duckdb.connect(str(db_path))
    result = con.execute(
        "SELECT date(ts) AS d, closure_minutes, wait_hours FROM turkish_events ORDER BY ts"
    ).fetchall()
    con.close()

    assert len(result) == 2
    # Day 1: two windows above threshold (6 and 7) -> 20 closure minutes.
    assert result[0][1] == 20.0
    avg_day1 = (6 + 2 + 7) / 3
    assert result[0][2] == pytest.approx(avg_day1)

    # Day 2: only one window meets threshold (slow_count = 5) -> 10 minutes.
    assert result[1][1] == 10.0
    avg_day2 = (1 + 5) / 2
    assert result[1][2] == pytest.approx(avg_day2)
