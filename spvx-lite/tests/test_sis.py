import datetime as dt

import duckdb
import pandas as pd
import pytest

from spvx.open_sea.sis import SISConfig, compute_samples, compute_sis_daily


def test_compute_samples_projects_head_components():
    df_tracklets = pd.DataFrame(
        {
            "tracklet_id": [1],
            "ts": [pd.Timestamp("2025-01-01T00:00:00Z")],
            "lat": [25.0],
            "lon": [56.0],
            "mean_cog": [0.0],
        }
    )
    df_cmems = pd.DataFrame(
        {
            "tracklet_id": [1],
            "ts": [pd.Timestamp("2025-01-01T00:00:00Z")],
            "lat": [25.0],
            "lon": [56.0],
            "hs": [2.0],
            "u10": [5.0],
            "v10": [0.0],
            "uo": [0.5],
            "vo": [0.0],
            "sst_anom": [0.2],
        }
    )

    merged = compute_samples(df_tracklets, df_cmems)
    assert not merged.empty
    assert merged.loc[0, "head_current_kn"] == pytest.approx(-0.5 * 1.94384)
    assert merged.loc[0, "head_wind_ms"] == pytest.approx(-5.0)
    assert merged.loc[0, "wave_encounter_m"] == pytest.approx(2.0)


def test_compute_sis_daily_inserts_rows(tmp_path):
    db_path = tmp_path / "sis.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE tracklets(
                tracklet_id TEXT,
                mmsi BIGINT,
                start_ts TIMESTAMP,
                end_ts TIMESTAMP,
                n_points INTEGER,
                mean_cog DOUBLE,
                mean_sog DOUBLE,
                poly_from_id TEXT,
                poly_to_id TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE sea_state_samples(
                tracklet_id TEXT,
                ts TIMESTAMP,
                lat DOUBLE,
                lon DOUBLE,
                hs DOUBLE,
                u10 DOUBLE,
                v10 DOUBLE,
                uo DOUBLE,
                vo DOUBLE,
                sst_anom DOUBLE,
                head_current_kn DOUBLE,
                head_wind_ms DOUBLE,
                wave_encounter_m DOUBLE
            )
            """
        )

        now = dt.datetime(2025, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        con.execute(
            """
            INSERT INTO tracklets VALUES
            ('1', 123456789, ?, ?, 12, 0.5, 12.0, 'AG', 'HORMUZ'),
            ('2', 987654321, ?, ?, 16, 1.0, 11.5, 'AG', 'HORMUZ')
            """,
            [now, now + dt.timedelta(hours=2), now, now + dt.timedelta(hours=3)],
        )
        con.execute(
            """
            INSERT INTO sea_state_samples VALUES
            ('1', ?, 25.0, 56.0, 2.0, 5.0, 1.0, 0.5, 0.2, 0.1, 1.2, 0.8, 2.0),
            ('2', ?, 25.1, 56.2, 3.5, 4.0, 1.5, 0.8, 0.4, 0.2, -0.5, 1.1, 3.5)
            """,
            [now, now + dt.timedelta(minutes=20)],
        )

        inserted = compute_sis_daily(con, SISConfig())
        assert inserted == 1

        rows = con.execute("SELECT corridor_id, sis_mean, n_samples FROM sea_state_daily").fetchall()
        assert len(rows) == 1
        corridor_id, sis_mean, n_samples = rows[0]
        assert corridor_id == "AG->HORMUZ"
        assert n_samples == 2
        assert 0.0 < sis_mean < 1.0
    finally:
        con.close()
