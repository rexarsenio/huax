"""
Model B — 72h throughput nowcast for Rotterdam (synthetic demo).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

from spvx.utils.runtime import make_run_meta, update_run_meta


CLASS_HORIZONS = [1, 2, 3]  # days (24/48/72h)


@dataclass
class ThroughputMetrics:
    auc_by_horizon: Dict[int, float]
    mae_improvement: float
    model_path: Path


def _load_ops() -> pd.DataFrame:
    import duckdb

    con = duckdb.connect("db/spvx.duckdb")
    df_ops = con.execute("select ts, tug_ops, pilot_ops, departures from port_ops_hourly order by ts").df()
    con.close()
    if df_ops.empty:
        raise RuntimeError("port_ops_hourly table empty. Run ingestion first.")
    df_ops["ts"] = pd.to_datetime(df_ops["ts"])
    df_ops = df_ops.set_index("ts").asfreq("h").ffill()
    daily = df_ops.resample("1D").sum()
    daily["departures_mean_7"] = df_ops["departures"].rolling("7D").mean().resample("1D").last()
    daily["departures_std_7"] = df_ops["departures"].rolling("7D").std().resample("1D").last()
    daily["tug_rolling_3"] = df_ops["tug_ops"].rolling("3D").sum().resample("1D").last()
    daily["pilot_rolling_3"] = df_ops["pilot_ops"].rolling("3D").sum().resample("1D").last()
    daily = daily.ffill()
    daily.index.name = "date"
    return daily


def _load_targets() -> pd.DataFrame:
    path = Path("data/ports/rotterdam_throughput.csv")
    if not path.exists():
        raise FileNotFoundError("data/ports/rotterdam_throughput.csv missing. Run mock ingest.")
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df


def _make_dataset() -> pd.DataFrame:
    ops = _load_ops()
    throughput = _load_targets()
    df = ops.join(throughput, how="inner").dropna()

    df["throughput_ret"] = df["throughput"].pct_change().fillna(0)
    for lag in [1, 3, 7]:
        df[f"throughput_lag_{lag}"] = df["throughput"].shift(lag)
        df[f"throughput_diff_{lag}"] = df["throughput"] - df["throughput"].shift(lag)

    for horizon in CLASS_HORIZONS:
        df[f"throughput_fwd_{horizon}"] = df["throughput"].shift(-horizon)
        diff = df[f"throughput_fwd_{horizon}"] - df["throughput"]
        thresh = df["throughput"].rolling(30).std().bfill() * 0.5
        df[f"depart_within_{horizon}d"] = (diff > thresh).astype(int)

    df = df.dropna()
    return df


def _time_series_split(n_splits: int = 5) -> TimeSeriesSplit:
    return TimeSeriesSplit(n_splits=n_splits, gap=2)


def train_throughput(model_path: str | Path = "data/outputs/model_throughput.pkl") -> ThroughputMetrics:
    df = _make_dataset()
    features = [col for col in df.columns if col.startswith(("tug_", "pilot_", "departures", "throughput_"))]
    features = [col for col in features if not col.startswith("throughput_fwd_") and not col.startswith("depart_within_")]
    X = df[features]

    classifiers: Dict[int, XGBClassifier] = {}
    aucs: Dict[int, List[float]] = {h: [] for h in CLASS_HORIZONS}

    tscv = _time_series_split()
    for horizon in CLASS_HORIZONS:
        y = df[f"depart_within_{horizon}d"]
        model = XGBClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            objective="binary:logistic",
            eval_metric="auc",
            random_state=42,
        )
        for train_idx, test_idx in tscv.split(X):
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            prob = model.predict_proba(X.iloc[test_idx])[:, 1]
            aucs[horizon].append(roc_auc_score(y.iloc[test_idx], prob))
        model.fit(X, y)
        classifiers[horizon] = model

    # Regression model for 72h throughput
    y_reg = df["throughput_fwd_3"]
    reg = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.1, max_iter=300, random_state=42)
    maes, baseline_maes = [], []
    for train_idx, test_idx in tscv.split(X):
        reg.fit(X.iloc[train_idx], y_reg.iloc[train_idx])
        pred = reg.predict(X.iloc[test_idx])
        maes.append(mean_absolute_error(y_reg.iloc[test_idx], pred))
        baseline = y_reg.iloc[train_idx].iloc[-1]  # persistence
        baseline_pred = np.full_like(pred, baseline, dtype=float)
        baseline_maes.append(mean_absolute_error(y_reg.iloc[test_idx], baseline_pred))
    reg.fit(X, y_reg)

    bundle = {"classifiers": classifiers, "regressor": reg, "features": features}
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)

    auc_summary = {h: float(np.nanmean(vals)) for h, vals in aucs.items()}
    mae_improvement = float(np.nanmean(baseline_maes) - np.nanmean(maes))

    meta = make_run_meta(
        extra={
            "auc_by_horizon": auc_summary,
            "mae_improvement": mae_improvement,
            "rows": int(len(X)),
            "features": features,
            "model_path": str(model_path),
        }
    )
    update_run_meta("train_throughput", meta)

    return ThroughputMetrics(auc_by_horizon=auc_summary, mae_improvement=mae_improvement, model_path=model_path)


def score_throughput(model_path: str | Path = "data/outputs/model_throughput.pkl") -> Path:
    bundle = joblib.load(model_path)
    features = bundle["features"]
    df = _make_dataset()
    X = df[features]

    scores = pd.DataFrame({"date": df.index})
    for horizon, clf in bundle["classifiers"].items():
        scores[f"prob_depart_{horizon}d"] = clf.predict_proba(X)[:, 1]

    reg = bundle["regressor"]
    scores["throughput_pred_72h"] = reg.predict(X)
    scores["throughput_actual_72h"] = df["throughput_fwd_3"]

    out_path = Path("data/outputs/throughput_scores.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(out_path, index=False)
    return out_path
