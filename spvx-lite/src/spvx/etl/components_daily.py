"""
Daily component assembly for basin-level SPVX indices.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

from spvx.db import ensure_core_tables
from spvx.features.baseline_tables import refresh_doy_baselines
from spvx.etl.portwatch import fetch_portwatch_daily, upsert_portwatch_rows

LOG = logging.getLogger(__name__)

KNOTS_TO_MPS = 0.514444

DWELL_REGIONS = {
    "CQ_SG": {"basin": "APAC", "regions": ["singapore_malacca"]},
    "CQ_HRZ": {"basin": "APAC", "regions": ["hormuz"]},
    "CQ_PAN_N": {"basin": "NAM", "regions": ["panama_n"]},
    "CQ_PAN_S": {"basin": "SAM", "regions": ["panama_s"]},
    "CQ_SUEZ": {"basin": "MED", "regions": ["suez"]},
    "CQ_GIBRALTAR": {"basin": "MED", "regions": ["gibraltar"]},
}

PORT_COMPONENTS = {
    "PORT_US": {"basin": "NAM", "ports": ["houston", "new_orleans", "south_louisiana"]},
    "PORT_BR": {"basin": "SAM", "ports": ["santos", "rio_de_janeiro"]},
    "PORT_MED": {"basin": "MED", "ports": ["augusta", "gioia_tauro", "lavera", "piraeus"]},
}

# Ports that require broader name matching in the ArcGIS source.
PORTWATCH_ALIASES = {
    "houston": ["houston", "port of houston"],
    "new_orleans": ["new orleans", "port of new orleans"],
    "south_louisiana": ["south louisiana", "port of south louisiana"],
    "santos": ["santos", "porto de santos"],
    "rio_de_janeiro": ["rio de janeiro", "porto do rio"],
    "augusta": ["augusta", "porto di augusta"],
    "gioia_tauro": ["gioia tauro", "porto di gioia tauro"],
    "lavera": ["lavera", "port de lavera"],
    "piraeus": ["piraeus", "piraiévs", "port of piraeus"],
}

BASELINE_FALLBACKS = {
    ("CQ_PAN_S", "NAM"): ("CQ_PAN_S", "SAM"),
}


def _load_dwell_daily(
    con: duckdb.DuckDBPyConnection,
) -> Tuple[Dict[Tuple[str, dt.date], float], Dict[Tuple[str, dt.date], int]]:
    df = con.execute(
        """
        SELECT
            date(window_start) AS d,
            region,
            SUM(slow_count) AS slow_sum,
            COUNT(*) AS windows
        FROM dwell_10m
        GROUP BY 1, 2
        """
    ).df()
    value_map: Dict[Tuple[str, dt.date], float] = {}
    obs_map: Dict[Tuple[str, dt.date], int] = {}
    if df.empty:
        return value_map, obs_map
    df["d"] = pd.to_datetime(df["d"]).dt.date
    for row in df.itertuples(index=False):
        key = (str(row.region), row.d)
        value_map[key] = float(row.slow_sum)
        obs_map[key] = int(row.windows)
    return value_map, obs_map


def _load_portwatch(con: duckdb.DuckDBPyConnection) -> Dict[Tuple[str, dt.date], Tuple[float, int]]:
    df = con.execute(
        """
        SELECT
            d,
            lower(port_code) AS port_code,
            SUM(COALESCE(movements, departures)) AS total_moves,
            COUNT(*) AS n_rows
        FROM portwatch_daily
        WHERE shiptype IS NULL
           OR lower(shiptype) IN ('tanker', 'oil', 'products', 'product', 'all', '')
        GROUP BY 1, 2
        """
    ).df()
    data: Dict[Tuple[str, dt.date], Tuple[float, int]] = {}
    if df.empty:
        return data
    df["d"] = pd.to_datetime(df["d"]).dt.date
    for row in df.itertuples(index=False):
        code = (str(row.port_code or ""), row.d)
        data[code] = (float(row.total_moves or 0.0), int(row.n_rows or 0))
    return data


def _load_sea_currents(
    con: duckdb.DuckDBPyConnection,
) -> Dict[Tuple[str, dt.date], Tuple[float, int, Optional[pd.Timestamp]]]:
    df = con.execute(
        """
        SELECT
            date(observed_at) AS d,
            upper(basin) AS basin,
            AVG(speed_knots) AS avg_speed_knots,
            COUNT(*) AS n_rows,
            MAX(observed_at) AS max_observed_at
        FROM sea_currents_daily
        GROUP BY 1, 2
        """
    ).df()
    data: Dict[Tuple[str, dt.date], Tuple[float, int, Optional[pd.Timestamp]]] = {}
    if df.empty:
        return data
    df["d"] = pd.to_datetime(df["d"]).dt.date
    for row in df.itertuples(index=False):
        key = (str(row.basin or "").upper(), row.d)
        ts = pd.to_datetime(row.max_observed_at) if getattr(row, "max_observed_at", None) is not None else None
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        speed_knots = float(row.avg_speed_knots or 0.0)
        data[key] = (speed_knots, int(row.n_rows or 0), ts)
    return data


def _load_sea_waves(
    con: duckdb.DuckDBPyConnection,
) -> Dict[Tuple[str, dt.date], Tuple[float, Optional[float], int, Optional[pd.Timestamp]]]:
    df = con.execute(
        """
        SELECT
            date(observed_at) AS d,
            upper(basin) AS basin,
            AVG(hs_m) AS hs_m,
            AVG(tp_s) AS tp_s,
            COUNT(*) AS n_rows,
            MAX(observed_at) AS max_observed_at
        FROM sea_waves_daily
        GROUP BY 1, 2
        """
    ).df()
    data: Dict[Tuple[str, dt.date], Tuple[float, Optional[float], int, Optional[pd.Timestamp]]] = {}
    if df.empty:
        return data
    df["d"] = pd.to_datetime(df["d"]).dt.date
    for row in df.itertuples(index=False):
        key = (str(row.basin or "").upper(), row.d)
        ts = pd.to_datetime(row.max_observed_at) if getattr(row, "max_observed_at", None) is not None else None
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        data[key] = (
            float(row.hs_m or 0.0),
            float(row.tp_s) if row.tp_s is not None else None,
            int(row.n_rows or 0),
            ts,
        )
    return data


def _load_weather_flags(con: duckdb.DuckDBPyConnection) -> Dict[Tuple[str, dt.date], int]:
    df = con.execute(
        """
        SELECT
            date(observed_at) AS d,
            lower(region) AS region,
            MAX(COALESCE(weather_flag, 0)) AS flag
        FROM weather_observations
        GROUP BY 1, 2
        """
    ).df()
    flags: Dict[Tuple[str, dt.date], int] = {}
    if not df.empty:
        df["d"] = pd.to_datetime(df["d"]).dt.date
        for row in df.itertuples(index=False):
            flags[(str(row.region), row.d)] = int(row.flag or 0)

    # Merge currents flags
    df_curr = con.execute(
        """
        SELECT
            date(observed_at) AS d,
            lower(region) AS region,
            MAX(COALESCE(weather_flag, 0)) AS flag
        FROM sea_currents_daily
        GROUP BY 1, 2
        """
    ).df()
    if not df_curr.empty:
        df_curr["d"] = pd.to_datetime(df_curr["d"]).dt.date
        for row in df_curr.itertuples(index=False):
            key = (str(row.region), row.d)
            flags[key] = max(flags.get(key, 0), int(row.flag or 0))

    df_wave = con.execute(
        """
        SELECT
            date(observed_at) AS d,
            lower(region) AS region,
            MAX(COALESCE(weather_flag, 0)) AS flag
        FROM sea_waves_daily
        GROUP BY 1, 2
        """
    ).df()
    if not df_wave.empty:
        df_wave["d"] = pd.to_datetime(df_wave["d"]).dt.date
        for row in df_wave.itertuples(index=False):
            key = (str(row.region), row.d)
            flags[key] = max(flags.get(key, 0), int(row.flag or 0))
    return flags


def _dates_union(*maps: Dict) -> List[dt.date]:
    dates: set[dt.date] = set()
    for mapping in maps:
        dates.update(value for (_, value) in mapping.keys() if isinstance(value, dt.date))
    return sorted(dates)


def _upsert_component_inputs(
    con: duckdb.DuckDBPyConnection,
    rows: Sequence[Tuple[dt.date, str, Optional[float], Optional[int]]],
) -> None:
    if not rows:
        return
    con.executemany(
        """
        INSERT INTO component_inputs_daily (d, key, raw_value, n_obs)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (d, key) DO UPDATE SET
            raw_value = excluded.raw_value,
            n_obs = excluded.n_obs
        """,
        rows,
    )


def _fetch_baselines(con: duckdb.DuckDBPyConnection) -> Dict[Tuple[str, int], Tuple[Optional[float], Optional[float]]]:
    df = con.execute(
        """
        SELECT key, doy, mean, std
        FROM baselines_doy
        """
    ).df()
    baseline_map: Dict[Tuple[str, int], Tuple[Optional[float], Optional[float]]] = {}
    for row in df.itertuples(index=False):
        baseline_map[(str(row.key), int(row.doy))] = (row.mean, row.std)
    return baseline_map


def _lookup_baseline(
    baseline_map: Dict[Tuple[str, int], Tuple[Optional[float], Optional[float]]],
    comp: str,
    basin: str,
    doy: int,
) -> Tuple[Optional[float], Optional[float]]:
    key = f"{comp}:{basin}"
    entry = baseline_map.get((key, doy))
    if entry is not None:
        return entry
    fallback = BASELINE_FALLBACKS.get((comp, basin))
    if fallback:
        fb_key = f"{fallback[0]}:{fallback[1]}"
        return baseline_map.get((fb_key, doy), (None, None))
    return (None, None)


def _compute_z(
    value: Optional[float],
    mean: Optional[float],
    std: Optional[float],
    *,
    sign: float = 1.0,
) -> Optional[float]:
    if value is None or mean is None or std is None or std == 0:
        return None
    z = sign * (value - mean) / std
    return float(np.clip(z, -5.0, 5.0))


def _build_input_rows(
    dates: Iterable[dt.date],
    dwell_map: Dict[Tuple[str, dt.date], float],
    dwell_obs: Dict[Tuple[str, dt.date], int],
    port_map: Dict[Tuple[str, dt.date], Tuple[float, int]],
    sea_curr_map: Dict[Tuple[str, dt.date], Tuple[float, int]],
    sea_wave_map: Dict[Tuple[str, dt.date], Tuple[float, Optional[float], int]],
) -> List[Tuple[dt.date, str, Optional[float], Optional[int]]]:
    rows: List[Tuple[dt.date, str, Optional[float], Optional[int]]] = []
    for date in dates:
        for comp, cfg in DWELL_REGIONS.items():
            regions = cfg["regions"]
            for region in regions:
                raw = dwell_map.get((region, date))
                obs = dwell_obs.get((region, date))
                key = f"{comp}:{cfg['basin']}" if comp in {"CQ_SG", "CQ_HRZ", "CQ_SUEZ", "CQ_GIBRALTAR"} else None
                if comp == "CQ_PAN_N":
                    key = "CQ_PAN_N:NAM"
                elif comp == "CQ_PAN_S":
                    # store for SAM
                    key = "CQ_PAN_S:SAM"
                    rows.append((date, key, raw, obs))
                    # duplicate entry for NAM baseline to support CQ_PAN aggregation
                    rows.append((date, "CQ_PAN_S:NAM", raw, obs))
                    continue
                if key:
                    rows.append((date, key, raw, obs))

        for comp, cfg in PORT_COMPONENTS.items():
            basin = cfg["basin"]
            total = 0.0
            obs = 0
            for port_code in cfg["ports"]:
                value, count = port_map.get((port_code, date), (0.0, 0))
                total += value
                obs += count
            rows.append((date, f"{comp}:{basin}", total if obs else None, obs if obs else None))

        for basin in ("APAC", "NAM", "SAM", "MED"):
            curr_entry = sea_curr_map.get((basin, date))
            if curr_entry and curr_entry[1]:
                rows.append((date, f"SEA_CURR:{basin}", curr_entry[0], curr_entry[1]))
            wave_entry = sea_wave_map.get((basin, date))
            if wave_entry and wave_entry[2]:
                rows.append((date, f"SEA_WAVE:{basin}", wave_entry[0], wave_entry[2]))
    return rows


def _build_component_row(
    date: dt.date,
    basin: str,
    comp: str,
    raw_value: Optional[float],
    n_obs: Optional[int],
    z_value: Optional[float],
    missing_reason: Optional[str],
    weather_flag: int,
    sea_hs_z: Optional[float] = None,
    sea_opp_current: Optional[float] = None,
    sea_data_timestamp: Optional[dt.datetime] = None,
) -> Tuple[
    dt.date,
    str,
    str,
    Optional[float],
    Optional[float],
    Optional[int],
    Optional[str],
    int,
    Optional[float],
    Optional[float],
    Optional[dt.datetime],
]:
    return (
        date,
        basin,
        comp,
        z_value,
        raw_value,
        n_obs,
        missing_reason,
        weather_flag,
        sea_hs_z,
        sea_opp_current,
        sea_data_timestamp,
    )


def build_components_daily(con: duckdb.DuckDBPyConnection) -> int:
    """
    Populate components_daily table for all available history.

    Returns the number of rows written.
    """
    ensure_core_tables(con)

    # Refresh PortWatch data for configured ports if no recent records exist.
    today = dt.datetime.utcnow().date()
    cutoff = today - dt.timedelta(days=3)
    existing_ports = con.execute(
        """
        SELECT DISTINCT lower(port_code)
        FROM portwatch_daily
        WHERE d >= ?
        """,
        [cutoff],
    ).fetchall()
    existing_codes = {row[0] for row in existing_ports}

    fetched_total = 0
    for component in PORT_COMPONENTS.values():
        for canonical in component["ports"]:
            aliases = PORTWATCH_ALIASES.get(canonical, [canonical])
            if any(alias.lower().replace(" ", "_") in existing_codes for alias in aliases):
                continue
            if component["basin"] == "NAM":
                iso3 = "USA"
            elif component["basin"] == "SAM":
                iso3 = "BRA"
            elif component["basin"] == "MED":
                # Mediterranean ports - cycle through relevant countries
                iso3 = "ITA"  # Will be overridden per port below
            else:
                iso3 = "USA"  # fallback
            all_rows: List = []
            for alias in aliases:
                rows = fetch_portwatch_daily(iso3=iso3, port_like=alias)
                all_rows.extend(rows)
            if not all_rows:
                LOG.warning("No PortWatch data fetched for aliases %s", aliases)
                continue
            upsert_portwatch_rows(con, all_rows)
            fetched_total += len(all_rows)

    dwell_map, dwell_obs = _load_dwell_daily(con)
    port_map = _load_portwatch(con)
    sea_curr_map = _load_sea_currents(con)
    sea_wave_map = _load_sea_waves(con)
    weather_flags = _load_weather_flags(con)

    if not dwell_map and not port_map:
        LOG.warning("No dwell or portwatch data available; skipping component build.")
        return 0

    all_dates = _dates_union(dwell_map, port_map, sea_curr_map, sea_wave_map)
    if not all_dates:
        LOG.warning("Could not determine date range for components.")
        return 0

    input_rows = _build_input_rows(all_dates, dwell_map, dwell_obs, port_map, sea_curr_map, sea_wave_map)
    _upsert_component_inputs(con, input_rows)

    refresh_doy_baselines(con)
    baseline_map = _fetch_baselines(con)

    component_rows: List[
        Tuple[
            dt.date,
            str,
            str,
            Optional[float],
            Optional[float],
            Optional[int],
            Optional[str],
            int,
            Optional[float],
            Optional[float],
            Optional[dt.datetime],
        ]
    ] = []

    for date in all_dates:
        doy = (
            dt.date.fromisoformat(str(date)).timetuple().tm_yday if isinstance(date, str) else date.timetuple().tm_yday
        )

        # APAC components
        sg_raw = dwell_map.get(("singapore_malacca", date))
        sg_obs = dwell_obs.get(("singapore_malacca", date))
        sg_mean, sg_std = _lookup_baseline(baseline_map, "CQ_SG", "APAC", doy)
        sg_z = _compute_z(sg_raw, sg_mean, sg_std)
        sg_reason = None
        if sg_z is None:
            if sg_raw is None:
                sg_reason = "no_data"
            elif sg_std in (None, 0):
                sg_reason = "baseline_missing"
        sg_flag = weather_flags.get(("singapore_malacca", date), 0)
        component_rows.append(_build_component_row(date, "APAC", "CQ_SG", sg_raw, sg_obs, sg_z, sg_reason, sg_flag))

        hrz_raw = dwell_map.get(("hormuz", date))
        hrz_obs = dwell_obs.get(("hormuz", date))
        hrz_mean, hrz_std = _lookup_baseline(baseline_map, "CQ_HRZ", "APAC", doy)
        hrz_z = _compute_z(hrz_raw, hrz_mean, hrz_std)
        hrz_reason = None
        if hrz_z is None:
            if hrz_raw is None:
                hrz_reason = "no_data"
            elif hrz_std in (None, 0):
                hrz_reason = "baseline_missing"
        hrz_flag = weather_flags.get(("hormuz", date), 0)
        component_rows.append(
            _build_component_row(date, "APAC", "CQ_HRZ", hrz_raw, hrz_obs, hrz_z, hrz_reason, hrz_flag)
        )
        apac_flag = max(sg_flag, hrz_flag)

        # NAM components
        pan_n_raw = dwell_map.get(("panama_n", date))
        pan_n_obs = dwell_obs.get(("panama_n", date))
        pan_n_mean, pan_n_std = _lookup_baseline(baseline_map, "CQ_PAN_N", "NAM", doy)
        pan_n_z = _compute_z(pan_n_raw, pan_n_mean, pan_n_std)

        pan_s_raw = dwell_map.get(("panama_s", date))
        pan_s_obs = dwell_obs.get(("panama_s", date))
        pan_s_mean, pan_s_std = _lookup_baseline(baseline_map, "CQ_PAN_S", "NAM", doy)
        pan_s_z = _compute_z(pan_s_raw, pan_s_mean, pan_s_std)
        pan_n_flag = weather_flags.get(("panama_n", date), 0)
        pan_s_flag = weather_flags.get(("panama_s", date), 0)

        pan_reason = None
        if pan_n_z is None or pan_s_z is None:
            if pan_n_z is None and pan_n_raw is None:
                pan_reason = "no_data_panama_n"
            elif pan_s_z is None and pan_s_raw is None:
                pan_reason = "no_data_panama_s"
            else:
                pan_reason = "baseline_missing"
        pan_raw_total = None
        pan_obs_total = None
        if pan_n_raw is not None or pan_s_raw is not None:
            pan_raw_total = (pan_n_raw or 0.0) + (pan_s_raw or 0.0)
            pan_obs_total = (pan_n_obs or 0) + (pan_s_obs or 0)
        pan_z = None if pan_n_z is None or pan_s_z is None else float(np.clip((pan_n_z + pan_s_z) / 2.0, -5.0, 5.0))
        component_rows.append(
            _build_component_row(
                date, "NAM", "CQ_PAN", pan_raw_total, pan_obs_total, pan_z, pan_reason, max(pan_n_flag, pan_s_flag)
            )
        )

        port_us_total = 0.0
        port_us_count = 0
        for code in PORT_COMPONENTS["PORT_US"]["ports"]:
            value, count = port_map.get((code, date), (0.0, 0))
            port_us_total += value
            port_us_count += count
        port_us_mean, port_us_std = _lookup_baseline(baseline_map, "PORT_US", "NAM", doy)
        port_us_raw = port_us_total if port_us_count else None
        port_us_z = _compute_z(port_us_raw, port_us_mean, port_us_std, sign=-1.0)
        port_us_reason = None
        if port_us_z is None:
            if port_us_raw is None:
                port_us_reason = "no_data"
            else:
                port_us_reason = "baseline_missing"
        component_rows.append(
            _build_component_row(
                date,
                "NAM",
                "PORT_US",
                port_us_raw,
                port_us_count,
                port_us_z,
                port_us_reason,
                max(pan_n_flag, pan_s_flag),
            )
        )
        nam_flag = max(pan_n_flag, pan_s_flag)

        # SAM components
        pan_s_mean_sam, pan_s_std_sam = _lookup_baseline(baseline_map, "CQ_PAN_S", "SAM", doy)
        pan_s_z_sam = _compute_z(pan_s_raw, pan_s_mean_sam, pan_s_std_sam)
        pan_s_reason = None
        if pan_s_z_sam is None:
            if pan_s_raw is None:
                pan_s_reason = "no_data"
            else:
                pan_s_reason = "baseline_missing"
        component_rows.append(
            _build_component_row(date, "SAM", "CQ_PAN_S", pan_s_raw, pan_s_obs, pan_s_z_sam, pan_s_reason, pan_s_flag)
        )

        port_br_total = 0.0
        port_br_count = 0
        for code in PORT_COMPONENTS["PORT_BR"]["ports"]:
            value, count = port_map.get((code, date), (0.0, 0))
            port_br_total += value
            port_br_count += count
        port_br_raw = port_br_total if port_br_count else None
        port_br_mean, port_br_std = _lookup_baseline(baseline_map, "PORT_BR", "SAM", doy)
        port_br_z = _compute_z(port_br_raw, port_br_mean, port_br_std, sign=-1.0)
        port_br_reason = None
        if port_br_z is None:
            if port_br_raw is None:
                port_br_reason = "no_data"
            else:
                port_br_reason = "baseline_missing"
        component_rows.append(
            _build_component_row(
                date, "SAM", "PORT_BR", port_br_raw, port_br_count, port_br_z, port_br_reason, pan_s_flag
            )
        )
        sam_flag = pan_s_flag

        # MED components
        suez_raw = dwell_map.get(("suez", date))
        suez_obs = dwell_obs.get(("suez", date))
        suez_mean, suez_std = _lookup_baseline(baseline_map, "CQ_SUEZ", "MED", doy)
        suez_z = _compute_z(suez_raw, suez_mean, suez_std)
        suez_reason = None
        if suez_z is None:
            if suez_raw is None:
                suez_reason = "no_data"
            elif suez_std in (None, 0):
                suez_reason = "baseline_missing"
        suez_flag = weather_flags.get(("suez", date), 0)
        component_rows.append(
            _build_component_row(date, "MED", "CQ_SUEZ", suez_raw, suez_obs, suez_z, suez_reason, suez_flag)
        )

        gib_raw = dwell_map.get(("gibraltar", date))
        gib_obs = dwell_obs.get(("gibraltar", date))
        gib_mean, gib_std = _lookup_baseline(baseline_map, "CQ_GIBRALTAR", "MED", doy)
        gib_z = _compute_z(gib_raw, gib_mean, gib_std)
        gib_reason = None
        if gib_z is None:
            if gib_raw is None:
                gib_reason = "no_data"
            elif gib_std in (None, 0):
                gib_reason = "baseline_missing"
        gib_flag = weather_flags.get(("gibraltar", date), 0)
        component_rows.append(
            _build_component_row(date, "MED", "CQ_GIBRALTAR", gib_raw, gib_obs, gib_z, gib_reason, gib_flag)
        )

        port_med_total = 0.0
        port_med_count = 0
        for code in PORT_COMPONENTS["PORT_MED"]["ports"]:
            value, count = port_map.get((code, date), (0.0, 0))
            port_med_total += value
            port_med_count += count
        port_med_mean, port_med_std = _lookup_baseline(baseline_map, "PORT_MED", "MED", doy)
        port_med_raw = port_med_total if port_med_count else None
        port_med_z = _compute_z(port_med_raw, port_med_mean, port_med_std, sign=-1.0)
        port_med_reason = None
        if port_med_z is None:
            if port_med_raw is None:
                port_med_reason = "no_data"
            else:
                port_med_reason = "baseline_missing"
        component_rows.append(
            _build_component_row(
                date,
                "MED",
                "PORT_MED",
                port_med_raw,
                port_med_count,
                port_med_z,
                port_med_reason,
                max(suez_flag, gib_flag),
            )
        )
        med_flag = max(suez_flag, gib_flag)

        # Sea-state components
        for basin, flag_value in (("APAC", apac_flag), ("NAM", nam_flag), ("SAM", sam_flag), ("MED", med_flag)):
            curr_entry = sea_curr_map.get((basin, date))
            if curr_entry and curr_entry[1]:
                curr_raw = curr_entry[0]
                curr_obs = curr_entry[1]
                curr_ts = curr_entry[2]
                curr_mean, curr_std = _lookup_baseline(baseline_map, "SEA_CURR", basin, doy)
                curr_z = _compute_z(curr_raw, curr_mean, curr_std)
                component_rows.append(
                    _build_component_row(
                        date,
                        basin,
                        "SEA_CURR",
                        curr_raw,
                        curr_obs,
                        curr_z,
                        None if curr_z is not None else "baseline_missing",
                        flag_value,
                        sea_opp_current=curr_raw * KNOTS_TO_MPS if curr_raw is not None else None,
                        sea_data_timestamp=curr_ts,
                    )
                )

            wave_entry = sea_wave_map.get((basin, date))
            if wave_entry and wave_entry[2]:
                wave_raw = wave_entry[0]
                wave_obs = wave_entry[2]
                wave_ts = wave_entry[3]
                wave_mean, wave_std = _lookup_baseline(baseline_map, "SEA_WAVE", basin, doy)
                wave_z = _compute_z(wave_raw, wave_mean, wave_std)
                component_rows.append(
                    _build_component_row(
                        date,
                        basin,
                        "SEA_WAVE",
                        wave_raw,
                        wave_obs,
                        wave_z,
                        None if wave_z is not None else "baseline_missing",
                        flag_value,
                        sea_hs_z=wave_z,
                        sea_data_timestamp=wave_ts,
                    )
                )

    con.executemany(
        """
        INSERT INTO components_daily (
            d,
            basin,
            comp,
            z_value,
            raw_value,
            n_obs,
            missing_reason,
            weather_flag,
            sea_hs_z,
            sea_opp_current,
            sea_data_timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (d, basin, comp) DO UPDATE SET
            z_value = excluded.z_value,
            raw_value = excluded.raw_value,
            n_obs = excluded.n_obs,
            missing_reason = excluded.missing_reason,
            weather_flag = excluded.weather_flag,
            sea_hs_z = excluded.sea_hs_z,
            sea_opp_current = excluded.sea_opp_current,
            sea_data_timestamp = excluded.sea_data_timestamp
        """,
        component_rows,
    )

    LOG.info("Upserted %s component rows across %s dates.", len(component_rows), len(all_dates))
    return len(component_rows)
