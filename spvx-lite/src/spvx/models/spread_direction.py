"""
Model A — Spread direction (Brent M1-M2 and cracks) using SPVX-Lite components.

This module trains a logistic-regression classifier with time-series cross validation,
calibrates probabilities via isotonic regression, monitors drift, and provides
fallback heuristics when model quality degrades.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from spvx.config import AppSettings, load_config
from spvx.features.baselines import winsorize
from spvx.metrics import spvx_model_drift, spvx_model_score
from spvx.utils.publish import atomic_write_json
from spvx.utils.runtime import make_run_meta, update_run_meta

PSI_BINS = np.linspace(0.0, 1.0, 11)  # 10 buckets
RECENT_WINDOW_DAYS = 30
ROLLING_STD_WINDOW = 21
VOL_LOOKBACK_DAYS = 730  # two years ~ 365*2
CALIBRATION_BINS = 10
DEGRADE_AUC_THRESHOLD = 0.60

LOG = logging.getLogger(__name__)


@dataclass
class TrainResult:
    auc: float
    auc_std: float
    pr_auc: float
    pr_auc_std: float
    brier: float
    brier_std: float
    sign_flip_auc: float
    calibration_curve: list[tuple[float, float]]
    model_version: str
    model_path: Path
    metrics: dict[str, float] = field(default_factory=dict)
    metrics_std: dict[str, float] = field(default_factory=dict)


@dataclass
class ScoreResult:
    scores_path: Path
    report_path: Path
    report: dict[str, object]


def _calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.DataFrame(index=index)
    df["weekday"] = index.weekday
    df["month"] = index.month
    df["weekofyear"] = index.isocalendar().week.astype(int)
    df["is_mon"] = (df["weekday"] == 0).astype(int)
    df["is_fri"] = (df["weekday"] == 4).astype(int)
    doy = index.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return df


def _macro_controls(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    result["spread_ret_1"] = frame["spread"].pct_change(1).fillna(0.0)
    result["spread_ret_5"] = frame["spread"].pct_change(5).fillna(0.0)
    return result


def _make_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=400, class_weight="balanced")),
        ]
    )


def _prepare_dataset() -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.DataFrame]:
    comps = pd.read_parquet("data/processed/components.parquet")
    comps["date"] = pd.to_datetime(comps["date"])
    spreads_path = Path("data/market/brent_spread.csv")
    if not spreads_path.exists():
        raise FileNotFoundError("data/market/brent_spread.csv missing. Run mock ingest or supply market data.")
    market = pd.read_csv(spreads_path, parse_dates=["date"])
    df = comps.merge(market, on="date", how="inner").set_index("date").sort_index()
    df = df.dropna(subset=["spread"])

    # Build features using only information available at time t.
    feature_cols: dict[str, pd.Series] = {}
    component_cols: list[str] = [col for col in df.columns if col.startswith("CQ_") or col == "PORT_EU"]
    min_history = 30
    filtered_cols: list[str] = []
    for col in component_cols:
        if df[col].notna().sum() < min_history:
            continue
        std_val = df[col].std(skipna=True)
        if pd.isna(std_val) or std_val == 0:
            continue
        filtered_cols.append(col)
    component_cols = filtered_cols
    for col in component_cols:
        feature_cols[col] = df[col]
        for lag in (1, 3, 5):
            feature_cols[f"{col}_lag_{lag}"] = df[col].shift(lag)
            feature_cols[f"{col}_chg_{lag}"] = df[col] - df[col].shift(lag)
        for window in (7, 14):
            roll = df[col].rolling(window=window, min_periods=window // 2)
            feature_cols[f"{col}_z_{window}"] = (df[col] - roll.mean()) / roll.std().replace(0, np.nan)

    features = pd.DataFrame(feature_cols)
    calendar_df = _calendar_features(df.index)
    macro_df = _macro_controls(df)
    features = pd.concat([features, calendar_df, macro_df], axis=1).replace([np.inf, -np.inf], np.nan)
    features = features.fillna(0.0)

    df["spread_fwd"] = df["spread"].shift(-1) - df["spread"]
    cfg = load_config()
    target_threshold = cfg["train"].get("spread_threshold_bp", 5) / 10000
    df["target"] = (df["spread_fwd"] > target_threshold).astype(int)

    valid_mask = df["target"].notna()
    features = features[valid_mask]
    aligned = df.loc[features.index]
    y = aligned["target"].astype(int)
    spread_fwd = aligned["spread_fwd"]

    # Additional artefacts for fallback heuristics.
    artefacts = pd.DataFrame(
        {
            "spread": aligned["spread"],
            "spread_fwd": aligned["spread_fwd"],
        },
        index=features.index,
    )

    return features, y, spread_fwd, artefacts


def _time_series_split(n_samples: int, n_splits: int = 5, gap: int = 7, test_size: int = 30) -> TimeSeriesSplit:
    """
    Construct a TimeSeriesSplit that gracefully degrades when the sample set is small.
    Ensures sklearn does not raise due to insufficient history by reducing split count
    and test window length when needed.
    """
    if n_samples <= gap + 5:
        # Trivial fallback: not enough observations even for a single test window.
        return TimeSeriesSplit(n_splits=2, gap=min(gap, max(n_samples // 4, 1)), test_size=max(1, n_samples // 3))

    # Ensure the number of splits is feasible for the dataset size.
    max_feasible_splits = (n_samples - gap) // max(test_size, 1) - 1
    if max_feasible_splits < 2:
        max_feasible_splits = 2
    n_splits = min(n_splits, max_feasible_splits)

    # Adjust test window so that total history covers all splits plus the terminal gap.
    max_test_size = max(1, (n_samples - gap) // (n_splits + 1))
    adjusted_test_size = min(test_size, max_test_size)

    # Final safeguard: ensure sklearn's internal check passes.
    while n_splits > 1 and (n_samples - gap - adjusted_test_size * n_splits) <= 0:
        n_splits -= 1
    if n_samples - gap - adjusted_test_size * n_splits <= 0:
        adjusted_test_size = max(1, (n_samples - gap) // (n_splits + 1))

    return TimeSeriesSplit(n_splits=n_splits, gap=gap, test_size=adjusted_test_size)


def _fold_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if len(np.unique(y_true)) < 2:
        return {"auc": math.nan, "pr_auc": math.nan, "brier": math.nan}
    metrics["auc"] = roc_auc_score(y_true, y_pred)
    metrics["pr_auc"] = average_precision_score(y_true, y_pred)
    metrics["brier"] = brier_score_loss(y_true, y_pred)
    return metrics


def _aggregate_metrics(fold_metrics: Sequence[dict[str, float]]) -> tuple[dict[str, float], dict[str, float]]:
    if not fold_metrics:
        return {}, {}
    metrics_df = pd.DataFrame(fold_metrics)
    metrics = metrics_df.mean(skipna=True).to_dict()
    metrics_std = metrics_df.std(skipna=True).to_dict()
    return metrics, metrics_std


def _calibration_bins(
    y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = CALIBRATION_BINS
) -> list[tuple[float, float]]:
    prob_true, prob_pred = calibration_curve(y_true, y_pred, n_bins=n_bins, strategy="quantile")
    return list(zip(prob_pred.tolist(), prob_true.tolist(), strict=False))


def _psi(expected: np.ndarray, actual: np.ndarray, bins: np.ndarray) -> float:
    if len(expected) == 0 or len(actual) == 0:
        return float("nan")
    exp_counts, _ = np.histogram(expected, bins=bins)
    act_counts, _ = np.histogram(actual, bins=bins)
    exp_frac = exp_counts / max(exp_counts.sum(), 1)
    act_frac = act_counts / max(act_counts.sum(), 1)
    eps = 1e-6
    ratios = np.clip(act_frac / np.clip(exp_frac, eps, None), eps, None)
    contributions = (act_frac - exp_frac) * np.log(ratios)
    return float(np.nansum(contributions))


def _ks_distance(sample_a: np.ndarray, sample_b: np.ndarray) -> float:
    if len(sample_a) == 0 or len(sample_b) == 0:
        return float("nan")
    values = np.sort(np.concatenate([sample_a, sample_b]))
    cdf_a = np.searchsorted(np.sort(sample_a), values, side="right") / len(sample_a)
    cdf_b = np.searchsorted(np.sort(sample_b), values, side="right") / len(sample_b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


def _recent_window(df: pd.DataFrame, days: int = RECENT_WINDOW_DAYS) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=days - 1)
    return df[df.index >= cutoff]


def _compute_volatility(series: pd.Series) -> pd.Series:
    returns = series.pct_change()
    vol = returns.rolling(ROLLING_STD_WINDOW).std()
    vol = winsorize(vol.dropna(), lower=0.01, upper=0.99)
    return vol


def _fallback_signal(series: pd.Series, vol_threshold: float) -> tuple[float, dict[str, float], list[str]]:
    reasons: list[str] = []
    if len(series) < max(ROLLING_STD_WINDOW, 21, 7) + 1:
        return 0.5, {"r7": 0.0, "r21": 0.0, "vol21": float("nan")}, ["insufficient_history"]
    r7 = (series.iloc[-1] - series.iloc[-7]) / series.iloc[-7] if series.iloc[-7] != 0 else 0.0
    r21 = (series.iloc[-1] - series.iloc[-21]) / series.iloc[-21] if series.iloc[-21] != 0 else 0.0
    vol_series = _compute_volatility(series)
    vol21 = float(vol_series.iloc[-1]) if not vol_series.empty else float("nan")
    drivers = {"r7": float(r7), "r21": float(r21), "vol21": vol21}
    if math.isnan(vol21):
        reasons.append("volatility_na")
    if not math.isnan(vol21) and vol_threshold is not None and vol21 > vol_threshold:
        reasons.append("high_volatility")
    if len(series.dropna()) < 21:
        reasons.append("low_support")

    if reasons and not {"volatility_na"} == set(reasons):
        p_up = 0.5
    else:
        m = r7 - 0.5 * r21
        denom = vol21 if not math.isnan(vol21) and vol21 > 0 else 1e-6
        raw = 0.5 + 0.5 * math.tanh((m / denom) * 3.0)
        p_up = float(np.clip(raw, 0.35, 0.65))

    return p_up, drivers, reasons


def _to_utc_iso(ts: object | None) -> str | None:
    if ts is None:
        return None
    try:
        stamp = pd.Timestamp(ts)
    except Exception:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat().replace("+00:00", "Z")


def _latest_sea_state() -> dict[str, object] | None:
    settings = AppSettings()
    db_path = Path(settings.duckdb_path)
    if not db_path.exists():
        return None
    try:
        con = duckdb.connect(str(db_path))
    except Exception as exc:  # pragma: no cover - DuckDB unavailable
        LOG.debug("Unable to connect to DuckDB for sea-state lookup: %s", exc)
        return None
    try:
        global_row = con.execute(
            """
            SELECT d, sea_hs_z_avg, sea_data_timestamp
            FROM spvx_global_daily
            ORDER BY d DESC
            LIMIT 1
            """
        ).fetchone()
        if not global_row:
            return None
        day_value, hs_z_avg, data_ts = global_row
        opp_row = con.execute(
            """
            SELECT AVG(sea_opp_current) AS opp_current
            FROM components_daily
            WHERE d = ? AND sea_opp_current IS NOT NULL
            """,
            [day_value],
        ).fetchone()
    except Exception as exc:  # pragma: no cover - diagnostic path
        LOG.debug("Sea-state aggregation lookup failed: %s", exc)
        return None
    finally:
        con.close()

    payload: dict[str, object] = {}
    if hs_z_avg is not None:
        payload["hs_z"] = float(hs_z_avg)
    if opp_row and opp_row[0] is not None:
        payload["opp_current"] = float(opp_row[0])

    iso_ts = _to_utc_iso(data_ts)
    if not iso_ts and isinstance(day_value, dt.date):
        iso_ts = _to_utc_iso(dt.datetime.combine(day_value, dt.time.min))
    if iso_ts:
        payload["as_of"] = iso_ts

    if "hs_z" not in payload or "as_of" not in payload:
        return None

    return payload


def train_spread(model_path: str | Path = "data/outputs/model_spread.pkl") -> TrainResult:
    feature_frame, target_series, spread_fwd, artefacts = _prepare_dataset()
    splitter = _time_series_split(len(feature_frame))

    fold_metrics: list[dict[str, float]] = []
    cv_predictions = np.full(len(feature_frame), np.nan, dtype=float)
    valid_mask = np.zeros(len(feature_frame), dtype=bool)

    for _fold_idx, (train_idx, test_idx) in enumerate(splitter.split(feature_frame)):
        pipeline = _make_pipeline()
        pipeline.fit(feature_frame.iloc[train_idx], target_series.iloc[train_idx])
        preds = pipeline.predict_proba(feature_frame.iloc[test_idx])[:, 1]
        cv_predictions[test_idx] = preds
        valid_mask[test_idx] = True
        metrics = _fold_metrics(target_series.iloc[test_idx].to_numpy(), preds)
        fold_metrics.append(metrics)

    if not valid_mask.any():
        raise RuntimeError("TimeSeriesSplit did not produce any validation predictions; insufficient data.")

    train_metrics, metrics_std = _aggregate_metrics(fold_metrics)
    cv_preds_valid = cv_predictions[valid_mask]
    y_valid = target_series.iloc[valid_mask].to_numpy()
    sign_flip_auc = roc_auc_score(y_valid, -cv_preds_valid) if len(np.unique(y_valid)) > 1 else float("nan")

    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(cv_preds_valid, y_valid)
    calib_curve = _calibration_bins(y_valid, calibrator.predict(cv_preds_valid))

    final_model = _make_pipeline()
    final_model.fit(feature_frame, target_series)

    spread_series = artefacts["spread"]
    vol_series = _compute_volatility(spread_series)
    vol_threshold = float(vol_series.tail(VOL_LOOKBACK_DAYS).quantile(0.75)) if not vol_series.empty else float("nan")

    expected_dist, _ = np.histogram(cv_preds_valid, bins=PSI_BINS)
    expected_frac = (expected_dist / max(expected_dist.sum(), 1)).tolist()

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    meta = make_run_meta(
        extra={
            "auc": float(train_metrics.get("auc", float("nan"))),
            "auc_std": float(metrics_std.get("auc", float("nan"))),
            "pr_auc": float(train_metrics.get("pr_auc", float("nan"))),
            "pr_auc_std": float(metrics_std.get("pr_auc", float("nan"))),
            "brier": float(train_metrics.get("brier", float("nan"))),
            "brier_std": float(metrics_std.get("brier", float("nan"))),
            "sign_flip_auc": float(sign_flip_auc),
            "model_path": str(model_path),
            "calibration_curve": calib_curve,
            "features": feature_frame.columns.tolist(),
            "rows": int(len(feature_frame)),
        }
    )

    model_bundle = {
        "model": final_model,
        "features": feature_frame.columns.tolist(),
        "calibrator": calibrator,
        "cv_predictions": cv_preds_valid.tolist(),
        "cv_labels": y_valid.tolist(),
        "cv_metrics": train_metrics,
        "cv_metrics_std": metrics_std,
        "sign_flip_auc": sign_flip_auc,
        "psi_bins": PSI_BINS.tolist(),
        "psi_expected": expected_frac,
        "base_rate": float(target_series.mean()),
        "vol_threshold": vol_threshold,
        "calibration_curve": calib_curve,
        "model_version": meta["ts"],
    }

    joblib.dump(model_bundle, model_path)
    update_run_meta("train_spread", meta)

    return TrainResult(
        auc=float(train_metrics.get("auc", float("nan"))),
        auc_std=float(metrics_std.get("auc", float("nan"))),
        pr_auc=float(train_metrics.get("pr_auc", float("nan"))),
        pr_auc_std=float(metrics_std.get("pr_auc", float("nan"))),
        brier=float(train_metrics.get("brier", float("nan"))),
        brier_std=float(metrics_std.get("brier", float("nan"))),
        sign_flip_auc=float(sign_flip_auc),
        calibration_curve=calib_curve,
        model_version=meta["ts"],
        model_path=model_path,
        metrics=train_metrics,
        metrics_std=metrics_std,
    )


def _load_model_bundle(model_path: str | Path) -> dict[str, object]:
    bundle = joblib.load(model_path)
    if "calibrator" not in bundle:
        raise RuntimeError("Model bundle missing calibrator; retrain spread model.")
    return bundle


def _drift_statistics(
    bundle: dict[str, object],
    recent_preds: np.ndarray,
    recent_labels: np.ndarray,
) -> tuple[dict[str, float], list[str]]:
    reasons: list[str] = []
    train_probs = np.asarray(bundle.get("cv_predictions", []), dtype=float)
    psi_bins = np.asarray(bundle.get("psi_bins", PSI_BINS), dtype=float)
    psi = float("nan")
    if train_probs.size and recent_preds.size:
        psi = _psi(train_probs, recent_preds, psi_bins)

    if math.isnan(psi):
        reasons.append("psi_unavailable")

    if not math.isnan(psi) and psi >= 0.25:
        reasons.append("psi_exceeds_threshold")

    ks = float("nan")
    if train_probs.size and recent_preds.size:
        ks = _ks_distance(train_probs, recent_preds)

    if not math.isnan(ks) and ks >= 0.20:
        reasons.append("ks_exceeds_threshold")

    base_rate_train = float(bundle.get("base_rate", float("nan")))
    base_rate_recent = float(np.mean(recent_labels)) if recent_labels.size else float("nan")
    base_rate_shift = (
        abs(base_rate_recent - base_rate_train)
        if not (math.isnan(base_rate_recent) or math.isnan(base_rate_train))
        else float("nan")
    )
    if not math.isnan(base_rate_shift) and base_rate_shift > 0.15:
        reasons.append("base_rate_shift")

    positives_recent = int(np.sum(recent_labels))
    if positives_recent < 50:
        reasons.append("insufficient_positive_samples")

    stats = {
        "psi": float(psi),
        "ks": float(ks),
        "base_rate_shift": float(base_rate_shift),
        "positives_30d": positives_recent,
        "base_rate_train": base_rate_train,
        "base_rate_recent": base_rate_recent,
    }
    return stats, reasons


def _maybe_damp(prev_prob: float | None, new_prob: float) -> float:
    if prev_prob is None:
        return new_prob
    if abs(new_prob - prev_prob) <= 0.05:
        return prev_prob
    return new_prob


def score_spread(model_path: str | Path = "data/outputs/model_spread.pkl") -> ScoreResult:
    bundle = _load_model_bundle(model_path)
    model: Pipeline = bundle["model"]
    calibrator: IsotonicRegression = bundle["calibrator"]
    feature_frame, target_series, spread_fwd, artefacts = _prepare_dataset()

    selected_features = feature_frame[bundle["features"]]
    raw_probs = model.predict_proba(selected_features)[:, 1]
    calibrated_probs = np.clip(calibrator.predict(raw_probs), 0.0, 1.0)
    scores = pd.DataFrame(
        {
            "date": selected_features.index,
            "prob_up_raw": raw_probs,
            "prob_up": calibrated_probs,
            "label": target_series.values,
            "spread_fwd": spread_fwd.reindex(selected_features.index).values,
        }
    ).sort_values("date")

    scores_path = Path("data/outputs/spread_scores.parquet")
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(scores_path)

    scores_indexed = scores.set_index("date")
    recent_window = _recent_window(scores_indexed)
    recent_preds = recent_window["prob_up"].dropna().to_numpy()
    recent_labels = recent_window["label"].dropna().to_numpy()
    drift_stats, drift_reasons = _drift_statistics(bundle, recent_preds, recent_labels)

    auc_mean = float(bundle.get("cv_metrics", {}).get("auc", float("nan")))
    degraded = False
    degrade_reasons: list[str] = []
    if math.isnan(auc_mean) or auc_mean < DEGRADE_AUC_THRESHOLD:
        degraded = True
        degrade_reasons.append("auc_below_threshold")
    degrade_reasons.extend(drift_reasons)
    if drift_reasons:
        degraded = True

    latest_row = scores_indexed.iloc[-1]
    vol_threshold = bundle.get("vol_threshold")
    fallback_p, fallback_drivers, fallback_reasons = _fallback_signal(
        artefacts["spread"], vol_threshold if isinstance(vol_threshold, (float, int)) else None
    )

    previous_report_path = Path("data/outputs/spread_report.json")
    prev_prob = None
    if previous_report_path.exists():
        try:
            prev_payload = json.loads(previous_report_path.read_text(encoding="utf-8"))
        except Exception:
            prev_payload = None
        if isinstance(prev_payload, dict):
            prev_prob = prev_payload.get("prob_up")

    mode = "model"
    final_prob = float(latest_row["prob_up"])
    drivers: dict[str, object] = {}
    reasons: list[str] = []
    if degraded:
        mode = "fallback"
        reasons = sorted(set(degrade_reasons + fallback_reasons))
        final_prob = fallback_p
        drivers = dict(fallback_drivers)
    final_prob = _maybe_damp(prev_prob if isinstance(prev_prob, (float, int)) else None, final_prob)

    sea_state_info = _latest_sea_state()
    if sea_state_info:
        drivers = dict(drivers)
        drivers["sea_state"] = sea_state_info

    if not scores_indexed.empty:
        prob_series = scores_indexed["prob_up"].dropna()
        top_threshold = float(np.quantile(prob_series, 0.9)) if not prob_series.empty else float("nan")
    else:
        top_threshold = float("nan")

    metrics_payload = {
        "auc": auc_mean,
        "auc_std": float(bundle.get("cv_metrics_std", {}).get("auc", float("nan"))),
        "pr_auc": float(bundle.get("cv_metrics", {}).get("pr_auc", float("nan"))),
        "pr_auc_std": float(bundle.get("cv_metrics_std", {}).get("pr_auc", float("nan"))),
        "brier": float(bundle.get("cv_metrics", {}).get("brier", float("nan"))),
        "brier_std": float(bundle.get("cv_metrics_std", {}).get("brier", float("nan"))),
        "sign_flip_auc": float(bundle.get("sign_flip_auc", float("nan"))),
    }

    for metric_name, metric_value in metrics_payload.items():
        if not math.isnan(metric_value):
            spvx_model_score.labels(model="spread", metric=metric_name).set(metric_value)

    for drift_name, drift_value in drift_stats.items():
        if not math.isnan(drift_value):
            spvx_model_drift.labels(model="spread", metric=drift_name).set(drift_value)

    calibration_curve_data = bundle.get("calibration_curve", [])

    report = {
        "model": "spread",
        "model_version": bundle.get("model_version"),
        "prob_up": final_prob,
        "prob_up_raw": float(latest_row["prob_up_raw"]),
        "prob_up_calibrated": float(latest_row["prob_up"]),
        "mode": mode,
        "degraded": degraded,
        "metrics": metrics_payload,
        "drift": drift_stats,
        "reasons": reasons,
        "drivers": drivers,
        "top_decile_threshold": top_threshold,
        "latest_date": latest_row.name.isoformat(),
        "calibration_curve": calibration_curve_data,
        "recent_window_days": RECENT_WINDOW_DAYS,
    }

    report_path = Path("data/outputs/spread_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report, report_path)

    return ScoreResult(scores_path=scores_path, report_path=report_path, report=report)
