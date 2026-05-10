#!/usr/bin/env python3
"""
Extrae un sub-período de un archivo de trades descargado.
Útil para crear datasets de condiciones de mercado específicas
(range, bull, bear) desde archivos mensuales de Binance Vision.

Uso:
    python3 utils/data/extract_period.py \
        --input data/raw/LTCUSDT_trades_2024_11.csv \
        --start "2024-11-01" \
        --end "2024-11-15" \
        --output tests/validation/market_regimes/ltc_range_audit.csv
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ExtractPeriod")


def parse_date_to_ts(date_str: str) -> float:
    """Parse YYYY-MM-DD to UTC timestamp."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.timestamp()


def main():
    parser = argparse.ArgumentParser(description="Extract a time period from a trades CSV.")
    parser.add_argument("--input", required=True, help="Input CSV file (timestamp, price, volume, side)")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    start_ts = parse_date_to_ts(args.start)
    end_ts = parse_date_to_ts(args.end)

    logger.info(f"📂 Loading {input_path.name}...")
    df = pd.read_csv(input_path, low_memory=False)

    # Ensure timestamp is numeric
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df.dropna(subset=["timestamp"], inplace=True)

    # Filter by period
    mask = (df["timestamp"] >= start_ts) & (df["timestamp"] < end_ts)
    filtered = df[mask].copy()

    if filtered.empty:
        logger.error(f"❌ No trades found between {args.start} and {args.end}")
        sys.exit(1)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(output_path, index=False)

    duration_days = (end_ts - start_ts) / 86400
    logger.info(f"✅ Saved {len(filtered):,} trades ({duration_days:.0f} days) → {output_path.name}")


if __name__ == "__main__":
    main()
