"""
FastAPI app exposing SPVX-Lite index and model scores with health and metrics.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import datetime as dt
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Sequence

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from spvx.config import AppSettings

INDEX_META = {
    "index": {
        "name": "SPVX-Lite",
        "tagline_key": "dashboard.meta.tagline",
        "tagline_default": "SPVX-Lite measures daily uncertainty in maritime oil flows.",
        "description_key": "dashboard.meta.description",
        "description_default": "Sources: AIS/port data plus weather adjustments; fixed at 12:00 UTC (T+1).",
        "fix_time_utc": "12:00",
        "version": "1.0.0",
        "rule_of_thumb_key": "dashboard.meta.ruleOfThumbText",
        "rule_of_thumb_default": "Rule of thumb: 80–120 normal, 120–150 tense, >150 stress. Moves ≥ +10 pts are material.",
        "material_move_points": 10,
        "bands": [
            {
                "label_key": "dashboard.meta.band.normal",
                "label_default": "Normal",
                "range_key": "dashboard.meta.band.normalRange",
                "range_default": "80–120",
            },
            {
                "label_key": "dashboard.meta.band.tense",
                "label_default": "Tense band",
                "range_key": "dashboard.meta.band.tenseRange",
                "range_default": "120–150",
            },
            {
                "label_key": "dashboard.meta.band.stress",
                "label_default": "Stress event",
                "range_key": "dashboard.meta.band.stressRange",
                "range_default": ">150",
            },
        ],
    },
    "drivers": [
        {
            "id": "CQ_SG",
            "label_key": "dashboard.meta.drivers.CQ_SG.label",
            "label_default": "CQ_SG",
            "title_key": "dashboard.meta.drivers.CQ_SG.title",
            "title_default": "Singapore/Malacca",
            "tooltip_key": "dashboard.meta.drivers.CQ_SG.tooltip",
            "tooltip_default": "Deviation of tanker movements versus the seasonal profile.",
        },
        {
            "id": "CQ_TR",
            "label_key": "dashboard.meta.drivers.CQ_TR.label",
            "label_default": "CQ_TR",
            "title_key": "dashboard.meta.drivers.CQ_TR.title",
            "title_default": "Turkish Straits",
            "tooltip_key": "dashboard.meta.drivers.CQ_TR.tooltip",
            "tooltip_default": "Bosporus & Dardanelles – closure and wait-time anomalies.",
        },
        {
            "id": "PORT_EU",
            "label_key": "dashboard.meta.drivers.PORT_EU.label",
            "label_default": "PORT_EU",
            "title_key": "dashboard.meta.drivers.PORT_EU.title",
            "title_default": "Rotterdam",
            "tooltip_key": "dashboard.meta.drivers.PORT_EU.tooltip",
            "tooltip_default": "Tanker departures as EU outflow proxy (grey = stale).",
        },
    ],
    "coverage": [
        {
            "id": "CQ_SG",
            "label_key": "dashboard.meta.coverageItems.CQ_SG.label",
            "label_default": "Singapore/Malacca",
            "description_key": "dashboard.meta.coverageItems.CQ_SG.description",
            "description_default": "AIS tanker movements vs day-of-year baseline.",
            "cadence_key": "dashboard.meta.coverageItems.CQ_SG.cadence",
            "cadence_default": "10-minute rollup",
            "note_key": "dashboard.meta.coverageItems.CQ_SG.note",
            "note_default": "Tanker movements vs seasonal profile",
        },
        {
            "id": "CQ_TR",
            "label_key": "dashboard.meta.coverageItems.CQ_TR.label",
            "label_default": "Turkish Straits",
            "description_key": "dashboard.meta.coverageItems.CQ_TR.description",
            "description_default": "Bosporus & Dardanelles – closure and wait times.",
            "cadence_key": "dashboard.meta.coverageItems.CQ_TR.cadence",
            "cadence_default": "Daily",
            "note_key": "dashboard.meta.coverageItems.CQ_TR.note",
            "note_default": "Closure and wait durations",
        },
        {
            "id": "PORT_EU",
            "label_key": "dashboard.meta.coverageItems.PORT_EU.label",
            "label_default": "Rotterdam",
            "description_key": "dashboard.meta.coverageItems.PORT_EU.description",
            "description_default": "Tanker departures as EU outflow proxy.",
            "cadence_key": "dashboard.meta.coverageItems.PORT_EU.cadence",
            "cadence_default": "Daily",
            "note_key": "dashboard.meta.coverageItems.PORT_EU.note",
            "note_default": "Departure tallies for EU throughput",
        },
    ],
    "freshness_badges": [
        {"state": "fresh", "text_key": "dashboard.meta.freshness.fresh", "text_default": "Sources ≤ 6 h"},
        {"state": "watch", "text_key": "dashboard.meta.freshness.watch", "text_default": "Sources 6–24 h"},
        {"state": "stale", "text_key": "dashboard.meta.freshness.stale", "text_default": "Sources >24 h"},
    ],
    "publish_badges": [
        {"state": "fixed", "text_key": "dashboard.meta.publish.fixed", "text_default": "T+1 fix"},
        {"state": "indicative", "text_key": "dashboard.meta.publish.indicative", "text_default": "Indicative"},
    ],
    "methodology": {
        "summary_key": "dashboard.meta.methodology.summary",
        "summary_default": "SPVX-Lite scales three components via seasonal z-scores, winsorises outliers and combines them into a logistics stress level. Weights favour stability and low revisions over price fit.",
        "interpretation_key": "dashboard.meta.methodology.interpretation",
        "interpretation_default": "+10 points ≈ significant logistics stress increase.",
        "table": [
            {
                "component_key": "dashboard.meta.methodology.table.CQ_SG.component",
                "component_default": "CQ_SG",
                "geofence_key": "dashboard.meta.methodology.table.CQ_SG.geofence",
                "geofence_default": "Singapore/Malacca",
                "cadence_key": "dashboard.meta.methodology.table.CQ_SG.cadence",
                "cadence_default": "10-minute rollup",
                "note_key": "dashboard.meta.methodology.table.CQ_SG.note",
                "note_default": "Tanker movements vs day-of-year baseline",
            },
            {
                "component_key": "dashboard.meta.methodology.table.CQ_TR.component",
                "component_default": "CQ_TR",
                "geofence_key": "dashboard.meta.methodology.table.CQ_TR.geofence",
                "geofence_default": "Turkish Straits",
                "cadence_key": "dashboard.meta.methodology.table.CQ_TR.cadence",
                "cadence_default": "Daily",
                "note_key": "dashboard.meta.methodology.table.CQ_TR.note",
                "note_default": "Closure & wait durations",
            },
            {
                "component_key": "dashboard.meta.methodology.table.PORT_EU.component",
                "component_default": "PORT_EU",
                "geofence_key": "dashboard.meta.methodology.table.PORT_EU.geofence",
                "geofence_default": "Rotterdam",
                "cadence_key": "dashboard.meta.methodology.table.PORT_EU.cadence",
                "cadence_default": "Daily",
                "note_key": "dashboard.meta.methodology.table.PORT_EU.note",
                "note_default": "Tanker departures as EU outflow proxy",
            },
        ],
        "quality_key": "dashboard.meta.methodology.quality",
        "quality_default": "Stale detection per component; stale contributions are down-weighted automatically (0–100%).",
        "transparency_keys": [
            "dashboard.meta.methodology.transparency.line1",
            "dashboard.meta.methodology.transparency.line2",
            "dashboard.meta.methodology.transparency.line3",
        ],
        "transparency_defaults": [
            "Timestamps (as-of) and revision metrics (30-day history).",
            "Source attribution (AIS / ports / weather).",
            "Methodology changelog (v1.0 → v1.1 …).",
        ],
        "disclaimer_key": "dashboard.meta.methodology.disclaimer",
        "disclaimer_default": "Methodology v1.0 • Transparency note (monthly) • No investment advice.",
    },
}

app = FastAPI(title="SPVX-Lite API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


REQUEST_COUNT = Counter(
    "spvx_api_requests_total",
    "API request count",
    ["endpoint", "method", "status"],
)
REQUEST_LATENCY = Histogram(
    "spvx_api_latency_seconds",
    "API latency in seconds",
    ["endpoint", "method"],
)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    elapsed = perf_counter() - start
    path = request.url.path
    method = request.method
    REQUEST_LATENCY.labels(endpoint=path, method=method).observe(elapsed)
    REQUEST_COUNT.labels(endpoint=path, method=method, status=str(response.status_code)).inc()
    return response


def _load_csv(path: Path, tail: int | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    df = pd.read_csv(path, parse_dates=["date"])
    if tail:
        df = df.tail(tail)
    return df


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _sanitize(data)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _sanitize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(obj, (np.ndarray,)):
        return [_sanitize(item) for item in obj.tolist()]
    return obj


def _json_response(payload: Dict[str, Any], max_age: int = 300) -> JSONResponse:
    sanitized = _sanitize(payload)
    body = json.dumps(sanitized, sort_keys=True, default=str, allow_nan=False)
    etag = hashlib.md5(body.encode("utf-8")).hexdigest()
    headers = {
        "Cache-Control": f"public, max-age={max_age}",
        "ETag": etag,
    }
    return JSONResponse(content=json.loads(body), headers=headers)


def _days_from_range(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    token = value.strip().lower()
    if token in ("all", "max", "full"):
        return None
    if token.endswith("d"):
        token = token[:-1]
    try:
        days = int(token)
        return days if days > 0 else default
    except ValueError:
        return default


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def readiness_check():
    settings = AppSettings()
    db_path = Path(settings.duckdb_path)
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "missing": [str(db_path)]},
        )

    try:
        df = _query_duckdb(
            """
            SELECT MAX(d) AS max_date
            FROM spvx_global_daily
            WHERE spvx_global IS NOT NULL
            """
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": f"duckdb_error:{exc}"},
        )

    if df.empty or pd.isna(df.iloc[0]["max_date"]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "no_global_index"},
        )

    latest = pd.to_datetime(df.iloc[0]["max_date"]).date()
    today = pd.Timestamp.utcnow().date()
    age_days = (today - latest).days
    if age_days > 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": "global_index_stale",
                "latest": latest.isoformat(),
                "age_days": age_days,
            },
        )

    return {"status": "ready", "latest": latest.isoformat(), "age_days": age_days}


@app.get("/metrics")
def metrics_endpoint():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/meta")
def get_index_meta():
    return _json_response(INDEX_META, max_age=1800)


@app.get("/spvx-lite")
def get_spvx_lite(days: int = 90):
    df = _load_csv(Path("data/outputs/spvx_lite.csv"), tail=days)
    payload = {
        "latest": df.iloc[-1].to_dict(),
        "series": df.to_dict(orient="records"),
    }
    return _json_response(payload)


@app.get("/signals-snapshot")
def get_signals_snapshot():
    path = Path("data/outputs/signals.json")
    try:
        data = _load_json(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Signals snapshot not available. Run `cli score` first.")
    return _json_response(data, max_age=60)


@app.get("/spread-signals")
def get_spread_signals(days: int = 90):
    path = Path("data/outputs/spread_scores.parquet")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Spread scores not available. Run `cli score` first.")
    df = pd.read_parquet(path)
    df = df.sort_values("date").tail(days)
    payload = {
        "latest": df.iloc[-1].to_dict(),
        "series": df.to_dict(orient="records"),
    }
    return _json_response(payload)


@app.get("/throughput-nowcast")
def get_throughput(days: int = 90):
    path = Path("data/outputs/throughput_scores.parquet")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Throughput scores not available. Run `cli score` first.")
    df = pd.read_parquet(path).sort_values("date").tail(days)
    payload = {
        "latest": df.iloc[-1].to_dict(),
        "series": df.to_dict(orient="records"),
    }
    return _json_response(payload)


def _serialise_index_frame(
    df: pd.DataFrame, value_column: str, extra_columns: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        base = {
            "d": pd.to_datetime(getattr(row, "d")).date().isoformat(),
            value_column: getattr(row, value_column),
        }
        if extra_columns:
            for col in extra_columns:
                base[col] = getattr(row, col)
        records.append(base)
    return records


@app.get("/api/index/global")
def api_get_global_index(range: str = "90d"):
    days = _days_from_range(range, 90)
    df = _query_duckdb(
        """
        SELECT d, spvx_global, basins_present, weather_flag
        FROM spvx_global_daily
        WHERE spvx_global IS NOT NULL
        ORDER BY d
        """
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Global index not available.")
    if days:
        df = df.tail(days)
    series = _serialise_index_frame(df, "spvx_global", extra_columns=["basins_present", "weather_flag"])
    latest = series[-1] if series else None
    return _json_response({"series": series, "latest": latest})


@app.get("/api/index/{basin}")
def api_get_basin_index(basin: str, range: str = "90d"):
    basin_upper = basin.upper()
    if basin_upper == "GLOBAL":
        return api_get_global_index(range=range)
    days = _days_from_range(range, 90)
    df = _query_duckdb(
        """
        SELECT d, spvx_basin, comps_present, weather_flag
        FROM spvx_basin_daily
        WHERE basin = ?
        ORDER BY d
        """,
        [basin_upper],
    )
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Basin '{basin_upper}' not found.")
    if days:
        df = df.tail(days)
    series = _serialise_index_frame(df, "spvx_basin", extra_columns=["comps_present", "weather_flag"])
    latest = series[-1] if series else None
    return _json_response({"basin": basin_upper, "series": series, "latest": latest})


@app.get("/api/components/{basin}")
def api_get_components(basin: str, range: str = "30d"):
    basin_upper = basin.upper()
    days = _days_from_range(range, 30)
    df = _query_duckdb(
        """
        SELECT d, comp, z_value, raw_value, n_obs, missing_reason, weather_flag
        FROM components_daily
        WHERE basin = ?
        ORDER BY d
        """,
        [basin_upper],
    )
    if df.empty:
        return _json_response({"basin": basin_upper, "series": []})

    df["d"] = pd.to_datetime(df["d"]).dt.date
    if days:
        cutoff = df["d"].max() - dt.timedelta(days=days - 1)
        df = df[df["d"] >= cutoff]

    series: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        series.append(
            {
                "d": row.d.isoformat(),
                "comp": row.comp,
                "z_value": None if pd.isna(row.z_value) else float(row.z_value),
                "raw_value": None if pd.isna(row.raw_value) else float(row.raw_value),
                "n_obs": None if row.n_obs is None else int(row.n_obs),
                "missing_reason": row.missing_reason,
                "weather_flag": (
                    int(row.weather_flag) if hasattr(row, "weather_flag") and row.weather_flag is not None else 0
                ),
            }
        )
    return _json_response({"basin": basin_upper, "series": series})


@app.get("/download/{basin}.csv")
def download_basin_csv(basin: str, range: str = "90d"):
    basin_upper = basin.upper()
    days = _days_from_range(range, 90)
    if basin_upper == "GLOBAL":
        df = _query_duckdb(
            """
            SELECT d, spvx_global AS value
            FROM spvx_global_daily
            WHERE spvx_global IS NOT NULL
            ORDER BY d
            """
        )
        value_col = "value"
    else:
        df = _query_duckdb(
            """
            SELECT d, spvx_basin AS value, comps_present
            FROM spvx_basin_daily
            WHERE basin = ?
            ORDER BY d
            """,
            [basin_upper],
        )
        value_col = "value"

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No series available for basin '{basin_upper}'.")

    if days:
        df = df.tail(days)

    df["d"] = pd.to_datetime(df["d"]).dt.date.astype(str)
    csv_buffer = io.StringIO()
    df.rename(columns={"d": "date", value_col: "value"}).to_csv(csv_buffer, index=False)
    csv_payload = csv_buffer.getvalue()
    filename = f"{basin_upper.lower()}_{range}.csv" if range else f"{basin_upper.lower()}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return PlainTextResponse(content=csv_payload, media_type="text/csv", headers=headers)


EXPECTED_COMPONENTS = {
    "APAC": ("CQ_SG", "CQ_HRZ"),
    "NAM": ("CQ_PAN", "PORT_US"),
    "SAM": ("CQ_PAN_S", "PORT_BR"),
}


@app.get("/ops/health")
def ops_health():
    try:
        global_df = _query_duckdb(
            """
            SELECT d, spvx_global
            FROM spvx_global_daily
            ORDER BY d DESC
            LIMIT 2
            """
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "error", "reason": f"duckdb_error:{exc}"})

    latest_snapshot = None
    revision_flag = False
    ready = False

    if not global_df.empty:
        latest_snapshot = pd.to_datetime(global_df.iloc[0]["d"]).date()
        today = pd.Timestamp.utcnow().date()
        age_days = (today - latest_snapshot).days
        ready = age_days <= 1
        if len(global_df) > 1:
            latest_val = global_df.iloc[0]["spvx_global"]
            prev_val = global_df.iloc[1]["spvx_global"]
            if latest_val is not None and prev_val is not None:
                revision_flag = abs(float(latest_val) - float(prev_val)) > 0.10
    else:
        age_days = None

    try:
        components_df = _query_duckdb(
            """
            SELECT d, basin, comp, z_value
            FROM components_daily
            """
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "error", "reason": f"duckdb_error:{exc}"})

    coverage_30d: dict[str, float | None] = {}
    components_present: dict[str, dict[str, int]] = {}
    weather_flags: dict[str, int | None] = {}

    if not components_df.empty:
        components_df["d"] = pd.to_datetime(components_df["d"]).dt.date
        max_date = components_df["d"].max()
        window_cutoff = max_date - dt.timedelta(days=29)
        window_df = components_df[components_df["d"] >= window_cutoff]
        total_days_window = max((max_date - window_cutoff).days + 1, 1)

        observed_components = {
            basin: sorted(subset["comp"].unique()) for basin, subset in components_df.groupby("basin")
        }
        all_basins = sorted(set(EXPECTED_COMPONENTS.keys()) | set(observed_components.keys()))

        for basin in all_basins:
            basin_window = window_df[window_df["basin"] == basin]
            if basin_window.empty:
                coverage_30d[basin] = None
            else:
                by_day = basin_window.groupby("d")["z_value"].apply(lambda series: series.notna().any())
                days_with_data = int(by_day.sum())
                coverage_30d[basin] = round(days_with_data / total_days_window, 3)

        latest_components = components_df[components_df["d"] == max_date]
        for basin in all_basins:
            subset = latest_components[latest_components["basin"] == basin]
            present = int(subset["z_value"].notna().sum())
            observed_count = len(observed_components.get(basin, []))
            expected_list = EXPECTED_COMPONENTS.get(basin)
            expected_count = len(expected_list) if expected_list else observed_count
            if expected_count == 0:
                expected_count = observed_count
            components_present[basin] = {
                "present": present,
                "expected": expected_count if expected_count else present,
            }
        if subset.empty or "weather_flag" not in subset.columns:
            weather_flags[basin] = None
        else:
            flag_value = subset["weather_flag"].max(skipna=True)
            weather_flags[basin] = int(flag_value) if pd.notna(flag_value) else 0
    else:
        for basin, expected in EXPECTED_COMPONENTS.items():
            coverage_30d[basin] = None
            components_present[basin] = {"present": 0, "expected": len(expected)}
            weather_flags[basin] = None

    payload = {
        "ready": ready,
        "latest_snapshot": latest_snapshot.isoformat() if isinstance(latest_snapshot, dt.date) else None,
        "coverage_30d": coverage_30d,
        "components_present": components_present,
        "revision_flag": revision_flag,
        "age_days": age_days,
        "weather_flags": weather_flags,
    }
    return _json_response(payload, max_age=60)


def _query_duckdb(sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
    import duckdb

    settings = AppSettings()
    con = duckdb.connect(settings.duckdb_path, read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


@app.get("/golden-probe")
def get_golden_probe(limit: int = 200):
    df = _query_duckdb(
        """
        SELECT msg_time, rx_time, mmsi, sog, lat, lon, region
        FROM golden_probe
        ORDER BY msg_time DESC
        LIMIT ?
        """,
        [limit],
    )
    payload = {
        "count": int(len(df)),
        "series": df.to_dict(orient="records"),
    }
    return _json_response(payload, max_age=30)
