import json
import sqlite3

import numpy as np
import pandas as pd

conn = sqlite3.connect("data/historian.db")

query = """
SELECT s.timestamp, s.symbol, s.side, s.price as entry_price, d.metrics
FROM signals s
INNER JOIN decision_traces d
ON s.timestamp = d.timestamp AND s.symbol = d.symbol
WHERE d.gate = 'STRUCTURE_GEOGRAPHY'
"""
df = pd.read_sql(query, conn)

# We also need to know which ones were EXECUTED
query_exec = """
SELECT timestamp, symbol FROM decision_traces WHERE status = 'EXECUTED'
"""
exec_df = pd.read_sql(query_exec, conn)
exec_keys = set(zip(exec_df.timestamp, exec_df.symbol))

# Filter df to only EXECUTED signals
df = df[df.apply(lambda row: (row["timestamp"], row["symbol"]) in exec_keys, axis=1)]

samples = pd.read_sql("SELECT timestamp, symbol, price FROM price_samples", conn)
conn.close()

results = []

for _, row in df.iterrows():
    try:
        metrics = json.loads(row["metrics"])
        poc = metrics.get("poc", 0)
        if poc == 0:
            continue

        entry = row["entry_price"]
        side = row["side"]

        # Calculate distance to POC in %
        dist_to_poc_pct = abs(entry - poc) / entry * 100

        # Calculate MFE in next 900s
        ts = row["timestamp"]
        sym = row["symbol"]
        sym_samples = samples[
            (samples["symbol"] == sym) & (samples["timestamp"] >= ts) & (samples["timestamp"] <= ts + 900)
        ]["price"].values

        if len(sym_samples) == 0:
            continue

        moves = (sym_samples - entry) / entry * 100
        if side == "SHORT":
            moves = -moves

        mfe = float(np.max(moves)) if len(moves) > 0 else 0.0

        reached_poc = False
        if side == "LONG" and np.max(sym_samples) >= poc:
            reached_poc = True
        elif side == "SHORT" and np.min(sym_samples) <= poc:
            reached_poc = True

        results.append({"dist_to_poc": dist_to_poc_pct, "mfe": mfe, "reached_poc": reached_poc})
    except Exception as e:
        continue

if results:
    res_df = pd.DataFrame(results)
    print(f"Total Trades Analyzed: {len(res_df)}")
    print(f"Average Distance to POC: {res_df['dist_to_poc'].mean():.3f}%")
    print(f"Average Real MFE: {res_df['mfe'].mean():.3f}%")
    print(f"% of times it REACHED the POC: {(res_df['reached_poc'].sum() / len(res_df) * 100):.1f}%")
else:
    print("No valid data found.")
