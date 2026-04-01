import sqlite3

import pandas as pd

try:
    with sqlite3.connect("data/historian.db") as conn:
        df = pd.read_sql("SELECT trade_id, symbol, side, setup_type, exit_reason FROM trades LIMIT 10", conn)
        print("--- Trades from historian.db ---")
        print(df.to_string())
except Exception as e:
    print(f"Error querying historian.db: {e}")
