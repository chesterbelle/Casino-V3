#!/usr/bin/env python3
"""
Per-Condition Edge Audit — Vectorized with pandas.
Analyzes MFE/MAE/WR per market regime (Range, Bear, Bull).

Uses pandas merge_asof for fast nearest-timestamp lookups instead of
per-signal SQL queries which are O(n*m) and time out on large datasets.
"""

import sqlite3
import statistics

import numpy as np
import pandas as pd

DB_PATH = "data/historian.db"
WINDOW_SECONDS = 900
TP_PCT = 0.3
SL_PCT = 0.3

CONDITIONS = {
    # Range: 2024-08-14, 2024-08-15, 2024-08-16
    "RANGE  (Aug 14-16)": (1723593600, 1723852800),
    # Bear:  2024-09-05, 2024-09-06, 2024-09-07
    "BEAR   (Sep 05-07)": (1725494400, 1725753600),
    # Bull:  2024-10-13, 2024-10-14, 2024-10-15
    "BULL   (Oct 13-15)": (1728777600, 1729036800),
}


def load_data():
    conn = sqlite3.connect(DB_PATH)
    signals = pd.read_sql("SELECT timestamp, symbol, side, price FROM signals ORDER BY timestamp", conn)
    samples = pd.read_sql("SELECT timestamp, symbol, price FROM price_samples ORDER BY timestamp", conn)
    conn.close()
    return signals, samples


def analyze_condition(cond_signals: pd.DataFrame, samples: pd.DataFrame) -> dict:
    """Vectorized MFE/MAE analysis for a set of signals."""
    if cond_signals.empty:
        return None

    results = []

    for _, sig in cond_signals.iterrows():
        ts = sig["timestamp"]
        sym = sig["symbol"]
        side = sig["side"]
        entry = sig["price"]

        # Get price samples in the 900s window for this symbol
        sym_samples = samples[
            (samples["symbol"] == sym) & (samples["timestamp"] >= ts) & (samples["timestamp"] <= ts + WINDOW_SECONDS)
        ]["price"].values

        if len(sym_samples) == 0:
            continue

        # Vectorized move calculation
        moves = (sym_samples - entry) / entry * 100
        if side == "SHORT":
            moves = -moves

        max_f = float(np.max(moves)) if len(moves) > 0 else 0.0
        neg_moves = moves[moves < 0]
        max_a = float(np.max(np.abs(neg_moves))) if len(neg_moves) > 0 else 0.0

        # First touch logic
        hit_tp = hit_sl = False
        for m in moves:
            if not hit_tp and m >= TP_PCT:
                hit_tp = True
                break
            if not hit_sl and m <= -SL_PCT:
                hit_sl = True
                break

        results.append(
            {
                "mfe": max_f,
                "mae": max_a,
                "win": 1 if hit_tp and not hit_sl else 0,
                "loss": 1 if hit_sl else 0,
            }
        )

    if not results:
        return None

    df = pd.DataFrame(results)
    n = len(df)
    mfe = df["mfe"].mean()
    mae = df["mae"].mean()
    ratio = mfe / (mae + 1e-9)
    resolved = df["win"].sum() + df["loss"].sum()
    wr = df["win"].sum() / resolved * 100 if resolved > 0 else 0

    if n < 20:
        verdict = "LOW_N"
    elif ratio > 1.2 and wr > 55:
        verdict = "CERTIFIED"
    elif ratio > 1.0 and wr > 50:
        verdict = "WATCH"
    else:
        verdict = "FAILED"

    return {"n": n, "wr": wr, "mfe": mfe, "mae": mae, "ratio": ratio, "verdict": verdict}


def main():
    print("Loading data from historian.db...")
    signals, samples = load_data()
    print(f"  Signals: {len(signals)}, Price Samples: {len(samples)}")

    print()
    print("PER-CONDITION EDGE BREAKDOWN (0.3%/0.3%)")
    print(f"{'Condition':25s} {'n':>4}  {'WR%':>6}  {'MFE%':>7}  {'MAE%':>7}  {'Ratio':>6}  {'Verdict':>12}")
    print("-" * 80)

    for cond_name, (ts_start, ts_end) in CONDITIONS.items():
        cond_signals = signals[(signals["timestamp"] >= ts_start) & (signals["timestamp"] < ts_end)]

        result = analyze_condition(cond_signals, samples)

        if result is None:
            print(f"{cond_name:25s}    0  — no signals or price samples")
            continue

        print(
            f"{cond_name:25s} {result['n']:>4}  {result['wr']:>5.1f}%  "
            f"{result['mfe']:>6.3f}%  {result['mae']:>6.3f}%  "
            f"{result['ratio']:>6.2f}  {result['verdict']:>12}"
        )


if __name__ == "__main__":
    main()
