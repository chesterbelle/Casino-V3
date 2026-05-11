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
TP_PCT = 0.3
SL_PCT = 0.3

# Dynamic window per setup type
SETUP_WINDOWS = {
    "reversion": 600,
    "rotation": 900,
    "continuation": 1800,
}
DEFAULT_WINDOW = 900

# Exact Day 1 Timestamps (Start, End)
CONDITIONS = {
    "LTC RANGE": [(1706745600, 1706832000), (1714521600, 1714608000), (1722470400, 1722556800)],
    "LTC BEAR ": [(1711929600, 1712016000), (1727740800, 1727827200), (1738368000, 1738454400)],
    "LTC BULL ": [(1709251200, 1709337600), (1733011200, 1733097600), (1746057600, 1746144000)],
    "DOGE RANGE": [(1706745600, 1706832000), (1717200000, 1717286400), (1730419200, 1730505600)],
    "DOGE BEAR ": [(1711929600, 1712016000), (1725148800, 1725235200), (1738368000, 1738454400)],
    "DOGE BULL ": [(1709251200, 1709337600), (1735689600, 1735776000), (1746057600, 1746144000)],
}


def load_data():
    conn = sqlite3.connect(DB_PATH)
    signals = pd.read_sql(
        "SELECT timestamp, symbol, side, price, setup_type, metadata FROM signals ORDER BY timestamp", conn
    )
    samples = pd.read_sql("SELECT timestamp, symbol, price FROM price_samples ORDER BY timestamp", conn)
    conn.close()
    return signals, samples


def analyze_condition(cond_signals: pd.DataFrame, samples: pd.DataFrame) -> dict:
    """Vectorized MFE/MAE analysis for a set of signals using dynamic windows and real targets."""
    if cond_signals.empty:
        return None

    import json as _json

    results = []

    for _, sig in cond_signals.iterrows():
        ts = sig["timestamp"]
        sym = sig["symbol"]
        side = sig["side"]
        entry = sig["price"]
        setup_type = sig.get("setup_type", "unknown")

        # Dynamic window based on setup type
        win = SETUP_WINDOWS.get(setup_type, DEFAULT_WINDOW)

        # Get price samples in the dynamic window for this symbol
        sym_samples = samples[
            (samples["symbol"] == sym) & (samples["timestamp"] >= ts) & (samples["timestamp"] <= ts + win)
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

        # Real target outcome (dynamic TP/SL from metadata)
        real_outcome = "TIMEOUT"
        tp_pct = 0.0
        sl_pct = 0.0
        if sig.get("metadata"):
            try:
                meta = _json.loads(sig["metadata"])
                tp_price = meta.get("tp_price", 0.0)
                sl_price = meta.get("sl_price", 0.0)
                if tp_price > 0 and sl_price > 0:
                    if side == "LONG":
                        tp_pct = (tp_price - entry) / entry * 100
                        sl_pct = (entry - sl_price) / entry * 100
                    else:
                        tp_pct = (entry - tp_price) / entry * 100
                        sl_pct = (sl_price - entry) / entry * 100

                    for p in sym_samples:
                        if side == "LONG":
                            if p >= tp_price:
                                real_outcome = "WIN"
                                break
                            if p <= sl_price:
                                real_outcome = "LOSS"
                                break
                        else:
                            if p <= tp_price:
                                real_outcome = "WIN"
                                break
                            if p >= sl_price:
                                real_outcome = "LOSS"
                                break
            except Exception:
                pass

        # Uniform 0.3/0.3 first touch for reference
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
                "setup_type": setup_type,
                "real_outcome": real_outcome,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
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

    # Real strategy metrics
    real_w = (df["real_outcome"] == "WIN").sum()
    real_l = (df["real_outcome"] == "LOSS").sum()
    real_d = real_w + real_l
    real_wr = (real_w / real_d * 100) if real_d > 0 else 0
    avg_tp = df["tp_pct"].mean()
    avg_sl = df["sl_pct"].mean()
    real_exp = (real_wr / 100) * avg_tp - ((100 - real_wr) / 100) * avg_sl if real_d > 0 else 0

    if n < 20:
        verdict = "LOW_N"
    elif real_exp > 0.36 and real_wr > 55:
        verdict = "CERTIFIED"
    elif real_exp > 0.12 and real_wr > 50:
        verdict = "WATCH"
    elif real_exp > 0:
        verdict = "FRAGILE"
    else:
        verdict = "FAILED"

    return {
        "n": n,
        "wr": wr,
        "mfe": mfe,
        "mae": mae,
        "ratio": ratio,
        "real_wr": real_wr,
        "avg_tp": avg_tp,
        "avg_sl": avg_sl,
        "real_exp": real_exp,
        "verdict": verdict,
    }


def main():
    print("Loading data from historian.db...")
    signals, samples = load_data()
    print(f"  Signals: {len(signals)}, Price Samples: {len(samples)}")

    print()
    print("PER-CONDITION EDGE BREAKDOWN (Dynamic Windows + Real Targets)")
    print(f"{'Condition':25s} {'n':>4}  {'RealWR%':>7}  {'AvgTP%':>7}  {'AvgSL%':>7}  {'RealExp%':>9}  {'Verdict':>12}")
    print("-" * 90)

    for cond_name, ranges in CONDITIONS.items():
        # Combine multiple ranges for this condition
        cond_signals = pd.concat(
            [signals[(signals["timestamp"] >= start) & (signals["timestamp"] < end)] for start, end in ranges]
        )

        result = analyze_condition(cond_signals, samples)

        if result is None:
            print(f"{cond_name:25s}    0  — no signals or price samples")
            continue

        print(
            f"{cond_name:25s} {result['n']:>4}  {result['real_wr']:>6.1f}%  "
            f"{result['avg_tp']:>6.3f}%  {result['avg_sl']:>6.3f}%  "
            f"{result['real_exp']:>+8.4f}%  {result['verdict']:>12}"
        )

    # Also show uniform 0.3/0.3 for reference
    print()
    print("REFERENCE: Uniform 0.3%/0.3% First Touch")
    print(f"{'Condition':25s} {'n':>4}  {'WR%':>6}  {'MFE%':>7}  {'MAE%':>7}  {'Ratio':>6}")
    print("-" * 65)

    for cond_name, ranges in CONDITIONS.items():
        # Combine multiple ranges for this condition
        cond_signals = pd.concat(
            [signals[(signals["timestamp"] >= start) & (signals["timestamp"] < end)] for start, end in ranges]
        )

        result = analyze_condition(cond_signals, samples)

        if result is None:
            print(f"{cond_name:25s}    0  — no signals or price samples")
            continue

        print(
            f"{cond_name:25s} {result['n']:>4}  {result['wr']:>5.1f}%  "
            f"{result['mfe']:>6.3f}%  {result['mae']:>6.3f}%  "
            f"{result['ratio']:>6.2f}"
        )


if __name__ == "__main__":
    main()
