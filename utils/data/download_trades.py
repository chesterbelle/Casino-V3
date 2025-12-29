#!/usr/bin/env python3
"""
Download historical aggTrades from Binance Vision.
URL: https://data.binance.vision/data/futures/um/monthly/aggTrades/{SYMBOL}/{SYMBOL}-aggTrades-{YEAR}-{MONTH}.zip
"""

import argparse
import io
import logging
import os
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data/futures/um/monthly/aggTrades"
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "raw",
)


def download_monthly_trades(symbol: str, year: str, month: str) -> str:
    """
    Download and process monthly trades for a symbol.
    Returns the path to the saved CSV.
    """
    url = f"{BASE_URL}/{symbol}/{symbol}-aggTrades-{year}-{month}.zip"
    logger.info(f"⬇️ Downloading: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            logger.error(f"❌ Data not found for {symbol} {year}-{month} (404).")
            return None
        raise e

    # Extract ZIP in memory
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        csv_filename = z.namelist()[0]
        logger.info(f"📦 Extracting: {csv_filename}")

        with z.open(csv_filename) as f:
            # Binance aggTrades columns: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
            df = pd.read_csv(
                f,
                header=None,
                names=["id", "price", "qty", "first_id", "last_id", "timestamp", "is_buyer_maker"],
            )

    # Process Data
    logger.info("⚙️ Processing data...")

    # Ensure numeric types
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")

    # Drop invalid rows
    df.dropna(subset=["timestamp", "price", "qty"], inplace=True)

    # Convert timestamp to seconds (from ms)
    df["timestamp"] = df["timestamp"] / 1000.0

    # Determine Side: is_buyer_maker=True -> SELL, False -> BUY
    df["side"] = df["is_buyer_maker"].apply(lambda x: "SELL" if x else "BUY")

    # Rename quantity to volume for consistency
    df.rename(columns={"qty": "volume"}, inplace=True)

    # Select relevant columns
    df = df[["timestamp", "price", "volume", "side"]]

    # Save to CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_filename = f"{symbol}_trades_{year}_{month}.csv"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    df.to_csv(output_path, index=False)
    logger.info(f"✅ Saved: {output_path} ({len(df)} trades)")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Download monthly aggTrades from Binance Vision.")
    parser.add_argument("--symbol", type=str, default="LTCUSDT", help="Symbol (e.g., LTCUSDT)")
    parser.add_argument("--year", type=str, default=None, help="Year (e.g., 2024)")
    parser.add_argument("--month", type=str, default=None, help="Month (e.g., 10)")
    parser.add_argument("--last-month", action="store_true", help="Download last month's data automatically")

    args = parser.parse_args()

    symbol = args.symbol.upper()

    if args.last_month:
        # Calculate last month
        today = datetime.now()
        first = today.replace(day=1)
        last_month_date = first - timedelta(days=1)
        year = str(last_month_date.year)
        month = f"{last_month_date.month:02d}"
    else:
        year = args.year
        month = args.month

    if not year or not month:
        logger.error("❌ Please specify --year and --month, or use --last-month")
        return

    download_monthly_trades(symbol, year, month)


if __name__ == "__main__":
    main()
