#!/usr/bin/env python3
"""
Setup ML Infrastructure for XGBoost Forecasting & Backtesting

Creates all necessary tables and schemas for:
- External data collection (oil prices, economic indicators)
- ML feature store
- Trading signal history (for backtesting)
- Model metadata and performance tracking
"""

import duckdb
from pathlib import Path
from datetime import datetime

DB_PATH = "db/spvx.duckdb"


def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH)

    print("🤖 Setting up ML Infrastructure for Trading Signals")
    print("=" * 70)
    print()

    # === 1. External Data Tables ===

    print("1️⃣  Creating external data tables...")

    # Oil prices (Brent, WTI, Dubai)
    con.execute("""
        CREATE TABLE IF NOT EXISTS oil_prices (
            ds DATE,
            brent_usd DOUBLE,
            wti_usd DOUBLE,
            dubai_usd DOUBLE,
            source VARCHAR DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ds)
        )
    """)
    print("   ✅ oil_prices table")

    # Economic indicators
    con.execute("""
        CREATE TABLE IF NOT EXISTS economic_indicators (
            ds DATE,
            indicator_name VARCHAR,
            country VARCHAR,
            value DOUBLE,
            unit VARCHAR,
            source VARCHAR DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ds, indicator_name, country)
        )
    """)
    print("   ✅ economic_indicators table")

    # Weather events (typhoons, storms)
    con.execute("""
        CREATE TABLE IF NOT EXISTS weather_events (
            event_id VARCHAR PRIMARY KEY,
            event_type VARCHAR,  -- 'typhoon', 'storm', 'monsoon'
            region VARCHAR,      -- 'malacca', 'south_china_sea', 'east_china_sea'
            start_date DATE,
            end_date DATE,
            severity VARCHAR,    -- 'low', 'medium', 'high'
            impact_corridors VARCHAR,  -- JSON array of affected corridor IDs
            source VARCHAR DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ weather_events table")

    # Port congestion reports (external sources)
    con.execute("""
        CREATE TABLE IF NOT EXISTS port_congestion_reports (
            report_id VARCHAR PRIMARY KEY,
            port_name VARCHAR,
            report_date DATE,
            vessels_waiting INTEGER,
            avg_waiting_time_h DOUBLE,
            source VARCHAR,  -- 'kpler', 'bloomberg', 'manual'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ port_congestion_reports table")

    print()

    # === 2. ML Feature Store ===

    print("2️⃣  Creating ML feature store...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS ml_features_daily (
            ds DATE,
            anchorage_id VARCHAR,

            -- Target variable
            median_dwell_h DOUBLE,
            is_congested BOOLEAN,  -- True if Z > 2.0

            -- Anchorage features
            episode_count INTEGER,
            avg_confidence DOUBLE,

            -- Temporal features
            day_of_week INTEGER,
            week_of_year INTEGER,
            month INTEGER,
            is_weekend BOOLEAN,
            is_holiday BOOLEAN,

            -- Lagged features (past values)
            dwell_lag_1d DOUBLE,   -- Yesterday
            dwell_lag_7d DOUBLE,   -- Last week
            dwell_lag_30d DOUBLE,  -- Last month
            dwell_rolling_7d DOUBLE,  -- 7-day moving average
            dwell_rolling_30d DOUBLE, -- 30-day moving average

            -- Statistical features
            z_score DOUBLE,
            baseline_median DOUBLE,
            baseline_std DOUBLE,

            -- Corridor features (sea state)
            malacca_sis_mean DOUBLE,
            malacca_sis_p90 DOUBLE,

            -- External data features
            brent_price DOUBLE,
            china_pmi DOUBLE,  -- Manufacturing PMI
            singapore_bunker_price DOUBLE,

            -- Supply chain features
            malacca_flux_24h INTEGER,  -- Gate crossings
            shandong_total_vessels INTEGER,

            -- Weather features
            typhoon_active BOOLEAN,
            monsoon_season BOOLEAN,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ds, anchorage_id)
        )
    """)
    print("   ✅ ml_features_daily table (comprehensive feature store)")

    print()

    # === 3. Trading Signal History ===

    print("3️⃣  Creating trading signal history...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_signals_history (
            signal_id VARCHAR PRIMARY KEY,
            ds DATE,
            anchorage_id VARCHAR,

            -- Signal details
            signal_type VARCHAR,  -- 'LONG', 'SHORT', 'NEUTRAL'
            confidence DOUBLE,
            predicted_dwell_h DOUBLE,
            actual_dwell_h DOUBLE,  -- Filled in retrospectively

            -- Model information
            model_version VARCHAR,
            features_used VARCHAR,  -- JSON string of feature names

            -- Trading outcome (for backtesting)
            was_correct BOOLEAN,  -- Filled in retrospectively
            profit_loss_estimate DOUBLE,  -- Estimated P&L

            -- Metadata
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP  -- When actual outcome known
        )
    """)

    # Create indexes separately
    con.execute("CREATE INDEX IF NOT EXISTS idx_signal_date ON trading_signals_history(ds)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_signal_anchorage ON trading_signals_history(anchorage_id)")
    print("   ✅ trading_signals_history table")

    print()

    # === 4. Model Metadata & Performance ===

    print("4️⃣  Creating model metadata tables...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS ml_models (
            model_id VARCHAR PRIMARY KEY,
            model_name VARCHAR,
            model_type VARCHAR,  -- 'xgboost', 'lstm', 'random_forest'
            version VARCHAR,

            -- Training details
            trained_at TIMESTAMP,
            training_data_start DATE,
            training_data_end DATE,
            n_training_samples INTEGER,

            -- Hyperparameters (JSON)
            hyperparameters TEXT,

            -- Performance metrics
            test_rmse DOUBLE,
            test_mae DOUBLE,
            test_r2 DOUBLE,
            congestion_precision DOUBLE,  -- For classification
            congestion_recall DOUBLE,
            congestion_f1 DOUBLE,

            -- Deployment
            is_production BOOLEAN DEFAULT FALSE,
            deployed_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ ml_models table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS model_performance_daily (
            ds DATE,
            model_id VARCHAR,

            -- Daily performance metrics
            predictions_made INTEGER,
            rmse DOUBLE,
            mae DOUBLE,
            accuracy DOUBLE,  -- For classification

            -- Trading performance
            signals_generated INTEGER,
            signals_correct INTEGER,
            win_rate DOUBLE,
            estimated_pnl DOUBLE,

            PRIMARY KEY (ds, model_id)
        )
    """)
    print("   ✅ model_performance_daily table")

    print()

    # === 5. Backtesting Framework ===

    print("5️⃣  Creating backtesting tables...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            backtest_id VARCHAR PRIMARY KEY,
            model_id VARCHAR,

            -- Backtest configuration
            start_date DATE,
            end_date DATE,
            initial_capital DOUBLE DEFAULT 100000.0,

            -- Strategy parameters
            long_threshold DOUBLE,   -- Enter long if P(congestion) > X
            short_threshold DOUBLE,  -- Enter short if P(congestion) < X
            position_size_pct DOUBLE DEFAULT 0.1,  -- 10% of capital per trade

            -- Performance metrics
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            win_rate DOUBLE,
            total_pnl DOUBLE,
            sharpe_ratio DOUBLE,
            max_drawdown DOUBLE,
            max_drawdown_duration_days INTEGER,

            -- Risk metrics
            var_95 DOUBLE,  -- Value at Risk (95%)
            cvar_95 DOUBLE, -- Conditional VaR

            -- Execution details
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            execution_time_seconds DOUBLE,

            notes TEXT
        )
    """)
    print("   ✅ backtest_runs table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS backtest_trades (
            trade_id VARCHAR PRIMARY KEY,
            backtest_id VARCHAR,

            -- Trade details
            entry_date DATE,
            exit_date DATE,
            anchorage_id VARCHAR,
            direction VARCHAR,  -- 'LONG', 'SHORT'

            -- Predictions
            predicted_dwell_h DOUBLE,
            actual_dwell_h DOUBLE,

            -- P&L
            entry_price DOUBLE,  -- Could be freight rate proxy
            exit_price DOUBLE,
            pnl DOUBLE,
            pnl_pct DOUBLE,

            -- Signal information
            signal_confidence DOUBLE,
            model_version VARCHAR,

            FOREIGN KEY (backtest_id) REFERENCES backtest_runs(backtest_id)
        )
    """)
    print("   ✅ backtest_trades table")

    print()

    # === 6. Sample Data for Testing ===

    print("6️⃣  Inserting sample external data...")

    # Insert some sample oil prices
    con.execute("""
        INSERT OR IGNORE INTO oil_prices (ds, brent_usd, wti_usd, dubai_usd, source)
        VALUES
            ('2025-11-01', 82.50, 78.30, 80.10, 'sample'),
            ('2025-11-02', 83.20, 79.00, 80.80, 'sample'),
            ('2025-11-03', 82.90, 78.70, 80.40, 'sample'),
            ('2025-11-04', 84.10, 80.20, 81.50, 'sample'),
            ('2025-11-05', 83.50, 79.80, 81.00, 'sample'),
            ('2025-11-06', 84.50, 80.50, 81.80, 'sample')
    """)
    print("   ✅ Sample oil prices (last 6 days)")

    # Insert sample economic indicators
    con.execute("""
        INSERT OR IGNORE INTO economic_indicators (ds, indicator_name, country, value, unit, source)
        VALUES
            ('2025-11-01', 'PMI_Manufacturing', 'China', 50.2, 'index', 'sample'),
            ('2025-11-01', 'PMI_Manufacturing', 'Singapore', 52.1, 'index', 'sample'),
            ('2025-11-02', 'PMI_Manufacturing', 'China', 50.5, 'index', 'sample'),
            ('2025-11-02', 'PMI_Manufacturing', 'Singapore', 51.8, 'index', 'sample')
    """)
    print("   ✅ Sample economic indicators (PMI)")

    print()

    con.commit()
    con.close()

    print("=" * 70)
    print("✅ ML Infrastructure Setup Complete!")
    print()
    print("🎯 Ready for:")
    print("   • External data collection (oil prices, PMI, weather)")
    print("   • ML feature engineering")
    print("   • XGBoost model training")
    print("   • Trading signal generation")
    print("   • Backtesting framework")
    print()
    print("📊 Tables Created:")
    print("   External: oil_prices, economic_indicators, weather_events, port_congestion_reports")
    print("   ML: ml_features_daily, ml_models, model_performance_daily")
    print("   Trading: trading_signals_history, backtest_runs, backtest_trades")
    print()
    print("Next Steps:")
    print("   1. Run: python3 populate_ml_features.py  # Build feature store")
    print("   2. Run: python3 train_xgboost_model.py   # Train forecasting model")
    print("   3. Run: python3 run_backtest.py          # Test trading strategy")
    print("   4. Start API: spvx serve-api             # Launch TH-4 REST API")


if __name__ == "__main__":
    main()
