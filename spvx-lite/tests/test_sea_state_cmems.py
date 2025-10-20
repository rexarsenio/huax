"""
Tests for CMEMS sea-state provider.
"""

from __future__ import annotations

import pandas as pd
import pytest

from spvx.sea_state.cmems import (
    DEFAULT_FEATURES,
    _list_days_yyyymmdd,
    area_mean_opp_current,
    area_mean_waves,
    extract_region_features,
)


def test_list_days_yyyymmdd():
    """Test date list generation for file filtering."""
    days = _list_days_yyyymmdd(3)
    assert len(days) == 4  # Today + 3 days back
    assert all(len(d) == 8 and d.isdigit() for d in days)


def test_area_mean_waves_empty():
    """Test wave processing with empty file list."""
    bbox = {"lat_min": 0, "lat_max": 1, "lon_min": 0, "lon_max": 1}
    result = area_mean_waves([], bbox)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["time", "hs"]
    assert len(result) == 0


def test_area_mean_opp_current_empty():
    """Test current processing with empty file list."""
    bbox = {"lat_min": 0, "lat_max": 1, "lon_min": 0, "lon_max": 1}
    result = area_mean_opp_current([], bbox, bearing_deg=300)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["time", "opp_current"]
    assert len(result) == 0


def test_extract_region_features_empty_inputs():
    bbox = {"lat_min": 0, "lat_max": 1, "lon_min": 0, "lon_max": 1}
    df = extract_region_features([], [], DEFAULT_FEATURES, bbox, bearing_deg=300.0)
    assert isinstance(df, pd.DataFrame)
    assert "time" in df.columns or df.empty


def test_seasonal_zscore_no_crash():
    """Test seasonal Z-score computation doesn't crash with sparse data."""
    import numpy as np
    from spvx.features.components import _seasonal_z_score

    # Create test data with NaNs
    dates = pd.date_range("2023-01-01", periods=400, freq="D")
    values = [np.nan if i % 5 == 0 else float(i % 10) for i in range(400)]
    df = pd.DataFrame({"date": dates, "value": values})

    z = _seasonal_z_score(df, "value", "date")

    assert isinstance(z, pd.Series)
    assert len(z) == len(df)
    assert not z.isna().all()  # Should have some non-NaN values


def test_seasonal_zscore_seasonality():
    """Test that Z-score captures seasonal patterns."""
    import numpy as np
    from spvx.features.components import _seasonal_z_score

    # Create 5 years of data with seasonal pattern + noise
    dates = pd.date_range("2019-01-01", periods=365 * 5, freq="D")
    doy = dates.dayofyear
    # Seasonal base pattern
    seasonal_base = 2.0 + 1.5 * np.sin(2 * np.pi * doy / 365.25)
    # Add random noise to create variation within each DOY
    noise = np.random.RandomState(42).normal(0, 0.3, len(dates))
    values = seasonal_base + noise
    df = pd.DataFrame({"date": dates, "hs": values})

    z = _seasonal_z_score(df, "hs", "date")

    # Z-scores should be roughly centered around 0
    assert abs(z.mean()) < 0.3
    # Should have some variance (noise creates variation within DOY groups)
    assert z.std() > 0.5


def test_sea_state_components_missing_file():
    """Test that missing sea-state files are handled gracefully."""
    from spvx.features.components import _sea_state_components

    result = _sea_state_components("NONEXISTENT_CQ")
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["date", "SEA_HS_Z", "OPPOSING_CURRENT"]
    assert len(result) == 0
