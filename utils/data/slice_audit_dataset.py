#!/usr/bin/env python3
"""
Slice a full monthly trades CSV into a 24h audit window.

Usage:
    python utils/data/slice_audit_dataset.py \
        --input data/raw/LTCUSDT_trades_2024_08.csv \
        --date 2024-08-15 \
        --out tests/validation/ltc_range_24h.csv
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("SliceAuditDataset")


def main():
    parser = argparse.ArgumentParser(description="Slice a 24h window from a monthly trades CSV.")
    parser.add_argument("--input", required=True, help="Path to monthly trades CSV")
    parser.add_argument("--date", required=True, help="Date to slice (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, help="Output file path")
    args = parser.parse_args()

    # Parse date
    try:
        day_start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"❌ Invalid date format: {args.date}. Use YYYY-MM-DD")
        sys.exit(1)

    day_end = day_start + timedelta(days=1)
    start_ts = day_start.timestamp()
    end_ts = day_end.timestamp()

    logger.info(f"📂 Loading {args.input}...")
    df = pd.read_csv(args.input, low_memory=False)

    # Ensure timestamp is numeric
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df.dropna(subset=["timestamp"], inplace=True)

    # Slice the 24h window
    mask = (df["timestamp"] >= start_ts) & (df["timestamp"] < end_ts)
    sliced = df[mask].copy()

    if sliced.empty:
        logger.error(f"❌ No trades found for {args.date}. Check the input file covers this date.")
        sys.exit(1)

    # Ensure output directory exists
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    sliced.to_csv(args.out, index=False)
    logger.info(f"✅ Saved {len(sliced):,} trades → {args.out}")
    logger.info(f"   Price range: {sliced['price'].min():.4f} - {sliced['price'].max():.4f}")
    logger.info(f"   Time range: {args.date} 00:00 UTC → {args.date} 23:59 UTC")


if __name__ == "__main__":
    main()
