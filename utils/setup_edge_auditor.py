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
import json
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

    # Dynamic window per setup type — reflects actual target horizons
    SETUP_WINDOWS = {
        "reversion": 600,  # Mean-reversion to VWAP: fast, 10 min
        "rotation": 900,  # IN_VALUE rotation to VA boundary: 15 min
        "continuation": 1800,  # Trend extension 1.5*ATR: slow, 30 min
    }
    DEFAULT_WINDOW = 900

    def analyze(self, window_seconds=900):
        signals, prices, traces = self.load_data()

        if signals.empty:
            print(f"{RED}❌ No signals found in database.{RESET}")
            return

        print(header(f"ANALYZING {len(signals)} SIGNALS (Dynamic Window per Setup)"))
        print(
            f"  Windows: reversion={self.SETUP_WINDOWS['reversion']}s, "
            f"rotation={self.SETUP_WINDOWS['rotation']}s, "
            f"continuation={self.SETUP_WINDOWS['continuation']}s"
        )

        results = []

        # Group prices by symbol for faster lookup
        prices_by_sym = {sym: df.sort_values("timestamp") for sym, df in prices.groupby("symbol")}

        for _, sig in signals.iterrows():
            ts = sig["timestamp"]
            sym = sig["symbol"]
            entry_price = sig["price"]
            side = sig["side"]
            setup_type = sig["setup_type"]

            if entry_price <= 0:
                continue

            if sym not in prices_by_sym:
                continue

            # Dynamic window based on setup type
            win = self.SETUP_WINDOWS.get(setup_type, window_seconds)

            # Get price trajectory within the window
            mask = (prices_by_sym[sym]["timestamp"] >= ts) & (prices_by_sym[sym]["timestamp"] <= ts + win)
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

            # Real Strategy Performance (Dynamic TP/SL from Metadata)
            real_outcome = "TIMEOUT"
            tp_price = 0.0
            sl_price = 0.0
            tp_pct = 0.0
            sl_pct = 0.0
            if sig["metadata"]:
                try:
                    meta = json.loads(sig["metadata"])
                    tp_price = meta.get("tp_price", 0.0)
                    sl_price = meta.get("sl_price", 0.0)

                    if tp_price > 0 and sl_price > 0:
                        # Calculate actual TP/SL distances as %
                        if side == "LONG":
                            tp_pct = (tp_price - entry_price) / entry_price * 100
                            sl_pct = (entry_price - sl_price) / entry_price * 100
                        else:
                            tp_pct = (entry_price - tp_price) / entry_price * 100
                            sl_pct = (sl_price - entry_price) / entry_price * 100

                        for p in prices_list:
                            if side == "LONG":
                                if p >= tp_price:
                                    real_outcome = "WIN"
                                    break
                                if p <= sl_price:
                                    real_outcome = "LOSS"
                                    break
                            else:  # SHORT
                                if p <= tp_price:
                                    real_outcome = "WIN"
                                    break
                                if p >= sl_price:
                                    real_outcome = "LOSS"
                                    break
                except Exception:
                    pass

            # First Touch Win-Rate per uniform TP/SL config (diagnostic)
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

            # Arbitrator Data
            is_composite = False
            conviction = 0
            if sig["metadata"]:
                try:
                    meta = json.loads(sig["metadata"])
                    is_composite = meta.get("is_composite", False)
                    conviction = meta.get("conviction_score", 0)
                except Exception:
                    pass

            results.append(
                {
                    "setup_type": setup_type,
                    "symbol": sym,
                    "mfe": mfe_pct,
                    "mae": mae_pct,
                    "ratio": mfe_pct / (mae_pct + 1e-9),
                    "real_outcome": real_outcome,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "tp_pct": tp_pct,
                    "sl_pct": sl_pct,
                    "window": win,
                    "is_composite": is_composite,
                    "conviction": conviction,
                    **first_touch,
                }
            )

        df_results = pd.DataFrame(results)
        self.print_report(df_results, traces)

    def print_report(self, df, traces=None):
        if df.empty:
            return

        FEE_TAKER_RT = 0.12
        FEE_MAKER_RT = 0.08
        FEE_THRESHOLD = 0.36

        # ── [1] SETUP EDGE BREAKDOWN (MFE/MAE raw) ──
        print(f"\n{BOLD}[1] SETUP EDGE BREAKDOWN (Raw MFE/MAE){RESET}")
        print(f"{'Setup Type':<20} {'n':<6} {'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8} {'Window':<8}")
        print("-" * 70)

        for setup, group in df.groupby("setup_type"):
            avg_mfe = group["mfe"].mean()
            avg_mae = group["mae"].mean()
            ratio = avg_mfe / (avg_mae + 1e-9)
            avg_win = group["window"].mean()
            color = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
            print(
                f"{setup:<20} {len(group):<6} {avg_mfe:>8.3f}% {avg_mae:>8.3f}% {color}{ratio:>6.2f}{RESET}  {avg_win:>4.0f}s"
            )

        # ── [2] PRIMARY: REAL STRATEGY PERFORMANCE (Dynamic TP/SL) ──
        print(f"\n{BOLD}[2] PRIMARY METRIC: REAL STRATEGY PERFORMANCE (Dynamic TP/SL){RESET}")
        print(
            f"{'Setup Type':<20} {'n':<6} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Avg TP%':<9} {'Avg SL%':<9} {'Exp%':<10} {'Verdict'}"
        )
        print("-" * 105)

        for setup, group in df.groupby("setup_type"):
            w = (group["real_outcome"] == "WIN").sum()
            losses = (group["real_outcome"] == "LOSS").sum()
            to = (group["real_outcome"] == "TIMEOUT").sum()
            d = w + losses
            wr = (w / d * 100) if d > 0 else 0

            # Average actual TP/SL distances
            avg_tp = group["tp_pct"].mean()
            avg_sl = group["sl_pct"].mean()

            # Gross Expectancy using actual TP/SL distances
            expectancy = (wr / 100) * avg_tp - ((100 - wr) / 100) * avg_sl if d > 0 else 0

            if d < 20:
                verdict = f"{YELLOW}LOW_N{RESET}"
            elif expectancy > FEE_THRESHOLD and wr > 55:
                verdict = f"{GREEN}CERTIFIED{RESET}"
            elif expectancy > FEE_TAKER_RT and wr > 50:
                verdict = f"{YELLOW}WATCH{RESET}"
            elif expectancy > 0:
                verdict = f"{YELLOW}FRAGILE{RESET}"
            else:
                verdict = f"{RED}FAILED{RESET}"

            print(
                f"{setup:<20} {len(group):<6} {w:<5} {losses:<5} {to:<5} {wr:>6.1f}%  {avg_tp:>7.3f}%  {avg_sl:>7.3f}%  {expectancy:>+8.4f}%  {verdict}"
            )

        # ── [3] DIAGNOSTIC: UNIFORM TP/SL (Target Calibration) ──
        print(f"\n{BOLD}[3] DIAGNOSTIC: UNIFORM TP/SL (Target Calibration Guide){RESET}")
        print(f"{'Setup Type':<20} {'Best TP/SL':<12} {'WR%':<8} {'Exp%':<10} {'vs Real Exp':<12} {'Target Advice'}")
        print("-" * 100)

        for setup, group in df.groupby("setup_type"):
            best_exp = -999
            best_config = (0, 0)
            best_wr = 0

            for tp_t, sl_t in [(0.15, 0.15), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.5)]:
                col = f"ft_{tp_t}_{sl_t}"
                if col not in group.columns:
                    continue
                w = (group[col] == "WIN").sum()
                losses = (group[col] == "LOSS").sum()
                d = w + losses
                if d == 0:
                    continue
                wr = w / d * 100
                ev = (wr / 100) * tp_t - ((100 - wr) / 100) * sl_t
                if ev > best_exp:
                    best_exp = ev
                    best_config = (tp_t, sl_t)
                    best_wr = wr

            # Compare with real strategy expectancy
            real_w = (group["real_outcome"] == "WIN").sum()
            real_l = (group["real_outcome"] == "LOSS").sum()
            real_d = real_w + real_l
            real_wr = (real_w / real_d * 100) if real_d > 0 else 0
            real_avg_tp = group["tp_pct"].mean()
            real_avg_sl = group["sl_pct"].mean()
            real_exp = (real_wr / 100) * real_avg_tp - ((100 - real_wr) / 100) * real_avg_sl if real_d > 0 else 0

            delta = real_exp - best_exp
            if delta >= -0.05:
                advice = f"{GREEN}Targets OK (within 0.05%){RESET}"
            elif delta >= -0.15:
                advice = f"{YELLOW}Targets slightly suboptimal{RESET}"
            else:
                advice = f"{RED}Targets need adjustment{RESET}"

            print(
                f"{setup:<20} {best_config[0]:.1f}/{best_config[1]:.1f}%    {best_wr:>5.1f}%  {best_exp:>+8.4f}%  {delta:>+10.4f}%  {advice}"
            )

        # ── [4] PER-SETUP UNIFORM GRID (Full Detail) ──
        print(f"\n{BOLD}[4] UNIFORM TP/SL GRID (Full Detail per Setup){RESET}")
        for setup, group in df.groupby("setup_type"):
            print(f"\n  {BOLD}{setup}{RESET} (n={len(group)})")
            print(
                f"  {'TP/SL':<12} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Exp%':<10} {'Net Taker':<10} {'Net Maker'}"
            )
            print("  " + "-" * 80)

            for tp_t, sl_t in [(0.15, 0.15), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.5)]:
                col = f"ft_{tp_t}_{sl_t}"
                if col not in group.columns:
                    continue
                w = (group[col] == "WIN").sum()
                losses = (group[col] == "LOSS").sum()
                to = (group[col] == "TIMEOUT").sum()
                d = w + losses
                wr = (w / d * 100) if d > 0 else 0
                ev = (wr / 100) * tp_t - ((100 - wr) / 100) * sl_t if d > 0 else 0
                net_taker = ev - FEE_TAKER_RT
                net_maker = ev - FEE_MAKER_RT

                color = GREEN if wr > 55 else (YELLOW if wr > 50 else RED)
                nc_t = GREEN if net_taker > 0 else RED
                nc_m = GREEN if net_maker > 0 else RED

                print(
                    f"  {tp_t:.1f}/{sl_t:.1f}%      {w:<5} {losses:<5} {to:<5} {color}{wr:>5.1f}%{RESET}  {ev:>+8.4f}%  {nc_t}{net_taker:>+8.4f}%{RESET}  {nc_m}{net_maker:>+8.4f}%{RESET}"
                )

        # ── [5] ALPHA FUSION & CONVICTION AUDIT ──
        if "is_composite" in df.columns:
            print(f"\n{BOLD}[5] ALPHA FUSION & CONVICTION AUDIT (Arbitrator Efficacy){RESET}")
            print(f"{'Signal Class':<20} {'n':<6} {'W':<5} {'L':<5} {'WR%':<8} {'Avg Conviction':<15} {'Verdict'}")
            print("-" * 75)

            for is_comp, group in df.groupby("is_composite"):
                label = f"{YELLOW}COMPOSITE (Fused){RESET}" if is_comp else "SOLO (Single)"
                w = (group["real_outcome"] == "WIN").sum()
                losses = (group["real_outcome"] == "LOSS").sum()
                d = w + losses
                wr = (w / d * 100) if d > 0 else 0
                avg_conv = group["conviction"].mean()

                v_color = GREEN if wr > 55 else (YELLOW if wr > 50 else RED)
                print(
                    f"{label:<30} {len(group):<6} {w:<5} {losses:<5} {v_color}{wr:>6.1f}%{RESET}   {avg_conv:>8.1f}        {'✅ ALPHA FUSION' if is_comp and wr > 50 else '-'}"
                )

        # ── [6] DECISION TRACE AUDIT ──
        if traces is not None and not traces.empty:
            print(f"\n{BOLD}[6] DECISION TRACE AUDIT (SetupEngine Gates){RESET}")
            print(f"{'Gate':<25} {'Reason':<40} {'Count':<6}")
            print("-" * 75)

            trace_counts = traces.groupby(["gate", "reason"]).size().reset_index(name="count")
            trace_counts = trace_counts.sort_values("count", ascending=False)

            for _, row in trace_counts.iterrows():
                print(f"{row['gate']:<25} {row['reason']:<40} {row['count']:<6}")

        # ── [6] OVERALL EDGE SUMMARY (Primary = Dynamic Targets) ──
        print(f"\n{BOLD}[6] OVERALL EDGE SUMMARY{RESET}")
        print("-" * 70)

        # Primary: Real strategy performance
        if "real_outcome" in df.columns:
            total_wins = (df["real_outcome"] == "WIN").sum()
            total_losses = (df["real_outcome"] == "LOSS").sum()
            total_timeouts = (df["real_outcome"] == "TIMEOUT").sum()
            total_decided = total_wins + total_losses

            if total_decided > 0:
                overall_wr = total_wins / total_decided * 100
                avg_tp = df["tp_pct"].mean()
                avg_sl = df["sl_pct"].mean()
                gross_expectancy = (overall_wr / 100) * avg_tp - ((100 - overall_wr) / 100) * avg_sl

                net_taker = gross_expectancy - FEE_TAKER_RT
                net_maker = gross_expectancy - FEE_MAKER_RT

                print(f"Total Signals:        {len(df)}")
                print(f"Decided (W+L):        {total_decided} (Timeouts: {total_timeouts})")
                print(f"Overall Win Rate:     {overall_wr:.1f}%")
                print(f"Avg TP Distance:      {avg_tp:.3f}%")
                print(f"Avg SL Distance:      {avg_sl:.3f}%")
                print(f"")
                print(f"{BOLD}Gross Expectancy:     {gross_expectancy:+.4f}%{RESET}")
                print(f"Net (Taker 0.12%):    {net_taker:+.4f}% {'✅' if net_taker > 0 else '❌'}")
                print(f"Net (Maker 0.08%):    {net_maker:+.4f}% {'✅' if net_maker > 0 else '❌'}")
                print(f"")

                if gross_expectancy > FEE_THRESHOLD:
                    print(f"{GREEN}✅ EDGE CONFIRMED: Gross expectancy > 3× taker fees (0.36%){RESET}")
                    print(f"{GREEN}   Strategy is viable even with taker orders.{RESET}")
                elif gross_expectancy > FEE_TAKER_RT:
                    print(f"{YELLOW}⚠️  MARGINAL EDGE: Gross expectancy > fees but < 3× threshold{RESET}")
                    print(f"{YELLOW}   Requires maker orders (limit sniper) to be profitable.{RESET}")
                elif gross_expectancy > 0:
                    print(f"{YELLOW}⚠️  THIN EDGE: Gross expectancy positive but below fees{RESET}")
                    print(f"{YELLOW}   Need fee reduction or target optimization.{RESET}")
                else:
                    print(f"{RED}❌ NO EDGE: Gross expectancy negative{RESET}")
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
                    print(f"    • Target calibration (see Section [3])")

        # Secondary: Best uniform TP/SL for reference
        print(f"\n{BOLD}Reference: Best Uniform TP/SL{RESET}")
        for tp_t, sl_t in [(0.15, 0.15), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.5)]:
            col = f"ft_{tp_t}_{sl_t}"
            if col not in df.columns:
                continue
            w = (df[col] == "WIN").sum()
            losses = (df[col] == "LOSS").sum()
            d = w + losses
            if d == 0:
                continue
            wr = w / d * 100
            ev = (wr / 100) * tp_t - ((100 - wr) / 100) * sl_t
            net_t = ev - FEE_TAKER_RT
            nc = GREEN if net_t > 0 else RED
            print(f"  {tp_t:.1f}/{sl_t:.1f}%: WR={wr:.1f}%, Exp={ev:+.4f}%, Net={nc}{net_t:+.4f}%{RESET}")

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
