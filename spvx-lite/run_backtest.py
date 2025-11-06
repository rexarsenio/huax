#!/usr/bin/env python3
"""
Backtest Trading Strategy

Simulates trading based on congestion predictions and calculates P&L.
"""

import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import uuid

DB_PATH = "db/spvx.duckdb"


def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH)

    print("📈 Running Trading Strategy Backtest")
    print("=" * 70)
    print()

    # === 1. Load Historical Data ===

    print("1️⃣  Loading historical anchorage data...")

    df = con.execute("""
        SELECT
            ds,
            anchorage_id,
            median_dwell_h,
            z_dwell,
            anomaly_detected
        FROM anchorage_daily
        WHERE anchorage_id = 'ANCH_OPL_SIN'  -- Focus on OPL Singapore
          AND median_dwell_h IS NOT NULL
          AND z_dwell IS NOT NULL
        ORDER BY ds
    """).df()

    if df.empty or len(df) < 30:
        print("❌ Insufficient historical data (need at least 30 days)")
        print("   Run TH-3 first: spvx anchorage-backfill")
        con.close()
        return

    print(f"   ✅ Loaded {len(df)} days of data")
    print(f"   📅 Date range: {df['ds'].min()} to {df['ds'].max()}")
    print()

    # === 2. Define Trading Strategy ===

    print("2️⃣  Defining trading strategy...")

    strategy_params = {
        "initial_capital": 100000.0,
        "position_size_pct": 0.1,  # 10% per trade
        "long_threshold": 2.5,      # Enter LONG if Z > 2.5 (expect reversion)
        "short_threshold": -1.0,    # Enter SHORT if Z < -1.0 (expect increase)
        "stop_loss_pct": 0.05,      # 5% stop loss
        "take_profit_pct": 0.15,    # 15% take profit
    }

    print("   Strategy: Mean Reversion on Congestion Z-Score")
    print(f"   • Initial capital: ${strategy_params['initial_capital']:,.0f}")
    print(f"   • Position size: {strategy_params['position_size_pct']*100}%")
    print(f"   • LONG threshold: Z > {strategy_params['long_threshold']}")
    print(f"   • SHORT threshold: Z < {strategy_params['short_threshold']}")
    print()

    # === 3. Simulate Trading ===

    print("3️⃣  Simulating trades...")

    capital = strategy_params["initial_capital"]
    position = None  # None, 'LONG', or 'SHORT'
    entry_z = None
    entry_dwell = None
    entry_date = None

    trades = []
    equity_curve = [capital]

    for i in range(1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]

        ds = current['ds']
        z = current['z_dwell']
        dwell = current['median_dwell_h']

        # Check exit conditions (if in position)
        if position is not None:
            # Simple P&L based on dwell time change
            if position == 'LONG':
                # LONG bet: dwell will decrease (reversion from high congestion)
                pnl_pct = (entry_dwell - dwell) / entry_dwell
            else:  # SHORT
                # SHORT bet: dwell will increase (from low baseline)
                pnl_pct = (dwell - entry_dwell) / entry_dwell

            # Exit conditions
            should_exit = False

            # Stop loss
            if pnl_pct < -strategy_params["stop_loss_pct"]:
                should_exit = True
                exit_reason = "stop_loss"

            # Take profit
            elif pnl_pct > strategy_params["take_profit_pct"]:
                should_exit = True
                exit_reason = "take_profit"

            # Reversion signal (Z returned to normal)
            elif position == 'LONG' and z < 1.0:
                should_exit = True
                exit_reason = "signal_reversion"

            elif position == 'SHORT' and z > 0.0:
                should_exit = True
                exit_reason = "signal_reversion"

            if should_exit:
                # Close position
                trade_pnl = capital * strategy_params["position_size_pct"] * pnl_pct
                capital += trade_pnl

                trades.append({
                    "entry_date": entry_date,
                    "exit_date": ds,
                    "direction": position,
                    "entry_z": entry_z,
                    "exit_z": z,
                    "entry_dwell": entry_dwell,
                    "exit_dwell": dwell,
                    "pnl": trade_pnl,
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason
                })

                position = None
                entry_z = None
                entry_dwell = None
                entry_date = None

        # Check entry conditions (if not in position)
        if position is None:
            # LONG signal: Extreme congestion (expect reversion)
            if z > strategy_params["long_threshold"]:
                position = 'LONG'
                entry_z = z
                entry_dwell = dwell
                entry_date = ds

            # SHORT signal: Low congestion (expect increase)
            elif z < strategy_params["short_threshold"]:
                position = 'SHORT'
                entry_z = z
                entry_dwell = dwell
                entry_date = ds

        equity_curve.append(capital)

    print(f"   ✅ Simulation complete: {len(trades)} trades executed")
    print()

    # === 4. Calculate Performance Metrics ===

    print("4️⃣  Calculating performance metrics...")

    if not trades:
        print("   ⚠️  No trades executed (signals not triggered)")
        con.close()
        return

    trades_df = pd.DataFrame(trades)

    winning_trades = trades_df[trades_df['pnl'] > 0]
    losing_trades = trades_df[trades_df['pnl'] <= 0]

    total_pnl = trades_df['pnl'].sum()
    win_rate = len(winning_trades) / len(trades) if len(trades) > 0 else 0
    avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
    avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
    profit_factor = abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum()) if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0 else float('inf')

    # Sharpe Ratio (simplified: assuming daily returns, risk-free rate = 0)
    daily_returns = pd.Series(equity_curve).pct_change().dropna()
    sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0

    # Max Drawdown
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = drawdown.min()

    print(f"   Total P&L:        ${total_pnl:+,.2f} ({100*total_pnl/strategy_params['initial_capital']:+.2f}%)")
    print(f"   Final Capital:    ${capital:,.2f}")
    print(f"   Total Trades:     {len(trades)}")
    print(f"   Winning Trades:   {len(winning_trades)}")
    print(f"   Losing Trades:    {len(losing_trades)}")
    print(f"   Win Rate:         {win_rate:.2%}")
    print(f"   Avg Win:          ${avg_win:+,.2f}")
    print(f"   Avg Loss:         ${avg_loss:+,.2f}")
    print(f"   Profit Factor:    {profit_factor:.2f}")
    print(f"   Sharpe Ratio:     {sharpe_ratio:.2f}")
    print(f"   Max Drawdown:     {max_drawdown:.2%}")
    print()

    # === 5. Show Top Trades ===

    print("5️⃣  Top 5 trades by P&L:")
    top_trades = trades_df.nlargest(5, 'pnl')

    print(f"   {'Entry':<12} {'Exit':<12} {'Dir':<6} {'Z_in':>6} {'Z_out':>6} {'P&L':>10} {'%':>7} {'Reason':<15}")
    print(f"   {'-'*12} {'-'*12} {'-'*6} {'-'*6} {'-'*6} {'-'*10} {'-'*7} {'-'*15}")

    for _, trade in top_trades.iterrows():
        print(f"   {str(trade['entry_date']):<12} {str(trade['exit_date']):<12} "
              f"{trade['direction']:<6} {trade['entry_z']:6.2f} {trade['exit_z']:6.2f} "
              f"${trade['pnl']:+9.2f} {trade['pnl_pct']:+6.2%} {trade['exit_reason']:<15}")
    print()

    # === 6. Store Backtest Results ===

    print("6️⃣  Storing backtest results in database...")

    backtest_id = str(uuid.uuid4())

    con.execute("""
        INSERT INTO backtest_runs (
            backtest_id, model_id,
            start_date, end_date, initial_capital,
            long_threshold, short_threshold, position_size_pct,
            total_trades, winning_trades, losing_trades, win_rate,
            total_pnl, sharpe_ratio, max_drawdown,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        backtest_id, "baseline_strategy_v1",
        df['ds'].min(), df['ds'].max(), strategy_params["initial_capital"],
        strategy_params["long_threshold"], strategy_params["short_threshold"],
        strategy_params["position_size_pct"],
        len(trades), len(winning_trades), len(losing_trades), win_rate,
        total_pnl, sharpe_ratio, max_drawdown,
        "Mean reversion strategy on OPL Singapore Z-score"
    ])

    # Store individual trades
    for _, trade in trades_df.iterrows():
        trade_id = str(uuid.uuid4())
        con.execute("""
            INSERT INTO backtest_trades (
                trade_id, backtest_id,
                entry_date, exit_date, anchorage_id, direction,
                predicted_dwell_h, actual_dwell_h,
                pnl, pnl_pct,
                signal_confidence, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            trade_id, backtest_id,
            trade['entry_date'], trade['exit_date'], 'ANCH_OPL_SIN', trade['direction'],
            trade['entry_dwell'], trade['exit_dwell'],
            trade['pnl'], trade['pnl_pct'],
            0.8, "baseline_v1"
        ])

    con.commit()
    con.close()

    print(f"   ✅ Backtest results saved (ID: {backtest_id[:8]}...)")
    print()

    print("=" * 70)
    print("✅ Backtest Complete!")
    print()
    print("📊 Strategy Performance Summary:")
    print(f"   {'Metric':<25} {'Value':>15}")
    print(f"   {'-'*25} {'-'*15}")
    print(f"   {'Total Return':<25} {100*total_pnl/strategy_params['initial_capital']:>14.2f}%")
    print(f"   {'Sharpe Ratio':<25} {sharpe_ratio:>15.2f}")
    print(f"   {'Win Rate':<25} {win_rate:>14.2%}")
    print(f"   {'Profit Factor':<25} {profit_factor:>15.2f}")
    print(f"   {'Max Drawdown':<25} {max_drawdown:>14.2%}")
    print()

    if sharpe_ratio > 1.5 and win_rate > 0.55:
        print("🎯 Strategy shows STRONG potential!")
        print("   • Sharpe > 1.5 (excellent risk-adjusted returns)")
        print("   • Win rate > 55% (consistent edge)")
    elif sharpe_ratio > 1.0 and win_rate > 0.50:
        print("✅ Strategy shows GOOD potential")
        print("   Consider refinement and live testing")
    else:
        print("⚠️  Strategy needs improvement")
        print("   Consider adjusting thresholds or adding more features")


if __name__ == "__main__":
    main()
