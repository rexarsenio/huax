"""
Relative stress analytics combining seasonal baselines, z-scores, and percentiles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from spvx.features.baselines import seasonal_stats_doy, zscore_doy


@dataclass(frozen=True)
class StressClassification:
    status: str
    severity: str
    direction: str | None
    color: str
    emoji: str | None = None
    headline: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelativeStressResult:
    value: float
    z_score: float
    percentile: float | None
    seasonal_mean: float | None
    seasonal_std: float | None
    deviation_pct: float | None
    doy: int | None
    sample_size: int
    lookback_window: int
    lookback_samples: int
    classification: StressClassification
    seasonal_label: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["classification"] = self.classification.to_dict()
        return payload


def _format_seasonal_label(date: pd.Timestamp) -> str:
    # Use a platform-safe month/day label without leading zero.
    return date.strftime("%b %d").replace(" 0", " ")


def classify_zscore(z: float | None) -> StressClassification:
    if z is None or pd.isna(z):
        return StressClassification(
            status="UNAVAILABLE",
            severity="unknown",
            direction=None,
            color="gray",
            emoji=None,
            headline="No signal",
        )

    direction = "above_seasonal" if z > 0 else "below_seasonal" if z < 0 else "in_line"
    abs_z = abs(z)

    if abs_z < 0.5:
        return StressClassification(
            status="NORMAL",
            severity="baseline",
            direction=direction,
            color="green",
            emoji="⚖️",
            headline="Seasonal normal",
        )
    if abs_z < 1.5:
        if z > 0:
            return StressClassification(
                status="ELEVATED",
                severity="watch",
                direction=direction,
                color="yellow",
                emoji="⚠️",
                headline="Elevated congestion",
            )
        return StressClassification(
            status="QUIET",
            severity="watch",
            direction=direction,
            color="blue",
            emoji="😌",
            headline="Quieter than normal",
        )
    if abs_z < 2.5:
        if z > 0:
            return StressClassification(
                status="STRESSED",
                severity="alert",
                direction=direction,
                color="orange",
                emoji="🚨",
                headline="Stress spike",
            )
        return StressClassification(
            status="UNUSUALLY_CALM",
            severity="alert",
            direction=direction,
            color="teal",
            emoji="🟢",
            headline="Exceptionally calm",
        )
    if z > 0:
        return StressClassification(
            status="CRITICAL",
            severity="critical",
            direction=direction,
            color="red",
            emoji="🛑",
            headline="Critical congestion",
        )
    return StressClassification(
        status="DEAD_CALM",
        severity="extreme_calm",
        direction=direction,
        color="navy",
        emoji="🟦",
        headline="Record calm",
    )


def _rolling_percentile(values: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    percentiles = np.full_like(values, fill_value=np.nan, dtype=float)
    for idx in range(len(values)):
        if np.isnan(values[idx]):
            continue
        start = 0 if window <= 0 else max(0, idx - window + 1)
        window_values = values[start : idx + 1]
        window_values = window_values[~np.isnan(window_values)]
        if window_values.size < min_periods:
            continue
        current = values[idx]
        # Percentile-of-score using rank of current within the window.
        rank = np.searchsorted(np.sort(window_values), current, side="right")
        percentiles[idx] = (rank / window_values.size) * 100.0
    return percentiles


def compute_relative_stress(
    frame: pd.DataFrame,
    value_col: str,
    date_col: str = "date",
    lookback_days: int = 365,
    min_samples: int = 60,
) -> Tuple[RelativeStressResult | None, pd.DataFrame]:
    """
    Compute relative seasonal stress metrics for a time series.

    Returns a tuple: (latest_result, enriched_dataframe)
    where enriched_dataframe contains the original dates/values plus seasonal stats.
    """
    if frame.empty:
        return None, frame.copy()

    data = frame[[date_col, value_col]].dropna()
    if data.empty:
        return None, data

    data = data.copy()
    data[date_col] = pd.to_datetime(data[date_col]).dt.normalize()
    data = data.sort_values(date_col).reset_index(drop=True)

    seasonal_mean, seasonal_std = seasonal_stats_doy(data, value_col, date_col)
    z_scores = zscore_doy(data, value_col, date_col)

    data["seasonal_mean"] = seasonal_mean
    data["seasonal_std"] = seasonal_std
    data["z_score"] = z_scores.replace([np.inf, -np.inf], np.nan)

    baseline = data["seasonal_mean"].replace(0, np.nan)
    deviation = (data[value_col] - baseline) / baseline * 100.0
    deviation = deviation.replace([np.inf, -np.inf], np.nan)
    data["deviation_pct"] = deviation

    lookback_window = max(lookback_days, min_samples)
    values = data[value_col].astype(float).to_numpy()
    percentiles = _rolling_percentile(values, window=lookback_window, min_periods=min_samples)
    data["percentile"] = percentiles

    data["doy"] = data[date_col].dt.dayofyear
    data["seasonal_label"] = data[date_col].apply(_format_seasonal_label)

    if data.empty:
        return None, data

    latest = data.iloc[-1]
    classification = classify_zscore(float(latest["z_score"]))

    lookback_samples = int(min(len(data), lookback_window))
    result = RelativeStressResult(
        value=float(latest[value_col]),
        z_score=float(latest["z_score"]),
        percentile=None if pd.isna(latest["percentile"]) else float(latest["percentile"]),
        seasonal_mean=None if pd.isna(latest["seasonal_mean"]) else float(latest["seasonal_mean"]),
        seasonal_std=None if pd.isna(latest["seasonal_std"]) else float(latest["seasonal_std"]),
        deviation_pct=None if pd.isna(latest["deviation_pct"]) else float(latest["deviation_pct"]),
        doy=int(latest["doy"]) if not pd.isna(latest["doy"]) else None,
        sample_size=int(len(data)),
        lookback_window=lookback_window,
        lookback_samples=lookback_samples,
        seasonal_label=str(latest["seasonal_label"]) if not pd.isna(latest["seasonal_label"]) else None,
        classification=classification,
    )
    return result, data


__all__ = [
    "RelativeStressResult",
    "StressClassification",
    "compute_relative_stress",
    "build_relative_stress_narrative",
    "classify_zscore",
]


def _ordinal_percentile(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    rank = int(round(value))
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix} percentile"


def build_relative_stress_narrative(result: RelativeStressResult) -> Dict[str, Any]:
    """
    Produce a compact natural-language summary for a relative stress assessment.
    """
    classification = result.classification
    emoji = classification.emoji or ""
    headline = classification.headline or classification.status.replace("_", " ").title()

    baseline_text = None
    if result.seasonal_mean is not None and result.seasonal_label:
        baseline_text = f"{result.seasonal_label}: baseline {result.seasonal_mean:.1f}"

    deviation_text = None
    if result.deviation_pct is not None:
        deviation_text = f"{result.deviation_pct:+.1f}% vs seasonal baseline"

    z_text = f"{result.z_score:+.1f}σ"
    percentile_text = None
    percentile_label = _ordinal_percentile(result.percentile)
    if percentile_label and result.lookback_samples:
        percentile_text = f"{percentile_label} across last {result.lookback_samples} days"
    elif percentile_label:
        percentile_text = percentile_label

    summary_parts = [part for part in (baseline_text, deviation_text, z_text, percentile_text) if part]
    summary = " · ".join(summary_parts)

    details: list[Dict[str, Any]] = []
    if result.seasonal_mean is not None:
        details.append(
            {
                "label": "Seasonal baseline",
                "value": round(result.seasonal_mean, 2),
                "context": result.seasonal_label,
            }
        )
    if result.seasonal_std is not None:
        details.append({"label": "Baseline σ", "value": round(result.seasonal_std, 2)})
    if result.deviation_pct is not None:
        details.append({"label": "Deviation %", "value": round(result.deviation_pct, 1)})
    details.append({"label": "Z-score", "value": round(result.z_score, 2)})
    if result.percentile is not None:
        details.append({"label": "Percentile", "value": round(result.percentile, 1)})

    return {
        "headline": f"{emoji} {headline}".strip(),
        "summary": summary,
        "status": classification.status,
        "color": classification.color,
        "details": details,
    }
