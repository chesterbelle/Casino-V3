#!/usr/bin/env python3
"""
Download CryptoHFTData for a full day, convert to Tardis-compatible CSV.gz,
and compare against existing Tardis data.
"""
import gzip
import io
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests
import zstandard as zstd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("CryptoCompare")

API_KEY = os.environ.get("CRYPTOHFTDATA_API_KEY")
BASE_URL = "https://api.cryptohftdata.com"
RAW_DIR = Path("data/datasets/raw")

EXCHANGE = "binance_futures"
SYMBOL = "BTCUSDT"
DATE = "2026-05-01"

TARDIS_TRADES = RAW_DIR / f"binance-futures_trades_{DATE}_{SYMBOL}.csv.gz"
TARDIS_ORDERBOOK = RAW_DIR / f"binance-futures_incremental_book_L2_{DATE}_{SYMBOL}.csv.gz"


def download_hour(exchange, symbol, data_type, date, hour):
    """Download one hour of parquet.zst data."""
    file_path = f"{exchange}/{date}/{hour:02d}/{symbol}_{data_type}.parquet.zst"
    url = f"{BASE_URL}/download"
    params = {"file": file_path, "api_key": API_KEY}
    resp = requests.get(url, params=params, timeout=120)
    if resp.status_code != 200:
        logger.warning(f"  {data_type} hour {hour:02d}: HTTP {resp.status_code}")
        return None
    compressed = resp.content
    try:
        decompressed = zstd.decompress(compressed)
    except Exception as e:
        logger.warning(f"  {data_type} hour {hour:02d}: decompress error: {e}")
        return None
    table = pq.read_table(io.BytesIO(decompressed))
    return table.to_pandas()


def convert_trades_to_tardis(df):
    """Convert CryptoHFTData trades DF to Tardis CSV format."""
    if df is None or df.empty:
        return pd.DataFrame()

    # CryptoHFTData: received_time(ns), event_time(ms), trade_id, price, quantity, is_buyer_maker
    # Tardis: exchange, symbol, timestamp(us), local_timestamp(us), id, side, price, amount

    result = pd.DataFrame()
    result["exchange"] = "binance-futures"
    result["symbol"] = SYMBOL
    # Tardis timestamps are in microseconds, Crypto event_time is in ms -> multiply by 1000
    result["timestamp"] = (df["event_time"] * 1000).astype(int)
    # received_time is in nanoseconds -> divide by 1000 for microseconds
    result["local_timestamp"] = (df["received_time"] / 1000).astype(int)
    result["id"] = df["trade_id"]
    result["side"] = df["is_buyer_maker"].apply(lambda x: "sell" if x else "buy")
    result["price"] = df["price"].astype(float)
    result["amount"] = df["quantity"].astype(float)

    return result


def convert_orderbook_to_tardis(df):
    """Convert CryptoHFTData orderbook DF to Tardis CSV format."""
    if df is None or df.empty:
        return pd.DataFrame()

    # CryptoHFTData: received_time, event_time, transaction_time, symbol, event_type, first_update_id,
    #                final_update_id, prev_final_update_id, last_update_id, side, price, quantity, order_count
    # Tardis: exchange, symbol, timestamp, local_timestamp, is_snapshot, side, price, amount

    result = pd.DataFrame()
    result["exchange"] = "binance-futures"
    result["symbol"] = SYMBOL
    result["timestamp"] = (df["event_time"] / 1_000_000).astype(int)
    result["local_timestamp"] = (df["received_time"] / 1_000_000).astype(int)
    result["is_snapshot"] = df["event_type"] == "snapshot"
    result["side"] = df["side"]
    result["price"] = df["price"].astype(float)
    result["amount"] = df["quantity"].astype(float)

    return result


def write_csv_gz(df, filepath):
    """Write dataframe to gzipped CSV matching Tardis format."""
    if df.empty:
        logger.warning(f"Empty dataframe, not writing {filepath}")
        return False
    with gzip.open(filepath, "wt") as f:
        df.to_csv(f, index=False)
    logger.info(f"  Written: {filepath} ({len(df):,} rows, {os.path.getsize(filepath) / 1e6:.1f} MB)")
    return True


def compare_files(tardis_file, crypto_file, data_type):
    """Compare Tardis vs CryptoHFTData CSV files."""
    if not tardis_file.exists():
        logger.warning(f"Tardis file not found: {tardis_file}")
        return
    if not crypto_file or not Path(crypto_file).exists():
        logger.warning(f"Crypto file not found: {crypto_file}")
        return

    with gzip.open(str(tardis_file), "rt") as f:
        df_tardis = pd.read_csv(f)
    with gzip.open(str(crypto_file), "rt") as f:
        df_crypto = pd.read_csv(f)

    print(f"\n{'='*60}")
    print(f"📊 {data_type.upper()} COMPARISON - {DATE} {SYMBOL}")
    print(f"{'='*60}")

    print(f"\n📏 Row Counts:")
    print(f"   Tardis:       {len(df_tardis):>12,}")
    print(f"   CryptoHFT:    {len(df_crypto):>12,}")
    diff = abs(len(df_tardis) - len(df_crypto))
    diff_pct = diff / len(df_tardis) * 100 if len(df_tardis) > 0 else 0
    print(f"   Difference:   {diff:>12,} ({diff_pct:.2f}%)")

    print(f"\n📋 Columns:")
    tardis_cols = set(df_tardis.columns)
    crypto_cols = set(df_crypto.columns)
    cols_match = tardis_cols == crypto_cols
    print(f"   Match:        {'✅' if cols_match else '❌'}")
    if tardis_cols - crypto_cols:
        print(f"   Missing:      {tardis_cols - crypto_cols}")
    if crypto_cols - tardis_cols:
        print(f"   Extra:        {crypto_cols - tardis_cols}")

    print(f"\n⏱️  Time Range (first/last timestamp):")
    if "timestamp" in df_tardis.columns and "timestamp" in df_crypto.columns:
        t_start = datetime.fromtimestamp(df_tardis["timestamp"].min() / 1000, tz=timezone.utc)
        t_end = datetime.fromtimestamp(df_tardis["timestamp"].max() / 1000, tz=timezone.utc)
        c_start = datetime.fromtimestamp(df_crypto["timestamp"].min() / 1000, tz=timezone.utc)
        c_end = datetime.fromtimestamp(df_crypto["timestamp"].max() / 1000, tz=timezone.utc)
        print(f"   Tardis:       {t_start}  →  {t_end}")
        print(f"   CryptoHFT:    {c_start}  →  {c_end}")

    print(f"\n🔍 Sample Match (first 100 rows):")
    sample_t = df_tardis.head(100)
    sample_c = df_crypto.head(100)

    matching = 0
    total = 0
    common_cols = [c for c in df_tardis.columns if c in df_crypto.columns and c not in ("exchange", "symbol")]
    for col in common_cols:
        for i in range(min(100, len(df_tardis), len(df_crypto))):
            total += 1
            if i < len(sample_t) and i < len(sample_c):
                v1, v2 = sample_t[col].iloc[i], sample_c[col].iloc[i]
                if col in ("price", "amount"):
                    if abs(float(v1) - float(v2)) / max(abs(float(v1)), 0.0001) < 0.001:
                        matching += 1
                elif str(v1) == str(v2):
                    matching += 1

    match_pct = matching / total * 100 if total > 0 else 0
    emoji = "✅" if match_pct > 95 else "⚠️" if match_pct > 80 else "❌"
    print(f"   Match rate:   {match_pct:.1f}% {emoji}")

    print(f"\n   Verdict: ", end="")
    if diff_pct < 5 and match_pct > 95:
        print("✅ VALID - Data is consistent with Tardis")
    elif diff_pct < 10 and match_pct > 80:
        print("⚠️  WARNING - Minor differences, review before use")
    else:
        print("❌ INVALID - Significant differences")
    print()

    return diff_pct, match_pct


def main():
    if not API_KEY:
        logger.error("CRYPTOHFTDATA_API_KEY not set")
        sys.exit(1)

    logger.info(f"🚀 Downloading CryptoHFTData for {SYMBOL} on {DATE}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # --- Download all hours ---
    for data_type, tardis_file in [("trades", TARDIS_TRADES), ("orderbook", TARDIS_ORDERBOOK)]:
        logger.info(f"\n📦 Processing {data_type}...")
        all_hours = []
        for hour in range(24):
            df = download_hour(EXCHANGE, SYMBOL, data_type, DATE, hour)
            if df is not None and not df.empty:
                all_hours.append(df)
                logger.info(f"  {data_type} hour {hour:02d}: {len(df):,} rows")

        if not all_hours:
            logger.warning(f"No data downloaded for {data_type}")
            continue

        df_all = pd.concat(all_hours, ignore_index=True)

        # Convert to Tardis format
        if data_type == "trades":
            df_tardis = convert_trades_to_tardis(df_all)
        else:
            df_tardis = convert_orderbook_to_tardis(df_all)

        # Sort by timestamp
        df_tardis = df_tardis.sort_values("timestamp").reset_index(drop=True)

        # Write to CSV.gz
        out_path = RAW_DIR / f"cryptohft_{data_type}_{DATE}_{SYMBOL}.csv.gz"
        write_csv_gz(df_tardis, out_path)

    logger.info("\n" + "=" * 60)
    logger.info("📊 COMPARISON RESULTS")
    logger.info("=" * 60)

    # --- Compare ---
    crypto_trades = RAW_DIR / f"cryptohft_trades_{DATE}_{SYMBOL}.csv.gz"
    crypto_orderbook = RAW_DIR / f"cryptohft_orderbook_{DATE}_{SYMBOL}.csv.gz"

    compare_files(TARDIS_TRADES, crypto_trades, "trades")
    compare_files(TARDIS_ORDERBOOK, crypto_orderbook, "orderbook")


if __name__ == "__main__":
    main()
