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
from trajectory_core import DEFAULT_WINDOW, SETUP_WINDOWS, get_trajectory, load_data

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
    def __init__(self, db_path: str, by_coin=False, coin_filter=None):
        self.db_path = db_path
        self.by_coin = by_coin
        self.coin_filter = coin_filter
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        # Import SETUP_WINDOWS for use in calibration
        from trajectory_core import SETUP_WINDOWS

        self.SETUP_WINDOWS = SETUP_WINDOWS

    def load_data(self):
        """Load data using trajectory_core module"""
        return load_data(self.db_path)

    def analyze(self, window_seconds=DEFAULT_WINDOW):
        signals, prices, traces = self.load_data()

        if self.coin_filter:
            before = len(signals)
            signals = signals[signals["symbol"] == self.coin_filter]
            print(f"  🪙 Filtered to {self.coin_filter}: {len(signals)}/{before} signals")

        if signals.empty:
            print(f"{RED}❌ No signals found in database.{RESET}")
            return

        print(header(f"ANALYZING {len(signals)} SIGNALS (Dynamic Window per Setup)"))
        # Get the first three setup types for display, or fewer if less exist
        setup_types = list(SETUP_WINDOWS.keys())
        display_types = setup_types[:3] if len(setup_types) >= 3 else setup_types

        # Build the window display string dynamically
        window_parts = []
        for st in display_types:
            window_parts.append(f"{st}={SETUP_WINDOWS[st]}s")

        windows_str = ", ".join(window_parts)
        if len(setup_types) > 3:
            windows_str += f" (and {len(setup_types)-3} more)"

        print(f"  Windows: {windows_str}")

        results = []

        for _, sig in signals.iterrows():
            entry_price = sig["price"]
            side = sig["side"]
            setup_type = sig["setup_type"]

            if entry_price <= 0:
                continue

            # Dynamic window based on setup type
            win = SETUP_WINDOWS.get(setup_type, window_seconds)

            # Get trajectory using trajectory_core
            trajectory = get_trajectory(sig, prices, win)

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

            # Real Strategy Performance (Dynamic TP/SL from Metadata already in sig)
            real_outcome = "TIMEOUT"
            tp_price = sig.get("tp_price", 0.0)
            sl_price = sig.get("sl_price", 0.0)
            tp_pct = sig.get("tp_distance_pct", 0.0)
            sl_pct = sig.get("sl_distance_pct", 0.0)

            # Fallback: calculate TP/SL pct from absolute prices when metadata missing
            if tp_pct == 0.0 and tp_price > 0 and entry_price > 0:
                tp_pct = abs(tp_price - entry_price) / entry_price * 100
            if sl_pct == 0.0 and sl_price > 0 and entry_price > 0:
                sl_pct = abs(sl_price - entry_price) / entry_price * 100

            # Determine real outcome
            for p in prices_list:
                if side == "LONG":
                    pnl_pct = (p - entry_price) / entry_price * 100
                else:
                    pnl_pct = (entry_price - p) / entry_price * 100
                if pnl_pct >= tp_pct and tp_pct > 0:
                    real_outcome = "WIN"
                    break
                if pnl_pct <= -sl_pct and sl_pct > 0:
                    real_outcome = "LOSS"
                    break

            # First Touch Analysis for uniform grids
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

            # Arbitrator Data (directly from sig)
            is_composite = sig.get("is_composite", False)
            conviction = sig.get("conviction_score", 0)

            results.append(
                {
                    "setup_type": setup_type,
                    "symbol": sig["symbol"],
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

    def _find_best_uniform(self, group, uniform_grids=None):
        """Find best uniform TP/SL for a group. Returns (best_exp, best_config, best_wr) or None."""
        if uniform_grids is None:
            uniform_grids = [
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
                (0.9, 0.6),
                (0.9, 1.0),
                (1.0, 1.0),
            ]
        best_exp = -999
        best_config = None
        best_wr = 0
        for tp_t, sl_t in uniform_grids:
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
        if best_config is None:
            return None
        return best_exp, best_config, best_wr

    def print_report(self, df, traces=None):
        if df.empty:
            return

        FEE_TAKER_RT = 0.12
        FEE_MAKER_RT = 0.08
        UNIFORM_GRIDS = [
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
            (0.9, 0.6),
            (0.9, 1.0),
            (1.0, 1.0),
        ]

        # ── [1] SETUP EDGE BREAKDOWN (MFE/MAE raw) ──
        suffix = " (Per Coin)" if self.by_coin else ""
        print(f"\n{BOLD}[1] SETUP EDGE BREAKDOWN (Raw MFE/MAE){suffix}{RESET}")
        if self.by_coin:
            print(
                f"{'Setup Type':<20} {'Coin':<26} {'n':<6} {'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8} {'Window':<8}"
            )
        else:
            print(f"{'Setup Type':<20} {'n':<6} {'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8} {'Window':<8}")
        print("-" * 70 if not self.by_coin else "-" * 100)

        for setup, s_group in df.groupby("setup_type"):
            if self.by_coin:
                for coin, group in s_group.groupby("symbol"):
                    avg_mfe = group["mfe"].mean()
                    avg_mae = group["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    avg_win = group["window"].mean()
                    color = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                    print(
                        f"{setup:<20} {coin:<26} {len(group):<6} {avg_mfe:>8.3f}% {avg_mae:>8.3f}% {color}{ratio:>6.2f}{RESET}  {avg_win:>4.0f}s"
                    )
            else:
                group = s_group
                avg_mfe = group["mfe"].mean()
                avg_mae = group["mae"].mean()
                ratio = avg_mfe / (avg_mae + 1e-9)
                avg_win = group["window"].mean()
                color = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                print(
                    f"{setup:<20} {len(group):<6} {avg_mfe:>8.3f}% {avg_mae:>8.3f}% {color}{ratio:>6.2f}{RESET}  {avg_win:>4.0f}s"
                )

        # ── [2] ENTRY QUALITY ASSESSMENT (Uniform Grid Ground Truth) ──
        suffix = " (Per Coin)" if self.by_coin else ""
        print(f"\n{BOLD}[2] ENTRY QUALITY ASSESSMENT (Uniform Grid as Ground Truth){suffix}{RESET}")
        print(f"  The Uniform Grid tests ALL possible TP/SL combinations. If NONE produce")
        print(f"  positive Net Taker, the entry signal ITSELF has no exploitable edge,")
        print(f"  regardless of target optimization.")
        print()
        if self.by_coin:
            print(
                f"{'Setup Type':<20} {'Coin':<26} {'Best TP/SL':<12} {'Best WR%':<9} {'Best Exp%':<11} {'Best Net':<10} {'Entry OK?'}"
            )
            print("-" * 120)
        else:
            print(
                f"{'Setup Type':<20} {'Best TP/SL':<12} {'Best WR%':<9} {'Best Exp%':<11} {'Best Net':<10} {'Entry OK?'}"
            )
            print("-" * 90)

        for setup, s_group in df.groupby("setup_type"):
            groups = [(setup, s_group)] if not self.by_coin else [(c, g) for c, g in s_group.groupby("symbol")]
            for label, group in groups:
                best = self._find_best_uniform(group, UNIFORM_GRIDS)
                if best is None:
                    continue
                best_exp, (tp_t, sl_t), best_wr = best
                best_net = best_exp - FEE_TAKER_RT
                entry_ok = best_net > 0
                status = f"{GREEN}✅ YES{RESET}" if entry_ok else f"{RED}❌ NO{RESET}"
                if self.by_coin:
                    print(
                        f"{setup:<20} {label:<26} {tp_t:.2f}/{sl_t:.2f}%    {best_wr:>6.1f}%  {best_exp:>+9.4f}%  {best_net:>+8.4f}%  {status}"
                    )
                else:
                    print(
                        f"{setup:<20} {tp_t:.2f}/{sl_t:.2f}%    {best_wr:>6.1f}%  {best_exp:>+9.4f}%  {best_net:>+8.4f}%  {status}"
                    )

        # ── [3] ROOT CAUSE DIAGNOSIS ──
        print(f"\n{BOLD}[3] ROOT CAUSE DIAGNOSIS{RESET}")
        for setup, s_group in df.groupby("setup_type"):
            groups = [(setup, s_group)] if not self.by_coin else [(c, g) for c, g in s_group.groupby("symbol")]
            for label, group in groups:
                tag = f" / {label}" if self.by_coin else ""
                print(f"\n  {BOLD}{setup}{tag}{RESET} (n={len(group)})")

                best = self._find_best_uniform(group, UNIFORM_GRIDS)
                if best is None:
                    continue
                best_exp, (tp_t, sl_t), best_wr = best
                best_net = best_exp - FEE_TAKER_RT

                avg_mfe = group["mfe"].mean()
                avg_mae = group["mae"].mean()
                ratio = avg_mfe / (avg_mae + 1e-9)

                print(
                    f"    MFE/MAE Ratio:     {ratio:.2f} {'✅' if ratio > 1.2 else '❌'} (need >1.2 for directional edge)"
                )
                print(f"    Best Uniform:      {tp_t:.2f}/{sl_t:.2f}% → Exp {best_exp:+.4f}%")
                print(f"    Best Net Taker:    {best_net:+.4f}% {'✅' if best_net > 0 else '❌'}")

                if best_net <= 0:
                    print(f"    {RED}VERDICT: ENTRY FAILURE{RESET}")
                    print(f"    No TP/SL configuration can produce positive expectancy.")
                    print(f"    The entry signal does not predict direction reliably enough.")
                    print(f"    Fix: tighten entry filters, improve scenario conditions,")
                    print(f"    or accept that this setup type has no edge on this coin.")
                else:
                    # Entry has edge — check AMT targets vs best uniform
                    real_w = (group["real_outcome"] == "WIN").sum()
                    real_l = (group["real_outcome"] == "LOSS").sum()
                    real_d = real_w + real_l
                    if real_d > 0:
                        real_wr = real_w / real_d * 100
                        real_avg_tp = group["tp_pct"].mean()
                        real_avg_sl = group["sl_pct"].mean()
                        real_exp = (real_wr / 100) * real_avg_tp - ((100 - real_wr) / 100) * real_avg_sl
                        delta = real_exp - best_exp
                        if delta >= -0.05:
                            print(f"    AMT Targets:       Exp {real_exp:+.4f}% (within 0.05% of best)")
                            print(f"    {GREEN}VERDICT: TARGETS OK ✅{RESET}")
                        else:
                            print(f"    AMT Targets:       Exp {real_exp:+.4f}% ({delta:+.2f}% vs best uniform)")
                            print(f"    {YELLOW}VERDICT: TARGET OPTIMIZATION NEEDED ⚠️{RESET}")
                            print(f"    AMT targets underperform the best uniform. Adjust formula.")
        # ── [4] DECISION TRACE AUDIT (SetupEngine Gates) ──
        if traces is not None and not traces.empty:
            print(f"\n{BOLD}[4] DECISION TRACE AUDIT (SetupEngine Gates){RESET}")
            print(f"{'Gate':<25} {'Reason':<40} {'Count':<6}")
            print("-" * 75)

            try:
                trace_counts = traces.groupby(["gate", "reason"]).size().reset_index(name="count")
                trace_counts = trace_counts.sort_values("count", ascending=False)
                for _, row in trace_counts.iterrows():
                    print(f"{row['gate']:<25} {row['reason']:<40} {row['count']:<6}")
            except KeyError as e:
                available = [c for c in traces.columns if c not in ("id",)]
                print(f"{YELLOW}⚠️ Column {e} not found in decision_traces. Available: {available}{RESET}")

        # ── [5] REAL STRATEGY PERFORMANCE (Dynamic AMT Targets) ──
        suffix = " (Per Coin)" if self.by_coin else ""
        print(f"\n{BOLD}[5] REAL STRATEGY PERFORMANCE (Dynamic AMT Targets){suffix}{RESET}")
        print(f"  Reference only — conclusion in [3] above determines if targets are the problem.")
        if self.by_coin:
            print(
                f"{'Setup Type':<20} {'Coin':<26} {'n':<6} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Avg TP%':<9} {'Avg SL%':<9} {'Exp%':<10} {'Net Taker'}"
            )
            print("-" * 130)
        else:
            print(
                f"{'Setup Type':<20} {'n':<6} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Avg TP%':<9} {'Avg SL%':<9} {'Exp%':<10} {'Net Taker'}"
            )
            print("-" * 105)

        for setup, s_group in df.groupby("setup_type"):
            groups = [(setup, s_group)] if not self.by_coin else [(c, g) for c, g in s_group.groupby("symbol")]
            for label, group in groups:
                w = (group["real_outcome"] == "WIN").sum()
                losses = (group["real_outcome"] == "LOSS").sum()
                to = (group["real_outcome"] == "TIMEOUT").sum()
                d = w + losses
                wr = (w / d * 100) if d > 0 else 0

                avg_tp = group["tp_pct"].mean()
                avg_sl = group["sl_pct"].mean()
                expectancy = (wr / 100) * avg_tp - ((100 - wr) / 100) * avg_sl if d > 0 else 0
                net_taker = expectancy - FEE_TAKER_RT
                nc = GREEN if net_taker > 0 else RED

                if self.by_coin:
                    print(
                        f"{setup:<20} {label:<26} {len(group):<6} {w:<5} {losses:<5} {to:<5} {wr:>6.1f}%  {avg_tp:>7.3f}%  {avg_sl:>7.3f}%  {expectancy:>+8.4f}%  {nc}{net_taker:>+8.4f}%{RESET}"
                    )
                else:
                    print(
                        f"{setup:<20} {len(group):<6} {w:<5} {losses:<5} {to:<5} {wr:>6.1f}%  {avg_tp:>7.3f}%  {avg_sl:>7.3f}%  {expectancy:>+8.4f}%  {nc}{net_taker:>+8.4f}%{RESET}"
                    )

        # ── [6] ALPHA FUSION & CONVICTION AUDIT ──
        if "is_composite" in df.columns:
            suffix = " (Per Coin)" if self.by_coin else ""
            print(f"\n{BOLD}[6] ALPHA FUSION & CONVICTION AUDIT (Arbitrator Efficacy){suffix}{RESET}")
            if self.by_coin:
                print(
                    f"{'Coin':<26} {'Class':<25} {'n':<6} {'W':<5} {'L':<5} {'WR%':<8} {'Avg Conviction':<15} {'Verdict'}"
                )
                print("-" * 110)
            else:
                print(f"{'Signal Class':<20} {'n':<6} {'W':<5} {'L':<5} {'WR%':<8} {'Avg Conviction':<15} {'Verdict'}")
                print("-" * 75)

            if self.by_coin:
                for coin, cg in df.groupby("symbol"):
                    for is_comp, group in cg.groupby("is_composite"):
                        label = f"{YELLOW}COMPOSITE (Fused){RESET}" if is_comp else "SOLO (Single)"
                        w = (group["real_outcome"] == "WIN").sum()
                        losses = (group["real_outcome"] == "LOSS").sum()
                        d = w + losses
                        wr = (w / d * 100) if d > 0 else 0
                        avg_conv = group["conviction"].mean()
                        v_color = GREEN if wr > 55 else (YELLOW if wr > 50 else RED)
                        print(
                            f"{coin:<26} {label:<30} {len(group):<6} {w:<5} {losses:<5} {v_color}{wr:>6.1f}%{RESET}   {avg_conv:>8.1f}        {'✅ ALPHA FUSION' if is_comp and wr > 50 else '-'}"
                        )
            else:
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

        # ── [7] OVERALL EDGE SUMMARY ──
        print(f"\n{BOLD}[7] OVERALL EDGE SUMMARY{RESET}")
        print("-" * 70)

        if "real_outcome" in df.columns:
            total_wins = (df["real_outcome"] == "WIN").sum()
            total_losses = (df["real_outcome"] == "LOSS").sum()
            total_timeouts = (df["real_outcome"] == "TIMEOUT").sum()
            total_decided = total_wins + total_losses

            if total_decided > 0:
                overall_wr = total_wins / total_decided * 100
                gross_expectancy = (overall_wr / 100) * df["tp_pct"].mean() - ((100 - overall_wr) / 100) * df[
                    "sl_pct"
                ].mean()
                net_taker = gross_expectancy - FEE_TAKER_RT
                net_maker = gross_expectancy - FEE_MAKER_RT
                coins_n = df["symbol"].nunique() if "symbol" in df.columns else 1

                # Determine root cause verdict from [3]
                all_entry_fail = True
                all_target_ok = True
                for setup, s_group in df.groupby("setup_type"):
                    groups = [(setup, s_group)] if not self.by_coin else [(c, g) for c, g in s_group.groupby("symbol")]
                    for label, group in groups:
                        best = self._find_best_uniform(group, UNIFORM_GRIDS)
                        if best is None:
                            continue
                        best_exp, _, _ = best
                        if best_exp - FEE_TAKER_RT > 0:
                            all_entry_fail = False
                        # Also check real targets vs best
                        real_w = (group["real_outcome"] == "WIN").sum()
                        real_l = (group["real_outcome"] == "LOSS").sum()
                        real_d = real_w + real_l
                        if real_d > 0:
                            real_wr = real_w / real_d * 100
                            real_exp = (real_wr / 100) * group["tp_pct"].mean() - ((100 - real_wr) / 100) * group[
                                "sl_pct"
                            ].mean()
                            if real_exp < best_exp - 0.05:
                                all_target_ok = False

                print(f"Total Signals:        {len(df)} ({coins_n} coins)")
                print(f"Decided (W+L):        {total_decided} (Timeouts: {total_timeouts})")
                print(f"Overall Win Rate:     {overall_wr:.1f}%")
                print(f"")
                print(f"{BOLD}Gross Expectancy:     {gross_expectancy:+.4f}%{RESET}")
                print(f"Net (Taker 0.12%):    {net_taker:+.4f}% {'✅' if net_taker > 0 else '❌'}")
                print(f"Net (Maker 0.08%):    {net_maker:+.4f}% {'✅' if net_maker > 0 else '❌'}")
                print(f"")

                if all_entry_fail:
                    print(f"{RED}❌ ROOT CAUSE: ENTRY FAILURE{RESET}")
                    print(f"{RED}   No TP/SL configuration across any setup produces positive expectancy.")
                    print(f"{RED}   The entry signal does not predict direction. Rework entry logic.{RESET}")
                elif not all_target_ok:
                    print(f"{YELLOW}⚠️  ROOT CAUSE: TARGET FAILURE{RESET}")
                    print(f"{YELLOW}   Entry has potential but AMT targets underperform best uniform.{RESET}")
                    print(f"{YELLOW}   Adjust target formula (see Section [3] for details).{RESET}")
                else:
                    if net_taker > 0:
                        print(f"{GREEN}✅ EDGE CONFIRMED: Both entry and targets are sound.{RESET}")
                    else:
                        print(f"{YELLOW}⚠️  EDGE MARGINAL: Entry is viable but costs exceed expectancy.{RESET}")

            # ── Per-Coin Summary (when --by-coin) ──
            if self.by_coin and "symbol" in df.columns:
                print(f"\n{BOLD}Per-Coin Summary{RESET}")
                print(
                    f"{'Coin':<26} {'n':<6} {'W':<5} {'L':<5} {'TO':<5} {'WR%':<8} {'Exp%':<10} {'Net Taker':<10} {'Verdict'}"
                )
                print("-" * 105)
                for coin, cg in df.groupby("symbol"):
                    cw = (cg["real_outcome"] == "WIN").sum()
                    cl = (cg["real_outcome"] == "LOSS").sum()
                    cto = (cg["real_outcome"] == "TIMEOUT").sum()
                    cd = cw + cl
                    if cd == 0:
                        continue
                    cwr = cw / cd * 100
                    ctp = cg["tp_pct"].mean()
                    csl = cg["sl_pct"].mean()
                    cexp = (cwr / 100) * ctp - ((100 - cwr) / 100) * csl
                    cnt = cexp - FEE_TAKER_RT
                    best = self._find_best_uniform(cg, UNIFORM_GRIDS)
                    if best is None:
                        verdict = f"{RED}NO DATA{RESET}"
                    else:
                        best_exp, _, _ = best
                        if best_exp - FEE_TAKER_RT <= 0:
                            verdict = f"{RED}ENTRY FAIL{RESET}"
                        elif cnt <= 0:
                            verdict = f"{YELLOW}TARGET FAIL{RESET}"
                        else:
                            verdict = f"{GREEN}EDGE ✅{RESET}"
                    nc = GREEN if cnt > 0 else RED
                    print(
                        f"{coin:<26} {len(cg):<6} {cw:<5} {cl:<5} {cto:<5} {cwr:>5.1f}%  {cexp:>+8.4f}%  {nc}{cnt:>+8.4f}%{RESET}  {verdict}"
                    )

        print(header("AUDIT COMPLETE"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--window", type=int, default=14400, help="Analysis window in seconds (default: 4h)")
    parser.add_argument("--by-coin", action="store_true", help="Group results by coin within each setup")
    parser.add_argument("--coin", type=str, default=None, help="Filter to specific coin/symbol (e.g. BTC/USDT:USDT)")
    args = parser.parse_args()

    try:
        auditor = EdgeAuditor(args.db, by_coin=args.by_coin, coin_filter=args.coin)
        auditor.analyze(window_seconds=args.window)
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")


if __name__ == "__main__":
    main()
