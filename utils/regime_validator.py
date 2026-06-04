#!/usr/bin/env python3
"""
=============================================================
🎯 REGIME VALIDATOR — Phase 900: Regime Classification Audit
=============================================================

Validates the MarketRegimeSensor's accuracy by comparing signal
entry regimes against ground truth (price displacement).
Cross-references signals to detect false admissions (counter-trend entries).

Metrics:
  - Ground Truth Regime Distribution (% time in UP/BALANCE/DOWN)
  - Signal Performance by Regime (MFE/MAE per GT class)
  - False Admissions (counter-trend entries and their cost)
  - Sensor Accuracy (confusion matrix vs GT, when --emulate-sensor)

Usage:
    python utils/regime_validator.py [--db data/historian.db] [--by-coin]
    python utils/regime_validator.py --coin DOGE/USDT:USDT
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from trajectory_core import load_data

# ANSI Colors
CYAN = "\033[96m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Ground truth thresholds — calibrated to actual market regime detection
# These define what WE consider a real TREND vs BALANCE, independent of the sensor.
# Old CB thresholds (0.8%/60c, 1.0%/120c) were too aggressive for crypto —
# they classified normal volatility as TREND, producing false positives.
FAST_WINDOW = 10
CRASH_THRESHOLD = 0.04  # 4% in 10 candles = crash/rally
TREND_THRESHOLD = 0.02  # 2% in 10 candles = strong directional move
SLOW_WINDOW = 60
SLOW_TREND_THRESHOLD = 0.015  # 1.5% in 60 candles = real slow trend (was 0.8%)
VERY_SLOW_WINDOW = 120
VERY_SLOW_TREND_THRESHOLD = 0.025  # 2.5% in 120 candles = very slow trend (was 1.0%)
RESET_THRESHOLD = 0.005  # 0.5% reversal to reset trend state

FEE_TAKER = 0.12
ANALYSIS_WINDOW = 14400  # 4 hours for MFE/MAE


def header(msg):
    line = "=" * 70
    return f"\n{BOLD}{CYAN}{line}\n  {msg}\n{line}{RESET}"


_gt_active = False
_gt_direction = "NEUTRAL"
_gt_reference = 0.0


def classify_regime(prices: np.ndarray, i: int):
    """
    Classify regime at index i using multi-window price displacement with persistence.
    Priority: crash > trend > slow_drift > very_slow_drift > balance.
    Once triggered, stays active until price reverses beyond RESET_THRESHOLD.
    """
    global _gt_active, _gt_direction, _gt_reference

    current = prices[i]

    # Check RESET: if active, has price reversed enough?
    if _gt_active and _gt_reference > 0:
        if _gt_direction == "UP":
            pullback = (_gt_reference - current) / _gt_reference
            if pullback > RESET_THRESHOLD:
                _gt_active = False
                _gt_direction = "NEUTRAL"
        elif _gt_direction == "DOWN":
            recovery = (current - _gt_reference) / _gt_reference
            if recovery > RESET_THRESHOLD:
                _gt_active = False
                _gt_direction = "NEUTRAL"

    # Fast window (10 candles)
    if i >= FAST_WINDOW - 1:
        displacement = (current - prices[i - FAST_WINDOW + 1]) / prices[i - FAST_WINDOW + 1]
        abs_disp = abs(displacement)
        direction = "UP" if displacement > 0 else "DOWN"

        if abs_disp >= CRASH_THRESHOLD:
            _gt_active = True
            _gt_direction = direction
            _gt_reference = current
            return f"TREND_{direction}", "crash_rally"
        if abs_disp >= TREND_THRESHOLD:
            _gt_active = True
            _gt_direction = direction
            _gt_reference = current
            return f"TREND_{direction}", "trend"

    # Slow window (60 candles)
    if i >= SLOW_WINDOW - 1:
        displacement = (current - prices[i - SLOW_WINDOW + 1]) / prices[i - SLOW_WINDOW + 1]
        if abs(displacement) >= SLOW_TREND_THRESHOLD:
            direction = "UP" if displacement > 0 else "DOWN"
            _gt_active = True
            _gt_direction = direction
            _gt_reference = current
            return f"TREND_{direction}", "slow_drift"

    # Very slow window (120 candles)
    if i >= VERY_SLOW_WINDOW - 1:
        displacement = (current - prices[i - VERY_SLOW_WINDOW + 1]) / prices[i - VERY_SLOW_WINDOW + 1]
        if abs(displacement) >= VERY_SLOW_TREND_THRESHOLD:
            direction = "UP" if displacement > 0 else "DOWN"
            _gt_active = True
            _gt_direction = direction
            _gt_reference = current
            return f"TREND_{direction}", "very_slow_drift"

    # Persistence: if still active, maintain the signal
    if _gt_active:
        return f"TREND_{_gt_direction}", f"{_gt_direction.lower()}_persistent"

    return "BALANCE", "stable"


class RegimeValidator:
    def __init__(self, db_path: str, by_coin=False, coin_filter=None):
        self.db_path = db_path
        self.by_coin = by_coin
        self.coin_filter = coin_filter
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def load_data(self):
        """Load signals, price_samples, and traces via trajectory_core, plus candles."""
        conn = sqlite3.connect(self.db_path)

        candles = pd.read_sql_query(
            "SELECT timestamp, symbol, close FROM price_candles ORDER BY timestamp, symbol",
            conn,
        )
        conn.close()

        signals, price_samples, traces = load_data(self.db_path)

        # If price_candles is empty (audit runs don't populate it),
        # generate them from price_samples
        if candles.empty and not price_samples.empty:
            print(f"  ⚠️  price_candles empty — generating from {len(price_samples):,} price_samples")
            candles = self._generate_candles_from_samples(price_samples)
        elif candles.empty:
            raise ValueError("No price_candles or price_samples found in database")

        if self.coin_filter:
            before = len(signals)
            signals = signals[signals["symbol"] == self.coin_filter]
            filtered_out = before - len(signals)
            if filtered_out > 0:
                print(f"  🪙 Filtered to {self.coin_filter}: {len(signals)}/{before} signals")
            else:
                print(f"  🪙 Coin filter '{self.coin_filter}' — no signals, but candles may exist")

        return candles, signals, price_samples, traces

    def compute_ground_truth(self, candles: pd.DataFrame) -> pd.DataFrame:
        """Add ground truth regime to each candle."""
        results = []

        for symbol, group in candles.groupby("symbol"):
            # Reset persistence state for each symbol
            global _gt_active, _gt_direction, _gt_reference
            _gt_active = False
            _gt_direction = "NEUTRAL"
            _gt_reference = 0.0

            prices = group["close"].values
            regimes = []
            reasons = []

            for i in range(len(prices)):
                regime, reason = classify_regime(prices, i)
                regimes.append(regime)
                reasons.append(reason)

            df = group.copy()
            df["gt_regime"] = regimes
            df["gt_reason"] = reasons
            results.append(df)

        return pd.concat(results, ignore_index=True)

    def _generate_candles_from_samples(self, price_samples: pd.DataFrame) -> pd.DataFrame:
        """Generate 1m candles from price_samples (timestamp, price rows)."""
        samples = price_samples.copy()
        samples["timestamp"] = samples["timestamp"].astype(float)
        samples["price"] = samples["price"].astype(float)
        samples["minute"] = (samples["timestamp"] // 60) * 60

        candles = []
        for (symbol, minute), group in samples.groupby(["symbol", "minute"]):
            prices = group["price"].values
            candles.append(
                {
                    "timestamp": minute,
                    "symbol": symbol,
                    "close": prices[-1],
                }
            )
        df = pd.DataFrame(candles).sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        print(f"  📊 Generated {len(df):,} candles for {df['symbol'].nunique()} symbols")
        return df

    def cross_reference_signals(self, signals: pd.DataFrame, gt_candles: pd.DataFrame) -> pd.DataFrame:
        """For each signal, find the GT regime and sensor regime at entry time."""
        signal_regimes = []

        for _, sig in signals.iterrows():
            symbol = sig["symbol"]
            ts = sig["timestamp"]

            mask = gt_candles["symbol"] == symbol
            symbol_candles = gt_candles[mask]

            if symbol_candles.empty:
                continue

            idx = (symbol_candles["timestamp"] - ts).abs().idxmin()
            gt_regime = symbol_candles.loc[idx, "gt_regime"]
            gt_reason = symbol_candles.loc[idx, "gt_reason"]

            # Sensor regime from signal metadata (populated by core.py _process_signal)
            sensor_regime = sig.get("sensor_regime")
            sensor_direction = sig.get("sensor_direction")
            sensor_confidence = sig.get("sensor_confidence")

            signal_regimes.append(
                {
                    "signal_id": sig["id"],
                    "symbol": symbol,
                    "timestamp": ts,
                    "side": sig["side"],
                    "price": sig["price"],
                    "setup_type": sig.get("setup_type", "unknown"),
                    "gt_regime": gt_regime,
                    "gt_reason": gt_reason,
                    "sensor_regime": sensor_regime,
                    "sensor_direction": sensor_direction,
                    "sensor_confidence": sensor_confidence,
                }
            )

        result = pd.DataFrame(signal_regimes)
        if result.empty:
            print(f"  {YELLOW}⚠️ No signals could be cross-referenced with ground truth.{RESET}")
        return result

    def compute_signal_outcomes(self, signal_ref: pd.DataFrame, price_samples: pd.DataFrame) -> pd.DataFrame:
        """Compute MFE/MAE and win/loss for each signal."""
        BARE_MINIMUM_SAMPLES = 2
        results = []

        for _, sig in signal_ref.iterrows():
            symbol = sig["symbol"]
            ts = sig["timestamp"]
            entry_price = sig["price"]
            side = sig["side"]

            if entry_price <= 0:
                continue

            mask = (
                (price_samples["symbol"] == symbol)
                & (price_samples["timestamp"] >= ts)
                & (price_samples["timestamp"] <= ts + ANALYSIS_WINDOW)
            )
            samples = price_samples[mask]

            if len(samples) < BARE_MINIMUM_SAMPLES:
                continue

            prices = samples["price"].values
            highest = float(np.max(prices))
            lowest = float(np.min(prices))

            if side == "LONG":
                mfe = (highest - entry_price) / entry_price * 100
                mae = (entry_price - lowest) / entry_price * 100
            else:
                mfe = (entry_price - lowest) / entry_price * 100
                mae = (highest - entry_price) / entry_price * 100

            results.append(
                {
                    "signal_id": sig["signal_id"],
                    "symbol": symbol,
                    "side": sig["side"],
                    "setup_type": sig["setup_type"],
                    "gt_regime": sig["gt_regime"],
                    "sensor_regime": sig.get("sensor_regime"),
                    "mfe": mfe,
                    "mae": mae,
                    "ratio": mfe / (mae + 1e-9),
                }
            )

        return pd.DataFrame(results)

    def _print_confusion_matrix(self, df):
        """Print confusion matrix: sensor_regime vs gt_regime."""
        regimes = ["TREND_UP", "BALANCE", "TREND_DOWN"]

        print(f"  {'GT ↓ / Sensor →':<20}", end="")
        for r in regimes:
            print(f"{r:<15}", end="")
        print(f"{'n':<8} {'Accuracy':<10}")
        print("  " + "-" * 65)

        total_correct = 0
        total_signals = len(df)

        for gt in regimes:
            subset = df[df["gt_regime"] == gt]
            n = len(subset)
            row = [f"  {gt:<18}", n]
            row_correct = 0
            for sr in regimes:
                c = len(subset[subset["sensor_regime"] == sr])
                row.append(c)
                if sr == gt:
                    row_correct = c
            acc = row_correct / n if n > 0 else 0
            total_correct += row_correct
            color = GREEN if acc > 0.8 else (YELLOW if acc > 0.5 else RED)
            c_str = f"{color}{acc*100:>5.1f}%{RESET}"
            print(f"  {gt:<18} {row[1]:<8} {row[2]:<15} {row[3]:<15} {row[4]:<15} {c_str}")

        overall_acc = total_correct / total_signals if total_signals > 0 else 0
        color = GREEN if overall_acc > 0.8 else (YELLOW if overall_acc > 0.5 else RED)
        print(f"\n  Overall Accuracy: {color}{overall_acc*100:.1f}%{RESET} " f"({total_correct}/{total_signals})")

        # Most common misclassifications
        print(f"\n  {BOLD}Top Misclassifications:{RESET}")
        for gt in regimes:
            for sr in regimes:
                if gt == sr:
                    continue
                subset = df[df["gt_regime"] == gt]
                n_wrong = len(subset[subset["sensor_regime"] == sr])
                if n_wrong > 0:
                    total_gt = len(subset)
                    pct = n_wrong / total_gt * 100
                    print(f"    Sensor said {sr:<12} but was {gt:<12} → {n_wrong:>4} ({pct:>4.1f}%)")

    def print_report(self, gt_candles, signal_ref, outcomes):
        """Print the full validator report."""

        # ── [1] REGIME DISTRIBUTION ──────────────────────────────────
        print(header("REGIME DISTRIBUTION (Ground Truth — Price Displacement)"))
        print(
            f"  Windows: {FAST_WINDOW}c/{TREND_THRESHOLD*100:.0f}% trend, "
            f"{FAST_WINDOW}c/{CRASH_THRESHOLD*100:.0f}% crash, "
            f"{SLOW_WINDOW}c/{SLOW_TREND_THRESHOLD*100:.1f}% slow, "
            f"{VERY_SLOW_WINDOW}c/{VERY_SLOW_TREND_THRESHOLD*100:.1f}% very slow"
        )

        groups = [gt_candles] if not self.by_coin else [g for _, g in gt_candles.groupby("symbol")]
        labels = ["ALL"] if not self.by_coin else [g["symbol"].iloc[0] for g in groups]

        for label, group in zip(labels, groups):
            dist = group["gt_regime"].value_counts()
            total = len(group)
            print(f"\n  {BOLD}{label}{RESET} ({total:,} candles)")
            for regime in ["TREND_UP", "BALANCE", "TREND_DOWN"]:
                n = int(dist.get(regime, 0))
                pct = n / total * 100
                c = GREEN if regime == "TREND_UP" else (YELLOW if regime == "BALANCE" else RED)
                print(f"    {c}{regime:<12}{RESET} {n:>8,} ({pct:>5.1f}%)")

        print()

        # ── [2] SENSOR ACCURACY ─────────────────────────────────────
        print(header("SENSOR ACCURACY (Sensor vs Ground Truth)"))

        has_sensor = "sensor_regime" in outcomes.columns and outcomes["sensor_regime"].notna().any()

        if not has_sensor:
            print(f"  {YELLOW}⚠️  No sensor regime data in signals.{RESET}")
            print(f"  Signals created before 2026-06-03 don't carry regime_v2 in metadata.")
            print(f"  Re-run with updated code to populate sensor_regime.")
        else:
            valid = outcomes[outcomes["sensor_regime"].notna()].copy()
            valid["sensor_regime"] = valid["sensor_regime"].replace({np.nan: None, "NEUTRAL": "BALANCE"})
            n_with_sensor = len(valid)
            print(f"\n  {n_with_sensor}/{len(outcomes)} signals have sensor regime data.")

            if self.by_coin:
                for symbol, group in valid.groupby("symbol"):
                    print(f"\n  {BOLD}{symbol}{RESET}")
                    self._print_confusion_matrix(group)
            else:
                self._print_confusion_matrix(valid)

        print()

        # ── [3] SIGNAL REGIME ANALYSIS ───────────────────────────────
        print(header("SIGNAL REGIME ANALYSIS (MFE/MAE by Ground Truth Regime)"))

        if outcomes.empty:
            print(f"  {YELLOW}⚠️ No outcome data available.{RESET}")
            return

        if self.by_coin:
            print(
                f"\n{'Setup Type':<22} {'Coin':<26} {'Regime':<12} {'n':<6} "
                f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}"
            )
            print("-" * 100)

            for (setup, symbol), group in outcomes.groupby(["setup_type", "symbol"]):
                for regime in ["TREND_UP", "BALANCE", "TREND_DOWN"]:
                    rg = group[group["gt_regime"] == regime]
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                    print(
                        f"{setup:<22} {symbol:<26} {regime:<12} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )
        else:
            print(f"\n{'Setup Type':<22} {'Regime':<12} {'n':<6} " f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}")
            print("-" * 74)

            for setup, group in outcomes.groupby("setup_type"):
                for regime in ["TREND_UP", "BALANCE", "TREND_DOWN"]:
                    rg = group[group["gt_regime"] == regime]
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                    print(
                        f"{setup:<22} {regime:<12} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )

        # ── [4] FALSE ADMISSION REPORT ────────────────────────────────
        print(header("FALSE ADMISSION REPORT (Counter-Trend Entries)"))
        print(f"  Signals entering in the WRONG direction for the current regime.\n")

        if self.by_coin:
            print(
                f"{'Coin':<26} {'Setup Type':<22} {'Admission':<20} {'n':<6} "
                f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}"
            )
            print("-" * 108)

            counter_trend_total = 0
            for (symbol, setup), group in outcomes.groupby(["symbol", "setup_type"]):
                # LONG in TREND_DOWN
                long_down = group[(group["side"] == "LONG") & (group["gt_regime"] == "TREND_DOWN")]
                # SHORT in TREND_UP
                short_up = group[(group["side"] == "SHORT") & (group["gt_regime"] == "TREND_UP")]

                for label, rg in [("LONG in DOWN", long_down), ("SHORT in UP", short_up)]:
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = RED if ratio < 0.8 else (YELLOW if ratio < 1.2 else GREEN)
                    counter_trend_total += len(rg)
                    print(
                        f"{symbol:<26} {setup:<22} {label:<20} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )

            print(f"\n  {BOLD}Total counter-trend signals: {counter_trend_total}{RESET}")

            # Track-aligned for reference
            print(f"\n{BOLD}Track-Aligned (for comparison):{RESET}")
            print(
                f"{'Coin':<26} {'Setup Type':<22} {'Admission':<20} {'n':<6} "
                f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}"
            )
            print("-" * 108)

            for (symbol, setup), group in outcomes.groupby(["symbol", "setup_type"]):
                long_up = group[(group["side"] == "LONG") & (group["gt_regime"] == "TREND_UP")]
                short_down = group[(group["side"] == "SHORT") & (group["gt_regime"] == "TREND_DOWN")]

                for label, rg in [("LONG in UP", long_up), ("SHORT in DOWN", short_down)]:
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                    print(
                        f"{symbol:<26} {setup:<22} {label:<20} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )
        else:
            print(f"{'Setup Type':<22} {'Admission':<20} {'n':<6} " f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}")
            print("-" * 82)

            counter_trend_total = 0
            for setup, group in outcomes.groupby("setup_type"):
                long_down = group[(group["side"] == "LONG") & (group["gt_regime"] == "TREND_DOWN")]
                short_up = group[(group["side"] == "SHORT") & (group["gt_regime"] == "TREND_UP")]

                for label, rg in [("LONG in DOWN", long_down), ("SHORT in UP", short_up)]:
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = RED if ratio < 0.8 else (YELLOW if ratio < 1.2 else GREEN)
                    counter_trend_total += len(rg)
                    print(
                        f"{setup:<22} {label:<20} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )

            print(f"\n  {BOLD}Total counter-trend signals: {counter_trend_total}{RESET}")

            # Track-aligned for reference
            print(f"\n{BOLD}Track-Aligned (for comparison):{RESET}")
            print(f"{'Setup Type':<22} {'Admission':<20} {'n':<6} " f"{'Avg MFE%':<10} {'Avg MAE%':<10} {'Ratio':<8}")
            print("-" * 82)

            for setup, group in outcomes.groupby("setup_type"):
                long_up = group[(group["side"] == "LONG") & (group["gt_regime"] == "TREND_UP")]
                short_down = group[(group["side"] == "SHORT") & (group["gt_regime"] == "TREND_DOWN")]

                for label, rg in [("LONG in UP", long_up), ("SHORT in DOWN", short_down)]:
                    if len(rg) == 0:
                        continue
                    avg_mfe = rg["mfe"].mean()
                    avg_mae = rg["mae"].mean()
                    ratio = avg_mfe / (avg_mae + 1e-9)
                    c = GREEN if ratio > 1.2 else (YELLOW if ratio > 1.0 else RED)
                    print(
                        f"{setup:<22} {label:<20} {len(rg):<6} "
                        f"{avg_mfe:>8.3f}% {avg_mae:>8.3f}% {c}{ratio:>6.2f}{RESET}"
                    )

        # ── [5] SIGNAL DISTRIBUTION (How signals distribute across regimes) ──
        print(header("SIGNAL DISTRIBUTION (Entry Regime Breakdown)"))
        print(f"  What percentage of signals enter in each ground truth regime.\n")

        if self.by_coin:
            print(f"{'Coin':<26} {'n':<8} {'TREND_UP':<12} {'BALANCE':<12} {'TREND_DOWN':<12}")
            print("-" * 62)
            for symbol, group in outcomes.groupby("symbol"):
                total = len(group)
                dist = group["gt_regime"].value_counts()
                up_pct = dist.get("TREND_UP", 0) / total * 100
                bal_pct = dist.get("BALANCE", 0) / total * 100
                down_pct = dist.get("TREND_DOWN", 0) / total * 100
                print(f"{symbol:<26} {total:<8} {up_pct:>6.1f}%     {bal_pct:>6.1f}%     {down_pct:>6.1f}%")
        else:
            total = len(outcomes)
            dist = outcomes["gt_regime"].value_counts()
            up_pct = dist.get("TREND_UP", 0) / total * 100
            bal_pct = dist.get("BALANCE", 0) / total * 100
            down_pct = dist.get("TREND_DOWN", 0) / total * 100
            print(f"{'Total':<26} {total:<8} {up_pct:>6.1f}%     {bal_pct:>6.1f}%     {down_pct:>6.1f}%")

        # ── [6] DIAGNOSIS ────────────────────────────────────────────
        print(header("DIAGNOSIS"))

        ct_entries = outcomes[
            ((outcomes["side"] == "LONG") & (outcomes["gt_regime"] == "TREND_DOWN"))
            | ((outcomes["side"] == "SHORT") & (outcomes["gt_regime"] == "TREND_UP"))
        ]
        n_ct = len(ct_entries)
        n_total = len(outcomes)

        if n_total == 0:
            print(f"  {YELLOW}No signals to analyze.{RESET}")
            return

        ct_pct = n_ct / n_total * 100

        if ct_entries.empty:
            print(f"  {GREEN}✅ No counter-trend admissions detected.{RESET}")
            print(f"  All {n_total} signals entered in regime-aligned or BALANCE conditions.")
        else:
            avg_ct_mfe = ct_entries["mfe"].mean()
            avg_ct_mae = ct_entries["mae"].mean()
            ct_ratio = avg_ct_mfe / (avg_ct_mae + 1e-9)

            print(f"  {RED}⚠️  {n_ct} counter-trend admissions detected ({ct_pct:.1f}% of {n_total} signals){RESET}")
            print(
                f"  Counter-trend MFE/MAE Ratio: {ct_ratio:.2f} "
                f"{'✅' if ct_ratio > 1.2 else '❌'} (entry quality in wrong direction)"
            )
            print(f"")
            print(f"  {BOLD}Root Cause:{RESET} Counter-trend signals pass the quality scorer")
            print(f"  when regime_score=0.0 is offset by high exhaustion scores.")
            print(f"  Structural fix applied (2026-06-03): regime_score==0.0 now requires A-grade.")
            print(f"  Re-run with updated code to verify reduction in false admissions.")

        # Regimes with worst MFE/MAE
        print(f"\n  {BOLD}Worst-performing regimes:{RESET}")
        worst = outcomes.groupby("gt_regime").agg(n=("mfe", "count"), avg_mfe=("mfe", "mean"), avg_mae=("mae", "mean"))
        worst["ratio"] = worst["avg_mfe"] / (worst["avg_mae"] + 1e-9)
        for regime in ["TREND_DOWN", "TREND_UP", "BALANCE"]:
            if regime in worst.index:
                r = worst.loc[regime]
                c = GREEN if r["ratio"] > 1.2 else (YELLOW if r["ratio"] > 1.0 else RED)
                print(
                    f"    {c}{regime:<12}{RESET} n={int(r['n']):<6} MFE={r['avg_mfe']:.3f}% "
                    f"MAE={r['avg_mae']:.3f}% Ratio={r['ratio']:.2f}"
                )

        print(header("VALIDATION COMPLETE"))


def main():
    parser = argparse.ArgumentParser(description="Regime Validator — Phase 900: Regime Classification Audit")
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--by-coin", action="store_true", help="Group results by coin")
    parser.add_argument("--coin", type=str, default=None, help="Filter to specific coin/symbol")
    args = parser.parse_args()

    try:
        validator = RegimeValidator(args.db, by_coin=args.by_coin, coin_filter=args.coin)
        candles, signals, price_samples, traces = validator.load_data()
        print(
            f"  📊 Loaded {len(candles):,} candles, {len(signals):,} signals, " f"{len(price_samples):,} price samples"
        )

        gt_candles = validator.compute_ground_truth(candles)
        print(f"  📈 Ground truth computed for {gt_candles['symbol'].nunique()} symbols")

        signal_ref = validator.cross_reference_signals(signals, gt_candles)
        if not signal_ref.empty:
            print(f"  🔗 Cross-referenced {len(signal_ref)}/{len(signals)} signals with ground truth")

        outcomes = validator.compute_signal_outcomes(signal_ref, price_samples)
        if not outcomes.empty:
            print(f"  📉 Computed outcomes for {len(outcomes)} signals")

        validator.print_report(gt_candles, signal_ref, outcomes)

    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
