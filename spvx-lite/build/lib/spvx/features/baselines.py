"""
Seasonal baselines and standardisation helpers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def zscore_doy(frame: pd.DataFrame, value_col: str, date_col: str = "date") -> pd.Series:
    """
    Compute z-score versus day-of-year seasonal baselines.
    """
    dates = pd.to_datetime(frame[date_col])
    values = pd.to_numeric(frame[value_col], errors="coerce")
    doy = dates.dt.dayofyear
    means = values.groupby(doy).transform("mean")
    stds = values.groupby(doy).transform("std").replace(0, np.nan)
    z = (values - means) / stds
    return z.fillna(0.0)


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """
    Clip extreme values to given quantiles.
    """
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lower=lo, upper=hi)
