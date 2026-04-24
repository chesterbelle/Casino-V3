#!/usr/bin/env python3
"""
Debug REGIME_ALIGNMENT_V2 guardian — why is discrimination weak?
Analyzes decision traces to understand what the guardian is actually doing.
"""

import sqlite3

import pandas as pd

DB_PATH = "data/historian.db"

CONDITIONS = {
    "RANGE  (04-12)": (1744416000, 1744502400),
    "BEAR_N (04-11)": (1744329600, 1744416000),
    "BEAR_C (04-02)": (1743552000, 1743638400),
    "BULL   (04-07)": (1743984000, 1744070400),
}


def main():
    conn = sqlite3.connect(DB_PATH)

    # Load only REGIME traces
    df = pd.read_sql(
        "SELECT timestamp, status, gate, reason FROM decision_traces WHERE gate = 'REGIME_ALIGNMENT_V2'",
        conn,
    )
    conn.close()

    print(f"Total REGIME_ALIGNMENT_V2 traces: {len(df)}")
    print()

    # Overall breakdown
    print("=== OVERALL REASON BREAKDOWN ===")
    summary = df.groupby(["status", "reason"]).size().reset_index(name="count")
    summary = summary.sort_values("count", ascending=False)
    for _, row in summary.iterrows():
        print(f"  {row['status']:8s} | {row['reason']:55s} | {row['count']:>5}")
    print()

    # Per condition
    print("=== PER CONDITION BREAKDOWN ===")
    for cond_name, (ts_start, ts_end) in CONDITIONS.items():
        cond_df = df[(df["timestamp"] >= ts_start) & (df["timestamp"] < ts_end)]
        total = len(cond_df)
        rejects = len(cond_df[cond_df["status"] == "REJECT"])
        passes = len(cond_df[cond_df["status"] == "PASS"])
        reject_pct = rejects / total * 100 if total > 0 else 0

        print(f"\n{cond_name} — Total: {total}, PASS: {passes}, REJECT: {rejects} ({reject_pct:.1f}%)")

        if total > 0:
            breakdown = cond_df.groupby(["status", "reason"]).size().reset_index(name="count")
            breakdown = breakdown.sort_values("count", ascending=False)
            for _, row in breakdown.iterrows():
                pct = row["count"] / total * 100
                print(f"    {row['status']:8s} | {row['reason']:50s} | {row['count']:>4} ({pct:.1f}%)")

    # Key question: In BEAR_CRASH, what is the guardian saying?
    print()
    print("=== KEY QUESTION: What does REGIME say during BEAR CRASH? ===")
    bear_crash_df = df[(df["timestamp"] >= 1743552000) & (df["timestamp"] < 1743638400)]
    print(f"Total traces in BEAR CRASH: {len(bear_crash_df)}")
    if len(bear_crash_df) > 0:
        print("All reasons:")
        for _, row in bear_crash_df.groupby(["status", "reason"]).size().reset_index(name="count").iterrows():
            print(f"  {row['status']:8s} | {row['reason']:50s} | {row['count']}")
    else:
        print("  NO TRACES — Guardian never evaluated during BEAR CRASH!")
        print("  This means the regime sensor never emitted a MarketRegime_V2 event,")
        print("  OR the event was emitted but the guardian was never called.")


if __name__ == "__main__":
    main()
