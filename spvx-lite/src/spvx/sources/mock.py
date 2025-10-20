"""
Mock data generator so the full pipeline can run without external feeds.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from spvx.config import AppSettings
from spvx.db import ensure_core_tables


RNG = np.random.default_rng(42)


def _make_turkish_events(start: datetime, days: int) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=days, freq="D")
    closure_minutes = np.clip(RNG.normal(loc=180, scale=75, size=days), 0, None)
    wait_hours = np.clip(RNG.normal(loc=6, scale=2.5, size=days), 0, None)
    df = pd.DataFrame({"d": idx, "closure_minutes": closure_minutes, "wait_hours": wait_hours})
    df["ts"] = df["d"] + pd.to_timedelta(RNG.integers(0, 12, size=days), unit="h")
    df = df.drop(columns="d")
    return df


def _make_mpa_moves(start: datetime, days: int) -> pd.DataFrame:
    rows = []
    for day in range(days):
        base_ts = start + timedelta(days=day)
        daily_tankers = RNG.integers(30, 70)
        for i in range(5):
            ts = base_ts + timedelta(hours=int(i * 4 + RNG.integers(0, 2)))
            tanker_share = 0.6 + RNG.normal(0, 0.1)
            tanker_events = max(int(daily_tankers * tanker_share / 5 + RNG.integers(-2, 3)), 0)
            rows.append(
                {
                    "ts": ts,
                    "vessel_type": "tanker" if i % 2 == 0 else "container",
                    "movement": RNG.choice(["arrival", "departure"]),
                    "vessels": tanker_events,
                }
            )
    return pd.DataFrame(rows)


def _make_rotterdam_calls(start: datetime, days: int) -> pd.DataFrame:
    rows = []
    for day in range(days):
        base_ts = start + timedelta(days=day)
        dep = RNG.integers(20, 55)
        arr = RNG.integers(20, 55)
        tanker_ratio = np.clip(0.5 + RNG.normal(scale=0.1), 0.2, 0.8)
        for event, count in [("departure", dep), ("arrival", arr)]:
            rows.append(
                {
                    "ts": base_ts + timedelta(hours=int(RNG.integers(0, 20))),
                    "event": event,
                    "vessels": count,
                    "is_tanker": event == "departure" and RNG.random() < tanker_ratio,
                }
            )
    return pd.DataFrame(rows)


def _make_port_operations(start: datetime, hours: int) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=hours, freq="h")
    tug_ops = RNG.poisson(4, size=hours)
    pilot_ops = RNG.poisson(6, size=hours)
    departures = np.clip(RNG.poisson(3, size=hours) + (tug_ops > 3), 0, None)
    df = pd.DataFrame(
        {
            "ts": idx,
            "tug_ops": tug_ops,
            "pilot_ops": pilot_ops,
            "departures": departures,
        }
    )
    return df


def _make_dwell_windows(start: datetime, days: int) -> pd.DataFrame:
    regions = [
        ("singapore_malacca", 18),
        ("hormuz", 14),
        ("panama_n", 12),
        ("panama_s", 10),
    ]
    windows = pd.date_range(start=start, periods=days * 144, freq="10min")
    rows = []
    for region, lam in regions:
        seasonal = np.sin(np.linspace(0, 6 * np.pi, len(windows))) * 0.2
        baseline = lam * (1 + seasonal)
        counts = np.clip(RNG.poisson(lam=np.maximum(baseline, 1e-2)), 0, None)
        for ts, slow_count in zip(windows, counts, strict=True):
            rows.append(
                {
                    "window_start": ts,
                    "region": region,
                    "slow_count": int(slow_count),
                }
            )
    return pd.DataFrame(rows)


def _make_portwatch_daily(start: datetime, days: int) -> pd.DataFrame:
    ports = [
        ("Houston", "houston", "USA", 68),
        ("New Orleans", "new_orleans", "USA", 42),
        ("South Louisiana", "south_louisiana", "USA", 55),
        ("Santos", "santos", "BRA", 50),
        ("Rio de Janeiro", "rio_de_janeiro", "BRA", 35),
    ]
    idx = pd.date_range(start=start, periods=days, freq="D")
    rows = []
    for date in idx:
        for name, code, iso3, base in ports:
            seasonal = 1 + 0.1 * np.sin((date.timetuple().tm_yday / 365) * 2 * np.pi)
            movements = max(base * seasonal + RNG.normal(0, base * 0.05), 1)
            departures = max(movements * (0.6 + RNG.normal(0, 0.05)), 0)
            arrivals = max(movements * (0.4 + RNG.normal(0, 0.04)), 0)
            rows.append(
                {
                    "d": date.date(),
                    "portname": name,
                    "port_code": code,
                    "iso3": iso3,
                    "shiptype": "tanker",
                    "departures": departures,
                    "arrivals": arrivals,
                    "movements": movements,
                    "source": "mock",
                }
            )
    return pd.DataFrame(rows)


def _write_market_data(project_root: Path, start: datetime, days: int) -> None:
    idx = pd.date_range(start=start, periods=days, freq="D")
    spread = 0.25 + np.cumsum(RNG.normal(scale=0.01, size=days))
    data = pd.DataFrame({"date": idx, "spread": spread})
    market_path = project_root / "data" / "market"
    market_path.mkdir(parents=True, exist_ok=True)
    data.to_csv(market_path / "brent_spread.csv", index=False)


def _write_throughput_data(project_root: Path, start: datetime, days: int) -> None:
    idx = pd.date_range(start=start, periods=days, freq="D")
    throughput = 250 + np.cumsum(RNG.normal(scale=5, size=days))
    df = pd.DataFrame({"date": idx, "throughput": throughput})
    ports_path = project_root / "data" / "ports"
    ports_path.mkdir(parents=True, exist_ok=True)
    df.to_csv(ports_path / "rotterdam_throughput.csv", index=False)


def run(days: int = 420) -> None:
    """
    Populate DuckDB and CSV fixtures with synthetic but structured data.
    """
    settings = AppSettings()
    duckdb_path = Path(settings.duckdb_path)
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    con = duckdb.connect(str(duckdb_path))
    con.execute("PRAGMA threads=4")
    ensure_core_tables(con)

    turkish_events = _make_turkish_events(start_date, days)
    mpa_moves = _make_mpa_moves(start_date, days)
    rotterdam_calls = _make_rotterdam_calls(start_date, days)
    port_ops = _make_port_operations(start_date, days * 24)
    dwell_windows = _make_dwell_windows(start_date, days)
    portwatch_daily = _make_portwatch_daily(start_date, days)

    con.execute("drop table if exists turkish_events")
    con.execute("drop table if exists mpa_moves")
    con.execute("drop table if exists rotterdam_calls")
    con.execute("drop table if exists port_ops_hourly")
    con.execute("delete from dwell_10m")
    con.execute("delete from portwatch_daily")
    con.execute("delete from component_inputs_daily")
    con.execute("delete from components_daily")
    con.execute("delete from spvx_basin_daily")
    con.execute("delete from spvx_global_daily")

    con.register("turkish_events_df", turkish_events)
    con.register("mpa_moves_df", mpa_moves)
    con.register("rotterdam_calls_df", rotterdam_calls)
    con.register("port_ops_hourly_df", port_ops)
    con.register("dwell_windows_df", dwell_windows)
    con.register("portwatch_daily_df", portwatch_daily)

    con.execute("create table turkish_events as select * from turkish_events_df")
    con.execute("create table mpa_moves as select * from mpa_moves_df")
    con.execute("create table rotterdam_calls as select * from rotterdam_calls_df")
    con.execute("create table port_ops_hourly as select * from port_ops_hourly_df")
    con.execute("insert into dwell_10m select * from dwell_windows_df")
    con.execute(
        """
        insert into portwatch_daily (d, portname, port_code, iso3, shiptype, departures, arrivals, movements, source)
        select d, portname, port_code, iso3, shiptype, departures, arrivals, movements, source
        from portwatch_daily_df
        """
    )

    project_root = Path(__file__).resolve().parents[3]
    _write_market_data(project_root, start_date, days)
    _write_throughput_data(project_root, start_date, days)

    con.close()
