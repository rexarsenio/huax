import datetime as dt
from pathlib import Path

import duckdb
import pytest

from spvx.db.schema import DDL_STATEMENTS
from spvx.open_sea.aggregate import compute_aggregates
from spvx.open_sea.config import (
    CMEMSConfig,
    GateDefaults,
    OpenSeaConfig,
    SISConfig,
    SISWeights,
    SOGThresholds,
    TTLConfig,
)


def _test_config() -> OpenSeaConfig:
    return OpenSeaConfig(
        downsample_secs=60,
        hysteresis_hits=2,
        ttl_min=TTLConfig(moving=30, anchorage=90),
        sog_thresholds=SOGThresholds(dwell_max_kn=1.5),
        gates=GateDefaults(width_nm_default=0.8),
        cmems=CMEMSConfig(enabled=False, features=()),
        sis=SISConfig(weights=SISWeights(wave=0.5, head_current=0.3, head_wind=0.2), high_impact_p=0.7),
    )


def _init_schema(db_path: Path) -> None:
    con = duckdb.connect(str(db_path))
    try:
        for ddl in DDL_STATEMENTS:
            con.execute(ddl)
    finally:
        con.close()


def _insert_gate_crossings(db_path: Path) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    entry_a = now - dt.timedelta(hours=6)
    exit_a = entry_a + dt.timedelta(hours=14)
    entry_b = now - dt.timedelta(hours=8)
    exit_b = entry_b + dt.timedelta(hours=18)
    rows = [
        (111000111, "GATE_SUEZ_N_10NM", entry_a, "AtoB", 31.25, 32.15, 12.0, 180.0),
        (111000111, "GATE_SUEZ_S_10NM", exit_a, "AtoB", 30.05, 32.40, 11.5, 180.0),
        (222000222, "GATE_SUEZ_N_10NM", entry_b, "AtoB", 31.30, 32.10, 13.2, 182.0),
        (222000222, "GATE_SUEZ_S_10NM", exit_b, "AtoB", 30.00, 32.35, 12.4, 182.0),
    ]
    con = duckdb.connect(str(db_path))
    try:
        con.executemany(
            """
            INSERT INTO gate_crossings
            (mmsi, gate_id, ts, direction, lat, lon, sog, cog)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    finally:
        con.close()


def test_compute_aggregates_transit_and_flux(tmp_path):
    db_path = tmp_path / "spvx.duckdb"
    _init_schema(db_path)
    _insert_gate_crossings(db_path)

    cfg = _test_config()
    compute_aggregates(cfg, db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        flux_rows = con.execute(
            """
            SELECT window_label, gate_id, direction, crossings
            FROM gate_flux_rolling
            WHERE gate_id = 'GATE_SUEZ_N_10NM'
            """
        ).fetchall()
        assert flux_rows
        flux = {row[0]: row[3] for row in flux_rows}
        assert flux.get("24h") == 2
        assert flux.get("7d") == 2

        transit_rows = con.execute(
            """
            SELECT corridor_id, from_id, to_id, median_h, mean_h, p90_h, n
            FROM transit_times_daily
            WHERE corridor_id = 'SUEZ_SOUTHBOUND'
            """
        ).fetchall()
        assert transit_rows
        corridor_id, from_id, to_id, median_h, mean_h, p90_h, n = transit_rows[0]
        assert corridor_id == "SUEZ_SOUTHBOUND"
        assert from_id == "GATE_SUEZ_N_10NM"
        assert to_id == "GATE_SUEZ_S_10NM"
        assert n == 2
        assert median_h == pytest.approx(16.0, rel=1e-5)
        assert mean_h == pytest.approx(16.0, rel=1e-5)
        assert p90_h >= max(median_h, mean_h)
    finally:
        con.close()
