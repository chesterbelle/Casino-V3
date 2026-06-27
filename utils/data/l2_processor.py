#!/usr/bin/env python3
"""
L2 & Trades Processor for Casino-V3
Processes raw Tardis files from data/datasets/raw/ into a high-fidelity SQLite DB in data/datasets/daily_backtest_ready/
Requires both trades and incremental_book_L2 files to proceed.
"""

import argparse
import csv
import glob
import gzip
import json
import logging
import os
import sqlite3
from typing import Dict, List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("L2Processor")


class OrderBook:
    def __init__(self):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}

    def update(self, side: str, price: float, amount: float):
        target = self.bids if side == "bid" else self.asks
        if amount == 0:
            target.pop(price, None)
        else:
            target[price] = amount

    def get_snapshot(self, levels: int = 5) -> Tuple[List[List[str]], List[List[str]]]:
        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:levels]
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:levels]

        bids_out = [[f"{p:.8f}".rstrip("0").rstrip("."), f"{a:.8f}".rstrip("0").rstrip(".")] for p, a in sorted_bids]
        asks_out = [[f"{p:.8f}".rstrip("0").rstrip("."), f"{a:.8f}".rstrip("0").rstrip(".")] for p, a in sorted_asks]

        while len(bids_out) < levels:
            bids_out.append(["0.0", "0.0"])
        while len(asks_out) < levels:
            asks_out.append(["0.0", "0.0"])

        return bids_out, asks_out


def normalize_symbol(sym: str) -> str:
    """Uses the bot's internal normalization logic (Simplified here to match utils/symbol_norm.py)"""
    return sym.upper().replace("/", "").split(":")[0]


def process_trades(file_path: str, symbol: str, conn: sqlite3.Connection):
    logger.info(f"📝 Ingesting trades from {file_path}...")
    cursor = conn.cursor()

    current_minute = -1
    candle = None  # [open, high, low, close, volume]

    with gzip.open(file_path, mode="rt") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            ts_us = int(row["timestamp"])
            ts_s = ts_us / 1_000_000.0
            price = float(row["price"])
            amount = float(row["amount"])
            side = row["side"].upper()

            # Store raw trade
            cursor.execute(
                "INSERT INTO market_trades (timestamp, symbol, price, amount, side) VALUES (?, ?, ?, ?, ?)",
                (ts_s, symbol, price, amount, side),
            )

            # Aggregate into 1m candle
            ts_min = int(ts_s // 60) * 60
            if ts_min != current_minute:
                if candle:
                    cursor.execute(
                        "INSERT INTO price_candles (timestamp, symbol, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (current_minute, symbol, candle[0], candle[1], candle[2], candle[3], candle[4]),
                    )
                current_minute = ts_min
                candle = [price, price, price, price, amount]
            else:
                candle[1] = max(candle[1], price)
                candle[2] = min(candle[2], price)
                candle[3] = price
                candle[4] += amount
            count += 1
            if count % 100000 == 0:
                logger.info(f"   Processed {count} trades...")

        if candle:
            cursor.execute(
                "INSERT INTO price_candles (timestamp, symbol, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (current_minute, symbol, candle[0], candle[1], candle[2], candle[3], candle[4]),
            )
    conn.commit()


def process_l2(file_path: str, symbol: str, conn: sqlite3.Connection, snapshot_interval: int):
    logger.info(f"📚 Reconstructing L2 Orderbook from {file_path}...")
    book = OrderBook()
    last_snapshot_ts = 0
    cursor = conn.cursor()

    with gzip.open(file_path, mode="rt") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            ts_us = int(row["timestamp"])
            ts_s = ts_us / 1_000_000.0

            book.update(row["side"], float(row["price"]), float(row["amount"]))

            if ts_s - last_snapshot_ts >= snapshot_interval:
                bids, asks = book.get_snapshot(5)
                cursor.execute(
                    "INSERT INTO depth_snapshots (timestamp, symbol, bids, asks) VALUES (?, ?, ?, ?)",
                    (ts_s, symbol, json.dumps(bids), json.dumps(asks)),
                )
                last_snapshot_ts = ts_s

            count += 1
            if count % 500000 == 0:
                logger.info(f"   Processed {count} L2 updates...")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Process raw datasets into backtest-ready SQLite DB")
    parser.add_argument(
        "--name", required=True, help="Base name or pattern of the files in raw/ (e.g. LTCUSDT_2024_01)"
    )
    parser.add_argument("--symbol", help="Target symbol (e.g. LTCUSDT). If not provided, will try to guess from name.")
    parser.add_argument("--raw-dir", default="data/datasets/raw", help="Source directory")
    parser.add_argument("--out-dir", default="data/datasets/daily_backtest_ready", help="Output directory")
    parser.add_argument("--snapshot-interval", type=int, default=60, help="L2 snapshot interval in seconds")

    args = parser.parse_args()

    # 1. Smart partner detection
    all_files = glob.glob(os.path.join(args.raw_dir, "*"))

    trades_files = [f for f in all_files if args.name in f and "trades" in f]
    l2_files = [f for f in all_files if args.name in f and "incremental_book_L2" in f]

    if not trades_files:
        logger.error(f"❌ Error: Missing 'trades' file for pattern '{args.name}'")
        return
    if not l2_files:
        logger.error(f"❌ Error: Missing 'incremental_book_L2' file for pattern '{args.name}'")
        return

    trades_file = trades_files[0]
    l2_file = l2_files[0]

    # 2. Prepare DB
    symbol = args.symbol if args.symbol else args.name.split("_")[0]
    norm_symbol = normalize_symbol(symbol)
    db_name = f"{args.name}.db"
    db_path = os.path.join(args.out_dir, db_name)

    os.makedirs(args.out_dir, exist_ok=True)
    if os.path.exists(db_path):
        logger.warning(f"⚠️ Overwriting existing DB: {db_path}")
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=OFF;")  # Speed up ingestion

    cursor = conn.cursor()
    cursor.execute("CREATE TABLE market_trades (timestamp REAL, symbol TEXT, price REAL, amount REAL, side TEXT)")
    cursor.execute("CREATE TABLE depth_snapshots (timestamp REAL, symbol TEXT, bids TEXT, asks TEXT)")
    cursor.execute(
        "CREATE TABLE price_candles (timestamp REAL, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    conn.commit()

    logger.info(f"🚀 Starting processing into {db_name} (Symbol: {norm_symbol})")

    # 3. Execution
    try:
        process_trades(trades_file, norm_symbol, conn)
        process_l2(l2_file, norm_symbol, conn, args.snapshot_interval)

        logger.info("⚡ Creating indexes...")
        cursor.execute("CREATE INDEX idx_trades_ts ON market_trades(timestamp)")
        cursor.execute("CREATE INDEX idx_depth_ts ON depth_snapshots(timestamp)")
        cursor.execute("CREATE INDEX idx_price_ts ON price_candles(timestamp)")
        conn.commit()

        logger.info(f"✨ Successfully created {db_path}")
    except Exception as e:
        logger.error(f"💥 Processing failed: {e}")
        if os.path.exists(db_path):
            os.remove(db_path)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
