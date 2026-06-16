#!/usr/bin/env python3
"""
CryptoHFTData Fetcher for Casino-V3
Downloads high-fidelity L2 and Trade data from CryptoHFTData.com
and stores them as Tardis-compatible CSV.gz in data/datasets/raw/

API docs: https://www.cryptohftdata.com/docs
OpenAPI: https://www.cryptohftdata.com/.well-known/openapi.json

Usage:
    # Download 1 day
    python utils/data/cryptohftdata_fetcher.py --symbol LTCUSDT --start 2026-05-15

    # Download 1 month
    python utils/data/cryptohftdata_fetcher.py --symbol SOLUSDT --start 2026-05-01 --end 2026-05-31

    # List available symbols
    python utils/data/cryptohftdata_fetcher.py --symbol LTCUSDT --list
"""

import argparse
import concurrent.futures
import csv
import gzip
import io
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq
import requests
import zstandard as zstd
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("CryptoHFTDataFetcher")

BASE_URL = "https://api.cryptohftdata.com"
EXCHANGE_MAP = {
    "binance-futures": "binance_futures",
    "binance": "binance_spot",
    "bybit": "bybit_spot",
    "okx": "okx",
    "hyperliquid": "hyperliquid",
    "kraken": "kraken_spot",
}


class CryptoHFTDataFetcher:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("CRYPTOHFTDATA_API_KEY")
        if not self.api_key:
            logger.error("CRYPTOHFTDATA_API_KEY not set. Get one at https://cryptohftdata.com/")
            sys.exit(1)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=24, pool_maxsize=48)
        self.session.mount("https://", adapter)

    def list_symbols(self, exchange: str, data_type: str = "trades") -> list[str]:
        exch = EXCHANGE_MAP.get(exchange, exchange)
        resp = self.session.get(f"{BASE_URL}/symbols", params={"exchange": exch, "data_type": data_type}, timeout=30)
        if resp.status_code != 200:
            logger.error(f"API error: {resp.status_code} {resp.text[:200]}")
            return []
        return resp.json().get("symbols", [])

    def download_hour(
        self, exchange: str, symbol: str, data_type: str, date: str, hour: int, retries: int = 3
    ) -> Optional[bytes]:
        file_path = f"{exchange}/{date}/{hour:02d}/{symbol}_{data_type}.parquet.zst"
        for attempt in range(retries):
            try:
                resp = self.session.get(
                    f"{BASE_URL}/download", params={"file": file_path, "api_key": self.api_key}, timeout=180
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return resp.content
                logger.warning(f"  hour {hour:02d}: HTTP {resp.status_code} (attempt {attempt+1})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"  hour {hour:02d}: connection error (attempt {attempt+1})")
                if attempt < retries - 1:
                    import time

                    time.sleep(1)
        return None

    def parquet_to_df(self, raw_bytes: bytes, data_type: str):
        decompressed = zstd.decompress(raw_bytes)
        table = pq.read_table(io.BytesIO(decompressed))
        return table.to_pandas()

    def convert_trades(self, df) -> pd.DataFrame:
        out = pd.DataFrame(
            {
                "exchange": "binance-futures",
                "symbol": df["symbol"],
                "timestamp": (df["event_time"] * 1000).astype(int),
                "local_timestamp": (df["received_time"] / 1000).astype(int),
                "id": df["trade_id"].astype(int),
                "side": df["is_buyer_maker"].apply(lambda x: "sell" if x else "buy"),
                "price": df["price"].astype(float),
                "amount": df["quantity"].astype(float),
            }
        )
        return out

    def convert_orderbook(self, df) -> pd.DataFrame:
        out = pd.DataFrame(
            {
                "exchange": "binance-futures",
                "symbol": df["symbol"],
                "timestamp": (df["event_time"] * 1000).astype(int),
                "local_timestamp": (df["received_time"] / 1000).astype(int),
                "is_snapshot": "False",
                "side": df["side"],
                "price": df["price"].astype(float),
                "amount": df["quantity"].astype(float),
            }
        )
        return out

    def write_csv_gz(self, df: pd.DataFrame, filepath: Path, columns: list[str]):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(filepath, "wt", newline="") as f:
            df[columns].to_csv(f, index=False)
        logger.info(f"  Written: {filepath.name} ({len(df):,} rows, {os.path.getsize(filepath) / 1e6:.1f} MB)")

    def _download_hours(
        self, exch: str, symbol: str, api_type: str, date: str, sequential: bool = False
    ) -> dict[int, bytes]:
        """Download all 24 hours, return dict of hour->raw_bytes.

        When sequential=True, downloads one hour at a time (memory-efficient
        for large symbols like ETH where 24 parallel decompressions would OOM).
        """
        hours = list(range(24))
        results = {}

        if sequential:
            for h in hours:
                try:
                    results[h] = self.download_hour(exch, symbol, api_type, date, h)
                except Exception as e:
                    logger.warning(f"  hour {h:02d}: error - {e}")
                    results[h] = None
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(self.download_hour, exch, symbol, api_type, date, h): h for h in hours}
            for future in concurrent.futures.as_completed(futures):
                h = futures[future]
                try:
                    results[h] = future.result()
                except Exception as e:
                    logger.warning(f"  hour {h:02d}: error - {e}")
                    results[h] = None
        return results

    def _process_hours(self, raw_by_hour: dict[int, bytes], api_type: str, dtype: str) -> pd.DataFrame:
        """Convert downloaded bytes per hour to DataFrame, preserving hour order."""
        chunks = []
        for hour in range(24):
            raw = raw_by_hour.get(hour)
            if raw is None:
                continue
            df = self.parquet_to_df(raw, api_type)
            if dtype == "trades":
                chunks.append(self.convert_trades(df))
            else:
                chunks.append(self.convert_orderbook(df))
        if not chunks:
            return pd.DataFrame()
        all_df = pd.concat(chunks, ignore_index=True)
        all_df = all_df.sort_values("timestamp").reset_index(drop=True)
        return all_df

    def _fetch_and_write_hour_seq(self, exch: str, symbol: str, api_type: str, date: str, out_file: Path, dtype: str):
        """Download, process and append each hour sequentially — uses ~1h RAM per iteration."""
        trades_cols = ["exchange", "symbol", "timestamp", "local_timestamp", "id", "side", "price", "amount"]
        ob_cols = ["exchange", "symbol", "timestamp", "local_timestamp", "is_snapshot", "side", "price", "amount"]
        first = True
        for hour in range(24):
            raw = self.download_hour(exch, symbol, api_type, date, hour)
            if raw is None:
                continue
            try:
                df = self.parquet_to_df(raw, api_type)
                if dtype == "trades":
                    rows = self.convert_trades(df)
                    cols = trades_cols
                else:
                    rows = self.convert_orderbook(df)
                    cols = ob_cols
                if rows.empty:
                    continue
                rows = rows.sort_values("timestamp").reset_index(drop=True)
                rows[cols].to_csv(out_file, mode="a", index=False, header=first, compression="gzip")
                first = False
                logger.info(f"    hour {hour:02d}: {len(rows):,} rows appended")
            except Exception as e:
                logger.warning(f"    hour {hour:02d}: processing error - {e}")

    def fetch_day(
        self,
        exchange: str,
        symbol: str,
        date: str,
        output_dir: Path,
        data_types: list[str],
        force: bool = False,
        sequential: bool = False,
    ) -> list[Path]:
        exch = EXCHANGE_MAP.get(exchange, exchange)
        files = []

        for dtype in data_types:
            api_type = "orderbook" if dtype == "incremental_book_L2" else dtype
            out_file = output_dir / f"{exchange}_{dtype}_{date}_{symbol}.csv.gz"

            if out_file.exists() and not force:
                logger.info(f"  {out_file.name} already exists, skipping")
                files.append(out_file)
                continue

            if sequential:
                logger.info(f"  Sequential hour-by-hour mode for {out_file.name}...")
                self._fetch_and_write_hour_seq(exch, symbol, api_type, date, out_file, dtype)
                if out_file.exists() and os.path.getsize(out_file) > 0:
                    files.append(out_file)
                else:
                    logger.warning(f"  No data for {date} {dtype}")
                continue

            # Step 1: download all 24 hours in parallel (I/O bound)
            raw_by_hour = self._download_hours(exch, symbol, api_type, date)

            # Step 2: process sequentially (CPU bound - parquet decompress + convert)
            all_rows = self._process_hours(raw_by_hour, api_type, dtype)

            if not all_rows.empty:
                if dtype == "trades":
                    cols = ["exchange", "symbol", "timestamp", "local_timestamp", "id", "side", "price", "amount"]
                else:
                    cols = [
                        "exchange",
                        "symbol",
                        "timestamp",
                        "local_timestamp",
                        "is_snapshot",
                        "side",
                        "price",
                        "amount",
                    ]
                self.write_csv_gz(all_rows, out_file, cols)
                files.append(out_file)
            else:
                logger.warning(f"  No data for {date} {dtype}")

        return files

    def fetch_range(
        self,
        exchange: str,
        symbol: str,
        start: str,
        end: str,
        output_dir: Path,
        data_types: list[str],
        force: bool = False,
        sequential: bool = False,
    ) -> list[Path]:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        total = (end_dt - start_dt).days + 1
        all_files = []
        for i in range(total):
            date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            logger.info(f"📅 Day {i+1}/{total}: {date}")
            files = self.fetch_day(exchange, symbol, date, output_dir, data_types, force, sequential)
            all_files.extend(files)
        return all_files


def main():
    parser = argparse.ArgumentParser(description="Download CryptoHFTData as Tardis-compatible CSV.gz")
    parser.add_argument("--symbol", required=True, help="Trading pair (e.g. LTCUSDT)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start")
    parser.add_argument("--exchange", default="binance-futures", help="Exchange")
    parser.add_argument("--types", nargs="+", default=["incremental_book_L2", "trades"], help="Data types to download")
    parser.add_argument("--out-dir", default="data/datasets/raw", help="Output directory")
    parser.add_argument("--list", action="store_true", help="List available symbols")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Download and process one hour at a time (memory-efficient, but slower)",
    )

    args = parser.parse_args()
    fetcher = CryptoHFTDataFetcher()

    if args.list:
        symbols = fetcher.list_symbols(args.exchange)
        if symbols:
            print(f"\nAvailable symbols on {args.exchange}:")
            for s in symbols:
                print(f"  {s}")
            print(f"\nTotal: {len(symbols)}")
        else:
            print("No symbols found or API error")
        return

    if not args.start:
        parser.error("--start is required for download mode")

    output_dir = Path(args.out_dir)

    logger.info(f"🚀 Downloading {args.symbol} from {args.start} to {args.end or args.start}")
    files = fetcher.fetch_range(
        args.exchange,
        args.symbol,
        args.start,
        args.end or args.start,
        output_dir,
        args.types,
        args.force,
        args.sequential,
    )

    logger.info(f"✅ Done! {len(files)} files")


if __name__ == "__main__":
    main()
