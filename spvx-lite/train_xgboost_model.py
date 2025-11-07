#!/usr/bin/env python3
"""
Train XGBoost Model for Anchorage Dwell Prediction

Trains a production-grade gradient boosting model to forecast:
1. Dwell time (regression)
2. Congestion probability (classification)
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

try:
    import xgboost as xgb
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from sklearn.metrics import precision_score, recall_score, f1_score
    HAS_ML_LIBS = True
except ImportError:
    HAS_ML_LIBS = False

DB_PATH = "db/spvx.duckdb"
MODEL_DIR = Path("models")


def main():
    if not HAS_ML_LIBS:
        print("❌ ML libraries not installed!")
        print()
        print("Install with:")
        print("  pip install xgboost scikit-learn")
        return

    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    MODEL_DIR.mkdir(exist_ok=True)

    con = duckdb.connect(DB_PATH)

    print("🤖 Training XGBoost Model for Dwell Prediction")
    print("=" * 70)
    print()

    # === 1. Load Feature Data ===

    print("1️⃣  Loading ML features...")

    df = con.execute("""
        SELECT *
        FROM ml_features_daily
        WHERE median_dwell_h IS NOT NULL
          AND dwell_lag_1d IS NOT NULL  -- Ensure we have historical data
          AND dwell_rolling_7d IS NOT NULL
        ORDER BY ds, anchorage_id
    """).df()

    if df.empty:
        print("❌ No data in ml_features_daily!")
        print("   Run: python3 populate_ml_features.py")
        con.close()
        return

    print(f"   ✅ Loaded {len(df):,} samples")
    print(f"   📅 Date range: {df['ds'].min()} to {df['ds'].max()}")
    print()

    # === 2. Feature Engineering ===

    print("2️⃣  Preparing features...")

    # Define feature columns
    feature_cols = [
        # Temporal
        'day_of_week', 'week_of_year', 'month', 'is_weekend', 'is_holiday',

        # Lagged
        'dwell_lag_1d', 'dwell_lag_7d', 'dwell_lag_30d',

        # Rolling
        'dwell_rolling_7d', 'dwell_rolling_30d',

        # Statistical
        'z_score', 'baseline_median', 'baseline_std',

        # Anchorage
        'episode_count', 'avg_confidence',

        # External (if available)
        'brent_price', 'china_pmi',

        # Corridor
        'malacca_sis_mean', 'malacca_sis_p90',

        # Supply chain
        'malacca_flux_24h', 'shandong_total_vessels',

        # Weather
        'typhoon_active', 'monsoon_season',
    ]

    # Filter to available features
    available_features = [col for col in feature_cols if col in df.columns]
    print(f"   Using {len(available_features)} features:")
    for feat in available_features:
        print(f"     • {feat}")
    print()

    # Prepare X and y
    X = df[available_features].fillna(0).astype(float)
    y_regression = df['median_dwell_h'].values
    y_classification = df['is_congested'].astype(int).values

    # Convert boolean columns to int
    for col in X.columns:
        if X[col].dtype == bool:
            X[col] = X[col].astype(int)

    # === 3. Train/Test Split (Time-based) ===

    print("3️⃣  Splitting data (time-based)...")

    # Use last 20% as test set
    split_idx = int(len(X) * 0.8)

    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_reg_train, y_reg_test = y_regression[:split_idx], y_regression[split_idx:]
    y_clf_train, y_clf_test = y_classification[:split_idx], y_classification[split_idx:]

    print(f"   Train: {len(X_train):,} samples ({df['ds'].iloc[0]} to {df['ds'].iloc[split_idx-1]})")
    print(f"   Test:  {len(X_test):,} samples ({df['ds'].iloc[split_idx]} to {df['ds'].iloc[-1]})")
    print()

    # === 4. Train Regression Model (Dwell Time) ===

    print("4️⃣  Training regression model (dwell time prediction)...")

    reg_model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='reg:squarederror',
        random_state=42,
        n_jobs=-1
    )

    reg_model.fit(
        X_train, y_reg_train,
        eval_set=[(X_test, y_reg_test)],
        verbose=False
    )

    # Evaluate
    y_pred_reg = reg_model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_reg_test, y_pred_reg))
    mae = mean_absolute_error(y_reg_test, y_pred_reg)
    r2 = r2_score(y_reg_test, y_pred_reg)

    print(f"   ✅ Model trained!")
    print(f"   RMSE: {rmse:.2f}h")
    print(f"   MAE:  {mae:.2f}h")
    print(f"   R²:   {r2:.3f}")
    print()

    # Feature importance
    print("   Top 10 features:")
    importances = reg_model.feature_importances_
    feat_imp = sorted(zip(available_features, importances), key=lambda x: x[1], reverse=True)
    for feat, imp in feat_imp[:10]:
        print(f"     {feat:30s}: {imp:.4f}")
    print()

    # === 5. Train Classification Model (Congestion) ===

    print("5️⃣  Training classification model (congestion detection)...")

    clf_model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='binary:logistic',
        random_state=42,
        n_jobs=-1
    )

    clf_model.fit(
        X_train, y_clf_train,
        eval_set=[(X_test, y_clf_test)],
        verbose=False
    )

    # Evaluate
    y_pred_clf = clf_model.predict(X_test)
    y_pred_proba = clf_model.predict_proba(X_test)[:, 1]

    precision = precision_score(y_clf_test, y_pred_clf)
    recall = recall_score(y_clf_test, y_pred_clf)
    f1 = f1_score(y_clf_test, y_pred_clf)

    print(f"   ✅ Model trained!")
    print(f"   Precision: {precision:.3f}")
    print(f"   Recall:    {recall:.3f}")
    print(f"   F1-Score:  {f1:.3f}")
    print()

    # === 6. Save Models ===

    print("6️⃣  Saving models...")

    model_version = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save XGBoost models
    reg_model_path = MODEL_DIR / f"xgb_regression_{model_version}.json"
    clf_model_path = MODEL_DIR / f"xgb_classification_{model_version}.json"

    reg_model.save_model(reg_model_path)
    clf_model.save_model(clf_model_path)

    print(f"   ✅ Saved regression model: {reg_model_path}")
    print(f"   ✅ Saved classification model: {clf_model_path}")
    print()

    # === 7. Store Metadata in Database ===

    print("7️⃣  Storing model metadata...")

    hyperparams_reg = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8
    }

    con.execute("""
        INSERT INTO ml_models (
            model_id, model_name, model_type, version,
            trained_at, training_data_start, training_data_end, n_training_samples,
            hyperparameters,
            test_rmse, test_mae, test_r2,
            congestion_precision, congestion_recall, congestion_f1,
            is_production
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        f"xgb_reg_{model_version}", "Dwell Time Predictor", "xgboost", model_version,
        datetime.now(), df['ds'].min(), df['ds'].max(), len(X_train),
        json.dumps(hyperparams_reg),
        rmse, mae, r2,
        precision, recall, f1,
        True  # Mark as production
    ])

    con.commit()

    print("   ✅ Model metadata stored in database")
    print()

    # === 8. Example Predictions ===

    print("8️⃣  Example predictions (last 5 test samples)...")

    sample_indices = range(len(X_test)-5, len(X_test))
    sample_dates = df['ds'].iloc[split_idx:].iloc[sample_indices].values
    sample_anchorages = df['anchorage_id'].iloc[split_idx:].iloc[sample_indices].values

    y_pred_sample = reg_model.predict(X_test.iloc[sample_indices])
    y_actual_sample = y_reg_test[sample_indices]
    y_prob_sample = clf_model.predict_proba(X_test.iloc[sample_indices])[:, 1]

    print(f"   {'Date':<12} {'Anchorage':<25} {'Actual':>8} {'Predicted':>10} {'Error':>7} {'P(Cong)':>8}")
    print(f"   {'-'*12} {'-'*25} {'-'*8} {'-'*10} {'-'*7} {'-'*8}")

    for i, (date, anch, actual, pred, prob) in enumerate(zip(
        sample_dates, sample_anchorages, y_actual_sample, y_pred_sample, y_prob_sample
    )):
        error = pred - actual
        anch_short = anch[:25]
        print(f"   {str(date):<12} {anch_short:<25} {actual:8.1f} {pred:10.1f} {error:+7.1f} {prob:8.1%}")
    print()

    con.close()

    print("=" * 70)
    print("✅ XGBoost Model Training Complete!")
    print()
    print("📊 Model Performance:")
    print(f"   Regression:  RMSE={rmse:.2f}h, MAE={mae:.2f}h, R²={r2:.3f}")
    print(f"   Classification: Precision={precision:.3f}, Recall={recall:.3f}, F1={f1:.3f}")
    print()
    print("🚀 Next Steps:")
    print("   1. Test predictions:")
    print("      python3 test_model_predictions.py")
    print()
    print("   2. Run backtest:")
    print("      python3 run_backtest.py")
    print()
    print("   3. Deploy to API:")
    print("      spvx serve-api  # Models auto-loaded")
    print()
    print("💡 Model files:")
    print(f"   {reg_model_path}")
    print(f"   {clf_model_path}")


if __name__ == "__main__":
    main()
