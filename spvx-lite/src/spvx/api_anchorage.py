"""
Teapot Heartbeat API - Anchorage Dwell Endpoints (TH-4)

Provides real-time and historical anchorage dwell metrics for teapot market intelligence.
Focus: Shandong anchorages (Qingdao, Rizhao, Yantai) + OPL Singapore.

Key Metrics:
- Dwell time (median, p90) - how long vessels stay anchored
- Z-scores - anomaly detection (high dwell = congestion signal)
- Coverage ratio - time utilization of anchorage areas
- Active vessels - current occupancy
"""

import datetime as dt
import logging
import math
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from spvx.config import AppSettings

LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anchorage", tags=["anchorage"])


def _connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Connect to DuckDB (prefer API snapshot if available)."""
    from pathlib import Path
    settings = AppSettings()

    api_db_path = Path(settings.duckdb_path).parent / "spvx_api.duckdb"
    if api_db_path.exists():
        return duckdb.connect(str(api_db_path), read_only=read_only)

    return duckdb.connect(settings.duckdb_path, read_only=read_only)


def _safe_float(value: Any) -> Optional[float]:
    """Convert value to float, handling NaN/inf."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


class AnchorageDailySummary(BaseModel):
    """Daily aggregated metrics for an anchorage."""
    ds: str
    anchorage_id: str
    episodes: Optional[int] = None
    active_vessels: Optional[int] = None
    dwell_median_h: Optional[float] = None
    dwell_p90_h: Optional[float] = None
    coverage_ratio: Optional[float] = None
    z_dwell: Optional[float] = None
    baseline_insufficient: Optional[bool] = None
    tanker_share: Optional[float] = None


class AnchorageEpisode(BaseModel):
    """Individual vessel episode at an anchorage."""
    mmsi: int
    anchorage_id: str
    t_in: str
    t_out: Optional[str] = None
    dwell_h: Optional[float] = None
    fixes_n: Optional[int] = None
    vessel_name: Optional[str] = None
    vessel_type: Optional[str] = None


class AnchorageSummaryResponse(BaseModel):
    """Summary response for an anchorage over a time window."""
    anchorage_id: str
    window: str
    start: str
    end: str
    latest: Optional[AnchorageDailySummary] = None
    statistics: Optional[Dict[str, Any]] = None
    trend: Optional[List[AnchorageDailySummary]] = None


@router.get("/daily")
def get_anchorage_daily(
    anchorage_ids: str = Query(..., description="Comma-separated anchorage IDs (e.g., ANCH_QINGDAO,ANCH_RIZHAO)"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD), default: 7 days ago"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD), default: today"),
) -> Dict[str, Any]:
    """
    Get daily aggregated dwell metrics for anchorages.

    Returns time-series data for:
    - Episode counts
    - Active vessel counts
    - Dwell time (median, p90)
    - Coverage ratio (time utilization)
    - Z-scores for anomaly detection

    Example:
        GET /api/anchorage/daily?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO&start=2025-11-01&end=2025-11-05
    """
    # Parse parameters
    ids = [aid.strip() for aid in anchorage_ids.split(",")]

    now = dt.datetime.utcnow().date()
    if end is None:
        end_date = now
    else:
        end_date = dt.datetime.strptime(end, "%Y-%m-%d").date()

    if start is None:
        start_date = end_date - dt.timedelta(days=7)
    else:
        start_date = dt.datetime.strptime(start, "%Y-%m-%d").date()

    with _connect() as con:
        # Check if table exists
        table_check = con.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name ILIKE 'anchorage_daily'
        """).fetchone()

        if not table_check:
            return {
                "anchorages": [],
                "message": "No anchorage data available. Run anchorage-episodes and anchorage-enrich CLI commands.",
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            }

        # Query daily data
        placeholders = ",".join("?" * len(ids))
        query = f"""
            SELECT
                ds,
                anchorage_id,
                episodes,
                active_vessels,
                dwell_median_h,
                dwell_p90_h,
                coverage_ratio,
                z_dwell,
                baseline_insufficient,
                tanker_share
            FROM anchorage_daily
            WHERE anchorage_id IN ({placeholders})
              AND ds >= ?
              AND ds <= ?
            ORDER BY anchorage_id, ds
        """

        df = con.execute(query, ids + [start_date, end_date]).df()

        if df.empty:
            return {
                "anchorages": [],
                "message": f"No data found for anchorages {ids} in date range {start_date} to {end_date}",
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            }

        # Group by anchorage
        result = {
            "anchorages": [],
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        }

        for anch_id in df["anchorage_id"].unique():
            anch_df = df[df["anchorage_id"] == anch_id].sort_values("ds")

            daily_records = []
            for _, row in anch_df.iterrows():
                daily_records.append(AnchorageDailySummary(
                    ds=row["ds"].isoformat() if hasattr(row["ds"], "isoformat") else str(row["ds"]),
                    anchorage_id=row["anchorage_id"],
                    episodes=int(row["episodes"]) if pd.notna(row["episodes"]) else None,
                    active_vessels=int(row["active_vessels"]) if pd.notna(row["active_vessels"]) else None,
                    dwell_median_h=_safe_float(row["dwell_median_h"]),
                    dwell_p90_h=_safe_float(row["dwell_p90_h"]),
                    coverage_ratio=_safe_float(row["coverage_ratio"]),
                    z_dwell=_safe_float(row["z_dwell"]),
                    baseline_insufficient=bool(row["baseline_insufficient"]) if pd.notna(row["baseline_insufficient"]) else None,
                    tanker_share=_safe_float(row["tanker_share"]),
                ).dict())

            result["anchorages"].append({
                "anchorage_id": anch_id,
                "data": daily_records,
            })

        return result


@router.get("/episodes")
def get_anchorage_episodes(
    anchorage_id: Optional[str] = Query(None, description="Filter by anchorage ID"),
    mmsi: Optional[int] = Query(None, description="Filter by vessel MMSI"),
    days: int = Query(7, description="Lookback period in days", ge=1, le=90),
    limit: int = Query(100, description="Max episodes to return", ge=1, le=1000),
) -> Dict[str, Any]:
    """
    Get individual vessel episodes at anchorages.

    Returns detailed episode data including:
    - Entry/exit times
    - Dwell duration
    - Number of AIS fixes
    - Vessel metadata (if available)

    Example:
        GET /api/anchorage/episodes?anchorage_id=ANCH_QINGDAO&days=14&limit=50
    """
    end_date = dt.datetime.utcnow()
    start_date = end_date - dt.timedelta(days=days)

    with _connect() as con:
        # Check if table exists
        table_check = con.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name ILIKE 'anchorage_episodes'
        """).fetchone()

        if not table_check:
            return {
                "episodes": [],
                "message": "No episode data available. Run anchorage-episodes CLI command.",
            }

        # Build query
        where_clauses = ["t_in >= ?"]
        params = [start_date]

        if anchorage_id:
            where_clauses.append("anchorage_id = ?")
            params.append(anchorage_id)

        if mmsi:
            where_clauses.append("mmsi = ?")
            params.append(mmsi)

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT
                e.mmsi,
                e.anchorage_id,
                e.t_in,
                e.t_out,
                e.dwell_h,
                e.fixes_n,
                s.ship_name as vessel_name,
                s.ship_type as vessel_type
            FROM anchorage_episodes e
            LEFT JOIN ship_registry s ON e.mmsi = s.mmsi
            WHERE {where_sql}
            ORDER BY e.t_in DESC
            LIMIT ?
        """

        df = con.execute(query, params + [limit]).df()

        if df.empty:
            return {
                "episodes": [],
                "message": "No episodes found matching criteria",
                "filters": {
                    "anchorage_id": anchorage_id,
                    "mmsi": mmsi,
                    "days": days,
                },
            }

        # Convert to response
        episodes = []
        for _, row in df.iterrows():
            episodes.append(AnchorageEpisode(
                mmsi=int(row["mmsi"]),
                anchorage_id=row["anchorage_id"],
                t_in=row["t_in"].isoformat() if hasattr(row["t_in"], "isoformat") else str(row["t_in"]),
                t_out=row["t_out"].isoformat() if pd.notna(row["t_out"]) and hasattr(row["t_out"], "isoformat") else None,
                dwell_h=_safe_float(row["dwell_h"]),
                fixes_n=int(row["fixes_n"]) if pd.notna(row["fixes_n"]) else None,
                vessel_name=str(row["vessel_name"]) if pd.notna(row["vessel_name"]) else None,
                vessel_type=str(row["vessel_type"]) if pd.notna(row["vessel_type"]) else None,
            ).dict())

        return {
            "episodes": episodes,
            "count": len(episodes),
            "filters": {
                "anchorage_id": anchorage_id,
                "mmsi": mmsi,
                "days": days,
                "limit": limit,
            },
        }


@router.get("/summary")
def get_anchorage_summary(
    anchorage_ids: str = Query(..., description="Comma-separated anchorage IDs"),
    window: str = Query("d7", pattern="^(d\\d+|h\\d+)$", description="Time window (e.g., d7, d14, d30)"),
) -> Dict[str, Any]:
    """
    Get summary statistics for anchorages over a time window.

    Returns:
    - Latest daily metrics
    - Aggregated statistics (mean, max, p90 for dwell times)
    - Trend data (time series)

    This endpoint is optimized for dashboards and alerts.

    Example:
        GET /api/anchorage/summary?anchorage_ids=ANCH_QINGDAO,ANCH_RIZHAO&window=d14
    """
    # Parse window
    window = window.lower()
    if window.startswith("d"):
        days = int(window[1:])
    else:
        days = max(1, int(window[1:]) // 24)

    ids = [aid.strip() for aid in anchorage_ids.split(",")]

    end_date = dt.datetime.utcnow().date()
    start_date = end_date - dt.timedelta(days=days)

    with _connect() as con:
        # Check if table exists
        table_check = con.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name ILIKE 'anchorage_daily'
        """).fetchone()

        if not table_check:
            return {
                "anchorages": [],
                "message": "No anchorage data available. Run anchorage-episodes and anchorage-enrich CLI commands.",
            }

        # Query data
        placeholders = ",".join("?" * len(ids))
        query = f"""
            SELECT
                ds,
                anchorage_id,
                episodes,
                active_vessels,
                dwell_median_h,
                dwell_p90_h,
                coverage_ratio,
                z_dwell,
                baseline_insufficient,
                tanker_share
            FROM anchorage_daily
            WHERE anchorage_id IN ({placeholders})
              AND ds >= ?
              AND ds <= ?
            ORDER BY anchorage_id, ds DESC
        """

        df = con.execute(query, ids + [start_date, end_date]).df()

        if df.empty:
            return {
                "anchorages": [],
                "message": f"No data for anchorages {ids} in window {window}",
                "window": window,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            }

        # Build response per anchorage
        result = {
            "anchorages": [],
            "window": window,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        }

        for anch_id in df["anchorage_id"].unique():
            anch_df = df[df["anchorage_id"] == anch_id].sort_values("ds", ascending=False)

            # Latest observation
            latest_row = anch_df.iloc[0]
            latest = AnchorageDailySummary(
                ds=latest_row["ds"].isoformat() if hasattr(latest_row["ds"], "isoformat") else str(latest_row["ds"]),
                anchorage_id=latest_row["anchorage_id"],
                episodes=int(latest_row["episodes"]) if pd.notna(latest_row["episodes"]) else None,
                active_vessels=int(latest_row["active_vessels"]) if pd.notna(latest_row["active_vessels"]) else None,
                dwell_median_h=_safe_float(latest_row["dwell_median_h"]),
                dwell_p90_h=_safe_float(latest_row["dwell_p90_h"]),
                coverage_ratio=_safe_float(latest_row["coverage_ratio"]),
                z_dwell=_safe_float(latest_row["z_dwell"]),
                baseline_insufficient=bool(latest_row["baseline_insufficient"]) if pd.notna(latest_row["baseline_insufficient"]) else None,
                tanker_share=_safe_float(latest_row["tanker_share"]),
            )

            # Statistics
            stats = {
                "samples_count": len(anch_df),
                "dwell_median_h": {
                    "mean": _safe_float(anch_df["dwell_median_h"].mean()),
                    "max": _safe_float(anch_df["dwell_median_h"].max()),
                    "p90": _safe_float(anch_df["dwell_median_h"].quantile(0.9)),
                },
                "dwell_p90_h": {
                    "mean": _safe_float(anch_df["dwell_p90_h"].mean()),
                    "max": _safe_float(anch_df["dwell_p90_h"].max()),
                },
                "coverage_ratio": {
                    "mean": _safe_float(anch_df["coverage_ratio"].mean()),
                    "max": _safe_float(anch_df["coverage_ratio"].max()),
                },
                "z_dwell": {
                    "mean": _safe_float(anch_df["z_dwell"].mean()),
                    "max": _safe_float(anch_df["z_dwell"].max()),
                    "anomaly_days": int((anch_df["z_dwell"].abs() > 2.0).sum()) if "z_dwell" in anch_df.columns else 0,
                },
            }

            # Trend (last 7 days or window, whichever is smaller)
            trend_days = min(7, len(anch_df))
            trend_df = anch_df.head(trend_days).sort_values("ds")

            trend = []
            for _, row in trend_df.iterrows():
                trend.append(AnchorageDailySummary(
                    ds=row["ds"].isoformat() if hasattr(row["ds"], "isoformat") else str(row["ds"]),
                    anchorage_id=row["anchorage_id"],
                    episodes=int(row["episodes"]) if pd.notna(row["episodes"]) else None,
                    active_vessels=int(row["active_vessels"]) if pd.notna(row["active_vessels"]) else None,
                    dwell_median_h=_safe_float(row["dwell_median_h"]),
                    dwell_p90_h=_safe_float(row["dwell_p90_h"]),
                    coverage_ratio=_safe_float(row["coverage_ratio"]),
                    z_dwell=_safe_float(row["z_dwell"]),
                    baseline_insufficient=bool(row["baseline_insufficient"]) if pd.notna(row["baseline_insufficient"]) else None,
                    tanker_share=_safe_float(row["tanker_share"]),
                ).dict())

            result["anchorages"].append(AnchorageSummaryResponse(
                anchorage_id=anch_id,
                window=window,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                latest=latest.dict(),
                statistics=stats,
                trend=trend,
            ).dict())

        return result
