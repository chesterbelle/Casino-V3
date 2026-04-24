#!/usr/bin/env python3
"""
Guardian Efficacy Audit — Analyzes decision trace data per market condition.

Answers:
1. Rejection rate per guardian per condition
2. Signal quality (WR) of signals that passed all guardians
3. Whether each guardian discriminates correctly between conditions

Usage:
    python utils/analysis/guardian_efficacy_audit.py
"""

import sqlite3
import statistics

DB_PATH = "data/historian.db"
WINDOW_SECONDS = 900
TP_PCT = 0.3
SL_PCT = 0.3

# Timestamp ranges per condition
CONDITIONS = {
    "RANGE       (2026-04-12)": (1744416000, 1744502400),
    "BEAR NORMAL (2026-04-11)": (1744329600, 1744416000),
    "BEAR CRASH  (2026-04-02)": (1743552000, 1743638400),
    "BULL        (2026-04-07)": (1743984000, 1744070400),
}

# Guardians we care about
GUARDIANS = [
    "REGIME_ALIGNMENT_V2",
    "POC_MIGRATION",
    "VA_INTEGRITY",
    "FAILED_AUCTION",
    "DELTA_DIVERGENCE",
]


def load_data(conn):
    traces = conn.execute(
        "SELECT timestamp, symbol, status, gate, reason FROM decision_traces ORDER BY timestamp"
    ).fetchall()
    signals = conn.execute("SELECT timestamp, symbol, side, price FROM signals ORDER BY timestamp").fetchall()
    samples = conn.execute("SELECT timestamp, symbol, price FROM price_samples ORDER BY timestamp").fetchall()
    return traces, signals, samples


def get_condition(ts):
    for name, (start, end) in CONDITIONS.items():
        if start <= ts < end:
            return name
    return None


def compute_wr(signal_list, samples_by_sym):
    """Compute WR at 0.3%/0.3% for a list of (ts, sym, side, price) signals."""
    wins = losses = 0
    for ts, sym, side, price in signal_list:
        window = [p for (t, p) in samples_by_sym.get(sym, []) if ts <= t <= ts + WINDOW_SECONDS]
        if not window:
            continue
        hit_tp = hit_sl = False
        for p in window:
            m = (p - price) / price * 100
            if side == "SHORT":
                m = -m
            if not hit_tp and m >= TP_PCT:
                hit_tp = True
                break
            if not hit_sl and m <= -SL_PCT:
                hit_sl = True
                break
        if hit_tp and not hit_sl:
            wins += 1
        elif hit_sl:
            losses += 1
    resolved = wins + losses
    wr = wins / resolved * 100 if resolved > 0 else 0
    return wins, losses, wr


def main():
    conn = sqlite3.connect(DB_PATH)
    traces, signals, samples = load_data(conn)
    conn.close()

    # Index samples by symbol
    from collections import defaultdict

    samples_by_sym = defaultdict(list)
    for ts, sym, price in samples:
        samples_by_sym[sym].append((ts, price))

    # ─────────────────────────────────────────────
    # SECTION 1: Rejection rate per guardian per condition
    # ─────────────────────────────────────────────
    print("=" * 80)
    print("  SECTION 1: GUARDIAN REJECTION RATE BY CONDITION")
    print("=" * 80)

    # Count PASS and REJECT per guardian per condition
    gate_stats = {}  # {condition: {gate: {pass: int, reject: int}}}
    for cond in CONDITIONS:
        gate_stats[cond] = {g: {"pass": 0, "reject": 0} for g in GUARDIANS}

    total_by_cond = {cond: {"pass": 0, "reject": 0} for cond in CONDITIONS}

    for ts, sym, status, gate, reason in traces:
        cond = get_condition(ts)
        if not cond:
            continue
        if gate in GUARDIANS:
            if status == "PASS":
                gate_stats[cond][gate]["pass"] += 1
                total_by_cond[cond]["pass"] += 1
            elif status == "REJECT":
                gate_stats[cond][gate]["reject"] += 1
                total_by_cond[cond]["reject"] += 1

    # Print header
    header = f"{'Guardian':25s}"
    for cond in CONDITIONS:
        short = cond.split("(")[0].strip()[:12]
        header += f"  {short:>12s}"
    print(header)
    print("-" * 80)

    for gate in GUARDIANS:
        row = f"{gate:25s}"
        for cond in CONDITIONS:
            p = gate_stats[cond][gate]["pass"]
            r = gate_stats[cond][gate]["reject"]
            total = p + r
            reject_pct = r / total * 100 if total > 0 else 0
            row += f"  {reject_pct:>10.1f}%"
        print(row)

    print()
    print(f"{'TOTAL TRACES':25s}", end="")
    for cond in CONDITIONS:
        p = total_by_cond[cond]["pass"]
        r = total_by_cond[cond]["reject"]
        total = p + r
        reject_pct = r / total * 100 if total > 0 else 0
        print(f"  {reject_pct:>10.1f}%", end="")
    print()

    # ─────────────────────────────────────────────
    # SECTION 2: Signal quality per condition
    # ─────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  SECTION 2: SIGNAL QUALITY (WR 0.3%/0.3%) BY CONDITION")
    print("=" * 80)
    print(f"{'Condition':30s} {'n':>4}  {'Wins':>4}  {'Loss':>4}  {'WR%':>6}  {'Verdict':>10}")
    print("-" * 70)

    for cond, (ts_start, ts_end) in CONDITIONS.items():
        cond_signals = [(ts, sym, side, price) for ts, sym, side, price in signals if ts_start <= ts < ts_end]
        wins, losses, wr = compute_wr(cond_signals, samples_by_sym)
        n = len(cond_signals)
        verdict = "CERTIFIED" if wr > 55 and n >= 10 else ("WATCH" if wr > 45 else "FAILED")
        if n < 10:
            verdict = "LOW_N"
        print(f"{cond:30s} {n:>4}  {wins:>4}  {losses:>4}  {wr:>5.1f}%  {verdict:>10}")

    # ─────────────────────────────────────────────
    # SECTION 3: Guardian discrimination score
    # ─────────────────────────────────────────────
    print()
    print("=" * 80)
    print("  SECTION 3: GUARDIAN DISCRIMINATION SCORE")
    print("  (How much MORE does each guardian reject in trending vs range?)")
    print("=" * 80)

    range_cond = "RANGE       (2026-04-12)"
    trending_conds = [c for c in CONDITIONS if c != range_cond]

    print(f"{'Guardian':25s}  {'RANGE%':>8}  {'BEAR_N%':>8}  {'BEAR_C%':>8}  {'BULL%':>8}  {'Discrimination':>15}")
    print("-" * 85)

    for gate in GUARDIANS:
        range_r = gate_stats[range_cond][gate]["reject"]
        range_p = gate_stats[range_cond][gate]["pass"]
        range_total = range_r + range_p
        range_pct = range_r / range_total * 100 if range_total > 0 else 0

        trending_pcts = []
        row_vals = [f"{range_pct:>8.1f}%"]

        for cond in trending_conds:
            r = gate_stats[cond][gate]["reject"]
            p = gate_stats[cond][gate]["pass"]
            total = r + p
            pct = r / total * 100 if total > 0 else 0
            trending_pcts.append(pct)
            row_vals.append(f"{pct:>8.1f}%")

        # Discrimination = avg(trending) - range
        avg_trending = statistics.mean(trending_pcts) if trending_pcts else 0
        discrimination = avg_trending - range_pct
        disc_label = "✅ GOOD" if discrimination > 5 else ("⚠️ WEAK" if discrimination > 0 else "❌ INVERTED")

        print(f"{gate:25s}  {'  '.join(row_vals)}  {discrimination:>+8.1f}%  {disc_label}")

    print()
    print("Discrimination = avg(BEAR_N + BEAR_C + BULL) rejection% - RANGE rejection%")
    print("Positive = guardian rejects MORE in trending conditions (correct behavior)")
    print("Negative = guardian rejects MORE in range (wrong — blocking our edge zone)")


if __name__ == "__main__":
    main()
