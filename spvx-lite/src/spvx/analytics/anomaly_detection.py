"""
Real-time anomaly detection for maritime traffic patterns.

Detects unusual patterns in:
- Traffic volume (sudden spikes/drops)
- Corridor utilization
- Vessel behavior
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class Anomaly:
    """Detected anomaly in maritime traffic."""

    timestamp: dt.datetime
    corridor_id: str
    anomaly_type: str  # "spike", "drop", "unusual_pattern"
    severity: float  # 0.0 to 1.0
    expected_value: float
    actual_value: float
    z_score: float
    description: str


class AnomalyDetector:
    """Detects anomalies in maritime traffic using statistical methods."""

    def __init__(self, window_hours: int = 168):  # 7 days
        """
        Initialize anomaly detector.

        Args:
            window_hours: Rolling window for baseline calculation (default: 7 days)
        """
        self.window_hours = window_hours
        self.baselines: Dict[str, Dict[str, float]] = {}

    def update_baseline(self, df: pd.DataFrame) -> None:
        """
        Update baseline statistics from historical data.

        Args:
            df: DataFrame with columns: timestamp, corridor_id, value
        """
        for corridor_id in df['corridor_id'].unique():
            corridor_data = df[df['corridor_id'] == corridor_id]['value']

            self.baselines[corridor_id] = {
                'mean': float(corridor_data.mean()),
                'std': float(corridor_data.std()),
                'median': float(corridor_data.median()),
                'mad': float((corridor_data - corridor_data.median()).abs().median()),
                'p95': float(corridor_data.quantile(0.95)),
                'p05': float(corridor_data.quantile(0.05)),
            }

    def detect_traffic_anomalies(
        self,
        corridor_id: str,
        current_value: float,
        timestamp: Optional[dt.datetime] = None,
    ) -> Optional[Anomaly]:
        """
        Detect anomalies in traffic volume using modified Z-score.

        Args:
            corridor_id: Corridor identifier
            current_value: Current traffic count
            timestamp: Event timestamp (default: now)

        Returns:
            Anomaly object if detected, None otherwise
        """
        if corridor_id not in self.baselines:
            return None

        baseline = self.baselines[corridor_id]
        timestamp = timestamp or dt.datetime.utcnow()

        # Calculate modified Z-score using MAD (more robust to outliers)
        mad = baseline['mad']
        if mad < 1e-6:
            mad = baseline['std']  # Fallback to std if MAD is too small

        if mad < 1e-6:
            return None  # Not enough variance to detect anomalies

        median = baseline['median']
        z_score = 0.6745 * (current_value - median) / mad

        # Thresholds for anomaly detection
        SPIKE_THRESHOLD = 3.5  # Modified Z-score > 3.5
        DROP_THRESHOLD = -3.5  # Modified Z-score < -3.5

        anomaly_type = None
        severity = 0.0

        if z_score > SPIKE_THRESHOLD:
            anomaly_type = "spike"
            severity = min(1.0, (z_score - SPIKE_THRESHOLD) / 5.0)
            description = f"Unusual traffic spike: {current_value:.0f} vessels (expected: {median:.0f})"

        elif z_score < DROP_THRESHOLD:
            anomaly_type = "drop"
            severity = min(1.0, (abs(z_score) - abs(DROP_THRESHOLD)) / 5.0)
            description = f"Unusual traffic drop: {current_value:.0f} vessels (expected: {median:.0f})"

        else:
            return None  # No anomaly detected

        return Anomaly(
            timestamp=timestamp,
            corridor_id=corridor_id,
            anomaly_type=anomaly_type,
            severity=severity,
            expected_value=median,
            actual_value=current_value,
            z_score=z_score,
            description=description,
        )

    def detect_time_series_anomalies(
        self,
        df: pd.DataFrame,
        corridor_id: str,
    ) -> List[Anomaly]:
        """
        Detect anomalies in time series data.

        Args:
            df: DataFrame with columns: timestamp, value
            corridor_id: Corridor identifier

        Returns:
            List of detected anomalies
        """
        anomalies = []

        # Calculate rolling statistics
        df = df.sort_values('timestamp')
        df['rolling_mean'] = df['value'].rolling(window=24, min_periods=6).mean()
        df['rolling_std'] = df['value'].rolling(window=24, min_periods=6).std()

        for idx, row in df.iterrows():
            if pd.isna(row['rolling_mean']) or pd.isna(row['rolling_std']):
                continue

            if row['rolling_std'] < 1e-6:
                continue

            z_score = (row['value'] - row['rolling_mean']) / row['rolling_std']

            if abs(z_score) > 3.0:
                anomaly_type = "spike" if z_score > 0 else "drop"
                severity = min(1.0, (abs(z_score) - 3.0) / 3.0)

                anomalies.append(Anomaly(
                    timestamp=row['timestamp'],
                    corridor_id=corridor_id,
                    anomaly_type=anomaly_type,
                    severity=severity,
                    expected_value=row['rolling_mean'],
                    actual_value=row['value'],
                    z_score=z_score,
                    description=f"Time series anomaly: {row['value']:.0f} vs expected {row['rolling_mean']:.0f}",
                ))

        return anomalies

    def get_baseline_summary(self) -> Dict[str, Dict[str, float]]:
        """Get current baseline statistics for all corridors."""
        return self.baselines


def detect_corridor_anomalies(
    con,
    lookback_hours: int = 24,
    baseline_window_hours: int = 168,
) -> List[Anomaly]:
    """
    Detect anomalies in corridor traffic from database.

    Args:
        con: DuckDB connection
        lookback_hours: Hours to analyze for anomalies
        baseline_window_hours: Hours for baseline calculation

    Returns:
        List of detected anomalies
    """
    # Fetch historical data for baseline
    baseline_df = con.execute(f"""
        SELECT
            DATE_TRUNC('hour', ts_in) as timestamp,
            polygon_id as corridor_id,
            COUNT(DISTINCT mmsi) as value
        FROM polygon_events
        WHERE ts_in >= NOW() - INTERVAL '{baseline_window_hours} hours'
        GROUP BY 1, 2
        ORDER BY 1
    """).df()

    # Fetch recent data for anomaly detection
    recent_df = con.execute(f"""
        SELECT
            DATE_TRUNC('hour', ts_in) as timestamp,
            polygon_id as corridor_id,
            COUNT(DISTINCT mmsi) as value
        FROM polygon_events
        WHERE ts_in >= NOW() - INTERVAL '{lookback_hours} hours'
        GROUP BY 1, 2
        ORDER BY 1
    """).df()

    if baseline_df.empty or recent_df.empty:
        return []

    # Initialize detector
    detector = AnomalyDetector(window_hours=baseline_window_hours)
    detector.update_baseline(baseline_df)

    # Detect anomalies
    all_anomalies = []

    for corridor_id in recent_df['corridor_id'].unique():
        corridor_data = recent_df[recent_df['corridor_id'] == corridor_id]

        # Check latest value
        latest = corridor_data.iloc[-1]
        anomaly = detector.detect_traffic_anomalies(
            corridor_id=corridor_id,
            current_value=latest['value'],
            timestamp=latest['timestamp'],
        )

        if anomaly:
            all_anomalies.append(anomaly)

        # Check time series
        ts_anomalies = detector.detect_time_series_anomalies(
            corridor_data[['timestamp', 'value']],
            corridor_id=corridor_id,
        )
        all_anomalies.extend(ts_anomalies)

    return all_anomalies


__all__ = [
    "Anomaly",
    "AnomalyDetector",
    "detect_corridor_anomalies",
]
