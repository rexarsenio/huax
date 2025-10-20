"""
Construct SPVX-Lite component features from the DuckDB staging area.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from spvx.config import AppSettings
from spvx.features.baselines import winsorize, zscore_doy
from spvx.validation.components import validate_components

ANTWERP_CODES = (
    "antwerp",
    "antwerp_bruges",
    "zeebrugge",
    "beanr",
    "beanz",
)


def _connect() -> duckdb.DuckDBPyConnection:
    settings = AppSettings()
    path = Path(settings.duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def _turkish_components(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    query = """
        select
            date(ts) as date,
            sum(closure_minutes) as closure_minutes,
            avg(wait_hours) as wait_hours
        from turkish_events
        group by 1
        order by 1
    """
    df = con.execute(query).df()
    if df.empty:
        return df

    df["closure_z"] = zscore_doy(df, "closure_minutes", "date")
    df["wait_z"] = zscore_doy(df, "wait_hours", "date")
    df["CQ_TR"] = winsorize((df["closure_z"] + df["wait_z"]) / 2.0)
    return df[["date", "CQ_TR"]]


def _mpa_components(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    query = """
        select
            date(ts) as date,
            sum(case when lower(vessel_type) like '%tanker%' then vessels else 0 end) as tanker_moves,
            sum(vessels) as total_moves
        from mpa_moves
        group by 1
        order by 1
    """
    df = con.execute(query).df()
    if df.empty:
        return df
    df["CQ_SG"] = winsorize(zscore_doy(df, "tanker_moves", "date"))
    return df[["date", "CQ_SG"]]


def _rotterdam_components(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    query = """
        select
            date(ts) as date,
            sum(case when event='departure' then vessels else 0 end) as dep_total,
            sum(case when event='departure' and is_tanker then vessels else 0 end) as dep_tankers
        from rotterdam_calls
        group by 1
        order by 1
    """
    df = con.execute(query).df()
    if df.empty:
        return df
    df["PORT_EU"] = winsorize(-zscore_doy(df, "dep_tankers", "date"))
    return df[["date", "PORT_EU"]]


def _portstays_components(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    query = """
        select
            d as date,
            sum(tanker_departures) as tanker_departures
        from portstays_daily
        where lower(port_code) in ({placeholders})
        group by 1
        order by 1
    """
    placeholders = ", ".join(["?"] * len(ANTWERP_CODES))
    df = con.execute(
        query.format(placeholders=placeholders),
        [code.lower() for code in ANTWERP_CODES],
    ).df()
    if df.empty:
        return df
    df["PORT_EU"] = winsorize(-zscore_doy(df, "tanker_departures", "date"))
    return df[["date", "PORT_EU"]]


def _ais_dwell_components(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Aggregate chokepoint dwell data from AIS stream.
    Higher slow_count = more congestion = positive CQ signal.
    """
    query = """
        select
            date(ts) as date,
            sum(case when region = 'singapore_malacca' then slow_count else 0 end) as sg_slow,
            sum(case when region = 'suez' then slow_count else 0 end) as suez_slow,
            sum(case when region = 'bosporus' then slow_count else 0 end) as bosporus_slow,
            sum(case when region = 'hormuz' then slow_count else 0 end) as hormuz_slow,
            sum(slow_count) as total_slow
        from chokepoint_dwell
        group by 1
        order by 1
    """
    df = con.execute(query).df()
    if df.empty:
        return df

    # Create individual region components
    df["CQ_SG_AIS"] = winsorize(zscore_doy(df, "sg_slow", "date"))
    df["CQ_SUEZ"] = winsorize(zscore_doy(df, "suez_slow", "date"))
    df["CQ_BOSPORUS"] = winsorize(zscore_doy(df, "bosporus_slow", "date"))
    df["CQ_HORMUZ"] = winsorize(zscore_doy(df, "hormuz_slow", "date"))

    # Composite chokepoint signal
    df["CQ_CHOKE"] = winsorize(zscore_doy(df, "total_slow", "date"))

    return df[["date", "CQ_SG_AIS", "CQ_SUEZ", "CQ_BOSPORUS", "CQ_HORMUZ", "CQ_CHOKE"]]


def _sea_state_components(chokepoint_id: str) -> pd.DataFrame:
    """
    Load sea-state data (waves & currents) for a chokepoint and compute features.
    Returns DataFrame with date, SEA_HS_Z, OPPOSING_CURRENT columns.
    """
    import numpy as np

    f = Path(f"data/processed/sea_state_{chokepoint_id}.parquet")
    if not f.exists():
        return pd.DataFrame(columns=["date", "SEA_HS_Z", "OPPOSING_CURRENT"])

    ss = pd.read_parquet(f)
    if ss.empty:
        return pd.DataFrame(columns=["date", "SEA_HS_Z", "OPPOSING_CURRENT"])

    ss["time"] = pd.to_datetime(ss["time"], utc=True)
    ss = ss.set_index("time").sort_index()

    # Resample to daily (mean of sub-daily observations)
    daily = ss.resample("1D").mean().reset_index()
    daily["date"] = daily["time"].dt.date
    daily = daily.drop(columns=["time"])

    # Compute seasonal Z-score for wave height
    if "hs" in daily.columns:
        daily["SEA_HS_Z"] = _seasonal_z_score(daily, "hs", "date")
    else:
        daily["SEA_HS_Z"] = 0.0

    # Opposing current (already in m/s, optionally z-score it too)
    if "opp_current" in daily.columns:
        daily["OPPOSING_CURRENT"] = daily["opp_current"]
    else:
        daily["OPPOSING_CURRENT"] = 0.0

    return daily[["date", "SEA_HS_Z", "OPPOSING_CURRENT"]]


def _seasonal_z_score(df: pd.DataFrame, col: str, date_col: str) -> pd.Series:
    """
    Compute day-of-year seasonal Z-scores.
    Uses simple method: for each day-of-year, compute Z-score against all observations
    from the same day-of-year across multiple years.
    """
    import numpy as np

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["doy"] = df[date_col].dt.dayofyear

    # For each DOY, compute mean and std across all years
    doy_stats = df.groupby("doy")[col].agg(["mean", "std"]).reset_index()
    doy_stats["std"] = doy_stats["std"].replace(0, np.nan)

    # Merge stats back and compute z-scores
    df_merged = df.merge(doy_stats, on="doy", how="left")
    z = (df_merged[col] - df_merged["mean"]) / df_merged["std"]

    return z.fillna(0.0)


def build_components(output_path: str | Path = "data/processed/components.parquet") -> Path:
    """
    Compute component features and persist them as a Parquet dataset.
    """
    con = _connect()
    cq_tr = _turkish_components(con)
    cq_sg = _mpa_components(con)
    port_eu = _portstays_components(con)
    if port_eu.empty:
        port_eu = _rotterdam_components(con)
    ais_dwell = _ais_dwell_components(con)

    if cq_tr.empty or cq_sg.empty or port_eu.empty:
        raise RuntimeError(
            "One or more component sources are empty. "
            "Ensure ingestion ran successfully (use mock.run() for local testing)."
        )

    # Merge all components - AIS dwell is optional
    df = cq_tr.merge(cq_sg, on="date", how="outer").merge(port_eu, on="date", how="outer")

    if not ais_dwell.empty:
        df = df.merge(ais_dwell, on="date", how="outer")

    # Attach sea-state components (optional, per chokepoint)
    # For now, we'll compute a composite sea-state signal across all chokepoints
    sea_state_dfs = []
    for cid in ["CQ_SG", "CQ_TR", "PORT_EU"]:
        ss_df = _sea_state_components(cid)
        if not ss_df.empty:
            sea_state_dfs.append(ss_df)

    if sea_state_dfs:
        # Average sea-state signals across chokepoints
        ss_combined = pd.concat(sea_state_dfs).groupby("date").mean().reset_index()
        df = df.merge(ss_combined, on="date", how="left")

    df = df.sort_values("date").ffill().dropna()

    df = validate_components(df)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    return out_path
