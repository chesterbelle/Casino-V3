import sqlite3

import pandas as pd

from core.pressure.engine import PressureEngine

engine = PressureEngine()
conn = sqlite3.connect("data/historian_LTC_TREND_UP_2024-03-01.db")
df = pd.read_sql("SELECT close, volume FROM price_candles", conn)

for _, row in df.iterrows():
    engine.update(qty=row["volume"], is_buyer_maker=False, ts=1.0, price=row["close"])
    state = engine.get_state()
    if state.cvd_velocity != 0.0:
        print(f"Velocity: {state.cvd_velocity}")
        break
