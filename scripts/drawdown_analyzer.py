#!/usr/bin/env python3
"""
===============================================================================
📊 DRAWDOWN ANALYZER — Phase 1.6 Risk Analysis
===============================================================================
Reads historian.db signals from audit mode backtests and simulates a portfolio
equity curve to extract:
  1. Max drawdown per asset and portfolio
  2. Max consecutive loss streak
  3. Average recovery time
  4. Recommended capital and position sizing

Uses signal outcomes (W/L/TO) with actual TP/SL percentages.
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from typing import List

import numpy as np
import pandas as pd


def load_signals(db_path: str) -> pd.DataFrame:
    """Load all signals with outcome data from historian.db."""
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        id, timestamp, symbol, side, price, session_id,
        json_extract(metadata, '$.scenario') as setup_type,
        json_extract(metadata, '$.tp_distance_pct') as tp_pct,
        json_extract(metadata, '$.sl_distance_pct') as sl_pct,
        json_extract(metadata, '$.tp_price') as tp_price,
        json_extract(metadata, '$.sl_price') as sl_price
    FROM signals
    ORDER BY timestamp
    """
    df = pd.read_sql_query(query, conn)

    # Load price_samples for outcome determination
    price_samples = pd.read_sql_query("SELECT timestamp, symbol, price FROM price_samples ORDER BY timestamp", conn)
    conn.close()

    # Convert numeric columns
    for col in ["tp_pct", "sl_pct", "tp_price", "sl_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, price_samples


def determine_outcome(signal: pd.Series, price_samples: pd.DataFrame, window_sec: int = 21600) -> dict:
    """Determine if a signal resulted in WIN, LOSS, or TIMEOUT."""
    sym = signal["symbol"]
    ts = signal["timestamp"]
    side = signal["side"]
    entry = signal["price"]
    tp_price = signal.get("tp_price")
    sl_price = signal.get("sl_price")
    tp_pct = signal.get("tp_pct", 0)
    sl_pct = signal.get("sl_pct", 0)

    # Calculate TP/SL prices if not provided
    if pd.isna(tp_price) or pd.isna(sl_price):
        if side == "LONG":
            tp_price = entry * (1 + tp_pct) if tp_pct else entry * 1.009
            sl_price = entry * (1 - sl_pct) if sl_pct else entry * 0.991
        else:
            tp_price = entry * (1 - tp_pct) if tp_pct else entry * 0.991
            sl_price = entry * (1 + sl_pct) if sl_pct else entry * 1.009

    # Filter price samples for this symbol within window
    mask = (
        (price_samples["symbol"] == sym)
        & (price_samples["timestamp"] >= ts)
        & (price_samples["timestamp"] <= ts + window_sec)
    )
    trajectory = price_samples.loc[mask].sort_values("timestamp")

    if trajectory.empty:
        return {"outcome": "TIMEOUT", "pnl_pct": 0.0}

    # Walk through prices chronologically
    for _, row in trajectory.iterrows():
        p = row["price"]
        if side == "LONG":
            if p >= tp_price:
                return {"outcome": "WIN", "pnl_pct": abs(tp_pct) if tp_pct else 0.9}
            if p <= sl_price:
                return {"outcome": "LOSS", "pnl_pct": -abs(sl_pct) if sl_pct else -0.9}
        else:  # SHORT
            if p <= tp_price:
                return {"outcome": "WIN", "pnl_pct": abs(tp_pct) if tp_pct else 0.9}
            if p >= sl_price:
                return {"outcome": "LOSS", "pnl_pct": -abs(sl_pct) if sl_pct else -0.9}

    # Timeout — use last price
    last_price = trajectory.iloc[-1]["price"]
    if side == "LONG":
        exit_pnl = (last_price - entry) / entry * 100
    else:
        exit_pnl = (entry - last_price) / entry * 100

    return {"outcome": "TIMEOUT", "pnl_pct": exit_pnl}


def simulate_equity_curve(
    trades: List[dict], initial_capital: float = 10000, risk_per_trade: float = 0.01, taker_fee_pct: float = 0.07
) -> pd.DataFrame:
    """
    Simulate equity curve from trade outcomes.
    risk_per_trade = fraction of equity risked per trade (1% default).
    """
    equity = initial_capital
    records = []
    peak = equity

    for t in trades:
        pnl_pct = t["pnl_pct"]
        # Position size = risk_per_trade * equity
        position_value = equity * risk_per_trade
        # PnL in dollars (pnl_pct is already in %, convert)
        gross_pnl = position_value * (pnl_pct / 100) if pnl_pct != 0 else 0
        # Fee: entry + exit
        fee = position_value * (taker_fee_pct / 100) * 2
        net_pnl = gross_pnl - fee

        equity += net_pnl
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak * 100

        records.append(
            {
                "trade_num": len(records) + 1,
                "timestamp": t["timestamp"],
                "symbol": t["symbol"],
                "setup_type": t.get("setup_type", "unknown"),
                "outcome": t["outcome"],
                "pnl_pct": pnl_pct,
                "gross_pnl": gross_pnl,
                "fee": fee,
                "net_pnl": net_pnl,
                "equity": equity,
                "peak": peak,
                "drawdown_pct": drawdown,
            }
        )

    return pd.DataFrame(records)


def analyze_loss_streaks(equity_df: pd.DataFrame) -> dict:
    """Analyze consecutive loss streaks."""
    outcomes = equity_df["outcome"].tolist()
    max_streak = 0
    current_streak = 0
    streaks = []

    for o in outcomes:
        if o == "LOSS":
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            if current_streak > 0:
                streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        streaks.append(current_streak)

    return {
        "max_loss_streak": max_streak,
        "avg_loss_streak": np.mean(streaks) if streaks else 0,
        "total_streaks": len(streaks),
        "streak_distribution": dict(zip(*np.unique(streaks, return_counts=True))) if streaks else {},
    }


def analyze_recovery(equity_df: pd.DataFrame) -> dict:
    """Analyze recovery times from drawdowns."""
    in_drawdown = False
    dd_start_trade = None
    recoveries = []

    for _, row in equity_df.iterrows():
        if row["drawdown_pct"] > 0 and not in_drawdown:
            in_drawdown = True
            dd_start_trade = row["trade_num"]
        elif row["drawdown_pct"] == 0 and in_drawdown:
            in_drawdown = False
            recovery_trades = row["trade_num"] - dd_start_trade
            recoveries.append(recovery_trades)

    return {
        "avg_recovery_trades": np.mean(recoveries) if recoveries else 0,
        "max_recovery_trades": max(recoveries) if recoveries else 0,
        "total_drawdown_episodes": len(recoveries) + (1 if in_drawdown else 0),
        "currently_in_drawdown": in_drawdown,
    }


def per_asset_analysis(equity_df: pd.DataFrame) -> pd.DataFrame:
    """Per-asset breakdown of risk metrics."""
    results = []
    for sym, group in equity_df.groupby("symbol"):
        wins = (group["outcome"] == "WIN").sum()
        losses = (group["outcome"] == "LOSS").sum()
        timeouts = (group["outcome"] == "TIMEOUT").sum()
        total = len(group)

        results.append(
            {
                "symbol": sym,
                "trades": total,
                "wins": wins,
                "losses": losses,
                "timeouts": timeouts,
                "win_rate": wins / (wins + losses) * 100 if (wins + losses) > 0 else 0,
                "total_net_pnl": group["net_pnl"].sum(),
                "max_single_loss": group["net_pnl"].min(),
                "avg_win": group.loc[group["outcome"] == "WIN", "net_pnl"].mean() if wins > 0 else 0,
                "avg_loss": group.loc[group["outcome"] == "LOSS", "net_pnl"].mean() if losses > 0 else 0,
            }
        )

    return pd.DataFrame(results).sort_values("total_net_pnl", ascending=False)


def main():
    parser = argparse.ArgumentParser(description="Phase 1.6 Drawdown & Risk Analysis")
    parser.add_argument("--db", default="data/historian.db", help="Path to historian.db")
    parser.add_argument("--capital", type=float, default=10000, help="Initial capital ($)")
    parser.add_argument("--risk", type=float, default=0.01, help="Risk per trade (fraction)")
    parser.add_argument("--fee", type=float, default=0.07, help="Taker fee (percent)")
    args = parser.parse_args()

    print("=" * 70)
    print("📊 PHASE 1.6 — DRAWDOWN & RISK ANALYSIS")
    print("=" * 70)

    # 1. Load signals
    print("\n[1] Loading signals from historian.db...")
    signals_df, price_samples = load_signals(args.db)
    print(f"    Signals: {len(signals_df)}")
    print(f"    Price samples: {len(price_samples)}")
    print(f"    Symbols: {signals_df['symbol'].nunique()}")

    if signals_df.empty:
        print("❌ No signals found. Run audit backtests first.")
        sys.exit(1)

    # 2. Determine outcomes
    print("\n[2] Determining trade outcomes...")
    trades = []
    for _, sig in signals_df.iterrows():
        outcome = determine_outcome(sig, price_samples)
        trades.append(
            {
                "timestamp": sig["timestamp"],
                "symbol": sig["symbol"],
                "side": sig["side"],
                "setup_type": sig.get("setup_type", "unknown"),
                **outcome,
            }
        )

    outcomes_summary = defaultdict(int)
    for t in trades:
        outcomes_summary[t["outcome"]] += 1
    print(
        f"    WIN: {outcomes_summary['WIN']} | LOSS: {outcomes_summary['LOSS']} | TIMEOUT: {outcomes_summary['TIMEOUT']}"
    )

    # 3. Simulate equity curve
    print(
        f"\n[3] Simulating equity curve (Capital=${args.capital:,.0f}, Risk={args.risk*100:.1f}%, Fee={args.fee}%)..."
    )
    equity_df = simulate_equity_curve(trades, args.capital, args.risk, args.fee)

    # 4. Portfolio-level metrics
    print("\n" + "=" * 70)
    print("📈 PORTFOLIO RISK METRICS")
    print("=" * 70)

    max_dd = equity_df["drawdown_pct"].max()
    max_dd_row = equity_df.loc[equity_df["drawdown_pct"].idxmax()]
    final_equity = equity_df.iloc[-1]["equity"]
    total_return = (final_equity - args.capital) / args.capital * 100

    print(f"  Initial Capital:       ${args.capital:,.2f}")
    print(f"  Final Equity:          ${final_equity:,.2f}")
    print(f"  Total Return:          {total_return:+.2f}%")
    print(f"  Total Trades:          {len(equity_df)}")
    print(f"  Max Drawdown:          {max_dd:.2f}% (at trade #{int(max_dd_row['trade_num'])})")
    print(f"  Avg Drawdown:          {equity_df['drawdown_pct'].mean():.2f}%")

    # 5. Loss streaks
    streaks = analyze_loss_streaks(equity_df)
    print(f"\n  Max Loss Streak:       {streaks['max_loss_streak']} consecutive")
    print(f"  Avg Loss Streak:       {streaks['avg_loss_streak']:.1f}")
    if streaks["streak_distribution"]:
        print(f"  Streak Distribution:   {streaks['streak_distribution']}")

    # 6. Recovery
    recovery = analyze_recovery(equity_df)
    print(f"\n  Drawdown Episodes:     {recovery['total_drawdown_episodes']}")
    print(f"  Avg Recovery:          {recovery['avg_recovery_trades']:.1f} trades")
    print(f"  Max Recovery:          {recovery['max_recovery_trades']} trades")
    print(f"  Currently in DD:       {'Yes' if recovery['currently_in_drawdown'] else 'No'}")

    # 7. Capital recommendations
    print("\n" + "=" * 70)
    print("💰 CAPITAL & SIZING RECOMMENDATIONS")
    print("=" * 70)

    # Kelly-inspired sizing
    wins_total = outcomes_summary["WIN"]
    losses_total = outcomes_summary["LOSS"]
    decided = wins_total + losses_total
    if decided > 0:
        wr = wins_total / decided
        avg_win = equity_df.loc[equity_df["outcome"] == "WIN", "pnl_pct"].mean() if wins_total > 0 else 0
        avg_loss = abs(equity_df.loc[equity_df["outcome"] == "LOSS", "pnl_pct"].mean()) if losses_total > 0 else 1
        rr = avg_win / avg_loss if avg_loss > 0 else 0
        kelly = (wr * rr - (1 - wr)) / rr if rr > 0 else 0
        half_kelly = kelly / 2

        print(f"  Win Rate:              {wr*100:.1f}%")
        print(f"  Risk/Reward Ratio:     {rr:.2f}")
        print(f"  Full Kelly:            {kelly*100:.1f}%")
        print(f"  Half Kelly (rec):      {half_kelly*100:.1f}%")

    # Max drawdown-based capital
    if max_dd > 0:
        # If max DD is X% with 1% risk, for 5% max DD limit:
        capital_multiplier = 5.0 / max_dd  # scale to keep DD < 5%
        rec_risk = args.risk * capital_multiplier
        rec_risk = min(rec_risk, 0.03)  # cap at 3%
        rec_risk = max(rec_risk, 0.005)  # floor at 0.5%
        print(f"\n  With {max_dd:.1f}% max DD at {args.risk*100:.1f}% risk:")
        print(f"  Recommended risk/trade: {rec_risk*100:.2f}%")
        print(f"  To keep DD < 5%:       risk ≤ {5.0/max_dd * args.risk * 100:.2f}%")
        print(f"  To keep DD < 10%:      risk ≤ {10.0/max_dd * args.risk * 100:.2f}%")

    # Min capital for $20 min notional
    min_notional = 20  # Binance minimum
    min_capital = min_notional / (rec_risk if max_dd > 0 else args.risk)
    print("\n  Min Capital (Binance $20 notional):")
    print(f"    At {rec_risk*100:.2f}% risk:     ${min_capital:,.0f}")
    print(f"    At 1% risk:          ${min_notional / 0.01:,.0f}")
    print(f"    At 2% risk:          ${min_notional / 0.02:,.0f}")

    # 8. Per-asset breakdown
    print("\n" + "=" * 70)
    print("📋 PER-ASSET BREAKDOWN")
    print("=" * 70)
    asset_df = per_asset_analysis(equity_df)
    print(
        f"\n{'Symbol':<12} {'Trades':>6} {'WR%':>6} {'Net PnL':>10} {'Max Loss':>10} {'Avg Win':>10} {'Avg Loss':>10}"
    )
    print("-" * 70)
    for _, row in asset_df.iterrows():
        print(
            f"{row['symbol']:<12} {int(row['trades']):>6} {row['win_rate']:>5.1f}% "
            f"${row['total_net_pnl']:>+9.2f} ${row['max_single_loss']:>+9.2f} "
            f"${row['avg_win']:>+9.2f} ${row['avg_loss']:>+9.2f}"
        )

    # 9. Verdict
    print("\n" + "=" * 70)
    print("🏁 VERDICT")
    print("=" * 70)
    if max_dd < 5:
        print(f"  ✅ Max Drawdown {max_dd:.1f}% < 5% — CONSERVATIVE RISK")
    elif max_dd < 10:
        print(f"  ⚠️  Max Drawdown {max_dd:.1f}% < 10% — MODERATE RISK")
    elif max_dd < 20:
        print(f"  ⚠️  Max Drawdown {max_dd:.1f}% < 20% — ELEVATED RISK (within roadmap threshold)")
    else:
        print(f"  ❌ Max Drawdown {max_dd:.1f}% ≥ 20% — EXCEEDS ROADMAP THRESHOLD")
        print("     Action: reduce risk/trade or remove underperforming assets")

    if streaks["max_loss_streak"] <= 5:
        print(f"  ✅ Max Loss Streak {streaks['max_loss_streak']} ≤ 5 — ACCEPTABLE")
    elif streaks["max_loss_streak"] <= 10:
        print(f"  ⚠️  Max Loss Streak {streaks['max_loss_streak']} — MONITOR CLOSELY")
    else:
        print(f"  ❌ Max Loss Streak {streaks['max_loss_streak']} > 10 — REVIEW STRATEGY")

    print("=" * 70)


if __name__ == "__main__":
    main()
