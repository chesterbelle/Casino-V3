#!/usr/bin/env python3
"""
=============================================================
🎯 SETUP EDGE AUDITOR — Phase 800 Alpha Analysis
=============================================================

Processes signals and price trajectories recorded during
--audit sessions to statistically prove the edge of each setup.

Metrics:
  - MFE (Maximum Favorable Excursion): Highest profit potential.
  - MAE (Maximum Adverse Excursion): Deepest drawdown risk.
  - Alpha Decay: Rate of profit loss over time.
  - Expected Value (EV): Real edge for specific TP/SL targets.

Usage:
    python utils/setup_edge_auditor.py [--db data/historian.db] [--window 300]
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ANSI Colors
CYAN = "\033[96m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def header(msg):
    line = "=" * 70
    return f"\n{BOLD}{CYAN}{line}\n  {msg}\n{line}{RESET}"


class EdgeAuditor:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def load_data(self):
        conn = sqlite3.connect(self.db_path)

        # Load Signals
        signals_df = pd.read_sql_query("SELECT * FROM signals", conn)

        # Load Price Samples
        prices_df = pd.read_sql_query("SELECT * FROM price_samples", conn)

        conn.close()
        return signals_df, prices_df

    def analyze(self, window_seconds=300):
        signals, prices = self.load_data()

        if signals.empty:
            print(f"{RED}❌ No signals found in database.{RESET}")
            return

        print(header(f"ANALYZING {len(signals)} SIGNALS (Window: {window_seconds}s)"))

        results = []

        # Group prices by symbol for faster lookup
        prices_by_sym = {sym: df.sort_values("timestamp") for sym, df in prices.groupby("symbol")}

        for _, sig in signals.iterrows():
            ts = sig["timestamp"]
            sym = sig["symbol"]
            entry_price = sig["price"]
            side = sig["side"]

            if entry_price <= 0:
                continue

            if sym not in prices_by_sym:
                continue

            # Get price trajectory within the window
            mask = (prices_by_sym[sym]["timestamp"] >= ts) & (prices_by_sym[sym]["timestamp"] <= ts + window_seconds)
            trajectory = prices_by_sym[sym].loc[mask]

            if trajectory.empty:
                continue

            prices_list = trajectory["price"].values

            if side == "LONG":
                mfe_price = np.max(prices_list)
                mae_price = np.min(prices_list)
                mfe_pct = (mfe_price - entry_price) / entry_price * 100
                mae_pct = (entry_price - mae_price) / entry_price * 100
            else:  # SHORT
                mfe_price = np.min(prices_list)
                mae_price = np.max(prices_list)
                mfe_pct = (entry_price - mfe_price) / entry_price * 100
                mae_pct = (mae_price - entry_price) / entry_price * 100

            # Phase 900A: First Touch Win-Rate per TP/SL config
            first_touch = {}
            for tp_t, sl_t in [(0.2, 0.2), (0.3, 0.3), (0.5, 0.5), (0.5, 0.25)]:
                result = "TIMEOUT"
                for p in prices_list:
                    if side == "LONG":
                        pnl_pct = (p - entry_price) / entry_price * 100
                    else:
                        pnl_pct = (entry_price - p) / entry_price * 100
                    if pnl_pct >= tp_t:
                        result = "WIN"
                        break
                    if pnl_pct <= -sl_t:
                        result = "LOSS"
                        break
                first_touch[f"ft_{tp_t}_{sl_t}"] = result

            results.append(
                {
                    "setup_type": sig["setup_type"],
                    "mfe": mfe_pct,
                    "mae": mae_pct,
                    "ratio": mfe_pct / (mae_pct + 1e-9),
                    **first_touch,
                }
            )

        df_results = pd.DataFrame(results)
        self.print_report(df_results)

    def print_report(self, df):
        if df.empty:
            return

        # Setup Type Breakdown
        print(f"\n{BOLD}[1] SETUP EDGE BREAKDOWN{RESET}")
        print(f"{'Setup Type':<25} {'n':<6} {'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<6}")
        print("-" * 70)

        for setup, group in df.groupby("setup_type"):
            avg_mfe = group["mfe"].mean()
            avg_mae = group["mae"].mean()
            ratio = avg_mfe / (avg_mae + 1e-9)

            color = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
            print(f"{setup:<25} {len(group):<6} {avg_mfe:>8.3f}% {avg_mae:>8.3f}% {color}{ratio:>6.2f}{RESET}")

        # Phase 900A: First Touch Win-Rate (Correct temporal calculation)
        print(f"\n{BOLD}[2] FIRST TOUCH WIN-RATE (Temporal Order){RESET}")
        print(f"{'TP/SL':<12} {'Wins':<8} {'Losses':<8} {'Timeout':<8} {'WR%':<8} {'Expectancy'}")
        print("-" * 70)

        configs = [(0.2, 0.2), (0.3, 0.3), (0.5, 0.5), (0.5, 0.25)]
        for tp, sl in configs:
            col = f"ft_{tp}_{sl}"
            if col not in df.columns:
                continue
            wins = (df[col] == "WIN").sum()
            losses = (df[col] == "LOSS").sum()
            timeouts = (df[col] == "TIMEOUT").sum()
            decided = wins + losses
            wr = (wins / decided * 100) if decided > 0 else 0
            ev = ((wr / 100) * tp - ((1 - wr / 100) * sl)) if decided > 0 else 0
            color = GREEN if wr > 55 else RED
            print(f"{tp:.1f}%/{sl:.1f}%    {wins:<8} {losses:<8} {timeouts:<8} {color}{wr:>6.1f}%{RESET}  {ev:>+.4f}")

        # Phase 900A: Per-Setup First Touch Breakdown
        print(f"\n{BOLD}[3] PER-SETUP FIRST TOUCH (0.3%/0.3%){RESET}")
        ft_col = "ft_0.3_0.3"
        if ft_col in df.columns:
            print(f"{'Setup Type':<25} {'n':<6} {'Wins':<6} {'WR%':<8} {'Verdict'}")
            print("-" * 60)
            for setup, group in df.groupby("setup_type"):
                w = (group[ft_col] == "WIN").sum()
                l = (group[ft_col] == "LOSS").sum()
                d = w + l
                wr = (w / d * 100) if d > 0 else 0
                if d < 20:
                    verdict = f"{YELLOW}INSUFFICIENT{RESET}"
                elif wr > 55:
                    verdict = f"{GREEN}CERTIFIED{RESET}"
                elif wr > 50:
                    verdict = f"{YELLOW}WATCH{RESET}"
                else:
                    verdict = f"{RED}FAILED{RESET}"
                print(f"{setup:<25} {len(group):<6} {w:<6} {wr:>6.1f}%  {verdict}")

        print(header("AUDIT COMPLETE"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--window", type=int, default=300, help="Analysis window in seconds")
    args = parser.parse_args()

    try:
        auditor = EdgeAuditor(args.db)
        auditor.analyze(window_seconds=args.window)
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")


if __name__ == "__main__":
    main()
