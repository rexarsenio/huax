import numpy as np
import pytest
from pathlib import Path

from spvx.models.spread_direction import (
    _compute_volatility,
    _fallback_signal,
    _ks_distance,
    _maybe_damp,
    _prepare_dataset,
    _psi,
    _time_series_split,
)

_REQUIRES_COMPONENTS = Path("data/processed/components.parquet").exists()
_REQUIRES_SPREAD = Path("data/market/brent_spread.csv").exists()


def _ensure_dataset():
    if not (_REQUIRES_COMPONENTS and _REQUIRES_SPREAD):
        pytest.skip("Spread dataset missing; run `spvx.cli compute-index` and prepare market data.")


def test_prepare_dataset_alignment():
    _ensure_dataset()
    features, y, spread_fwd, _ = _prepare_dataset()
    assert not features.empty
    assert features.index.equals(y.index)
    assert spread_fwd.index.equals(y.index)


def test_time_series_split_gap():
    _ensure_dataset()
    features, *_ = _prepare_dataset()
    splitter = _time_series_split(len(features), n_splits=5, gap=7, test_size=30)
    for train_idx, test_idx in splitter.split(np.arange(len(features))):
        assert train_idx.max() <= test_idx.min() - 8  # gap of at least 7 days


def test_psi_and_ks_metrics():
    baseline = np.linspace(0.1, 0.9, 100)
    recent_same = baseline.copy()
    recent_shifted = baseline + 0.05
    assert abs(_psi(baseline, recent_same, np.linspace(0, 1, 11))) <= 1e-6
    assert _psi(baseline, recent_shifted, np.linspace(0, 1, 11)) > 0
    assert abs(_ks_distance(baseline, recent_same)) < 1e-6
    assert _ks_distance(baseline, recent_shifted) > 0


def test_probability_damping():
    assert _maybe_damp(None, 0.5) == 0.5
    assert _maybe_damp(0.5, 0.52) == 0.5  # damped
    assert _maybe_damp(0.5, 0.7) == 0.7  # large move allowed


def test_fallback_signal_high_volatility_triggers_neutral():
    _ensure_dataset()
    features, _, _, artefacts = _prepare_dataset()
    series = artefacts["spread"]
    vol_series = _compute_volatility(series)
    threshold = float(vol_series.quantile(0.75)) if not vol_series.empty else 0.1
    p_up, drivers, reasons = _fallback_signal(series, threshold * 0.8)
    assert 0.35 <= p_up <= 0.65
    assert {"r7", "r21", "vol21"}.issubset(drivers.keys())
    # Force high volatility scenario
    p_up_neutral, _, reasons_high = _fallback_signal(series, threshold * 0.5 if threshold else 0.01)
    assert abs(p_up_neutral - 0.5) < 1e-6 or "high_volatility" in reasons_high
