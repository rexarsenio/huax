"""
TH-4: Teapot Heartbeat REST API

Production-grade API for real-time anchorage monitoring and trading signals.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Models

class AnchorageStatus(BaseModel):
    """Current anchorage status with live metrics."""
    anchorage_id: str
    name: str
    current_vessels: int
    median_dwell_h: float
    p90_dwell_h: float
    z_score: Optional[float] = None
    anomaly_detected: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    last_updated: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "anchorage_id": "ANCH_OPL_SIN",
                "name": "OPL Singapore",
                "current_vessels": 23,
                "median_dwell_h": 35.2,
                "p90_dwell_h": 48.5,
                "z_score": 6.52,
                "anomaly_detected": True,
                "confidence": 0.92,
                "last_updated": "2025-11-06T10:30:00Z"
            }
        }


class CorridorSIS(BaseModel):
    """Sea Impact Score for a corridor."""
    corridor_id: str
    date: datetime
    sis_mean: float
    sis_p90: float
    head_current_p90: float
    head_wind_p90: float
    wave_encounter_p90: float
    samples_n: int


class Episode(BaseModel):
    """Anchorage dwell episode."""
    episode_id: str
    anchorage_id: str
    mmsi: int
    vessel_name: Optional[str] = None
    ts_entry: datetime
    ts_exit: Optional[datetime] = None
    dwell_hours: Optional[float] = None
    confidence: float
    still_anchored: bool


class SupplyChainHealth(BaseModel):
    """Health metrics for entire supply chain."""
    chain_name: str
    timestamp: datetime

    # Malacca Pulse
    malacca_gate_flux_24h: int
    malacca_sis_current: float
    malacca_status: str  # "green", "yellow", "red"

    # OPL Dwell
    opl_vessels_current: int
    opl_median_dwell_h: float
    opl_z_score: float
    opl_status: str

    # Shandong Anchorages
    shandong_total_vessels: int
    shandong_avg_dwell_h: float
    shandong_status: str

    # Overall health score (0-100)
    health_score: float = Field(ge=0, le=100)

    # Trading signal
    trading_signal: str  # "LONG", "SHORT", "NEUTRAL"
    signal_confidence: float = Field(ge=0, le=1)


class ForecastPoint(BaseModel):
    """Single forecast point."""
    date: datetime
    predicted_dwell_h: float
    confidence_lower: float  # 5th percentile
    confidence_upper: float  # 95th percentile
    probability_congestion: float  # P(dwell > threshold)


class AnchorageForecast(BaseModel):
    """Multi-day anchorage forecast."""
    anchorage_id: str
    forecast_generated: datetime
    model_version: str
    forecast: List[ForecastPoint]


# API App

def create_app(db_path: str = "db/spvx.duckdb") -> FastAPI:
    """Create FastAPI app with all endpoints."""

    app = FastAPI(
        title="Teapot Heartbeat API (TH-4)",
        description="Real-time maritime intelligence for trading signals",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production: specify allowed origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db():
        """Get database connection."""
        return duckdb.connect(db_path, read_only=True)

    # === Endpoints ===

    @app.get("/", tags=["Health"])
    def root():
        """API health check."""
        return {
            "status": "operational",
            "api": "Teapot Heartbeat TH-4",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat()
        }

    @app.get("/api/v1/anchorages", response_model=List[str], tags=["Anchorages"])
    def list_anchorages():
        """List all available anchorages."""
        con = get_db()
        result = con.execute("""
            SELECT DISTINCT anchorage_id
            FROM anchorage_episodes
            ORDER BY anchorage_id
        """).fetchall()
        con.close()
        return [row[0] for row in result]

    @app.get("/api/v1/anchorages/{anchorage_id}/status", response_model=AnchorageStatus, tags=["Anchorages"])
    def get_anchorage_status(anchorage_id: str):
        """Get current status for an anchorage."""
        con = get_db()

        # Get latest daily metrics
        result = con.execute("""
            SELECT
                ds,
                median_dwell_h,
                p90_dwell_h,
                z_dwell,
                anomaly_detected,
                episode_count
            FROM anchorage_daily_dwell
            WHERE anchorage_id = ?
            ORDER BY ds DESC
            LIMIT 1
        """, [anchorage_id]).fetchone()

        if not result:
            con.close()
            raise HTTPException(status_code=404, detail=f"Anchorage {anchorage_id} not found")

        ds, median_dwell, p90_dwell, z_score, anomaly, episodes = result

        # Count currently anchored vessels (open sessions)
        current = con.execute("""
            SELECT COUNT(*)
            FROM anchorage_open_sessions
            WHERE anchorage_id = ?
        """, [anchorage_id]).fetchone()[0]

        # Get average confidence from recent episodes
        confidence = con.execute("""
            SELECT AVG(confidence)
            FROM anchorage_episodes
            WHERE anchorage_id = ?
              AND ts_exit >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        """, [anchorage_id]).fetchone()[0] or 0.85

        con.close()

        return AnchorageStatus(
            anchorage_id=anchorage_id,
            name=anchorage_id.replace("ANCH_", "").replace("_", " ").title(),
            current_vessels=current,
            median_dwell_h=median_dwell,
            p90_dwell_h=p90_dwell,
            z_score=z_score,
            anomaly_detected=anomaly,
            confidence=confidence,
            last_updated=datetime.fromisoformat(str(ds))
        )

    @app.get("/api/v1/anchorages/{anchorage_id}/episodes", response_model=List[Episode], tags=["Anchorages"])
    def get_anchorage_episodes(
        anchorage_id: str,
        days: int = Query(7, description="Lookback window in days")
    ):
        """Get recent episodes for an anchorage."""
        con = get_db()

        result = con.execute("""
            SELECT
                episode_id,
                anchorage_id,
                mmsi,
                vessel_name,
                ts_entry,
                ts_exit,
                dwell_hours,
                COALESCE(confidence, 1.0) as confidence
            FROM anchorage_episodes
            WHERE anchorage_id = ?
              AND ts_entry >= CURRENT_TIMESTAMP - INTERVAL '{days} days'
            ORDER BY ts_entry DESC
            LIMIT 100
        """.format(days=days), [anchorage_id]).fetchall()

        con.close()

        episodes = []
        for row in result:
            ep_id, anch, mmsi, vname, entry, exit, dwell, conf = row
            episodes.append(Episode(
                episode_id=ep_id,
                anchorage_id=anch,
                mmsi=mmsi,
                vessel_name=vname,
                ts_entry=entry,
                ts_exit=exit,
                dwell_hours=dwell,
                confidence=conf,
                still_anchored=(exit is None)
            ))

        return episodes

    @app.get("/api/v1/corridors/{corridor_id}/sis", response_model=List[CorridorSIS], tags=["Corridors"])
    def get_corridor_sis(
        corridor_id: str,
        days: int = Query(30, description="Lookback window in days")
    ):
        """Get historical SIS data for a corridor."""
        con = get_db()

        result = con.execute("""
            SELECT
                corridor_id,
                ds,
                sis_mean,
                sis_p90,
                head_current_p90,
                head_wind_p90,
                wave_encounter_p90,
                samples_n
            FROM sis_daily
            WHERE corridor_id = ?
              AND ds >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY ds DESC
        """.format(days=days), [corridor_id]).fetchall()

        con.close()

        if not result:
            raise HTTPException(status_code=404, detail=f"No SIS data for corridor {corridor_id}")

        return [
            CorridorSIS(
                corridor_id=r[0],
                date=r[1],
                sis_mean=r[2],
                sis_p90=r[3],
                head_current_p90=r[4],
                head_wind_p90=r[5],
                wave_encounter_p90=r[6],
                samples_n=r[7]
            )
            for r in result
        ]

    @app.get("/api/v1/supply-chain/malacca-shandong/health", response_model=SupplyChainHealth, tags=["Supply Chain"])
    def get_supply_chain_health():
        """Get complete Malacca → OPL → Shandong supply chain health."""
        con = get_db()

        # Malacca gate flux (last 24h)
        malacca_flux = con.execute("""
            SELECT COUNT(*)
            FROM gate_crossings
            WHERE gate_id LIKE 'GATE_MALACCA%'
              AND ts >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """).fetchone()[0] or 0

        # Malacca SIS (latest)
        malacca_sis = con.execute("""
            SELECT sis_mean
            FROM sis_daily
            WHERE corridor_id LIKE '%MALACCA%'
            ORDER BY ds DESC
            LIMIT 1
        """).fetchone()
        malacca_sis_val = malacca_sis[0] if malacca_sis else 0.0

        # OPL dwell metrics
        opl_metrics = con.execute("""
            SELECT
                episode_count as vessels,
                median_dwell_h,
                z_dwell,
                anomaly_detected
            FROM anchorage_daily_dwell
            WHERE anchorage_id = 'ANCH_OPL_SIN'
            ORDER BY ds DESC
            LIMIT 1
        """).fetchone()

        if opl_metrics:
            opl_vessels, opl_dwell, opl_z, opl_anomaly = opl_metrics
        else:
            opl_vessels, opl_dwell, opl_z, opl_anomaly = 0, 0.0, 0.0, False

        # Shandong anchorages (aggregate)
        shandong_metrics = con.execute("""
            SELECT
                SUM(episode_count) as total_vessels,
                AVG(median_dwell_h) as avg_dwell
            FROM anchorage_daily_dwell
            WHERE anchorage_id LIKE 'ANCH_%'
              AND anchorage_id NOT LIKE 'ANCH_OPL%'
              AND ds = (SELECT MAX(ds) FROM anchorage_daily_dwell)
        """).fetchone()

        if shandong_metrics and shandong_metrics[0]:
            shandong_vessels, shandong_dwell = shandong_metrics
        else:
            shandong_vessels, shandong_dwell = 0, 0.0

        con.close()

        # Determine status
        malacca_status = "green" if malacca_sis_val < 0.3 else ("yellow" if malacca_sis_val < 0.6 else "red")
        opl_status = "green" if not opl_anomaly else ("yellow" if opl_z < 4.0 else "red")
        shandong_status = "green" if shandong_vessels < 50 else ("yellow" if shandong_vessels < 80 else "red")

        # Health score (0-100)
        health_score = 100.0
        if malacca_status == "yellow": health_score -= 15
        if malacca_status == "red": health_score -= 35
        if opl_status == "yellow": health_score -= 20
        if opl_status == "red": health_score -= 40
        if shandong_status == "yellow": health_score -= 10
        if shandong_status == "red": health_score -= 25

        # Trading signal
        if health_score > 80:
            signal, signal_conf = "LONG", 0.85
        elif health_score < 50:
            signal, signal_conf = "SHORT", 0.75
        else:
            signal, signal_conf = "NEUTRAL", 0.60

        return SupplyChainHealth(
            chain_name="Malacca → OPL → Shandong",
            timestamp=datetime.utcnow(),
            malacca_gate_flux_24h=malacca_flux,
            malacca_sis_current=malacca_sis_val,
            malacca_status=malacca_status,
            opl_vessels_current=opl_vessels,
            opl_median_dwell_h=opl_dwell,
            opl_z_score=opl_z,
            opl_status=opl_status,
            shandong_total_vessels=shandong_vessels,
            shandong_avg_dwell_h=shandong_dwell,
            shandong_status=shandong_status,
            health_score=health_score,
            trading_signal=signal,
            signal_confidence=signal_conf
        )

    @app.get("/api/v1/anchorages/{anchorage_id}/forecast", response_model=AnchorageForecast, tags=["Forecasting"])
    def get_anchorage_forecast(
        anchorage_id: str,
        days_ahead: int = Query(7, description="Forecast horizon in days")
    ):
        """
        Get ML-based forecast for anchorage dwell times.

        NOTE: This endpoint requires ML model training (Phase 2).
        Currently returns placeholder forecast based on historical baseline.
        """
        con = get_db()

        # Get historical baseline
        baseline = con.execute("""
            SELECT AVG(median_dwell_h), STDDEV(median_dwell_h)
            FROM anchorage_daily_dwell
            WHERE anchorage_id = ?
              AND ds >= CURRENT_DATE - INTERVAL '90 days'
        """, [anchorage_id]).fetchone()

        con.close()

        if not baseline or baseline[0] is None:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient historical data for {anchorage_id}"
            )

        mean, std = baseline
        std = std or mean * 0.15  # Assume 15% std if not available

        # Generate simple forecast (placeholder until ML model trained)
        forecast_points = []
        for i in range(1, days_ahead + 1):
            forecast_date = datetime.utcnow() + timedelta(days=i)

            # Simple baseline forecast (will be replaced by XGBoost)
            predicted = mean
            lower = mean - 1.96 * std  # 95% CI
            upper = mean + 1.96 * std
            prob_congestion = 0.3  # Placeholder

            forecast_points.append(ForecastPoint(
                date=forecast_date,
                predicted_dwell_h=predicted,
                confidence_lower=max(0, lower),
                confidence_upper=upper,
                probability_congestion=prob_congestion
            ))

        return AnchorageForecast(
            anchorage_id=anchorage_id,
            forecast_generated=datetime.utcnow(),
            model_version="baseline_v1",  # Will be "xgboost_v1" after Phase 2
            forecast=forecast_points
        )

    return app


# Development server
if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
