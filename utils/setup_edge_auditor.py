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
    python utils/setup_edge_auditor.py [--db data/historian.db] [--window 900]
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

        # Load Decision Traces
        try:
            traces_df = pd.read_sql_query("SELECT * FROM decision_traces", conn)
        except sqlite3.OperationalError:
            traces_df = pd.DataFrame()

        conn.close()
        return signals_df, prices_df, traces_df

    def analyze(self, window_seconds=900):
        signals, prices, traces = self.load_data()

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
            for tp_t, sl_t in [(0.15, 0.15), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.5)]:
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
        self.print_report(df_results, traces)

    def print_report(self, df, traces=None):
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

        # NEW: Gross Expectancy Analysis (Pre-Fee Edge)
        print(f"\n{BOLD}[1B] GROSS EXPECTANCY (Pre-Fee Edge in %){RESET}")
        print(
            f"{'Setup Type':<25} {'n':<6} {'WR%':<8} {'Avg Win%':<10} {'Avg Loss%':<10} {'Expectancy%':<12} {'Viable?'}"
        )
        print("-" * 95)

        # Fee assumptions (round-trip)
        FEE_TAKER_RT = 0.12  # 0.06% entry + 0.06% exit (taker/taker)
        FEE_MAKER_RT = 0.08  # 0.02% entry + 0.06% exit (maker/taker with limit sniper)
        FEE_THRESHOLD = FEE_TAKER_RT * 3  # Minimum viable edge = 3x fees

        for setup, group in df.groupby("setup_type"):
            # Calculate using 0.3%/0.3% first touch results
            ft_col = "ft_0.3_0.3"
            if ft_col not in group.columns:
                continue

            wins = (group[ft_col] == "WIN").sum()
            losses = (group[ft_col] == "LOSS").sum()
            decided = wins + losses

            if decided == 0:
                continue

            wr = wins / decided
            lr = losses / decided

            # Average MFE for winners, MAE for losers
            winners = group[group[ft_col] == "WIN"]
            losers = group[group[ft_col] == "LOSS"]

            avg_win_pct = winners["mfe"].mean() if len(winners) > 0 else 0.0
            avg_loss_pct = losers["mae"].mean() if len(losers) > 0 else 0.0

            # Gross Expectancy = (WR × Avg Win) - (LR × Avg Loss)
            expectancy = (wr * avg_win_pct) - (lr * avg_loss_pct)

            # Viability check
            if expectancy > FEE_THRESHOLD:
                viable = f"{GREEN}YES (>{FEE_THRESHOLD:.2f}%){RESET}"
            elif expectancy > FEE_TAKER_RT:
                viable = f"{YELLOW}MARGINAL (>{FEE_TAKER_RT:.2f}%){RESET}"
            else:
                viable = f"{RED}NO (<{FEE_TAKER_RT:.2f}%){RESET}"

            print(
                f"{setup:<25} {len(group):<6} {wr*100:>6.1f}%  {avg_win_pct:>8.3f}%  {avg_loss_pct:>9.3f}%  "
                f"{expectancy:>+10.4f}%  {viable}"
            )

        # Phase 900A: First Touch Win-Rate (Correct temporal calculation)
        print(f"\n{BOLD}[2] THEORETICAL WIN-RATE (First Touch @ Fixed TP/SL){RESET}")
        print(
            f"{'TP/SL':<12} {'Wins':<8} {'Losses':<8} {'Timeout':<8} {'WR%':<8} {'Expectancy%':<12} {'Net (Taker)':<12} {'Net (Maker)'}"
        )
        print("-" * 105)

        FEE_TAKER_RT = 0.12
        FEE_MAKER_RT = 0.08

        configs = [(0.15, 0.15), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.5)]
        for tp, sl in configs:
            col = f"ft_{tp}_{sl}"
            if col not in df.columns:
                continue
            wins = (df[col] == "WIN").sum()
            losses = (df[col] == "LOSS").sum()
            timeouts = (df[col] == "TIMEOUT").sum()
            decided = wins + losses
            wr = (wins / decided * 100) if decided > 0 else 0

            # Gross Expectancy (assumes you capture full TP/SL)
            ev = ((wr / 100) * tp - ((1 - wr / 100) * sl)) if decided > 0 else 0

            # Net Expectancy after fees
            net_taker = ev - FEE_TAKER_RT
            net_maker = ev - FEE_MAKER_RT

            # Color coding based on WR
            color = GREEN if wr > 55 else (YELLOW if wr > 50 else RED)

            # Color for net profitability
            net_color_taker = GREEN if net_taker > 0 else RED
            net_color_maker = GREEN if net_maker > 0 else RED

            print(
                f"{tp:.1f}%/{sl:.1f}%    {wins:<8} {losses:<8} {timeouts:<8} {color}{wr:>6.1f}%{RESET}  "
                f"{ev:>+10.4f}%  {net_color_taker}{net_taker:>+10.4f}%{RESET}  {net_color_maker}{net_maker:>+10.4f}%{RESET}"
            )

        # Phase 900A: Per-Setup First Touch Breakdown
        print(f"\n{BOLD}[3] PER-SETUP FIRST TOUCH (0.3%/0.3%) + GROSS EXPECTANCY{RESET}")
        ft_col = "ft_0.3_0.3"
        if ft_col in df.columns:
            print(f"{'Setup Type':<25} {'n':<6} {'Wins':<6} {'WR%':<8} {'Expectancy%':<12} {'Verdict'}")
            print("-" * 85)

            FEE_THRESHOLD = 0.36  # 3x taker fees

            for setup, group in df.groupby("setup_type"):
                w = (group[ft_col] == "WIN").sum()
                loss_cnt = (group[ft_col] == "LOSS").sum()
                d = w + loss_cnt
                wr = (w / d * 100) if d > 0 else 0

                # Calculate gross expectancy using actual MFE/MAE
                winners = group[group[ft_col] == "WIN"]
                losers = group[group[ft_col] == "LOSS"]
                avg_win = winners["mfe"].mean() if len(winners) > 0 else 0.0
                avg_loss = losers["mae"].mean() if len(losers) > 0 else 0.0
                expectancy = (wr / 100) * avg_win - ((100 - wr) / 100) * avg_loss

                # Verdict based on sample size, WR, and expectancy
                if d < 20:
                    verdict = f"{YELLOW}INSUFFICIENT{RESET}"
                elif expectancy > FEE_THRESHOLD and wr > 55:
                    verdict = f"{GREEN}CERTIFIED{RESET}"
                elif expectancy > 0.12 and wr > 50:
                    verdict = f"{YELLOW}WATCH{RESET}"
                else:
                    verdict = f"{RED}FAILED{RESET}"

                print(f"{setup:<25} {len(group):<6} {w:<6} {wr:>6.1f}%  {expectancy:>+10.4f}%  {verdict}")

        # Phase 1850: Decision Trace Audit
        if traces is not None and not traces.empty:
            print(f"\n{BOLD}[4] DECISION TRACE AUDIT (SetupEngine Gates){RESET}")
            print(f"{'Gate':<25} {'Reason':<40} {'Count':<6}")
            print("-" * 75)

            trace_counts = traces.groupby(["gate", "reason"]).size().reset_index(name="count")
            trace_counts = trace_counts.sort_values("count", ascending=False)

            for _, row in trace_counts.iterrows():
                count = row["count"]
                gate = row["gate"]
                # Highlight in red if it's a rejection, though reason tells us. Actually just print cleanly.
                print(f"{gate:<25} {row['reason']:<40} {count:<6}")

        # NEW: Overall Edge Summary
        print(f"\n{BOLD}[5] OVERALL EDGE SUMMARY{RESET}")
        print("-" * 70)

        # Calculate aggregate metrics using 0.3%/0.3%
        ft_col = "ft_0.3_0.3"
        if ft_col in df.columns:
            total_wins = (df[ft_col] == "WIN").sum()
            total_losses = (df[ft_col] == "LOSS").sum()
            total_decided = total_wins + total_losses

            if total_decided > 0:
                overall_wr = total_wins / total_decided * 100

                # Calculate aggregate expectancy
                winners = df[df[ft_col] == "WIN"]
                losers = df[df[ft_col] == "LOSS"]
                avg_win = winners["mfe"].mean() if len(winners) > 0 else 0.0
                avg_loss = losers["mae"].mean() if len(losers) > 0 else 0.0
                gross_expectancy = (overall_wr / 100) * avg_win - ((100 - overall_wr) / 100) * avg_loss

                # Net expectancy after fees
                net_taker = gross_expectancy - 0.12
                net_maker = gross_expectancy - 0.08

                print(f"Total Signals:        {len(df)}")
                print(f"Decided (W+L):        {total_decided}")
                print(f"Overall Win Rate:     {overall_wr:.1f}%")
                print(f"Avg Win (MFE):        {avg_win:.3f}%")
                print(f"Avg Loss (MAE):       {avg_loss:.3f}%")
                print(f"")
                print(f"{BOLD}Gross Expectancy:     {gross_expectancy:+.4f}%{RESET}")
                print(f"Net (Taker 0.12%):    {net_taker:+.4f}% {'✅' if net_taker > 0 else '❌'}")
                print(f"Net (Maker 0.08%):    {net_maker:+.4f}% {'✅' if net_maker > 0 else '❌'}")
                print(f"")

                # Viability assessment
                if gross_expectancy > 0.36:
                    print(f"{GREEN}✅ EDGE CONFIRMED: Gross expectancy > 3× taker fees (0.36%){RESET}")
                    print(f"{GREEN}   Strategy is viable even with taker orders.{RESET}")
                elif gross_expectancy > 0.12:
                    print(f"{YELLOW}⚠️  MARGINAL EDGE: Gross expectancy > fees but < 3× threshold{RESET}")
                    print(f"{YELLOW}   Requires maker orders (limit sniper) to be profitable.{RESET}")
                else:
                    print(f"{RED}❌ NO EDGE: Gross expectancy < taker fees (0.12%){RESET}")
                    print(f"{RED}   Strategy is not viable. Rework entry logic or exit management.{RESET}")

                print(f"")
                print(f"{BOLD}Recommendation:{RESET}")
                if net_maker > 0 and net_taker <= 0:
                    print(f"  → ENABLE Limit Sniper (maker entries) to capture the edge")
                elif net_taker > 0:
                    print(f"  → Edge is strong enough for market orders")
                else:
                    print(f"  → Edge is too thin. Consider:")
                    print(f"    • Tighter entry filters (reduce MAE)")
                    print(f"    • Better exit timing (capture more MFE)")
                    print(f"    • Wider TP targets if MFE supports it")

        print(header("AUDIT COMPLETE"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--window", type=int, default=900, help="Analysis window in seconds")
    args = parser.parse_args()

    try:
        auditor = EdgeAuditor(args.db)
        auditor.analyze(window_seconds=args.window)
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")


if __name__ == "__main__":
    main()
