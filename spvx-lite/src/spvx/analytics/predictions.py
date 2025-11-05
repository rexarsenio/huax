"""
Predictive models for maritime traffic forecasting.

Models:
- Traffic volume prediction (next 24h)
- ETA prediction for vessels
- Port occupancy forecasting
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class TrafficPrediction:
    """Predicted traffic for a corridor."""

    corridor_id: str
    timestamp: dt.datetime
    predicted_vessels: float
    confidence_lower: float
    confidence_upper: float
    confidence_level: float = 0.95


class TrafficPredictor:
    """Simple traffic prediction using exponential smoothing."""

    def __init__(self, alpha: float = 0.3):
        """
        Initialize predictor.

        Args:
            alpha: Smoothing parameter (0 < alpha < 1)
        """
        self.alpha = alpha
        self.models: Dict[str, Dict] = {}

    def fit(self, df: pd.DataFrame, corridor_id: str) -> None:
        """
        Fit model to historical data.

        Args:
            df: DataFrame with columns: timestamp, value
            corridor_id: Corridor identifier
        """
        df = df.sort_values('timestamp')
        values = df['value'].values

        # Calculate trend and seasonality
        level = values[0]
        trend = 0.0

        levels = []
        trends = []

        for value in values:
            # Update level and trend using Holt's linear method
            prev_level = level
            level = self.alpha * value + (1 - self.alpha) * (level + trend)
            trend = self.alpha * (level - prev_level) + (1 - self.alpha) * trend

            levels.append(level)
            trends.append(trend)

        # Calculate residuals for confidence intervals
        predictions = np.array([l + t for l, t in zip(levels, trends)])
        residuals = values - predictions[:-1]  # Skip last (no actual to compare)

        self.models[corridor_id] = {
            'level': level,
            'trend': trend,
            'residual_std': np.std(residuals) if len(residuals) > 0 else 0.0,
            'last_update': dt.datetime.utcnow(),
        }

    def predict(
        self,
        corridor_id: str,
        horizon_hours: int = 24,
    ) -> List[TrafficPrediction]:
        """
        Predict traffic for next N hours.

        Args:
            corridor_id: Corridor identifier
            horizon_hours: Hours to predict ahead

        Returns:
            List of predictions
        """
        if corridor_id not in self.models:
            return []

        model = self.models[corridor_id]
        predictions = []

        level = model['level']
        trend = model['trend']
        residual_std = model['residual_std']

        # Z-score for 95% confidence interval
        z_score = 1.96

        base_time = dt.datetime.utcnow()

        for h in range(1, horizon_hours + 1):
            # Point forecast
            forecast = level + h * trend

            # Confidence interval (wider for longer horizons)
            error_margin = z_score * residual_std * np.sqrt(h)

            predictions.append(TrafficPrediction(
                corridor_id=corridor_id,
                timestamp=base_time + dt.timedelta(hours=h),
                predicted_vessels=max(0, forecast),
                confidence_lower=max(0, forecast - error_margin),
                confidence_upper=forecast + error_margin,
            ))

        return predictions

    def get_model_info(self, corridor_id: str) -> Optional[Dict]:
        """Get model information for a corridor."""
        return self.models.get(corridor_id)


def predict_corridor_traffic(
    con,
    corridor_id: str,
    horizon_hours: int = 24,
    training_hours: int = 168,  # 7 days
) -> List[TrafficPrediction]:
    """
    Predict traffic for a corridor.

    Args:
        con: DuckDB connection
        corridor_id: Corridor to predict
        horizon_hours: Hours to predict ahead
        training_hours: Hours of historical data for training

    Returns:
        List of predictions
    """
    # Fetch historical data
    df = con.execute(
        f"""
        SELECT
            DATE_TRUNC('hour', ts) AS timestamp,
            COUNT(DISTINCT mmsi) AS value
        FROM polygon_events
        WHERE polygon_id = ?
          AND event = 'enter'
          AND ts >= NOW() - INTERVAL '{training_hours} hours'
        GROUP BY 1
        ORDER BY 1
        """,
        [corridor_id],
    ).df()

    if df.empty:
        return []

    # Train and predict
    predictor = TrafficPredictor()
    predictor.fit(df, corridor_id)

    return predictor.predict(corridor_id, horizon_hours)


def predict_all_corridors(
    con,
    horizon_hours: int = 24,
) -> Dict[str, List[TrafficPrediction]]:
    """
    Predict traffic for all corridors.

    Args:
        con: DuckDB connection
        horizon_hours: Hours to predict ahead

    Returns:
        Dictionary mapping corridor_id to predictions
    """
    # Get list of corridors
    corridors = con.execute(
        """
        SELECT DISTINCT polygon_id
        FROM polygon_events
        WHERE event = 'enter'
          AND ts >= NOW() - INTERVAL '7 days'
        """
    ).df()

    if corridors.empty:
        return {}

    predictions = {}

    for corridor_id in corridors['polygon_id']:
        preds = predict_corridor_traffic(con, corridor_id, horizon_hours)
        if preds:
            predictions[corridor_id] = preds

    return predictions


__all__ = [
    "TrafficPrediction",
    "TrafficPredictor",
    "predict_corridor_traffic",
    "predict_all_corridors",
]
