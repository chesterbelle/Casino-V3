import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))


def analyze_rejections(db_path="data/historian.db", window_ticks=900):
    if not os.path.exists(db_path):
        print(f"❌ Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)

    # Check if decision_traces exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decision_traces'")
    if not cursor.fetchone():
        print("❌ Error: Table 'decision_traces' not found.")
        return

    print("=" * 60)
    print("GUARDIAN REJECTION EFFICIENCY AUDIT")
    print("=" * 60)

    # 1. Get all traces
    traces_df = pd.read_sql_query("SELECT * FROM decision_traces", conn)
    if traces_df.empty:
        print("❌ No decision traces found.")
        return

    # 2. Get price samples for trajectory analysis
    prices_df = pd.read_sql_query("SELECT * FROM price_samples", conn)
    if prices_df.empty:
        print("❌ No price samples found.")
        return

    prices_df["timestamp"] = pd.to_numeric(prices_df["timestamp"])
    prices_df = prices_df.sort_values("timestamp")

    results = []

    print(f"Analyzing {len(traces_df)} traces...")

    for _, trace in traces_df.iterrows():
        # Only analyze rejections
        if trace["status"] == "PASS":
            continue

        timestamp = float(trace["timestamp"])
        symbol = trace["symbol"]
        entry_price = float(trace["price"])
        gate_name = trace["gate"]
        reason = trace["reason"]

        # Get forward trajectory (window_ticks samples)
        trajectory = (
            prices_df[prices_df["timestamp"] >= timestamp].head(window_ticks)["price"].tolist()
        )

        if not trajectory:
            continue

        # Calculate MFE / MAE
        mfe = 0.0
        mae = 0.0

        if trace["side"] == "LONG":
            mfe = (max(trajectory) - entry_price) / entry_price * 100
            mae = (entry_price - min(trajectory)) / entry_price * 100
        else:  # SHORT
            mfe = (entry_price - min(trajectory)) / entry_price * 100
            mae = (max(trajectory) - entry_price) / entry_price * 100

        # Outcome based on 0.3%/0.3% baseline
        outcome = "TIMEOUT"
        if mfe >= 0.3 and mae < 0.3:
            outcome = "WINNER"
        elif mae >= 0.3:
            outcome = "LOSER"

        results.append(
            {
                "gate": gate_name,
                "reason": reason,
                "mfe": mfe,
                "mae": mae,
                "outcome": outcome,
                "z_score": (
                    float(reason.split("at ")[1].split("Z")[0])
                    if "at " in reason and "Z" in reason
                    else 0
                ),
            }
        )

    results_df = pd.DataFrame(results)

    if results_df.empty:
        print("❌ No rejected traces could be analyzed for trajectory.")
        return

    # Summary per Gate
    print("\n[EFFICIENCY BY GUARDIAN]")
    print("-" * 60)
    for gate, group in results_df.groupby("gate"):
        total = len(group)
        winners = len(group[group["outcome"] == "WINNER"])
        num_losers = len(group[group["outcome"] == "LOSER"])

        # PnL Estimado (TP=0.3%, SL=0.3%, Fee=0.06% x 2)
        pnl = (winners * 0.3) - (num_losers * 0.3) - (total * 0.12)

        print(f"Guardian: {gate:20s}")
        print(f"  Total Blocked : {total}")
        print(f"  True Rejections (Losers) : {num_losers} ✅")
        print(f"  False Rejections (Winners): {winners} ❌")
        print(f"  Estimated PnL if passed  : {pnl:.2f}%")
        print("-" * 30)

    print("\n[Z-SCORE DETAILED PNL ANALYSIS]")
    if "z_score" in results_df.columns:
        results_df["z_bin"] = pd.cut(
            results_df["z_score"].abs(), bins=[0, 1.0, 1.2, 1.5, 1.8, 2.1, 5.0]
        )

        def calc_pnl(x):
            w = len(x[x == "WINNER"])
            num_l = len(x[x == "LOSER"])
            t = len(x)
            return (w * 0.3) - (num_l * 0.3) - (t * 0.12)

        z_pnl = results_df.groupby("z_bin")["outcome"].apply(calc_pnl)
        z_counts = results_df.groupby("z_bin")["outcome"].count()

        pnl_table = pd.DataFrame({"Signals": z_counts, "Est_PnL": z_pnl})
        print(pnl_table)

    conn.close()


if __name__ == "__main__":
    analyze_rejections()
