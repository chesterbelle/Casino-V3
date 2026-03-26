import asyncio
import os
from typing import Dict, List

import aiohttp


async def fetch_agg_trades(symbol: str, start_ts: int, end_ts: int) -> List[Dict]:
    """
    Fetch aggTrades from Binance Futures REST API.
    start_ts/end_ts are in milliseconds.
    """
    base_url = "https://fapi.binance.com/fapi/v1/aggTrades"
    trades = []
    current_start = start_ts

    async with aiohttp.ClientSession() as session:
        while current_start < end_ts:
            params = {
                "symbol": symbol.replace("/", "").replace(":USDT", ""),
                "startTime": current_start,
                "endTime": min(current_start + 3600000, end_ts),  # 1h chunks
                "limit": 1000,
            }

            async with session.get(base_url, params=params) as resp:
                if resp.status != 200:
                    print(f"Error fetching: {resp.status} - {await resp.text()}")
                    break

                data = await resp.json()
                if not data:
                    break

                trades.extend(data)
                # Move start to last trade time + 1ms
                current_start = data[-1]["T"] + 1

                print(f"Fetched {len(trades)} trades... (Last TS: {current_start})")

                if len(data) < 1000:
                    # End of range reached for this chunk but check if there's more time
                    if current_start >= end_ts:
                        break
                    else:
                        # Wait 100ms to avoid rate limits
                        await asyncio.sleep(0.1)

    return trades


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Binance aggTrades")
    parser.add_argument("--symbol", required=True, help="Target Symbol")
    parser.add_argument("--start", required=True, type=int, help="Start Epoch")
    parser.add_argument("--end", required=True, type=int, help="End Epoch")
    parser.add_argument("--out", required=False, help="Output File")
    args = parser.parse_args()

    symbol = args.symbol
    start_ts = args.start * 1000
    end_ts = args.end * 1000
    output_file = args.out if args.out else f"data/{symbol.replace('/', '_')}_golden.csv"

    print(f"📥 Fetching Golden Dataset for {symbol}...")
    print(f"⏰ Window: {args.start} -> {args.end}")

    trades = await fetch_agg_trades(symbol, start_ts, end_ts)

    # Convert to CSV format expected by BacktestFeed
    import pandas as pd

    df = pd.DataFrame(trades)
    if not df.empty:
        # Binance fields: T=timestamp, p=price, q=quantity, m=is_maker
        df["timestamp"] = df["T"] / 1000.0
        df["price"] = df["p"].astype(float)
        df["volume"] = df["q"].astype(float)
        df["side"] = df["m"].map({True: "sell", False: "buy"})

        # Select and reorder columns
        df = df[["timestamp", "price", "volume", "side"]]

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df.to_csv(output_file, index=False)
        print(f"✅ Saved {len(df)} trades to {output_file}")
    else:
        print("⚠️ No trades found in this window.")


if __name__ == "__main__":
    asyncio.run(main())
