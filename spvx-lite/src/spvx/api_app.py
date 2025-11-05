"""
FastAPI app exposing SPVX-Lite index and model scores with health and metrics.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import smtplib
import datetime as dt
import logging
from email.message import EmailMessage
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Sequence, Tuple, Optional
from contextlib import suppress
from copy import deepcopy

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from spvx.config import AppSettings
from spvx.api_index import router as index_router
from spvx.api_open_sea import router as open_sea_router
from spvx.api_market import router as market_router
from spvx.analytics.relative_stress import compute_relative_stress, build_relative_stress_narrative, classify_zscore
from spvx.open_sea.corridors import corridor_ids as known_corridor_ids

LOG = logging.getLogger(__name__)

RELATIVE_STRESS_CACHE: Dict[str, Tuple[Tuple[str, int], Dict[str, Any]]] = {}

WAITLIST_FILE = Path("data/landing_waitlist.csv")


class LandingWaitlistEntry(BaseModel):
    email: EmailStr
    source: Optional[str] = None

INDEX_META_BASE = {
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
                "range_default": "Dynamic ±0.5σ vs seasonal baseline",
            },
            {
                "label_key": "dashboard.meta.band.tense",
                "label_default": "Tense band",
                "range_key": "dashboard.meta.band.tenseRange",
                "range_default": "+0.5σ to +1.5σ vs seasonal baseline",
            },
            {
                "label_key": "dashboard.meta.band.stress",
                "label_default": "Stress event",
                "range_key": "dashboard.meta.band.stressRange",
                "range_default": "> +1.5σ vs seasonal baseline",
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
        {
            "id": "CQ_SUEZ",
            "label_key": "dashboard.meta.drivers.CQ_SUEZ.label",
            "label_default": "CQ_SUEZ",
            "title_key": "dashboard.meta.drivers.CQ_SUEZ.title",
            "title_default": "Suez Canal",
            "tooltip_key": "dashboard.meta.drivers.CQ_SUEZ.tooltip",
            "tooltip_default": "Tanker congestion at Suez Canal chokepoint.",
        },
        {
            "id": "CQ_GIBRALTAR",
            "label_key": "dashboard.meta.drivers.CQ_GIBRALTAR.label",
            "label_default": "CQ_GIBRALTAR",
            "title_key": "dashboard.meta.drivers.CQ_GIBRALTAR.title",
            "title_default": "Strait of Gibraltar",
            "tooltip_key": "dashboard.meta.drivers.CQ_GIBRALTAR.tooltip",
            "tooltip_default": "Tanker congestion at Gibraltar chokepoint.",
        },
        {
            "id": "PORT_MED",
            "label_key": "dashboard.meta.drivers.PORT_MED.label",
            "label_default": "PORT_MED",
            "title_key": "dashboard.meta.drivers.PORT_MED.title",
            "title_default": "Mediterranean Ports",
            "tooltip_key": "dashboard.meta.drivers.PORT_MED.tooltip",
            "tooltip_default": "Tanker departures from key Mediterranean ports (Augusta, Gioia Tauro, Lavera, Piraeus).",
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
        {
            "id": "CQ_SUEZ",
            "label_key": "dashboard.meta.coverageItems.CQ_SUEZ.label",
            "label_default": "Suez Canal",
            "description_key": "dashboard.meta.coverageItems.CQ_SUEZ.description",
            "description_default": "AIS-based tanker dwell time at Suez chokepoint.",
            "cadence_key": "dashboard.meta.coverageItems.CQ_SUEZ.cadence",
            "cadence_default": "10-minute rollup",
            "note_key": "dashboard.meta.coverageItems.CQ_SUEZ.note",
            "note_default": "Slow-moving tankers vs seasonal baseline",
        },
        {
            "id": "CQ_GIBRALTAR",
            "label_key": "dashboard.meta.coverageItems.CQ_GIBRALTAR.label",
            "label_default": "Strait of Gibraltar",
            "description_key": "dashboard.meta.coverageItems.CQ_GIBRALTAR.description",
            "description_default": "AIS-based tanker dwell time at Gibraltar chokepoint.",
            "cadence_key": "dashboard.meta.coverageItems.CQ_GIBRALTAR.cadence",
            "cadence_default": "10-minute rollup",
            "note_key": "dashboard.meta.coverageItems.CQ_GIBRALTAR.note",
            "note_default": "Slow-moving tankers vs seasonal baseline",
        },
        {
            "id": "PORT_MED",
            "label_key": "dashboard.meta.coverageItems.PORT_MED.label",
            "label_default": "Mediterranean Ports",
            "description_key": "dashboard.meta.coverageItems.PORT_MED.description",
            "description_default": "Tanker departures from major Mediterranean ports.",
            "cadence_key": "dashboard.meta.coverageItems.PORT_MED.cadence",
            "cadence_default": "Daily",
            "note_key": "dashboard.meta.coverageItems.PORT_MED.note",
            "note_default": "Departure tallies for Mediterranean throughput",
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

RELATIVE_STRESS_BANDS = [
    {
        "status": "DEAD_CALM",
        "label": "Dead calm",
        "description": "< -2.5σ vs seasonal baseline",
        "min_z": None,
        "max_z": -2.5,
        "color": "navy",
        "emoji": "🟦",
    },
    {
        "status": "UNUSUALLY_CALM",
        "label": "Exceptionally calm",
        "description": "-2.5σ to -1.5σ",
        "min_z": -2.5,
        "max_z": -1.5,
        "color": "teal",
        "emoji": "🟢",
    },
    {
        "status": "QUIET",
        "label": "Quieter than normal",
        "description": "-1.5σ to -0.5σ",
        "min_z": -1.5,
        "max_z": -0.5,
        "color": "blue",
        "emoji": "😌",
    },
    {
        "status": "NORMAL",
        "label": "Seasonal normal",
        "description": "±0.5σ window (auto-updating)",
        "min_z": -0.5,
        "max_z": 0.5,
        "color": "green",
        "emoji": "⚖️",
    },
    {
        "status": "ELEVATED",
        "label": "Elevated pressure",
        "description": "+0.5σ to +1.5σ",
        "min_z": 0.5,
        "max_z": 1.5,
        "color": "yellow",
        "emoji": "⚠️",
    },
    {
        "status": "STRESSED",
        "label": "Stress spike",
        "description": "+1.5σ to +2.5σ",
        "min_z": 1.5,
        "max_z": 2.5,
        "color": "orange",
        "emoji": "🚨",
    },
    {
        "status": "CRITICAL",
        "label": "Critical congestion",
        "description": "> +2.5σ",
        "min_z": 2.5,
        "max_z": None,
        "color": "red",
        "emoji": "🛑",
    },
]

app = FastAPI(title="SPVX-Lite API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(index_router)
app.include_router(open_sea_router)
app.include_router(market_router)

def _persist_waitlist_entry(entry: LandingWaitlistEntry) -> None:
    WAITLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    is_new = not WAITLIST_FILE.exists()
    source = (entry.source or "landing").strip()
    if not source:
        source = "landing"
    record = {
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "email": entry.email.lower().strip(),
        "source": source,
    }
    with WAITLIST_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ts_utc", "email", "source"])
        if is_new:
            writer.writeheader()
        writer.writerow(record)


def _send_waitlist_notification(entry: LandingWaitlistEntry) -> None:
    host = os.getenv("WAITLIST_SMTP_HOST")
    notify_email = os.getenv("WAITLIST_NOTIFY_EMAIL")
    if not host or not notify_email:
        LOG.debug("Waitlist email notification skipped (missing WAITLIST_SMTP_HOST or WAITLIST_NOTIFY_EMAIL).")
        return

    port_str = os.getenv("WAITLIST_SMTP_PORT", "587")
    try:
        port = int(port_str)
    except ValueError:
        LOG.warning("Invalid WAITLIST_SMTP_PORT %s; defaulting to 587", port_str)
        port = 587

    use_tls = os.getenv("WAITLIST_SMTP_TLS", "true").lower() in {"1", "true", "yes", "on"}
    username = os.getenv("WAITLIST_SMTP_USER")
    password = os.getenv("WAITLIST_SMTP_PASS")
    from_email = os.getenv("WAITLIST_FROM_EMAIL") or username or "notifications@huax.one"

    msg = EmailMessage()
    msg["Subject"] = "HUAX waitlist: Neue Anmeldung"
    msg["From"] = from_email
    msg["To"] = notify_email
    msg.set_content(
        (
            "Neue Waitlist-Anmeldung für HUAX Energy Intelligence:\n\n"
            f"Email: {entry.email}\n"
            f"Quelle: {entry.source or 'landing'}\n"
            f"Zeit (UTC): {dt.datetime.now(dt.timezone.utc).isoformat()}\n\n"
            f"CSV: {WAITLIST_FILE.resolve()}"
        )
    )

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:  # pragma: no cover - depends on external SMTP
        LOG.warning("Failed to send waitlist notification email: %s", exc)


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


def _format_percentile(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    rank = int(round(value))
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix} percentile"


def _relative_stress_payload(
    df: pd.DataFrame,
    value_col: str,
    date_col: str,
    history_days: int = 365,
) -> Dict[str, Any] | None:
    if df.empty:
        return None
    frame = df[[date_col, value_col]].dropna()
    if frame.empty:
        return None
    frame = frame.copy()
    frame[date_col] = pd.to_datetime(frame[date_col]).dt.normalize()
    frame = frame.sort_values(date_col).reset_index(drop=True)

    last_ts = pd.to_datetime(frame[date_col].iloc[-1])
    signature = (last_ts.isoformat(), int(len(frame)))
    cache_key = f"{value_col}:{history_days}"
    cached = RELATIVE_STRESS_CACHE.get(cache_key)
    if cached and cached[0] == signature:
        return cached[1]

    result, enriched = compute_relative_stress(frame, value_col=value_col, date_col=date_col, lookback_days=history_days)
    if result is None:
        return None

    history_cols = [date_col, value_col, "z_score", "percentile", "seasonal_mean", "seasonal_std", "deviation_pct"]
    history = enriched[history_cols].rename(columns={date_col: "date", value_col: "value"})
    history["date"] = pd.to_datetime(history["date"]).dt.date.astype(str)
    history = history.where(pd.notnull(history), None)
    history_tail = history.tail(result.lookback_samples)
    history_records: list[Dict[str, Any]] = []
    for row in history_tail.itertuples(index=False):
        history_records.append(
            {
                "date": getattr(row, "date"),
                "value": None if getattr(row, "value") is None else float(getattr(row, "value")),
                "z_score": None if getattr(row, "z_score") is None else float(getattr(row, "z_score")),
                "percentile": None if getattr(row, "percentile") is None else float(getattr(row, "percentile")),
                "seasonal_mean": (
                    None if getattr(row, "seasonal_mean") is None else float(getattr(row, "seasonal_mean"))
                ),
                "seasonal_std": None if getattr(row, "seasonal_std") is None else float(getattr(row, "seasonal_std")),
                "deviation_pct": None if getattr(row, "deviation_pct") is None else float(getattr(row, "deviation_pct")),
            }
        )

    payload = {
        "latest": result.to_dict(),
        "history": history_records,
        "narrative": build_relative_stress_narrative(result),
    }
    RELATIVE_STRESS_CACHE[cache_key] = (signature, payload)
    return payload


def _format_relative_rule_of_thumb(latest: Dict[str, Any]) -> str:
    classification = latest.get("classification", {})
    status = classification.get("status", "Unknown status")
    seasonal_label = latest.get("seasonal_label") or "Today"
    baseline = latest.get("seasonal_mean")
    baseline_std = latest.get("seasonal_std")
    value = latest.get("value")
    z_score = latest.get("z_score")
    percentile = latest.get("percentile")
    percentile_text = _format_percentile(percentile)
    lookback_samples = latest.get("lookback_samples")

    parts: list[str] = ["Seasonal baseline adjusts daily."]
    if baseline is not None and baseline_std is not None:
        parts.append(f"{seasonal_label}: {baseline:.1f} ± {baseline_std:.1f}.")
    else:
        parts.append(f"{seasonal_label} baseline pending calibration.")

    if value is not None and z_score is not None:
        parts.append(f"Current reading {value:.2f} ({z_score:+.1f}σ).")

    if percentile_text and lookback_samples:
        parts.append(f"{percentile_text} over last {lookback_samples} days.")

    parts.append(f"Status: {status}.")
    return " ".join(parts)


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


@app.post("/api/landing/waitlist", status_code=status.HTTP_201_CREATED)
def landing_waitlist(entry: LandingWaitlistEntry) -> Dict[str, str]:
    _persist_waitlist_entry(entry)
    _send_waitlist_notification(entry)
    return {"status": "ok"}


@app.get("/ready")
def readiness_check():
    """
    Readiness check for production deployments.
    Returns 200 with status info if database is accessible (even if empty).
    Returns 503 only if database is inaccessible or has critical errors.
    """
    settings = AppSettings()
    db_path = Path(settings.duckdb_path)
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": "database_missing",
                "missing": [str(db_path)],
                "help": "Run 'python -m spvx.cli ingest' to initialize the database",
            },
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
            detail={
                "status": "not_ready",
                "reason": "duckdb_error",
                "error": str(exc),
            },
        )

    # Database is accessible, check data availability
    if df.empty or pd.isna(df.iloc[0]["max_date"]):
        return {
            "status": "ready",
            "data_status": "initializing",
            "reason": "no_global_index",
            "message": "Database is empty. Run CLI commands to populate: ingest, compute-index, build-basins",
            "latest": None,
            "age_days": None,
        }

    latest = pd.to_datetime(df.iloc[0]["max_date"]).date()
    today = pd.Timestamp.utcnow().date()
    age_days = (today - latest).days

    if age_days > 1:
        return {
            "status": "ready",
            "data_status": "stale",
            "reason": "global_index_stale",
            "latest": latest.isoformat(),
            "age_days": age_days,
            "message": f"Data is {age_days} days old. Consider running: ingest, compute-index, build-basins",
        }

    return {
        "status": "ready",
        "data_status": "fresh",
        "latest": latest.isoformat(),
        "age_days": age_days,
    }


@app.get("/metrics")
def metrics_endpoint():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/meta")
def get_index_meta():
    meta = deepcopy(INDEX_META_BASE)
    try:
        df = _load_csv(Path("data/outputs/spvx_lite.csv"))
    except FileNotFoundError:
        return _json_response(meta, max_age=1800)

    stress_payload = _relative_stress_payload(df, value_col="SPVX_LITE", date_col="date")
    latest = stress_payload["latest"] if stress_payload else None
    if latest:
        meta["index"]["latest_status"] = latest
        meta["index"]["latest_narrative"] = stress_payload.get("narrative")
        meta["index"]["rule_of_thumb_default"] = _format_relative_rule_of_thumb(latest)
        meta["index"]["relative_bands"] = RELATIVE_STRESS_BANDS
    return _json_response(meta, max_age=1800)


@app.get("/spvx-lite")
def get_spvx_lite(days: int = 90):
    df_full = _load_csv(Path("data/outputs/spvx_lite.csv"))
    stress_payload = _relative_stress_payload(df_full, value_col="SPVX_LITE", date_col="date")
    df = df_full.tail(days) if days else df_full
    payload = {
        "latest": df.iloc[-1].to_dict(),
        "series": df.to_dict(orient="records"),
    }
    if stress_payload:
        payload["relative_stress"] = stress_payload
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
    stress_payload = _relative_stress_payload(df.rename(columns={"d": "date"}), value_col="spvx_global", date_col="date")
    if days:
        df = df.tail(days)
    series = _serialise_index_frame(df, "spvx_global", extra_columns=["basins_present", "weather_flag"])
    latest = series[-1] if series else None
    payload: Dict[str, Any] = {"series": series, "latest": latest}
    if stress_payload:
        payload["relative_stress"] = stress_payload
    return _json_response(payload)


@app.get("/api/index/v1_5")
def get_index_v1_5(date: str = None, range: str = None):
    """
    Get Global Index v1.5 (robust & explainable).

    Query params:
      - date: Single date (YYYY-MM-DD), defaults to today
      - range: Time range (e.g. "7d", "30d", "90d") - mutually exclusive with date

    Examples:
      /api/index/v1_5                    -> Today's index
      /api/index/v1_5?date=2025-10-31    -> Specific date
      /api/index/v1_5?range=30d          -> Last 30 days
    """
    import duckdb
    from pathlib import Path
    from spvx.index.v1_5 import compute_global_index_v15, compute_global_index_timeseries

    try:
        # Use API snapshot database
        db_path = Path(__file__).parent.parent.parent / "db" / "spvx_api.duckdb"
        if not db_path.exists():
            db_path = Path(__file__).parent.parent.parent / "db" / "spvx.duckdb"

        con = duckdb.connect(str(db_path), read_only=True)

        if range:
            # Time series mode
            days = _days_from_range(range, 30)
            end_date = dt.date.today()
            start_date = end_date - dt.timedelta(days=days - 1)

            df = compute_global_index_timeseries(con, start_date, end_date)
            con.close()

            # Check for NaN values in the DataFrame
            if df.empty or df.isnull().values.any():
                LOG.warning("DataFrame contains NaN values or is empty - returning collecting status")
                return {
                    "version": "1.5",
                    "type": "timeseries",
                    "status": "collecting",
                    "message": "Collecting data, available soon",
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "series": [],
                    "latest": None,
                }

            series = df.to_dict(orient="records")
            latest = series[-1] if series else None

            return {
                "version": "1.5",
                "type": "timeseries",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "series": series,
                "latest": latest,
            }
        else:
            # Single date mode
            target_date = dt.date.fromisoformat(date) if date else dt.date.today()
            result = compute_global_index_v15(con, target_date)
            con.close()

            return {
                "version": "1.5",
                "type": "single",
                **result
            }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        LOG.warning(f"Failed to compute index v1.5 (likely insufficient data): {e}")
        # Return a friendly "collecting data" message instead of error
        if range:
            days = _days_from_range(range, 30)
            return {
                "version": "1.5",
                "type": "timeseries",
                "status": "collecting",
                "message": "Collecting data, available soon",
                "start_date": (dt.date.today() - dt.timedelta(days=days-1)).isoformat(),
                "end_date": dt.date.today().isoformat(),
                "series": [],
                "latest": None,
            }
        else:
            return {
                "version": "1.5",
                "type": "single",
                "status": "collecting",
                "message": "Collecting data, available soon",
                "global_index": None,
                "date": (dt.date.fromisoformat(date) if date else dt.date.today()).isoformat(),
            }


@app.get("/api/index/global")
def get_index_global(date: str = None, range: str = None):
    """
    Alias for /api/index/v1_5 - backwards compatibility with dashboard.

    This endpoint serves the same data as /api/index/v1_5 but uses the legacy "/global" path
    that the dashboard expects.
    """
    return get_index_v1_5(date=date, range=range)


@app.get("/api/forecast/v1_5")
def get_forecast_v1_5(horizon: int = 7, date: str = None):
    """
    Get 7-day forecast for Global Index v1.5.

    Query params:
      - horizon: Forecast horizon in days (default: 7)
      - date: Base date (YYYY-MM-DD), defaults to today

    Examples:
      /api/forecast/v1_5                    -> 7-day forecast from today
      /api/forecast/v1_5?horizon=14         -> 14-day forecast
      /api/forecast/v1_5?date=2025-10-31&horizon=7  -> Forecast from specific date
    """
    import duckdb
    from pathlib import Path
    from spvx.index.v1_5 import forecast_global_index_v15

    try:
        # Use API snapshot database
        db_path = Path(__file__).parent.parent.parent / "db" / "spvx_api.duckdb"
        if not db_path.exists():
            db_path = Path(__file__).parent.parent.parent / "db" / "spvx.duckdb"

        con = duckdb.connect(str(db_path), read_only=True)

        base_date = dt.date.fromisoformat(date) if date else dt.date.today()
        df = forecast_global_index_v15(con, base_date, horizon_days=horizon)
        con.close()

        forecast_data = df.to_dict(orient="records")

        return {
            "version": "1.5",
            "type": "forecast",
            "base_date": base_date.isoformat(),
            "horizon_days": horizon,
            "method": df["method"].iloc[0] if not df.empty else "unknown",
            "coverage": df["coverage"].iloc[0] if not df.empty else 0.0,
            "forecast": forecast_data,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        LOG.exception("Failed to generate forecast v1.5")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate forecast v1.5: {str(e)}"
        )


@app.get("/api/index/latest")
def api_index_latest_direct(scope: str = "global"):
    """
    Direct endpoint for /api/index/latest - forwards to index_router.
    This must be defined BEFORE the wildcard {basin} route.
    """
    from spvx.api_index import latest_index
    return latest_index(scope=scope)


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
    stress_payload = _relative_stress_payload(df.rename(columns={"d": "date"}), value_col="spvx_basin", date_col="date")
    if days:
        df = df.tail(days)
    series = _serialise_index_frame(df, "spvx_basin", extra_columns=["comps_present", "weather_flag"])
    latest = series[-1] if series else None
    payload: Dict[str, Any] = {"basin": basin_upper, "series": series, "latest": latest}
    if stress_payload:
        payload["relative_stress"] = stress_payload
    return _json_response(payload)


@app.get("/api/components/{basin}")
def api_get_components(basin: str, range: str = "30d"):
    basin_upper = basin.upper()
    days = _days_from_range(range, 30)
    df = _query_duckdb(
        """
        SELECT
            c.d,
            c.comp,
            c.z_value,
            c.raw_value,
            c.n_obs,
            c.missing_reason,
            COALESCE(c.weather_flag, 0) AS weather_flag,
            b.mean AS seasonal_mean,
            b.std AS seasonal_std
        FROM components_daily AS c
        LEFT JOIN baselines_doy AS b
          ON b.key = c.comp || ':' || c.basin
         AND b.doy = EXTRACT(DOY FROM c.d)
        WHERE c.basin = ?
        ORDER BY c.d, c.comp
        """,
        [basin_upper],
    )
    if df.empty:
        return _json_response({"basin": basin_upper, "series": []})

    df["d"] = pd.to_datetime(df["d"]).dt.date
    if days:
        cutoff = df["d"].max() - dt.timedelta(days=days - 1)
        df = df[df["d"] >= cutoff]

    def _float_or_none(value):
        if value is None or pd.isna(value):
            return None
        return float(value)

    series: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        seasonal_mean = _float_or_none(getattr(row, "seasonal_mean", None))
        seasonal_std = _float_or_none(getattr(row, "seasonal_std", None))
        raw_value = _float_or_none(getattr(row, "raw_value", None))

        deviation_pct = None
        if seasonal_mean not in (None, 0) and raw_value is not None:
            deviation_pct = ((raw_value - seasonal_mean) / seasonal_mean) * 100.0
            if pd.isna(deviation_pct):
                deviation_pct = None

        lower = upper = lower_extreme = upper_extreme = None
        if seasonal_mean is not None and seasonal_std is not None:
            lower = max(0.0, seasonal_mean - seasonal_std)
            upper = seasonal_mean + seasonal_std
            lower_extreme = max(0.0, seasonal_mean - 2 * seasonal_std)
            upper_extreme = seasonal_mean + 2 * seasonal_std

        z_value = _float_or_none(getattr(row, "z_value", None))
        classification = classify_zscore(z_value).to_dict() if z_value is not None else None

        series.append(
            {
                "d": row.d.isoformat(),
                "comp": row.comp,
                "z_value": z_value,
                "raw_value": raw_value,
                "n_obs": None if row.n_obs is None else int(row.n_obs),
                "missing_reason": row.missing_reason,
                "weather_flag": (
                    int(row.weather_flag) if hasattr(row, "weather_flag") and row.weather_flag is not None else 0
                ),
                "seasonal_mean": seasonal_mean,
                "seasonal_std": seasonal_std,
                "seasonal_lower": lower,
                "seasonal_upper": upper,
                "seasonal_lower_extreme": lower_extreme,
                "seasonal_upper_extreme": upper_extreme,
                "deviation_pct": deviation_pct,
                "classification": classification,
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


@app.get("/api/open_sea/occupancy_now")
def api_open_sea_occupancy(polygon_id: str | None = None):
    params: list[Any] = []
    where = ""
    if polygon_id:
        where = "WHERE polygon_id = ?"
        params.append(polygon_id)
    df = _query_duckdb(
        f"""
        SELECT ts, polygon_id, count_now
        FROM tanker_occupancy_intraday
        {where}
        ORDER BY ts DESC, polygon_id
        """,
        params,
    )
    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})
    latest_ts = pd.to_datetime(df["ts"]).max()
    latest_df = df[pd.to_datetime(df["ts"]) == latest_ts]
    payload = {
        "as_of": latest_ts.isoformat(),
        "polygons": latest_df.to_dict(orient="records"),
    }
    return JSONResponse(payload)


@app.get("/api/open_sea/gate_flux")
def api_open_sea_gate_flux(
    gate_id: str | None = None,
    corridor_id: str | None = None,
    direction: str | None = None,
    window: str = "h24",
    mode: str = "gate_hits",
):
    mode_normalized = mode.lower().strip()
    if mode_normalized not in {"gate_hits", "paired_transits"}:
        raise HTTPException(
            status_code=400,
            detail={"status": "invalid", "reason": "mode must be 'gate_hits' or 'paired_transits'"},
        )

    if mode_normalized == "paired_transits":
        target_corridor = corridor_id or gate_id
        if not target_corridor:
            raise HTTPException(
                status_code=400,
                detail={"status": "invalid", "reason": "corridor_id (or gate_id) required for paired_transits"},
            )
        if not window.lower().startswith("d"):
            raise HTTPException(
                status_code=400,
                detail={"status": "invalid", "reason": "paired_transits mode supports daily windows only"},
            )
        horizon_days = 7
        with suppress(ValueError):
            horizon_days = int(window[1:])
        cutoff_date = (pd.Timestamp.utcnow() - pd.Timedelta(days=horizon_days - 1)).date()
        df = _query_duckdb(
            """
            SELECT
                ds AS ts,
                corridor_id,
                paired_transits,
                mean_transit_h,
                median_transit_h,
                p90_transit_h
            FROM gate_paired_transits_daily
            WHERE corridor_id = ? AND ds >= ?
            ORDER BY ds
            """,
            [target_corridor, cutoff_date],
        )
        payload = {
            "mode": "paired_transits",
            "corridor_id": target_corridor,
            "window": window,
            "series": df.to_dict(orient="records"),
            "total_transits": int(df["paired_transits"].sum()) if not df.empty else 0,
        }
        return JSONResponse(payload)

    if not gate_id:
        raise HTTPException(status_code=400, detail={"status": "invalid", "reason": "gate_id required"})

    if window.lower().startswith("d"):
        horizon_days = 7
        with suppress(ValueError):
            horizon_days = int(window[1:])
        cutoff_date = (pd.Timestamp.utcnow() - pd.Timedelta(days=horizon_days - 1)).date()
        params: list[Any] = [gate_id, cutoff_date]
        direction_clause = ""
        if direction:
            direction_clause = "AND direction = ?"
            params.append(direction)
        else:
            direction_clause = "AND direction = 'all'"
        df = _query_duckdb(
            f"""
            SELECT ds as ts, gate_id, direction, crossings, unique_vessels
            FROM gate_flux_daily_deduplicated
            WHERE gate_id = ? AND ds >= ? {direction_clause}
            ORDER BY ds
            """,
            params,
        )
        payload = {
            "mode": "gate_hits",
            "gate_id": gate_id,
            "direction": direction,
            "window": window,
            "series": df.to_dict(orient="records"),
            "total_crossings": int(df["crossings"].sum()) if not df.empty else 0,
            "unique_vessels": int(df["unique_vessels"].sum()) if not df.empty else 0,
        }
    else:
        horizon_hours = 24
        if window.lower().startswith("h"):
            with suppress(ValueError):
                horizon_hours = int(window[1:])
        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=horizon_hours)
        params: list[Any] = [gate_id, cutoff]
        direction_clause = ""
        if direction:
            direction_clause = "AND direction = ?"
            params.append(direction)
        else:
            direction_clause = "AND direction = 'all'"
        df = _query_duckdb(
            f"""
            SELECT ts, gate_id, direction, crossings
            FROM gate_flux_hourly
            WHERE gate_id = ? AND ts >= ? {direction_clause}
            ORDER BY ts
            """,
            params,
        )
        payload = {
            "mode": "gate_hits",
            "gate_id": gate_id,
            "direction": direction,
            "window_hours": horizon_hours,
            "series": df.to_dict(orient="records"),
            "total_crossings": int(df["crossings"].sum()) if not df.empty else 0,
        }
    return JSONResponse(payload)


@app.get("/api/open_sea/transit")
def api_open_sea_transit(from_id: str, to: str, lookback: str = "30d", corridor: str | None = None):
    if not from_id or not to:
        raise HTTPException(status_code=400, detail={"status": "invalid", "reason": "from/to required"})
    if corridor and corridor not in known_corridor_ids():
        raise HTTPException(status_code=404, detail={"status": "invalid", "reason": "corridor_not_found"})
    days = 30
    if lookback.endswith("d"):
        with suppress(ValueError):
            days = int(lookback[:-1])
    start_date = (pd.Timestamp.utcnow() - pd.Timedelta(days=days - 1)).date()
    conditions = ["from_id = ?", "to_id = ?", "ds >= ?"]
    params: list[Any] = [from_id, to, start_date]
    if corridor:
        conditions.insert(0, "corridor_id = ?")
        params.insert(0, corridor)
    where_clause = " AND ".join(conditions)
    df = _query_duckdb(
        f"""
        SELECT ds, corridor_id, from_id, to_id, median_h, mean_h, p90_h, n
        FROM transit_times_daily
        WHERE {where_clause}
        ORDER BY ds DESC
        """,
        params,
    )
    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})
    latest = df.iloc[0]
    latest_ds = latest["ds"].isoformat() if isinstance(latest["ds"], (dt.date, dt.datetime)) else latest["ds"]
    resolved_corridor = corridor or str(latest["corridor_id"])

    series = []
    for record in df.to_dict(orient="records"):
        ds_value = record["ds"]
        if isinstance(ds_value, (dt.date, dt.datetime)):
            record["ds"] = ds_value.isoformat()
        record["median_h"] = float(record["median_h"])
        record["mean_h"] = float(record["mean_h"])
        record["p90_h"] = float(record["p90_h"])
        record["n"] = int(record["n"])
        series.append(record)

    payload = {
        "corridor": resolved_corridor,
        "from": from_id,
        "to": to,
        "from_id": from_id,
        "to_id": to,
        "lookback_days": days,
        "latest": {
            "ds": latest_ds,
            "median_h": float(latest["median_h"]),
            "mean_h": float(latest["mean_h"]),
            "p90_h": float(latest["p90_h"]),
            "n": int(latest["n"]),
        },
        "series": series,
    }
    return JSONResponse(payload)


@app.get("/api/open_sea/sis")
def api_open_sea_sis(corridor: str, window: str = "d7"):
    if not corridor:
        raise HTTPException(status_code=400, detail={"status": "invalid", "reason": "corridor required"})
    days = 7
    if window.endswith("d"):
        with suppress(ValueError):
            days = int(window[:-1])
    start_date = pd.Timestamp.utcnow().date() - pd.Timedelta(days=days)
    df = _query_duckdb(
        """
        SELECT ds, corridor_id, sis_mean, sis_p90, pct_sis_gt_0_7,
               hc_p90_kn, hw_p90_ms, we_p90_m, n_samples
        FROM sea_state_daily
        WHERE corridor_id = ? AND ds >= ?
        ORDER BY ds DESC
        """,
        [corridor, start_date],
    )
    if df.empty:
        raise HTTPException(status_code=404, detail={"status": "not_found"})
    payload = {
        "corridor": corridor,
        "window_days": days,
        "series": df.to_dict(orient="records"),
        "latest": df.iloc[0].to_dict(),
    }
    return JSONResponse(payload)


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


@app.get("/api/registry/status")
def get_registry_status():
    """
    Get ship registry statistics including tanker classification counts and confidence metrics.

    Returns:
        - total_vessels: Total number of vessels in registry
        - tankers: Number of identified tankers
        - tanker_percentage: Percentage of tankers
        - avg_confidence: Average classification confidence
        - sources: Breakdown by classification source (TYPE5, PORT_BEHAVIOR, STS_BEHAVIOR, CORRIDOR)
        - top_polygons: Top 10 polygons by visit count
        - recent_events: Recent polygon events (last 24h)
    """
    import duckdb
    from pathlib import Path

    try:
        # Use absolute path to ensure we find the database
        # Use a separate API database snapshot to avoid lock conflicts with the consumer
        db_path = Path(__file__).parent.parent.parent / "db" / "spvx_api.duckdb"
        if not db_path.exists():
            # Fall back to main database (try read-only)
            db_path = Path(__file__).parent.parent.parent / "db" / "spvx.duckdb"
            if not db_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Database not found at {db_path}"
                )
        con = duckdb.connect(str(db_path), read_only=True)

        # Basic registry stats
        stats = con.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN ship_type_code BETWEEN 80 AND 89 THEN 1 END) as tankers,
                AVG(CASE WHEN ship_type_code BETWEEN 80 AND 89 THEN confidence END) as avg_confidence
            FROM ship_registry
        """).fetchone()

        total, tankers, avg_conf = stats

        # Source breakdown
        sources = con.execute("""
            SELECT
                type_source,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence
            FROM ship_registry
            WHERE ship_type_code BETWEEN 80 AND 89
            GROUP BY type_source
            ORDER BY count DESC
        """).fetchall()

        sources_data = [
            {
                "source": row[0] if row[0] else "UNKNOWN",
                "count": row[1],
                "avg_confidence": float(row[2]) if row[2] else None
            }
            for row in sources
        ]

        # Top polygons (last 7 days)
        top_polygons = con.execute("""
            SELECT
                polygon_id,
                kind,
                COUNT(*) as visit_count,
                SUM(dwell_min) as total_dwell_min,
                COUNT(DISTINCT mmsi) as unique_vessels
            FROM polygon_events
            WHERE ts_in >= NOW() - INTERVAL '7 days'
            GROUP BY polygon_id, kind
            ORDER BY visit_count DESC
            LIMIT 10
        """).fetchall()

        polygons_data = [
            {
                "polygon_id": row[0],
                "kind": row[1],
                "visit_count": row[2],
                "total_dwell_hours": round(row[3] / 60, 1),
                "unique_vessels": row[4]
            }
            for row in top_polygons
        ]

        # Recent events (last 24h)
        recent_events = con.execute("""
            SELECT
                COUNT(*) as event_count,
                COUNT(DISTINCT mmsi) as unique_vessels,
                SUM(dwell_min) as total_dwell_min
            FROM polygon_events
            WHERE ts_in >= NOW() - INTERVAL '24 hours'
        """).fetchone()

        con.close()

        payload = {
            "total_vessels": total,
            "tankers": tankers,
            "tanker_percentage": round(tankers / total * 100, 1) if total > 0 else 0,
            "avg_confidence": round(avg_conf, 2) if avg_conf else None,
            "sources": sources_data,
            "top_polygons": polygons_data,
            "recent_events_24h": {
                "event_count": recent_events[0],
                "unique_vessels": recent_events[1],
                "total_dwell_hours": round(recent_events[2] / 60, 1) if recent_events[2] else 0
            },
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()
        }

        return _json_response(payload, max_age=60)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch registry status: {str(e)}"
        )


@app.get("/api/open_sea/corridor_view")
def get_corridor_view(window: str = "h24"):
    """
    Get corridor traffic data based on real ship registry and polygon events.

    Returns simulated corridor features using actual tanker traffic data.
    """
    import duckdb
    from pathlib import Path

    try:
        # Use API snapshot database
        db_path = Path(__file__).parent.parent.parent / "db" / "spvx_api.duckdb"
        if not db_path.exists():
            db_path = Path(__file__).parent.parent.parent / "db" / "spvx.duckdb"

        con = duckdb.connect(str(db_path), read_only=True)

        # Get actual polygon traffic statistics
        polygon_stats = con.execute("""
            SELECT
                polygon_id,
                kind,
                COUNT(*) as event_count,
                COUNT(DISTINCT mmsi) as vessel_count,
                AVG(dwell_min) as avg_dwell
            FROM polygon_events
            WHERE ts_in >= NOW() - INTERVAL '24 hours'
            GROUP BY polygon_id, kind
            ORDER BY event_count DESC
        """).fetchall()

        con.close()

        # Map polygon data to corridor features with realistic routes
        corridors = []

        # Define realistic maritime corridors based on actual polygon locations
        corridor_configs = [
            {
                "id": "PERSIAN_GULF",
                "coords": [[50.5, 26.5], [55.0, 26.3], [56.25, 26.5], [58.0, 25.5]],
                "polygons": ["RAS_TANURA", "KHARG_ISLAND", "BASRA"],
            },
            {
                "id": "MALACCA_STRAIT",
                "coords": [[98.0, 2.5], [100.35, 1.4], [103.0, 1.2], [104.0, 1.3]],
                "polygons": ["SINGAPORE_STS", "SINGAPORE_JURONG"],
            },
            {
                "id": "MEDITERRANEAN",
                "coords": [[32.3, 30.5], [30.0, 32.0], [25.0, 34.0], [20.0, 36.0]],
                "polygons": ["PORT_SAID_ANCHORAGE", "CEYHAN", "SIDI_KERIR"],
            },
            {
                "id": "NORTH_SEA",
                "coords": [[4.0, 51.9], [3.0, 53.0], [2.0, 55.0], [0.0, 57.0]],
                "polygons": ["ROTTERDAM_OIL", "ANTWERP_OIL"],
            },
            {
                "id": "TURKISH_STRAITS",
                "coords": [[28.0, 40.5], [29.0, 41.0], [30.0, 41.2]],
                "polygons": ["TURKISH"],
            },
            {
                "id": "RED_SEA",
                "coords": [[42.0, 11.5], [43.3, 12.6], [44.5, 13.5], [45.0, 15.0]],
                "polygons": ["YANBU"],
            },
            {
                "id": "BLACK_SEA",
                "coords": [[30.0, 41.2], [32.0, 42.0], [37.0, 43.0], [41.0, 43.5]],
                "polygons": ["PRIMORSK", "NOVOROSSIYSK"],
            },
            {
                "id": "US_GULF",
                "coords": [[-95.0, 28.5], [-92.0, 28.0], [-88.0, 28.5], [-85.0, 29.0]],
                "polygons": ["LOUISIANA_LOOP"],
            },
        ]

        # Build corridors from actual polygon traffic
        for config in corridor_configs:
            # Sum up traffic from related polygons
            total_flux = 0
            for poly_stat in polygon_stats:
                polygon_id, kind, events, vessels, avg_dwell = poly_stat
                if any(p in polygon_id for p in config["polygons"]):
                    total_flux += events

            # Only include corridors with actual traffic
            if total_flux > 0:
                corridors.append({
                    "corridor_id": config["id"],
                    "geometry": {
                        "type": "LineString",
                        "coordinates": config["coords"],
                    },
                    "flux_h": total_flux,
                    "flux_z": (total_flux - 50) / 30,  # Normalize around 50 baseline
                    "delay_ratio": 1.0 + (total_flux / 200),  # Higher traffic = more delay
                    "sis_p90": 0.5,
                    "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
                })

        return corridors

    except Exception as e:
        # Fallback to empty list on error
        return []


try:
    from pydantic import EmailStr as _EmailStr
    import email_validator  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    EmailStr = str  # type: ignore
else:
    EmailStr = _EmailStr
