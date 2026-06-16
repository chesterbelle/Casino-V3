import os
import sqlite3
import sys

import pandas as pd

DB_PATH = "data/historian.db"


def analyze_coin(symbol):
    conn = sqlite3.connect(DB_PATH)
    # Get signals for this coin
    query = f"SELECT * FROM signals WHERE symbol = '{symbol}'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return None

    # Simplified PnL calculation based on typical AMT logic
    # outcome: 1 = win, 0 = loss/timeout (approx)
    # In a real scenario, we'd use the trade outcomes from the DB
    # But since we are in audit mode, we use the signals and their results

    # Let's use a simpler approach: calculate based on the 'outcome' or 'pnl' if available
    # The signals table usually has the results after the backtest

    # If we don't have a clean 'pnl' column, we'll look at the signals
    # For the sake of this audit, we'll assume we can calculate it via the auditor's logic
    # But since we want a quick breakdown, let's use a simplified version of the auditor

    return {
        "symbol": symbol,
        "count": len(df),
        "details": df.groupby("setup_type")["pnl"].agg(["mean", "count"]) if "pnl" in df.columns else "No PnL column",
    }


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    symbols = pd.read_sql_query("SELECT DISTINCT symbol FROM signals", conn)
    conn.close()

    for sym in symbols["symbol"]:
        res = analyze_coin(sym)
        print(f"\n--- {sym} ---")
        print(res)
