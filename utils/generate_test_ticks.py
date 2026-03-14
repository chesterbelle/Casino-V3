#!/usr/bin/env python3
"""
Generate synthetic tick data for V4 Backtest validation.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def generate_ticks(symbol="BTC/USDT", num_ticks=1000, start_price=60000.0):
    ticks = []
    current_time = datetime.now()
    price = start_price

    for i in range(num_ticks):
        # Random walk for price
        price += np.random.normal(0, 0.5)
        # Random volume
        volume = np.random.lognormal(0, 1)
        # Random side
        side = "BUY" if np.random.random() > 0.5 else "SELL"

        ticks.append(
            {
                "timestamp": int(current_time.timestamp()),
                "price": round(price, 2),
                "volume": round(volume, 4),
                "side": side,
            }
        )
        # Advance time by 0-2 seconds
        current_time += timedelta(milliseconds=np.random.randint(100, 2000))

    df = pd.DataFrame(ticks)
    return df


if __name__ == "__main__":
    import os

    os.makedirs("data/test", exist_ok=True)
    df = generate_ticks()
    path = "data/test/synthetic_ticks_v4.csv"
    df.to_csv(path, index=False)
    print(f"✅ Generated {len(df)} ticks at {path}")
