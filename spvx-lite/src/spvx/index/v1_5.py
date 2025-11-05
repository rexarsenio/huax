"""
SPVX Global Index v1.5 - Robust & Explainable

Formula per corridor c:
  S_c(t) = w_flux · FluxScore + w_delay · DelayScore + w_sis · SIS_score

Where:
  - FluxScore: Seasonal z-score of gate crossings (robust scaling)
  - DelayScore: Transit time ratio vs. 30d baseline (when available)
  - SIS_score: Sea Impact Score (weather impact)

Global Index:
  GI(t) = Σ w_c · S_c'(t)  where S_c' includes coverage-gating

Simplified for limited data:
  - No 30-day baseline yet → use simple normalization
  - Transit times = 0 → skip DelayScore
  - Weights: 0.7·Flux + 0.3·SIS
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import duckdb
import numpy as np
import pandas as pd


@dataclass
class IndexConfig:
    """Configuration for v1.5 index calculation."""

    # Component weights (when transit data available)
    weight_flux: float = 0.50
    weight_delay: float = 0.30
    weight_sis: float = 0.20

    # Weights for simplified version (no transit data)
    weight_flux_simple: float = 0.70
    weight_sis_simple: float = 0.30

    # Baseline window for z-score
    baseline_days: int = 30

    # Coverage gating threshold
    coverage_threshold: float = 0.7

    # Corridor weights (anti-correlation, traffic share)
    corridor_weights: dict[str, float] = None

    def __post_init__(self):
        if self.corridor_weights is None:
            # Default: Equal weight for major chokepoints
            # Malacca & Singapore treated as one (high correlation)
            # Updated to use actual CHOKEPOINT_ IDs from polygon_events
            self.corridor_weights = {
                "CHOKEPOINT_MALACCA->UNK": 0.40,
                "CHOKEPOINT_SINGAPORE_STRAIT->UNK": 0.00,  # Skip, correlated with Malacca
                "CHOKEPOINT_SUEZ_NORTH->UNK": 0.30,
                "CHOKEPOINT_GIBRALTAR->UNK": 0.15,
                "CHOKEPOINT_BOSPORUS->UNK": 0.15,
            }


def sigmoid(x: float) -> float:
    """Sigmoid function σ(x) = 1 / (1 + e^-x), clipped to [0,1]."""
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -10, 10))))


def compute_flux_score(
    flux_current: float,
    flux_baseline_median: float,
    flux_baseline_mad: float,
) -> float:
    """
    Compute FluxScore from z-score.

    z_flux = (flux - median_30d) / MAD_30d
    FluxScore = σ(z_flux / 1.5)

    Higher flux → higher score (more congestion)
    """
    if flux_baseline_mad == 0:
        return 0.5  # Neutral if no variance

    z_flux = (flux_current - flux_baseline_median) / flux_baseline_mad
    flux_score = sigmoid(z_flux / 1.5)
    return float(np.clip(flux_score, 0.0, 1.0))


def compute_sis_score(sis_mean: float) -> float:
    """
    Normalize SIS to [0,1].

    SIS already in [0,1], just clip.
    """
    return float(np.clip(sis_mean, 0.0, 1.0))


def compute_corridor_stress(
    flux_score: float,
    sis_score: float,
    delay_score: float = 0.0,
    use_delay: bool = False,
    config: Optional[IndexConfig] = None,
) -> float:
    """
    Compute corridor stress S_c(t).

    S_c = w_flux · FluxScore + w_delay · DelayScore + w_sis · SIS_score

    If no transit data: S_c = 0.7 · FluxScore + 0.3 · SIS_score
    """
    cfg = config or IndexConfig()

    if use_delay:
        stress = (
            cfg.weight_flux * flux_score
            + cfg.weight_delay * delay_score
            + cfg.weight_sis * sis_score
        )
    else:
        # Simplified: no delay data
        stress = (
            cfg.weight_flux_simple * flux_score
            + cfg.weight_sis_simple * sis_score
        )

    return float(np.clip(stress, 0.0, 1.0))


def compute_global_index_v15(
    con: duckdb.DuckDBPyConnection,
    target_date: Optional[dt.date] = None,
    config: Optional[IndexConfig] = None,
) -> dict:
    """
    Compute Global Index v1.5 for a given date.

    Returns:
        {
            "date": date,
            "global_index": float,  # 0-1
            "global_index_scaled": float,  # 0-200, baseline=100
            "components": {
                "corridor_id": {
                    "flux_score": float,
                    "sis_score": float,
                    "stress": float,
                    "weight": float,
                },
                ...
            },
            "coverage": float,  # fraction of corridors with data
        }
    """
    cfg = config or IndexConfig()
    target_date = target_date or dt.date.today()

    # 1. Get SIS data for target date
    sis_data = con.execute("""
        SELECT corridor_id, sis_mean, sis_p90, we_p90_m, n_samples
        FROM sea_state_daily
        WHERE ds = ?
    """, [target_date]).fetchdf()

    # 2. Get flux data for target date & baseline
    baseline_start = target_date - dt.timedelta(days=cfg.baseline_days)

    flux_current = con.execute("""
        SELECT
            gate_id as corridor_id,
            SUM(crossings) as total_crossings
        FROM gate_flux_daily
        WHERE ds = ?
        GROUP BY gate_id
    """, [target_date]).fetchdf()

    flux_baseline = con.execute("""
        SELECT
            gate_id as corridor_id,
            ds,
            SUM(crossings) as total_crossings
        FROM gate_flux_daily
        WHERE ds BETWEEN ? AND ?
        GROUP BY gate_id, ds
    """, [baseline_start, target_date]).fetchdf()

    # 3. Compute components per corridor
    components = {}
    total_weight = 0.0
    weighted_stress_sum = 0.0
    corridors_with_data = 0

    # Combine SIS and Flux corridors
    all_corridors = set(sis_data['corridor_id'].tolist() if not sis_data.empty else []) | \
                    set(flux_current['corridor_id'].tolist() if not flux_current.empty else [])

    for corridor_id in all_corridors:
        weight = cfg.corridor_weights.get(corridor_id, 0.0)
        if weight == 0:
            continue  # Skip corridors with 0 weight

        # SIS Score
        sis_row = sis_data[sis_data['corridor_id'] == corridor_id]
        if not sis_row.empty:
            sis_score = compute_sis_score(float(sis_row['sis_mean'].iloc[0]))
            has_sis = True
        else:
            sis_score = 0.5  # Neutral default
            has_sis = False

        # Flux Score
        flux_row = flux_current[flux_current['corridor_id'] == corridor_id]
        if not flux_row.empty and not flux_baseline.empty:
            current_flux = float(flux_row['total_crossings'].iloc[0])
            baseline_data = flux_baseline[flux_baseline['corridor_id'] == corridor_id]['total_crossings']

            if len(baseline_data) > 0:
                flux_median = float(baseline_data.median())
                # Compute MAD manually: median(|x - median(x)|)
                flux_mad = float((baseline_data - flux_median).abs().median())
                flux_score = compute_flux_score(current_flux, flux_median, flux_mad)
                has_flux = True
            else:
                flux_score = 0.5
                has_flux = False
        else:
            flux_score = 0.5
            has_flux = False

        # Compute stress
        stress = compute_corridor_stress(
            flux_score=flux_score,
            sis_score=sis_score,
            use_delay=False,  # No transit data yet
            config=cfg,
        )

        # Coverage check
        if has_sis or has_flux:
            corridors_with_data += 1

        components[corridor_id] = {
            "flux_score": flux_score,
            "sis_score": sis_score,
            "delay_score": 0.0,  # Not available
            "stress": stress,
            "weight": weight,
            "has_data": has_sis or has_flux,
        }

        # Accumulate weighted stress
        weighted_stress_sum += weight * stress
        total_weight += weight

    # 4. Global Index
    if total_weight > 0:
        global_index = weighted_stress_sum / total_weight
    else:
        global_index = 0.5  # Neutral if no data

    # Scale to 0-200 (baseline = 100)
    global_index_scaled = global_index * 200

    # Coverage
    coverage = corridors_with_data / len(all_corridors) if all_corridors else 0.0

    return {
        "date": target_date.isoformat(),
        "global_index": float(global_index),
        "global_index_scaled": float(global_index_scaled),
        "components": components,
        "coverage": float(coverage),
        "num_corridors": len(all_corridors),
        "corridors_with_data": corridors_with_data,
    }


def compute_global_index_timeseries(
    con: duckdb.DuckDBPyConnection,
    start_date: dt.date,
    end_date: dt.date,
    config: Optional[IndexConfig] = None,
) -> pd.DataFrame:
    """
    Compute Global Index v1.5 for a time range.

    Returns DataFrame with columns:
      - date
      - global_index (0-1)
      - global_index_scaled (0-200)
      - coverage
    """
    cfg = config or IndexConfig()
    results = []

    current_date = start_date
    while current_date <= end_date:
        result = compute_global_index_v15(con, current_date, cfg)
        results.append({
            "date": current_date,
            "global_index": result["global_index"],
            "global_index_scaled": result["global_index_scaled"],
            "coverage": result["coverage"],
        })
        current_date += dt.timedelta(days=1)

    return pd.DataFrame(results)


def forecast_global_index_v15(
    con: duckdb.DuckDBPyConnection,
    forecast_date: dt.date,
    horizon_days: int = 7,
    config: Optional[IndexConfig] = None,
) -> pd.DataFrame:
    """
    Forecast Global Index v1.5 for next H days.

    Fallback approach (no CMEMS forecast data):
      Ŝ_c(t+h) = EMA_7d(S_c) + α·(hs_forecast - hs_norm)

    Where:
      - EMA_7d: 7-day exponential moving average of corridor stress
      - hs_forecast: Assumed constant (persistence) or use seasonal norm
      - α: Weather sensitivity parameter (default 0.3)
      - Uncertainty bands: ±20% around forecast

    Args:
        con: DuckDB connection
        forecast_date: Base date for forecast (typically today)
        horizon_days: Number of days to forecast (default 7)
        config: Index configuration

    Returns:
        DataFrame with columns:
          - forecast_date: Date of forecast
          - horizon_h: Hours ahead (24, 48, ..., 168)
          - global_index_forecast: Point forecast (0-1)
          - global_index_scaled: Scaled forecast (0-200)
          - lower_bound: 20th percentile
          - upper_bound: 80th percentile
          - method: "persistence" or "seasonal_norm"
    """
    cfg = config or IndexConfig()
    alpha = 0.3  # Weather sensitivity

    # Step 1: Get historical stress for EMA calculation (last 30 days)
    lookback_days = 30
    start_date = forecast_date - dt.timedelta(days=lookback_days)

    historical_df = compute_global_index_timeseries(con, start_date, forecast_date, config=cfg)

    if historical_df.empty or len(historical_df) < 7:
        # Not enough data - return baseline forecast
        results = []
        for h in range(1, horizon_days + 1):
            fdate = forecast_date + dt.timedelta(days=h)
            results.append({
                "forecast_date": fdate,
                "horizon_h": h * 24,
                "global_index_forecast": 0.5,
                "global_index_scaled": 100.0,
                "lower_bound": 90.0,
                "upper_bound": 110.0,
                "method": "baseline_fallback",
                "coverage": 0.0,
            })
        return pd.DataFrame(results)

    # Step 2: Compute 7-day EMA of global index
    historical_df = historical_df.sort_values("date")
    ema_7d = historical_df["global_index"].ewm(span=7, adjust=False).mean().iloc[-1]

    # Step 3: Get average SIS for weather component
    # Query recent SIS data to understand current weather conditions
    sis_query = """
        SELECT
            corridor_id,
            AVG(sis_mean) as avg_sis,
            AVG(we_p90_m) as avg_wave_height
        FROM sea_state_daily
        WHERE ds >= ? AND ds <= ?
        GROUP BY corridor_id
    """
    sis_recent = con.execute(
        sis_query,
        [forecast_date - dt.timedelta(days=7), forecast_date]
    ).df()

    # Step 4: Generate forecast for each horizon
    results = []
    for h in range(1, horizon_days + 1):
        fdate = forecast_date + dt.timedelta(days=h)

        # Persistence assumption: weather stays the same
        # In production, this would use CMEMS forecast data
        weather_delta = 0.0  # Assume no change from current conditions

        # Forecast = EMA + weather adjustment
        forecast_value = float(np.clip(ema_7d + alpha * weather_delta, 0.0, 1.0))
        forecast_scaled = forecast_value * 200.0

        # Uncertainty increases with horizon
        uncertainty_factor = 1.0 + (h / horizon_days) * 0.2  # 0-20% increase
        lower = max(0.0, forecast_scaled - 10 * uncertainty_factor)
        upper = min(200.0, forecast_scaled + 10 * uncertainty_factor)

        results.append({
            "forecast_date": fdate,
            "horizon_h": h * 24,
            "global_index_forecast": forecast_value,
            "global_index_scaled": forecast_scaled,
            "lower_bound": lower,
            "upper_bound": upper,
            "method": "persistence_ema",
            "coverage": historical_df["coverage"].iloc[-1] if not historical_df.empty else 0.0,
        })

    return pd.DataFrame(results)
