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

        # Load Signals but ONLY those that actually passed the guardians
        # We do this by inner joining with decision_traces where status = 'EXECUTED'
        # Phase 800: Use UDT trace_id for robust correlation immune to delays
        query = """
        SELECT s.*
        FROM signals s
        INNER JOIN decision_traces d
        ON json_extract(s.metadata, '$.trace_id') = json_extract(d.metrics, '$.trace_id')
        WHERE d.status = 'EXECUTED'
        AND json_extract(s.metadata, '$.trace_id') IS NOT NULL
        """
        try:
            signals_df = pd.read_sql_query(query, conn)
        except sqlite3.OperationalError:
            # Fallback if decision_traces table doesn't exist
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
            for tp_t, sl_t in [
                (0.1, 0.1),
                (0.15, 0.15),
                (0.2, 0.2),
                (0.3, 0.3),
                (0.4, 0.4),
                (0.5, 0.5),
                (0.6, 0.6),
                (0.7, 0.7),
                (0.8, 0.8),
                (0.9, 0.9),
                (0.9, 0.6),  # Historical Asymmetric Standard
                (0.9, 1.0),  # Historical Asymmetric Standard
                (1.0, 1.0),
            ]:
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

            # Net metrics for verdict
            net_taker = expectancy - FEE_TAKER_RT

            if d < 20:
                verdict = f"{YELLOW}LOW_N{RESET}"
            elif expectancy > FEE_THRESHOLD and wr > 55:
                verdict = f"{GREEN}CERTIFIED{RESET}"
            elif net_taker > 0.05:  # Clear profit after fees
                verdict = f"{YELLOW}WATCH{RESET}"
            elif net_taker > -0.02:  # Near break-even
                verdict = f"{RED}MARGINAL (NO EDGE){RESET}"
            else:
                verdict = f"{RED}FAILED (BLEEDING){RESET}"

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

            for tp_t, sl_t in [
                (0.1, 0.1),
                (0.15, 0.15),
                (0.2, 0.2),
                (0.3, 0.3),
                (0.4, 0.4),
                (0.5, 0.5),
                (0.6, 0.6),
                (0.7, 0.7),
                (0.8, 0.8),
                (0.9, 0.9),
                (0.9, 0.6),  # Historical Asymmetric Standard
                (0.9, 1.0),  # Historical Asymmetric Standard
                (1.0, 1.0),
            ]:
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
                f"{setup:<20} {best_config[0]:.2f}/{best_config[1]:.2f}%    {best_wr:>5.1f}%  {best_exp:>+8.4f}%  {delta:>+10.4f}%  {advice}"
            )

        # ── [4] DECISION TRACE AUDIT (SetupEngine Gates) ──
        if traces is not None and not traces.empty:
            print(f"\n{BOLD}[4] DECISION TRACE AUDIT (SetupEngine Gates){RESET}")
            print(f"{'Gate':<25} {'Reason':<40} {'Count':<6}")
            print("-" * 75)

            trace_counts = traces.groupby(["gate", "reason"]).size().reset_index(name="count")
            trace_counts = trace_counts.sort_values("count", ascending=False)

            for _, row in trace_counts.iterrows():
                print(f"{row['gate']:<25} {row['reason']:<40} {row['count']:<6}")

        # ── [5] PER-SETUP UNIFORM GRID (Full Detail) ──
        print(f"\n{BOLD}[5] UNIFORM TP/SL GRID (Full Detail per Setup){RESET}")
        for setup, group in df.groupby("setup_type"):
            print(f"\n  {BOLD}{setup}{RESET} (n={len(group)})")
            print(
                f"  {'TP/SL':<12} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Exp%':<10} {'Net Taker':<10} {'Net Maker'}"
            )
            print("  " + "-" * 80)

            for tp_t, sl_t in [
                (0.1, 0.1),
                (0.15, 0.15),
                (0.2, 0.2),
                (0.3, 0.3),
                (0.4, 0.4),
                (0.5, 0.5),
                (0.6, 0.6),
                (0.7, 0.7),
                (0.8, 0.8),
                (0.9, 0.9),
                (0.9, 0.6),  # Historical Asymmetric Standard
                (0.9, 1.0),  # Historical Asymmetric Standard
                (1.0, 1.0),
            ]:
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
                    f"  {tp_t:.2f}/{sl_t:.2f}%      {w:<5} {losses:<5} {to:<5} {color}{wr:>5.1f}%{RESET}  {ev:>+8.4f}%  {nc_t}{net_taker:>+8.4f}%{RESET}  {nc_m}{net_maker:>+8.4f}%{RESET}"
                )

        # ── [6] ALPHA FUSION & CONVICTION AUDIT ──
        if "is_composite" in df.columns:
            print(f"\n{BOLD}[6] ALPHA FUSION & CONVICTION AUDIT (Arbitrator Efficacy){RESET}")
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

        # ── [7] OVERALL EDGE SUMMARY (Primary = Dynamic Targets) ──
        print(f"\n{BOLD}[7] OVERALL EDGE SUMMARY{RESET}")
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

    def calibrate(self, window_seconds=900):
        signals, prices, traces = self.load_data()

        if signals.empty:
            print(f"{RED}❌ No signals found in database.{RESET}")
            return

        print(header("CALIBRATING DYNAMIC GEOMETRIC AMT TARGETS (Reverse-Engineering)"))

        # Group prices by symbol for faster lookup
        prices_by_sym = {sym: df.sort_values("timestamp") for sym, df in prices.groupby("symbol")}

        # Prepare path data for fast execution
        valid_paths = []
        for _, sig in signals.iterrows():
            ts = sig["timestamp"]
            sym = sig["symbol"]
            entry_price = sig["price"]
            side = sig["side"]
            setup_type = sig["setup_type"]

            if entry_price <= 0 or sym not in prices_by_sym or not sig["metadata"]:
                continue

            try:
                meta = json.loads(sig["metadata"])
            except Exception:
                continue

            poc = meta.get("poc")
            vah = meta.get("vah")
            val = meta.get("val")
            atr_pct = meta.get("atr_1m") or meta.get("atr_pct") or 0.35

            if not poc or not vah or not val:
                continue  # Skip if AMT levels aren't recorded

            win = self.SETUP_WINDOWS.get(setup_type, window_seconds)
            mask = (prices_by_sym[sym]["timestamp"] >= ts) & (prices_by_sym[sym]["timestamp"] <= ts + win)
            trajectory = prices_by_sym[sym].loc[mask]

            if trajectory.empty:
                continue

            prices_list = trajectory["price"].values
            valid_paths.append(
                {
                    "entry_price": entry_price,
                    "side": side,
                    "setup_type": setup_type,
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "atr_pct": atr_pct,
                    "prices_list": prices_list,
                }
            )

        if not valid_paths:
            print(f"{RED}❌ No signals with valid AMT metadata (poc, vah, val) and trajectories found.{RESET}")
            return

        print(f"  Loaded {len(valid_paths)} valid signals with rich AMT structural metrics.")

        # Parameter Grid
        k_tp_values = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        k_sl_values = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]

        sweep_results = []

        print("  ⏳ Sweeping target configurations in memory...")
        for k_tp in k_tp_values:
            for k_sl in k_sl_values:
                wins = 0
                losses = 0
                timeouts = 0
                total_pnl = 0.0

                for path in valid_paths:
                    entry = path["entry_price"]
                    side = path["side"]
                    poc = path["poc"]
                    vah = path["vah"]
                    val = path["val"]
                    atr_pct = path["atr_pct"]
                    prices_list = path["prices_list"]

                    # Distance to POC
                    d_poc = abs(entry - poc)

                    # Distance to invalidation boundary
                    if side == "LONG":
                        d_boundary = entry - val
                    else:
                        d_boundary = vah - entry

                    # Safe fallbacks if price is already outside the boundary
                    if d_boundary <= 0:
                        d_boundary = d_poc * 0.8

                    # 1. Calculate TP and SL as percentage of entry price
                    noise_floor_pct = 1.0 * atr_pct
                    tp_pct = max(noise_floor_pct, k_tp * (d_poc / entry) * 100.0)
                    sl_pct = max(noise_floor_pct * 0.8, k_sl * (d_boundary / entry) * 100.0)

                    # Apply tp_pct / sl_pct to find the target prices
                    if side == "LONG":
                        tp_price = entry * (1.0 + tp_pct / 100.0)
                        sl_price = entry * (1.0 - sl_pct / 100.0)
                    else:
                        tp_price = entry * (1.0 - tp_pct / 100.0)
                        sl_price = entry * (1.0 + sl_pct / 100.0)

                    # 2. Simulate price trajectory
                    outcome = "TIMEOUT"
                    final_pnl = 0.0
                    for p in prices_list:
                        if side == "LONG":
                            if p >= tp_price:
                                outcome = "WIN"
                                final_pnl = tp_pct
                                break
                            if p <= sl_price:
                                outcome = "LOSS"
                                final_pnl = -sl_pct
                                break
                        else:  # SHORT
                            if p <= tp_price:
                                outcome = "WIN"
                                final_pnl = tp_pct
                                break
                            if p >= sl_price:
                                outcome = "LOSS"
                                final_pnl = -sl_pct
                                break

                    if outcome == "TIMEOUT":
                        timeouts += 1
                        # Close at market price
                        close_price = prices_list[-1]
                        if side == "LONG":
                            final_pnl = (close_price - entry) / entry * 100.0
                        else:
                            final_pnl = (entry - close_price) / entry * 100.0
                    elif outcome == "WIN":
                        wins += 1
                    else:
                        losses += 1

                    total_pnl += final_pnl

                total_signals = len(valid_paths)
                wr = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0
                to_rate = timeouts / total_signals * 100.0
                gross_exp = total_pnl / total_signals
                net_taker = gross_exp - 0.12

                sweep_results.append(
                    {
                        "k_tp": k_tp,
                        "k_sl": k_sl,
                        "wr": wr,
                        "to": to_rate,
                        "gross_exp": gross_exp,
                        "net_taker": net_taker,
                    }
                )

        df_sweep = pd.DataFrame(sweep_results)
        df_sweep = df_sweep.sort_values("gross_exp", ascending=False)

        # Print Top 15 configurations
        print(f"\n{BOLD}🎯 TOP 15 GEOMETRIC AMT TARGET CONFIGURATIONS (Sorted by Expectancy){RESET}")
        print(
            f"{'Rank':<5} {'k_TP (POC)':<12} {'k_SL (Bound)':<12} {'WR%':<8} {'TO%':<8} {'Gross Exp%':<12} {'Net Taker%':<12} {'Status'}"
        )
        print("-" * 90)

        for i, (_, row) in enumerate(df_sweep.head(15).iterrows(), 1):
            status = (
                f"{GREEN}CERTIFIED{RESET}"
                if row["net_taker"] > 0.05
                else (f"{YELLOW}WATCH{RESET}" if row["net_taker"] > 0 else f"{RED}FAIL{RESET}")
            )
            print(
                f"{i:<5} {row['k_tp']:<12.1f} {row['k_sl']:<12.1f} {row['wr']:>5.1f}% {row['to']:>5.1f}% {row['gross_exp']:>+10.4f}% {row['net_taker']:>+10.4f}% {status}"
            )

        champion = df_sweep.iloc[0]
        print(f"\n{BOLD}🏆 CHAMPION CONFIGURATION:{RESET}")
        print(f"  • {BOLD}k_TP (POC Multiplier):{RESET}  {GREEN}{champion['k_tp']:.2f}{RESET}")
        print(f"  • {BOLD}k_SL (VAL/VAH Multiplier):{RESET} {GREEN}{champion['k_sl']:.2f}{RESET}")
        print(f"  • {BOLD}Expected Win Rate:{RESET}          {champion['wr']:.1f}%")
        print(f"  • {BOLD}Expected Timeout Rate:{RESET}      {champion['to']:.1f}%")
        print(f"  • {BOLD}Gross Expectancy:{RESET}          {GREEN}{champion['gross_exp']:+.4f}%{RESET}")
        print(f"  • {BOLD}Net Taker Expectancy:{RESET}      {GREEN}{champion['net_taker']:+.4f}%{RESET}")

        print(f"\n{BOLD}📝 CALIBRATED PRODUCTION CODE FORMULA FOR setup_engine.py:{RESET}")
        print("```python")
        print(f"def _calculate_targets(self, entry_price, side, poc, vah, val, atr_pct):")
        print(f"    # Dynamic AMT Targets Calibrated via Edge Auditor on {datetime.now().strftime('%Y-%m-%d')}")
        print(f"    dist_to_poc = abs(entry_price - poc)")
        print(f"    dist_to_boundary = (entry_price - val) if side == 'LONG' else (vah - entry_price)")
        print(f"    if dist_to_boundary <= 0:")
        print(f"        dist_to_boundary = dist_to_poc * 0.8")
        print(f"")
        print(f"    noise_floor_pct = 1.0 * atr_pct")
        print(f"    tp_dist_pct = max(noise_floor_pct, {champion['k_tp']:.1f} * (dist_to_poc / entry_price) * 100.0)")
        print(
            f"    sl_dist_pct = max(noise_floor_pct * 0.8, {champion['k_sl']:.1f} * (dist_to_boundary / entry_price) * 100.0)"
        )
        print(f"")
        print(
            f"    tp_price = entry_price * (1.0 + tp_dist_pct/100.0) if side == 'LONG' else entry_price * (1.0 - tp_dist_pct/100.0)"
        )
        print(
            f"    sl_price = entry_price * (1.0 - sl_dist_pct/100.0) if side == 'LONG' else entry_price * (1.0 + sl_dist_pct/100.0)"
        )
        print(f"    return tp_price, sl_price")
        print("```")
        print(header("CALIBRATION COMPLETE"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--window", type=int, default=900, help="Analysis window in seconds")
    parser.add_argument("--calibrate", action="store_true", help="Run dynamic AMT target calibration sweep")
    args = parser.parse_args()

    try:
        auditor = EdgeAuditor(args.db)
        if args.calibrate:
            auditor.calibrate(window_seconds=args.window)
        else:
            auditor.analyze(window_seconds=args.window)
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")


if __name__ == "__main__":
    main()
