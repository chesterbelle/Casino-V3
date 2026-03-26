#!/usr/bin/env python3
"""
Simulation Parity Check - Data Fetcher
Downloads highly granular aggTrades from Binance for a specific time window
and formats them for Casino V4 BacktestFeed.
"""

import argparse
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Parity-Fetcher")

BINANCE_API_URL = "https://fapi.binance.com/fapi/v1/aggTrades"

async def fetch_agg_trades(symbol: str, start_ts_ms: int, end_ts_ms: int):
    """Fetches all aggTrades for a symbol between start and end timestamps."""
    all_trades = []
    current_start = start_ts_ms
    
    # Binance strict limit per request
    limit = 1000 
    
    logger.info(f"📥 Starting download for {symbol} from {datetime.fromtimestamp(start_ts_ms/1000, tz=timezone.utc)} to {datetime.fromtimestamp(end_ts_ms/1000, tz=timezone.utc)}")

    async with aiohttp.ClientSession() as session:
        while current_start < end_ts_ms:
            params = {
                "symbol": symbol.replace("/", "").replace(":", ""),  # BTC/USDT:USDT -> BTCUSDT
                "startTime": current_start,
                "endTime": end_ts_ms,
                "limit": limit
            }
            
            async with session.get(BINANCE_API_URL, params=params) as response:
                if response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Sleeping for 5 seconds...")
                    await asyncio.sleep(5)
                    continue
                
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"❌ Failed to fetch data: HTTP {response.status} - {text}")
                    break
                    
                data = await response.json()
                
                if not data:
                    break
                    
                all_trades.extend(data)
                
                # Update current_start to the timestamp of the last trade + 1ms
                # to avoid fetching the same trade twice
                last_ts = data[-1]["T"]
                if current_start == last_ts + 1:
                    # Protection against infinite loops if multiple trades have EXACT same ms
                    current_start += 1
                else:
                    current_start = last_ts + 1
                    
                # Rate limit respect
                await asyncio.sleep(0.1)
                
                # Progress logging
                if len(all_trades) % 50000 < limit:
                    logger.info(f"⏳ Downloaded {len(all_trades)} trades... (Current TS: {datetime.fromtimestamp(last_ts/1000, tz=timezone.utc)})")

    return all_trades

def process_trades(raw_trades, output_path: str):
    """Processes Binance aggTrades into Casino V4 CSV format."""
    logger.info(f"🔄 Processing {len(raw_trades)} trades into Fast-Track CSV format...")
    
    if not raw_trades:
        logger.warning("⚠️ No trades found to process.")
        return
        
    # 'a': aggTradeId
    # 'p': price
    # 'q': quantity
    # 'f': firstTradeId
    # 'l': lastTradeId
    # 'T': timestamp
    # 'm': isBuyerMaker (True = SELL aggressively, False = BUY aggressively)
    
    processed = []
    for t in raw_trades:
        processed.append({
            "timestamp": t["T"] / 1000.0, # Backtester expects Epoch seconds
            "price": float(t["p"]),
            "volume": float(t["q"]),
            # If buyer is maker, the aggressive side was SELL. If buyer is NOT maker, aggressive side was BUY.
            "side": "SELL" if t["m"] else "BUY" 
        })
        
    df = pd.DataFrame(processed)
    
    # Sort just in case API returned them slightly out of order
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    
    df.to_csv(output_path, index=False)
    logger.info(f"✅ Generated Golden Dataset: {output_path} ({len(df)} rows)")

async def main():
    parser = argparse.ArgumentParser(description="Fetch Binance aggTrades to create an exact Parity Dataset.")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol to fetch (e.g., BTCUSDT or BTC/USDT:USDT)")
    parser.add_argument("--start", type=float, required=True, help="Start time (Epoch Seconds)")
    parser.add_argument("--end", type=float, required=True, help="End time (Epoch Seconds)")
    parser.add_argument("--out", type=str, required=True, help="Output CSV path")
    
    args = parser.parse_args()
    
    # Format symbol for Binance
    symbol = args.symbol.replace("/", "").replace(":", "")
    if symbol.endswith("USDTUSDT"):
        symbol = symbol[:-4]
        
    start_ms = int(args.start * 1000)
    end_ms = int(args.end * 1000)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    
    trades = await fetch_agg_trades(symbol, start_ms, end_ms)
    process_trades(trades, args.out)

if __name__ == "__main__":
    asyncio.run(main())
