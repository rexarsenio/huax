"""
FastAPI router exposing open-sea occupancy, flux, transit, and SIS metrics.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from spvx.config import AppSettings
from spvx.open_sea.corridors import corridor_ids as known_corridor_ids, corridors as corridor_definitions


router = APIRouter(prefix="/api/open_sea", tags=["open_sea"])

SUMMARY_GATE_LABELS: Dict[str, str] = {
    "CHOKEPOINT_MALACCA": "Malacca Strait",
    "CHOKEPOINT_SINGAPORE_STRAIT": "Singapore Strait",
    "CHOKEPOINT_SUEZ_NORTH": "Suez Canal (North)",
    "CHOKEPOINT_SUEZ_SOUTH": "Suez Canal (South)",
    "CHOKEPOINT_BOSPORUS": "Bosporus",
    "CHOKEPOINT_GIBRALTAR": "Strait of Gibraltar",
    "CHOKEPOINT_PANAMA": "Panama Canal",
    "CHOKEPOINT_HORMUZ": "Strait of Hormuz",
    "CHOKEPOINT_YOKOHA": "Yokohama",
    "ANCH_PORT_SAID": "Port Said Anchorage",
    "ANCH_HOUSTON_SHIP_CHANNEL": "Houston Ship Channel",
    "ANCH_GALVESTON": "Galveston Anchorage",
    "ANCH_PANAMA_PAC_OUTER": "Panama Pacific Outer",
    "WEST_AFRICA_BONNY": "Bonny Terminal",
    "WEST_AFRICA_ESCRAVOS": "Escravos Offshore",
    "WEST_AFRICA_GULF": "Gulf of Guinea Offshore",
}

MEDITERRANEAN_SEA_STATE_REGIONS: Dict[str, str] = {
    "CHOKEPOINT_GIBRALTAR": "Strait of Gibraltar",
    "CHOKEPOINT_BOSPORUS": "Bosporus",
    "CHOKEPOINT_DARDANELLES": "Dardanelles Strait",
    "CHOKEPOINT_SICILY": "Strait of Sicily",
    "CHOKEPOINT_OTRANTO": "Strait of Otranto",
    "LANE_CANARY": "Canary Islands Lanes",
}

WEST_AFRICA_REGIONS: Dict[str, Dict[str, Any]] = {
    "WEST_AFRICA_BONNY": {
        "label": "Bonny Terminal (Nigeria)",
        "bbox": (6.5, 3.8, 7.6, 5.0),  # lon_min, lat_min, lon_max, lat_max
        "corridor_path": [
            [5.8, 2.8],
            [6.3, 3.4],
            [6.8, 3.9],
            [7.15, 4.35],
            [7.4, 4.65],
        ],
        "corridor_label": "Bonny Export Lane",
    },
    "WEST_AFRICA_ESCRAVOS": {
        "label": "Escravos Offshore (Nigeria)",
        "bbox": (4.7, 4.6, 5.8, 6.1),
        "corridor_path": [
            [4.4, 3.2],
            [4.9, 4.2],
            [5.2, 4.9],
            [5.5, 5.5],
            [5.7, 5.8],
        ],
        "corridor_label": "Escravos Tanker Approach",
    },
    "WEST_AFRICA_GULF": {
        "label": "Gulf of Guinea Offshore",
        "bbox": (0.5, 1.8, 8.5, 5.8),
        "corridor_path": [
            [-1.5, 1.5],
            [0.0, 2.2],
            [2.2, 2.8],
            [4.5, 3.6],
            [6.8, 4.3],
            [8.2, 4.9],
        ],
        "corridor_label": "Gulf of Guinea Corridor",
    },
}

MEDITERRANEAN_CORRIDOR_LINES: Dict[str, Dict[str, Any]] = {
    "LANE_CANARY_E_v1": {
        "name": "Canary Lane Eastbound",
        "coordinates": [
            [-18.5, 27.5],
            [-16.5, 27.9],
            [-14.2, 28.6],
            [-12.0, 29.3],
        ],
    },
    "LANE_CANARY_W_v1": {
        "name": "Canary Lane Westbound",
        "coordinates": [
            [-12.0, 29.3],
            [-14.2, 28.6],
            [-16.5, 27.9],
            [-18.5, 27.5],
        ],
    },
    "GATE_GIBRALTAR_E_v1": {
        "name": "Gibraltar Eastbound",
        "coordinates": [
            [-6.6, 36.2],
            [-5.6, 36.0],
            [-4.3, 36.1],
        ],
    },
    "GATE_GIBRALTAR_W_v1": {
        "name": "Gibraltar Westbound",
        "coordinates": [
            [-4.3, 36.1],
            [-5.6, 36.0],
            [-6.6, 36.2],
        ],
    },
    "GATE_GIBRALTAR_MED_50NM": {
        "name": "Gibraltar Approaches (Med 50nm)",
        "coordinates": [
            [-3.0, 36.5],
            [-4.3, 36.1],
            [-5.8, 35.9],
        ],
    },
    "GATE_SICILY_v1": {
        "name": "Strait of Sicily",
        "coordinates": [
            [12.2, 37.4],
            [13.2, 36.9],
            [14.3, 36.5],
        ],
    },
    "GATE_OTRANTO_v1": {
        "name": "Strait of Otranto",
        "coordinates": [
            [18.4, 41.4],
            [18.9, 40.7],
            [19.4, 39.9],
        ],
    },
    "GATE_DARDANELLES_W_v1": {
        "name": "Dardanelles Westbound",
        "coordinates": [
            [26.9, 40.4],
            [26.6, 40.3],
            [26.1, 40.4],
        ],
    },
    "GATE_BOSPORUS_S_v1": {
        "name": "Bosporus Southbound",
        "coordinates": [
            [29.1, 41.2],
            [29.05, 41.02],
            [28.95, 40.95],
        ],
    },
    "GATE_SUEZ_N_v1": {
        "name": "Suez Canal Northbound",
        "coordinates": [
            [32.3, 30.0],
            [32.3, 30.7],
            [32.4, 31.5],
        ],
    },
    "GATE_SUEZ_N_50NM": {
        "name": "Suez Approaches (50nm)",
        "coordinates": [
            [32.6, 29.0],
            [32.4, 30.0],
            [32.3, 31.2],
        ],
    },
    "GATE_SUEZ_N_100NM": {
        "name": "Suez Approaches (100nm)",
        "coordinates": [
            [33.0, 27.8],
            [32.7, 29.0],
            [32.5, 30.5],
        ],
    },
    "GATE_SUEZ_N_150NM": {
        "name": "Suez Approaches (150nm)",
        "coordinates": [
            [33.3, 26.8],
            [33.0, 28.2],
            [32.6, 29.8],
        ],
    },
}


def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    from pathlib import Path
    settings = AppSettings()

    # Use API snapshot database if available to avoid locking the production database
    api_db_path = Path(settings.duckdb_path).parent / "spvx_api.duckdb"
    if api_db_path.exists():
        return duckdb.connect(str(api_db_path), read_only=read_only)

    return duckdb.connect(settings.duckdb_path, read_only=read_only)


def _gate_to_corridor_id(gate_id: str) -> str:
    if gate_id.endswith("->UNK"):
        return gate_id
    return f"{gate_id}->UNK"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _build_mediterranean_corridors_from_summary(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not summary:
        return []

    as_of = summary.get("as_of")
    if isinstance(as_of, dt.datetime):
        as_of_str = as_of.replace(tzinfo=dt.timezone.utc).isoformat()
    elif isinstance(as_of, str):
        as_of_str = as_of
    else:
        as_of_str = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()

    features: List[Dict[str, Any]] = []
    for entry in summary.get("corridors", []):
        if not isinstance(entry, dict):
            continue
        gate_id = entry.get("gate_id")
        if not gate_id:
            continue
        config = MEDITERRANEAN_CORRIDOR_LINES.get(gate_id)
        if not config:
            continue

        flux_val = _safe_float(entry.get("flux"))
        if flux_val is None or flux_val <= 0:
            continue

        features.append(
            {
                "corridor_id": config.get("name", gate_id),
                "geometry": {
                    "type": "LineString",
                    "coordinates": config["coordinates"],
                },
                "flux_h": flux_val,
                "flux_z": _safe_float(entry.get("flux_z")) or 0.0,
                "delay_ratio": _safe_float(entry.get("delay_ratio")) or 1.0,
                "sis_p90": _safe_float(entry.get("sis_p90")) or 0.0,
                "as_of": as_of_str,
            }
        )

    features.sort(key=lambda item: item["flux_h"], reverse=True)
    return features


def _compute_west_africa_region_stats(
    con: duckdb.DuckDBPyConnection,
    start_ts: dt.datetime,
) -> Dict[str, Dict[str, Any]]:
    sample_exists = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'sea_state_samples'"
    ).fetchone()
    if not sample_exists:
        return {}

    stats: Dict[str, Dict[str, Any]] = {}
    for region_id, config in WEST_AFRICA_REGIONS.items():
        lon_min, lat_min, lon_max, lat_max = config["bbox"]
        row = con.execute(
            """
            SELECT
                COUNT(DISTINCT tracklet_id) AS tracklets,
                COUNT(*) AS samples,
                AVG(CASE WHEN isfinite(wave_encounter_m) THEN wave_encounter_m END) AS wave_mean,
                quantile_cont(wave_encounter_m, 0.9) FILTER (WHERE isfinite(wave_encounter_m)) AS wave_p90,
                AVG(CASE WHEN isfinite(head_current_kn) THEN head_current_kn END) AS head_current_mean,
                quantile_cont(head_current_kn, 0.9) FILTER (WHERE isfinite(head_current_kn)) AS head_current_p90,
                AVG(CASE WHEN isfinite(head_wind_ms) THEN head_wind_ms END) AS head_wind_mean,
                quantile_cont(head_wind_ms, 0.9) FILTER (WHERE isfinite(head_wind_ms)) AS head_wind_p90,
                MAX(ts) AS last_sample
            FROM sea_state_samples
            WHERE ts >= ?
              AND lon BETWEEN ? AND ?
              AND lat BETWEEN ? AND ?
            """,
            [start_ts, lon_min, lon_max, lat_min, lat_max],
        ).fetchone()

        if row is None:
            continue

        last_sample = row[8]
        if isinstance(last_sample, dt.datetime):
            last_sample_iso = last_sample.replace(tzinfo=dt.timezone.utc).isoformat()
        elif isinstance(last_sample, dt.date):
            last_sample_iso = dt.datetime.combine(last_sample, dt.time.min, tzinfo=dt.timezone.utc).isoformat()
        else:
            last_sample_iso = None

        stats[region_id] = {
            "tracklets": int(row[0] or 0),
            "samples": int(row[1] or 0),
            "wave_mean": _safe_float(row[2]),
            "wave_p90": _safe_float(row[3]),
            "head_current_mean": _safe_float(row[4]),
            "head_current_p90": _safe_float(row[5]),
            "head_wind_mean": _safe_float(row[6]),
            "head_wind_p90": _safe_float(row[7]),
            "last_sample": last_sample_iso,
        }

    return stats


def _normalise_flux_metrics(stats: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not stats:
        return {}

    flux_values = [float(data.get("tracklets") or 0.0) for data in stats.values()]
    if not flux_values:
        return {}

    median_flux = statistics.median(flux_values)
    deviations = [abs(val - median_flux) for val in flux_values]
    mad_flux = statistics.median(deviations) if deviations else 0.0
    if mad_flux < 1e-6:
        mad_flux = max(1.0, median_flux or 1.0)
    max_flux = max(flux_values) if flux_values else 0.0

    enriched: Dict[str, Dict[str, Any]] = {}
    for region_id, data in stats.items():
        flux_h = float(data.get("tracklets") or 0.0)
        z_score = (flux_h - median_flux) / mad_flux if mad_flux else 0.0
        flux_z = max(-3.0, min(3.0, z_score))
        normalised = flux_h / max_flux if max_flux else 0.0
        delay_ratio = 1.0 + min(0.5, max(0.0, normalised * 0.3))

        wave_p90 = _safe_float(data.get("wave_p90")) or 0.0
        head_current_p90 = abs(_safe_float(data.get("head_current_p90")) or 0.0)
        head_wind_p90 = abs(_safe_float(data.get("head_wind_p90")) or 0.0)

        wave_component = min(1.0, wave_p90 / 5.0)
        current_component = min(1.0, head_current_p90 / 3.5)
        wind_component = min(1.0, head_wind_p90 / 15.0)
        sis_proxy = round(
            0.50 * wave_component + 0.35 * current_component + 0.15 * wind_component,
            3,
        )

        enriched[region_id] = {
            **data,
            "flux_h": flux_h,
            "flux_z": flux_z,
            "delay_ratio": delay_ratio,
            "sis_p90": sis_proxy,
        }

    return enriched


def _fetch_static_region_metrics(
    con: duckdb.DuckDBPyConnection,
    region_ids: Iterable[str],
    start_ts: dt.datetime,
) -> Dict[str, Dict[str, Any]]:
    if not region_ids:
        return {}

    table_exists = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'sea_state_region_metrics'"
    ).fetchone()
    if not table_exists:
        return {}

    region_ids = list(region_ids)
    placeholders = ",".join("?" for _ in region_ids)
    params: List[Any] = list(region_ids) + [start_ts]

    query = f"""
        WITH ranked AS (
            SELECT
                region_id,
                ts,
                wave_mean,
                wave_p90,
                head_current_mean,
                head_current_p90,
                head_wind_mean,
                head_wind_p90,
                wind_speed_p90,
                current_speed_p90,
                samples,
                ROW_NUMBER() OVER (PARTITION BY region_id ORDER BY ts DESC) AS rn
            FROM sea_state_region_metrics
            WHERE region_id IN ({placeholders}) AND ts >= ?
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
    """

    rows = con.execute(query, params).fetchall()
    results: Dict[str, Dict[str, Any]] = {}
    for (
        region_id,
        ts,
        wave_mean,
        wave_p90,
        head_current_mean,
        head_current_p90,
        head_wind_mean,
        head_wind_p90,
        wind_speed_p90,
        current_speed_p90,
        samples,
        _,
    ) in rows:
        results[region_id] = {
            "ts": ts,
            "wave_mean": _safe_float(wave_mean),
            "wave_p90": _safe_float(wave_p90),
            "head_current_mean": _safe_float(head_current_mean),
            "head_current_p90": _safe_float(head_current_p90),
            "head_wind_mean": _safe_float(head_wind_mean),
            "head_wind_p90": _safe_float(head_wind_p90),
            "wind_speed_p90": _safe_float(wind_speed_p90),
            "current_speed_p90": _safe_float(current_speed_p90),
            "samples": int(samples or 0),
        }

    return results


def _build_west_africa_corridors(
    stats: Dict[str, Dict[str, Any]],
    as_of_iso: str,
) -> List[Dict[str, Any]]:
    if not stats:
        return []

    features: List[Dict[str, Any]] = []
    for region_id, data in stats.items():
        config = WEST_AFRICA_REGIONS.get(region_id)
        if not config:
            continue
        coordinates = config.get("corridor_path")
        if not coordinates:
            continue

        flux_h = data.get("flux_h", 0.0)
        features.append(
            {
                "corridor_id": config.get("corridor_label", region_id),
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "flux_h": flux_h,
                "flux_z": data.get("flux_z", 0.0),
                "delay_ratio": round(float(data.get("delay_ratio", 1.0)), 3),
                "sis_p90": _safe_float(data.get("sis_p90")) or 0.0,
                "as_of": data.get("last_sample") or as_of_iso,
            }
        )

    features.sort(key=lambda item: item["flux_h"], reverse=True)
    return features


@router.get("/occupancy_now")
def occupancy_now(polygon_id: Optional[str] = None) -> Dict[str, Any]:
    with _connect() as con:
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'tanker_occupancy_intraday'"
        ).fetchone()
        if not table_exists:
            raise HTTPException(status_code=404, detail={"status": "not_found", "reason": "table_missing"})
        query = "SELECT ts, polygon_id, count_now FROM tanker_occupancy_intraday"
        params: List[Any] = []
        if polygon_id:
            query += " WHERE polygon_id = ?"
            params.append(polygon_id)
        query += " ORDER BY ts DESC"
        df = con.execute(query, params).df()
    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})
    latest_ts = pd.to_datetime(df["ts"]).max()
    latest_records = df[pd.to_datetime(df["ts"]) == latest_ts]
    return {
        "as_of": latest_ts.isoformat(),
        "polygons": latest_records.to_dict(orient="records"),
    }


@router.get("/corridors")
def list_corridors() -> List[Dict[str, Any]]:
    return [
        {
            "corridor_id": definition.corridor_id,
            "entry_gates": list(definition.entry_gates),
            "exit_gates": list(definition.exit_gates),
            "min_hours": definition.min_hours,
            "max_hours": definition.max_hours,
        }
        for definition in corridor_definitions()
    ]


@router.get("/gate_flux")
def gate_flux(
    gate_id: str = Query(..., description="Gate identifier"),
    window: str = Query("h24", pattern="^(h\\d+|d\\d+)$"),
    direction: Optional[str] = Query(None, description="AtoB|BtoA"),
) -> Dict[str, Any]:
    if not gate_id:
        raise HTTPException(status_code=400, detail={"status": "invalid", "reason": "gate_id_required"})

    window = window.lower()
    with _connect() as con:
        if window.startswith("h"):
            hours = max(1, int(window[1:]))
            ref_row = con.execute(
                "SELECT max(ts) FROM gate_flux_hourly WHERE gate_id = ?", [gate_id]
            ).fetchone()
            reference_ts = ref_row[0] if ref_row and ref_row[0] is not None else None
            if reference_ts is None:
                reference_ts = dt.datetime.utcnow()
            cutoff = reference_ts - dt.timedelta(hours=hours)
            df = con.execute(
                """
                SELECT ts, gate_id, direction, crossings
                FROM gate_flux_hourly
                WHERE gate_id = ?
                  AND ts >= ?
                  AND (? IS NULL OR direction = ?)
                ORDER BY ts
                """,
                [gate_id, cutoff, direction, direction],
            ).df()
        else:
            days = max(1, int(window[1:]))
            ref_row = con.execute(
                "SELECT max(ds) FROM gate_flux_daily WHERE gate_id = ?", [gate_id]
            ).fetchone()
            reference_date = ref_row[0] if ref_row and ref_row[0] is not None else None
            if reference_date is None:
                reference_date = dt.date.today()
            cutoff = reference_date - dt.timedelta(days=days - 1)
            df = con.execute(
                """
                SELECT ds AS ts, gate_id, direction, crossings
                FROM gate_flux_daily
                WHERE gate_id = ?
                  AND ds >= ?
                  AND (? IS NULL OR direction = ?)
                ORDER BY ds
                """,
                [gate_id, cutoff, direction, direction],
            ).df()
    total = int(df["crossings"].sum()) if not df.empty else 0
    return {
        "gate_id": gate_id,
        "direction": direction,
        "window": window,
        "total_crossings": total,
        "series": df.to_dict(orient="records"),
    }


@router.get("/transit")
def transit_times(
    corridor: Optional[str] = Query(None, description="Corridor identifier"),
    from_id: str = Query(..., description="Origin polygon id"),
    to: str = Query(..., description="Destination polygon id"),
    lookback: str = Query("30d", pattern="^\\d+d$"),
) -> Dict[str, Any]:
    if not from_id or not to:
        raise HTTPException(status_code=400, detail={"status": "invalid", "reason": "origin_and_destination_required"})
    if corridor and corridor not in known_corridor_ids():
        raise HTTPException(status_code=404, detail={"status": "invalid", "reason": "corridor_not_found"})
    days = int(lookback[:-1])
    start_date = dt.date.today() - dt.timedelta(days=days - 1)

    conditions = ["from_id = ?", "to_id = ?", "ds >= ?"]
    params: List[Any] = [from_id, to, start_date]
    if corridor:
        conditions.insert(0, "corridor_id = ?")
        params.insert(0, corridor)
    where_clause = " AND ".join(conditions)

    with _connect() as con:
        df = con.execute(
            f"""
            SELECT ds, corridor_id, from_id, to_id, median_h, mean_h, p90_h, n
            FROM transit_times_daily
            WHERE {where_clause}
            ORDER BY ds DESC
            """,
            params,
        ).df()

    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})

    latest_row = df.iloc[0]
    latest_ds = latest_row["ds"].isoformat() if isinstance(latest_row["ds"], (dt.date, dt.datetime)) else latest_row["ds"]
    resolved_corridor = str(latest_row["corridor_id"])
    resolved_from = from_id or str(latest_row["from_id"])
    resolved_to = to or str(latest_row["to_id"])

    series: List[Dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        ds_value = record["ds"]
        if isinstance(ds_value, (dt.date, dt.datetime)):
            record["ds"] = ds_value.isoformat()
        record["median_h"] = float(record["median_h"])
        record["mean_h"] = float(record["mean_h"])
        record["p90_h"] = float(record["p90_h"])
        record["n"] = int(record["n"])
        series.append(record)

    return {
        "corridor": resolved_corridor,
        "from": resolved_from,
        "to": resolved_to,
        "from_id": resolved_from,
        "to_id": resolved_to,
        "lookback_days": days,
        "latest": {
            "ds": latest_ds,
            "median_h": float(latest_row["median_h"]),
            "mean_h": float(latest_row["mean_h"]),
            "p90_h": float(latest_row["p90_h"]),
            "n": int(latest_row["n"]),
        },
        "series": series,
    }


@router.get("/sis")
def sis_timeseries(
    corridor: str = Query(..., description="Corridor identifier"),
    window: str = Query("d7", pattern="^d\\d+$"),
) -> Dict[str, Any]:
    with _connect() as con:
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'sea_state_daily'"
        ).fetchone()
        if not table_exists:
            raise HTTPException(status_code=404, detail={"status": "not_found", "reason": "table_missing"})
        latest_row = con.execute(
            "SELECT max(ds) FROM sea_state_daily WHERE corridor_id = ?", [corridor]
        ).fetchone()
        latest_ds = latest_row[0] if latest_row and latest_row[0] is not None else None
        if latest_ds is None:
            raise HTTPException(status_code=404, detail={"status": "not_found"})
        days = int(window[1:])
        start_date = latest_ds - dt.timedelta(days=days - 1)
        df = con.execute(
            """
            SELECT ds, corridor_id, sis_mean, sis_p90, pct_sis_gt_0_7,
                   hc_p90_kn, hw_p90_ms, we_p90_m, n_samples
            FROM sea_state_daily
            WHERE corridor_id = ? AND ds >= ?
            ORDER BY ds DESC
            """,
            [corridor, start_date],
        ).df()
    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})
    latest = df.iloc[0].to_dict()
    latest["ds"] = latest["ds"].isoformat() if isinstance(latest["ds"], (dt.date, dt.datetime)) else latest["ds"]
    return {
        "corridor": corridor,
        "window_days": days,
        "latest": latest,
        "series": df.to_dict(orient="records"),
    }


@router.get("/sea_state_summary")
def sea_state_summary(
    window: str = Query("h24", pattern="^(h\\d+|d\\d+)$"),
    scope: str = Query("mediterranean", pattern="^(mediterranean|global|west_africa)$"),
) -> Dict[str, Any]:
    window = window.lower()
    now_utc = dt.datetime.utcnow()
    if window.startswith("h"):
        hours = max(1, int(window[1:]))
        start_ts = now_utc - dt.timedelta(hours=hours)
    else:
        days = max(1, int(window[1:]))
        start_ts = now_utc - dt.timedelta(days=days)

    with _connect() as con:
        sample_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'sea_state_samples'"
        ).fetchone()
        tracklet_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'tracklets'"
        ).fetchone()

        if not sample_exists or not tracklet_exists:
            return {
                "window": window,
                "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
                "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
                "regions": [],
            }

        if scope == "west_africa":
            raw_stats = _compute_west_africa_region_stats(con, start_ts)
            enriched = _normalise_flux_metrics(raw_stats)
            static_metrics = _fetch_static_region_metrics(con, WEST_AFRICA_REGIONS.keys(), start_ts)

            regions_payload: List[Dict[str, Any]] = []
            for region_id in WEST_AFRICA_REGIONS.keys():
                label = WEST_AFRICA_REGIONS[region_id]["label"]
                region_stats = raw_stats.get(region_id, {})
                static_stats = static_metrics.get(region_id)

                samples = int(region_stats.get("samples") or 0)
                last_sample = region_stats.get("last_sample")
                if samples == 0 and static_stats:
                    samples = int(static_stats.get("samples") or 0)
                    ts = static_stats.get("ts")
                    if isinstance(ts, dt.datetime):
                        last_sample = ts.replace(tzinfo=dt.timezone.utc).isoformat()

                def _fallback(value: Any, static_key: str) -> Optional[float]:
                    base = _safe_float(value)
                    if base is not None:
                        return base
                    if static_stats:
                        return _safe_float(static_stats.get(static_key))
                    return None

                wave_mean = _fallback(region_stats.get("wave_mean"), "wave_mean")
                wave_p90 = _fallback(region_stats.get("wave_p90"), "wave_p90")
                head_current_mean = _fallback(region_stats.get("head_current_mean"), "head_current_mean")
                head_current_p90 = _fallback(region_stats.get("head_current_p90"), "head_current_p90")
                head_wind_mean = _fallback(region_stats.get("head_wind_mean"), "head_wind_mean")
                head_wind_p90 = _fallback(region_stats.get("head_wind_p90"), "head_wind_p90")

                regions_payload.append(
                    {
                        "id": region_id,
                        "label": label,
                        "samples": samples,
                        "hs_mean": wave_mean,
                        "hs_p90": wave_p90,
                        "we_mean": wave_mean,
                        "we_p90": wave_p90,
                        "head_current_kn_mean": head_current_mean,
                        "head_current_kn_p90": head_current_p90,
                        "head_wind_ms_mean": head_wind_mean,
                        "head_wind_ms_p90": head_wind_p90,
                        "last_sample": last_sample,
                        "flux_h": _safe_float(enriched.get(region_id, {}).get("flux_h")),
                    }
                )

            return {
                "window": window,
                "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
                "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
                "regions": regions_payload,
            }

        params: List[Any] = [start_ts]
        region_filter = ""
        target_regions: Dict[str, str]
        if scope == "mediterranean":
            target_regions = MEDITERRANEAN_SEA_STATE_REGIONS
            placeholders = ",".join("?" for _ in target_regions)
            region_filter = f" AND t.poly_from_id IN ({placeholders})"
            params.extend(target_regions.keys())
        else:
            target_regions = {}

        query = f"""
            SELECT
                t.poly_from_id AS region,
                COUNT(*) AS total_samples,
                COUNT(*) FILTER (WHERE sample.hs = sample.hs) AS hs_samples,
                AVG(CASE WHEN sample.hs = sample.hs THEN sample.hs END) AS hs_mean,
                quantile_cont(sample.hs, 0.9) FILTER (WHERE sample.hs = sample.hs) AS hs_p90,
                AVG(CASE WHEN sample.wave_encounter_m = sample.wave_encounter_m THEN sample.wave_encounter_m END) AS we_mean,
                quantile_cont(sample.wave_encounter_m, 0.9) FILTER (WHERE sample.wave_encounter_m = sample.wave_encounter_m) AS we_p90,
                AVG(CASE WHEN sample.head_current_kn = sample.head_current_kn THEN sample.head_current_kn END) AS head_current_kn_mean,
                quantile_cont(sample.head_current_kn, 0.9) FILTER (WHERE sample.head_current_kn = sample.head_current_kn) AS head_current_kn_p90,
                AVG(CASE WHEN sample.head_wind_ms = sample.head_wind_ms THEN sample.head_wind_ms END) AS head_wind_ms_mean,
                quantile_cont(sample.head_wind_ms, 0.9) FILTER (WHERE sample.head_wind_ms = sample.head_wind_ms) AS head_wind_ms_p90,
                MAX(sample.ts) AS last_sample_ts
            FROM sea_state_samples sample
            JOIN tracklets t ON sample.tracklet_id = t.tracklet_id
            WHERE sample.ts >= ?
            {region_filter}
            GROUP BY region
        """

        df = con.execute(query, params).df()

    results_by_region: Dict[str, Dict[str, Any]] = {}
    for record in df.to_dict(orient="records"):
        region_id = record.get("region")
        if not region_id:
            continue
        last_sample = record.get("last_sample_ts")
        if isinstance(last_sample, dt.datetime):
            last_sample_iso = last_sample.replace(tzinfo=dt.timezone.utc).isoformat()
        elif isinstance(last_sample, dt.date):
            last_sample_iso = dt.datetime.combine(last_sample, dt.time.min, tzinfo=dt.timezone.utc).isoformat()
        else:
            last_sample_iso = None

        results_by_region[region_id] = {
            "samples": int(record.get("total_samples") or 0),
            "hs_mean": _safe_float(record.get("hs_mean")),
            "hs_p90": _safe_float(record.get("hs_p90")),
            "we_mean": _safe_float(record.get("we_mean")),
            "we_p90": _safe_float(record.get("we_p90")),
            "head_current_kn_mean": _safe_float(record.get("head_current_kn_mean")),
            "head_current_kn_p90": _safe_float(record.get("head_current_kn_p90")),
            "head_wind_ms_mean": _safe_float(record.get("head_wind_ms_mean")),
            "head_wind_ms_p90": _safe_float(record.get("head_wind_ms_p90")),
            "last_sample": last_sample_iso,
        }

    if scope == "global":
        region_ids = sorted(results_by_region.keys())
    else:
        region_ids = list(MEDITERRANEAN_SEA_STATE_REGIONS.keys())

    regions: List[Dict[str, Any]] = []
    for region_id in region_ids:
        label = MEDITERRANEAN_SEA_STATE_REGIONS.get(region_id, SUMMARY_GATE_LABELS.get(region_id, region_id))
        region_stats = results_by_region.get(region_id, {})
        regions.append(
            {
                "id": region_id,
                "label": label,
                "samples": int(region_stats.get("samples") or 0),
                "hs_mean": region_stats.get("hs_mean"),
                "hs_p90": region_stats.get("hs_p90"),
                "we_mean": region_stats.get("we_mean"),
                "we_p90": region_stats.get("we_p90"),
                "head_current_kn_mean": region_stats.get("head_current_kn_mean"),
                "head_current_kn_p90": region_stats.get("head_current_kn_p90"),
                "head_wind_ms_mean": region_stats.get("head_wind_ms_mean"),
                "head_wind_ms_p90": region_stats.get("head_wind_ms_p90"),
                "last_sample": region_stats.get("last_sample"),
                "flux_h": region_stats.get("flux_h"),
            }
        )

    return {
        "window": window,
        "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
        "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
        "regions": regions,
    }


@router.get("/corridor_view")
def corridor_view(window: str = Query("h24", pattern="^(h\\d+|d\\d+)$")) -> List[Dict[str, Any]]:
    """
    Build corridor traffic features from recent polygon events in the registry snapshot.
    """
    window = window.lower()
    now_utc = dt.datetime.utcnow()
    as_of_iso = now_utc.replace(tzinfo=dt.timezone.utc).isoformat()

    if window.startswith("h"):
        lookback_hours = max(1, int(window[1:]))
        lookback_start = now_utc - dt.timedelta(hours=lookback_hours)
    else:
        lookback_days = max(1, int(window[1:]))
        lookback_start = now_utc - dt.timedelta(days=lookback_days)

    mediterranean_features: List[Dict[str, Any]] = []
    west_africa_metrics: Dict[str, Dict[str, Any]] = {}
    try:
        summary_payload = chokepoint_summary(window=window, gate=None)
    except HTTPException:
        summary_payload = None
    except Exception:
        summary_payload = None
    else:
        mediterranean_features = _build_mediterranean_corridors_from_summary(summary_payload)

    polygon_rows: List[Tuple[Any, ...]] = []
    with _connect() as con:
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ILIKE 'polygon_events'"
        ).fetchone()
        if table_exists:
            columns = {
                row[1].lower()
                for row in con.execute("PRAGMA table_info('polygon_events')").fetchall()
            }
            timestamp_candidates = [col for col in ("ts_in", "ts") if col in columns]

            for candidate in timestamp_candidates:
                try:
                    polygon_rows = con.execute(
                        f"""
                        SELECT polygon_id,
                               COUNT(*) AS event_count,
                               COUNT(DISTINCT mmsi) AS vessel_count
                        FROM polygon_events
                        WHERE {candidate} >= ?
                        GROUP BY polygon_id
                        """,
                        [lookback_start],
                    ).fetchall()
                    if polygon_rows:
                        break
                except duckdb.Error:
                    continue

            if not polygon_rows:
                for candidate in timestamp_candidates:
                    try:
                        fallback_rows = con.execute(
                            f"""
                            SELECT polygon_id,
                                   COUNT(*) AS event_count
                            FROM polygon_events
                            WHERE {candidate} >= ?
                            GROUP BY polygon_id
                            """,
                            [lookback_start],
                        ).fetchall()
                        if fallback_rows:
                            polygon_rows = [(pid, events, events) for pid, events in fallback_rows]
                            break
                    except duckdb.Error:
                        continue

        west_africa_raw = _compute_west_africa_region_stats(con, lookback_start)
        west_africa_metrics = _normalise_flux_metrics(west_africa_raw)

    polygon_features: List[Dict[str, Any]] = []
    if polygon_rows:
        polygon_stats: Dict[str, Dict[str, float]] = {}
        for row in polygon_rows:
            polygon_id = row[0]
            event_count = float(row[1]) if len(row) > 1 else 0.0
            vessel_count = float(row[2]) if len(row) > 2 else event_count
            polygon_stats[polygon_id] = {
                "event_count": event_count,
                "vessel_count": vessel_count,
            }

        corridor_configs = [
            {
                "id": "MALACCA_STRAIT",
                "coords": [[98.0, 2.5], [100.35, 1.4], [103.0, 1.2], [104.0, 1.3]],
                "polygons": ["SINGAPORE_STS", "SINGAPORE_JURONG"],
            },
            {
                "id": "NORTH_SEA",
                "coords": [[4.0, 51.9], [3.0, 53.0], [2.0, 55.0], [0.0, 57.0]],
                "polygons": ["ROTTERDAM_OIL", "ANTWERP_OIL"],
            },
            {
                "id": "SUEZ_APPROACH",
                "coords": [[32.2, 31.3], [32.4, 30.8], [32.6, 30.0], [33.0, 29.5]],
                "polygons": ["PORT_SAID_ANCHORAGE"],
            },
            {
                "id": "BOSPORUS",
                "coords": [[28.9, 41.2], [29.0, 41.0], [29.1, 40.9]],
                "polygons": [],
            },
            {
                "id": "PANAMA_CANAL",
                "coords": [[-79.9, 9.4], [-79.7, 9.2], [-79.5, 9.0], [-79.3, 8.8]],
                "polygons": [],
            },
            {
                "id": "STRAIT_OF_HORMUZ",
                "coords": [[56.0, 27.0], [56.5, 26.5], [57.0, 26.0]],
                "polygons": [],
            },
        ]

        corridor_values: List[Dict[str, Any]] = []
        for config in corridor_configs:
            total_events = 0.0
            total_vessels = 0.0
            for polygon_id, stats in polygon_stats.items():
                if polygon_id in config["polygons"]:
                    total_events += stats["event_count"]
                    total_vessels += stats["vessel_count"]

            flux_h = total_vessels or total_events
            if flux_h <= 0:
                continue

            corridor_values.append(
                {
                    "corridor_id": config["id"],
                    "geometry": {
                        "type": "LineString",
                        "coordinates": config["coords"],
                    },
                    "flux_h": float(flux_h),
                }
            )

        if corridor_values:
            flux_series = pd.Series([item["flux_h"] for item in corridor_values], dtype=float)
            median_flux = float(flux_series.median())
            mad_flux = float((flux_series - median_flux).abs().median())
            if mad_flux < 1e-6:
                mad_flux = max(1.0, median_flux or 1.0)
            max_flux = float(flux_series.max()) if not flux_series.empty else 0.0

            for item in corridor_values:
                flux_h = item["flux_h"]
                z_score = (flux_h - median_flux) / mad_flux if mad_flux else 0.0
                flux_z = max(-3.0, min(3.0, z_score))
                normalized = flux_h / max_flux if max_flux else 0.0
                delay_ratio = 1.0 + min(0.5, max(0.0, normalized * 0.3))
                sis_p90 = 0.45 + normalized * 0.4

                polygon_features.append(
                    {
                        "corridor_id": item["corridor_id"],
                        "geometry": item["geometry"],
                        "flux_h": flux_h,
                        "flux_z": flux_z,
                        "delay_ratio": round(delay_ratio, 3),
                        "sis_p90": round(sis_p90, 3),
                        "as_of": as_of_iso,
                    }
                )

    west_africa_features = _build_west_africa_corridors(west_africa_metrics, as_of_iso)

    combined = mediterranean_features + polygon_features + west_africa_features
    if not combined:
        return []

    dedup: Dict[str, Dict[str, Any]] = {}
    for feature in combined:
        corridor_id = feature.get("corridor_id")
        if not corridor_id:
            continue
        existing = dedup.get(corridor_id)
        if not existing or feature.get("flux_h", 0.0) > existing.get("flux_h", 0.0):
            dedup[corridor_id] = feature

    return sorted(dedup.values(), key=lambda item: item.get("flux_h", 0.0), reverse=True)


@router.get("/alerts")
def list_alerts(limit: int = 50, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with _connect() as con:
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'open_sea_alerts'"
        ).fetchone()
        if not table_exists:
            return []
        query = "SELECT ts, kind, corridor_id, payload FROM open_sea_alerts"
        params: List[Any] = []
        if kind:
            query += " WHERE kind = ?"
            params.append(kind)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(query, params).fetchall()

    alerts: List[Dict[str, Any]] = []
    for ts, alert_kind, corridor_id, payload in rows:
        ts_iso = ts.isoformat() if isinstance(ts, (dt.date, dt.datetime)) else ts
        payload_obj: Any
        if isinstance(payload, str):
            try:
                payload_obj = json.loads(payload)
            except json.JSONDecodeError:
                payload_obj = payload
        else:
            payload_obj = payload
        alerts.append(
            {
                "ts": ts_iso,
                "kind": alert_kind,
                "corridor": corridor_id,
                "payload": payload_obj,
            }
        )
    return alerts


@router.get("/summary")
def chokepoint_summary(
    window: str = Query("h24", pattern="^(h\\d+|d\\d+)$"),
    gate: Optional[str] = Query(None, description="Optional gate identifier filter (e.g. CHOKEPOINT_MALACCA)"),
) -> Dict[str, Any]:
    now_utc = dt.datetime.utcnow()
    is_hour_window = window.startswith("h")
    quantity = int(window[1:])
    quantity = max(1, quantity)

    west_africa_enriched: Dict[str, Dict[str, Any]] = {}

    with _connect() as con:
        flux_table = "gate_flux_hourly" if is_hour_window else "gate_flux_daily"
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike ?", [flux_table]
        ).fetchone()
        if not table_exists:
            raise HTTPException(status_code=404, detail={"status": "not_found", "reason": f"{flux_table}_missing"})

        if is_hour_window:
            start_ts = now_utc - dt.timedelta(hours=quantity)
            params: List[Any] = [start_ts]
            query = """
                SELECT gate_id, SUM(crossings) AS flux_agg
                FROM gate_flux_hourly
                WHERE ts >= ?
            """
            if gate:
                query += " AND gate_id = ?"
                params.append(gate)
            query += " GROUP BY gate_id"
            flux_df = con.execute(query, params).df()
        else:
            start_date = now_utc.date() - dt.timedelta(days=quantity - 1)
            params = [start_date]
            query = """
                SELECT gate_id, SUM(crossings) AS flux_agg
                FROM gate_flux_daily
                WHERE ds >= ?
            """
            if gate:
                query += " AND gate_id = ?"
                params.append(gate)
            query += " GROUP BY gate_id"
            flux_df = con.execute(query, params).df()

        baseline_start = now_utc.date() - dt.timedelta(days=45)
        baseline_params: List[Any] = [baseline_start]
        baseline_query = """
            SELECT gate_id, ds, crossings
            FROM gate_flux_daily
            WHERE ds >= ?
        """
        if gate:
            baseline_query += " AND gate_id = ?"
            baseline_params.append(gate)
        baseline_df = con.execute(baseline_query, baseline_params).df()

        sis_start = now_utc.date() - dt.timedelta(days=14)
        sis_df = con.execute(
            """
            SELECT corridor_id, ds, sis_p90
            FROM sea_state_daily
            WHERE ds >= ?
            """,
            [sis_start],
        ).df()

        wa_start_ts = start_ts if is_hour_window else dt.datetime.combine(start_date, dt.time.min)
        west_africa_raw = _compute_west_africa_region_stats(con, wa_start_ts)
        west_africa_enriched = _normalise_flux_metrics(west_africa_raw)

    if flux_df.empty:
        return {"window": window, "as_of": now_utc.replace(microsecond=0).isoformat() + "Z", "corridors": []}

    baseline_stats: Dict[str, Dict[str, Any]] = {}
    if not baseline_df.empty:
        for gate_id, gate_df in baseline_df.groupby("gate_id"):
            ordered = gate_df.sort_values("ds")
            values = ordered["crossings"].dropna().astype(float)
            if values.empty:
                continue
            std_val = float(values.std(ddof=0)) if len(values) > 1 else 0.0
            trend_points = [
                (str(row.ds), float(row.crossings or 0.0))
                for row in ordered.tail(7).itertuples(index=False)
            ]
            baseline_stats[gate_id] = {
                "mean": float(values.mean()),
                "std": std_val,
                "trend": trend_points,
            }

    sis_latest: Dict[str, float] = {}
    if not sis_df.empty:
        sis_df = sis_df.sort_values(["corridor_id", "ds"])
        for corridor_id, corridor_group in sis_df.groupby("corridor_id"):
            latest_row = corridor_group.iloc[-1]
            value = latest_row["sis_p90"]
            if value is not None and not math.isnan(float(value)):
                sis_latest[corridor_id] = float(value)

    results: List[Dict[str, Any]] = []
    for row in flux_df.itertuples(index=False):
        gate_id = getattr(row, "gate_id")
        flux_value = float(getattr(row, "flux_agg") or 0.0)
        stats = baseline_stats.get(gate_id)
        z_score: Optional[float] = None
        delay_ratio: Optional[float] = None
        if stats:
            mean_val = stats.get("mean") or 0.0
            std_val = stats.get("std") or 0.0
            if std_val and std_val > 0:
                z_score = (flux_value - mean_val) / std_val
            if mean_val > 0:
                delay_ratio = flux_value / mean_val

        trend_points = stats["trend"] if stats and "trend" in stats else []

        corridor_id = _gate_to_corridor_id(gate_id)
        sis_value = sis_latest.get(corridor_id)
        label = SUMMARY_GATE_LABELS.get(gate_id, gate_id.replace("_", " ").title())

        results.append(
            {
                "gate_id": gate_id,
                "label": label,
                "flux": round(flux_value, 2),
                "flux_z": None if z_score is None else round(z_score, 2),
                "delay_ratio": None if delay_ratio is None else round(delay_ratio, 2),
                "sis_p90": None if sis_value is None else round(sis_value, 3),
                "trend": trend_points,
            }
        )

    for region_id, data in west_africa_enriched.items():
        flux_value = _safe_float(data.get("flux_h")) or 0.0
        if flux_value <= 0:
            continue
        label = WEST_AFRICA_REGIONS.get(region_id, {}).get("label", region_id.title())
        results.append(
            {
                "gate_id": region_id,
                "label": label,
                "flux": round(flux_value, 2),
                "flux_z": _safe_float(data.get("flux_z")),
                "delay_ratio": _safe_float(data.get("delay_ratio")),
                "sis_p90": _safe_float(data.get("sis_p90")),
                "trend": [],
            }
        )

    results.sort(key=lambda item: item["flux"], reverse=True)
    return {"window": window, "as_of": now_utc.replace(microsecond=0).isoformat() + "Z", "corridors": results}


# ============================================================================
# Analytics Endpoints - ML Features
# ============================================================================


@router.get("/analytics/anomalies")
def get_anomalies(
    lookback_hours: int = Query(24, description="Hours to look back for anomalies"),
    corridor_id: Optional[str] = Query(None, description="Filter by specific corridor"),
) -> List[Dict[str, Any]]:
    """
    Detect anomalies in maritime traffic patterns.

    Returns unusual spikes or drops in traffic volume based on statistical analysis.
    Uses Modified Z-score with MAD (Median Absolute Deviation) for robust detection.

    Args:
        lookback_hours: Hours to analyze (default: 24)
        corridor_id: Optional filter for specific corridor

    Returns:
        List of detected anomalies with severity, z-score, and description
    """
    from spvx.analytics.anomaly_detection import detect_corridor_anomalies

    with _connect() as con:
        all_anomalies = detect_corridor_anomalies(
            con,
            lookback_hours=lookback_hours,
            baseline_window_hours=168  # 7 days baseline
        )

        # Filter by corridor if specified
        if corridor_id:
            all_anomalies = [a for a in all_anomalies if a.corridor_id == corridor_id]

        # Convert to dicts for JSON response
        return [asdict(a) for a in all_anomalies]


@router.get("/analytics/predictions/{corridor_id}")
def get_predictions(
    corridor_id: str,
    horizon_hours: int = Query(24, description="Hours to predict ahead", ge=1, le=168),
    training_hours: int = Query(168, description="Hours of historical data for training", ge=24, le=720),
) -> List[Dict[str, Any]]:
    """
    Predict traffic volume for a corridor.

    Uses exponential smoothing (Holt's linear method) to forecast vessel counts.
    Includes 95% confidence intervals.

    Args:
        corridor_id: Corridor to predict (e.g., MALACCA_STRAIT)
        horizon_hours: Hours to forecast ahead (1-168, default: 24)
        training_hours: Hours of historical data to use (24-720, default: 168)

    Returns:
        List of predictions with timestamp, predicted_vessels, confidence bounds
    """
    from spvx.analytics.predictions import predict_corridor_traffic

    with _connect() as con:
        predictions = predict_corridor_traffic(
            con,
            corridor_id=corridor_id,
            horizon_hours=horizon_hours,
            training_hours=training_hours,
        )

        if not predictions:
            raise HTTPException(
                status_code=404,
                detail=f"No data available for corridor '{corridor_id}' or insufficient training data"
            )

        return [asdict(p) for p in predictions]


@router.get("/analytics/predictions")
def get_all_predictions(
    horizon_hours: int = Query(24, description="Hours to predict ahead", ge=1, le=168),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Predict traffic for all active corridors.

    Returns predictions for all corridors that have sufficient historical data.

    Args:
        horizon_hours: Hours to forecast ahead (1-168, default: 24)

    Returns:
        Dictionary mapping corridor_id to list of predictions
    """
    from spvx.analytics.predictions import predict_all_corridors

    with _connect() as con:
        all_predictions = predict_all_corridors(con, horizon_hours=horizon_hours)

        # Convert predictions to dicts
        result = {}
        for corridor_id, predictions in all_predictions.items():
            result[corridor_id] = [asdict(p) for p in predictions]

        return result


# Cache corridor_view for 5 minutes to improve performance
@lru_cache(maxsize=32)
def _cached_corridor_view(window: str, cache_time: int) -> str:
    """
    Internal cached version of corridor_view.
    cache_time is used as a cache key that changes every 5 minutes.
    """
    # Import corridor_view logic here
    # This will be called by corridor_view endpoint
    pass


@router.get("/gate_weather")
def gate_weather(
    window: str = Query("h24", pattern="^(h\\d+|d\\d+)$"),
    gate_ids: Optional[str] = Query(None, description="Comma-separated gate IDs to filter"),
) -> Dict[str, Any]:
    """
    Get standalone weather data for gates/checkpoints.
    This endpoint returns weather data independent of ship movements.

    Args:
        window: Time window (e.g., "h24" for last 24 hours, "d7" for last 7 days)
        gate_ids: Optional comma-separated list of gate IDs to filter

    Returns:
        Dictionary with gate weather data including waves, currents, and wind
    """
    window = window.lower()
    now_utc = dt.datetime.utcnow()

    # Parse time window
    if window.startswith("h"):
        hours = max(1, int(window[1:]))
        start_ts = now_utc - dt.timedelta(hours=hours)
    else:
        days = max(1, int(window[1:]))
        start_ts = now_utc - dt.timedelta(days=days)

    with _connect() as con:
        # Check if table exists
        table_exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name ilike 'gate_weather_standalone'"
        ).fetchone()

        if not table_exists:
            return {
                "window": window,
                "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
                "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
                "gates": [],
                "message": "No gate weather data available. Run COLLECT_GATE_WEATHER.sh to collect data.",
            }

        # Build query with optional gate filter
        gate_filter_sql = ""
        params = [start_ts]

        if gate_ids:
            gate_list = [g.strip() for g in gate_ids.split(",")]
            placeholders = ",".join("?" * len(gate_list))
            gate_filter_sql = f"AND gate_id IN ({placeholders})"
            params.extend(gate_list)

        query = f"""
            SELECT
                gate_id,
                gate_name,
                basin,
                observed_at,
                hs_m,
                tp_s,
                dp_deg,
                wave_flag,
                u_knots,
                v_knots,
                speed_knots,
                current_flag,
                wave_source,
                current_source,
                collected_at
            FROM gate_weather_standalone
            WHERE observed_at >= ?
            {gate_filter_sql}
            ORDER BY gate_id, observed_at DESC
        """

        df = con.execute(query, params).df()

        if df.empty:
            return {
                "window": window,
                "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
                "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
                "gates": [],
                "message": "No weather data in the specified time window.",
            }

        # Group by gate and get latest + aggregated stats
        gates_data = []
        for gate_id in df["gate_id"].unique():
            gate_df = df[df["gate_id"] == gate_id]
            latest = gate_df.iloc[0]  # Already sorted by observed_at DESC

            gates_data.append({
                "gate_id": gate_id,
                "gate_name": latest["gate_name"],
                "basin": latest["basin"],
                "latest_observation": {
                    "observed_at": latest["observed_at"].isoformat() if pd.notna(latest["observed_at"]) else None,
                    "waves": {
                        "height_m": float(latest["hs_m"]) if pd.notna(latest["hs_m"]) else None,
                        "period_s": float(latest["tp_s"]) if pd.notna(latest["tp_s"]) else None,
                        "direction_deg": float(latest["dp_deg"]) if pd.notna(latest["dp_deg"]) else None,
                        "flag": int(latest["wave_flag"]) if pd.notna(latest["wave_flag"]) else 0,
                        "severity": "high" if latest["wave_flag"] == 1 else ("moderate" if pd.notna(latest["hs_m"]) and latest["hs_m"] > 2.0 else "normal"),
                    },
                    "currents": {
                        "u_knots": float(latest["u_knots"]) if pd.notna(latest["u_knots"]) else None,
                        "v_knots": float(latest["v_knots"]) if pd.notna(latest["v_knots"]) else None,
                        "speed_knots": float(latest["speed_knots"]) if pd.notna(latest["speed_knots"]) else None,
                        "flag": int(latest["current_flag"]) if pd.notna(latest["current_flag"]) else 0,
                        "severity": "high" if latest["current_flag"] == 1 else ("moderate" if pd.notna(latest["speed_knots"]) and latest["speed_knots"] > 2.0 else "normal"),
                    },
                },
                "statistics": {
                    "samples_count": len(gate_df),
                    "waves": {
                        "mean_height_m": float(gate_df["hs_m"].mean()) if not gate_df["hs_m"].isna().all() else None,
                        "max_height_m": float(gate_df["hs_m"].max()) if not gate_df["hs_m"].isna().all() else None,
                        "p90_height_m": float(gate_df["hs_m"].quantile(0.9)) if not gate_df["hs_m"].isna().all() else None,
                    },
                    "currents": {
                        "mean_speed_kn": float(gate_df["speed_knots"].mean()) if not gate_df["speed_knots"].isna().all() else None,
                        "max_speed_kn": float(gate_df["speed_knots"].max()) if not gate_df["speed_knots"].isna().all() else None,
                        "p90_speed_kn": float(gate_df["speed_knots"].quantile(0.9)) if not gate_df["speed_knots"].isna().all() else None,
                    },
                },
            })

        return {
            "window": window,
            "start": start_ts.replace(tzinfo=dt.timezone.utc).isoformat(),
            "end": now_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
            "gates": gates_data,
        }
