#!/usr/bin/env python3
"""
Tardis Fetcher for Casino-V3
Downloads high-fidelity L2 and Trade data from Tardis.dev and stores them in data/datasets/raw/
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta

from tardis_dev import download_datasets_async

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("TardisFetcher")


async def main():
    parser = argparse.ArgumentParser(description="Download high-fidelity datasets from Tardis.dev")
    parser.add_argument("--symbol", required=True, help="Trading pair symbol (e.g. LTCUSDT)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), defaults to start + 1 day")
    parser.add_argument(
        "--exchange", default="binance-futures", help="Exchange name in Tardis (default: binance-futures)"
    )
    parser.add_argument("--types", nargs="+", default=["incremental_book_L2", "trades"], help="Data types to download")
    parser.add_argument("--out-dir", default="data/datasets/raw", help="Directory to save downloaded files")

    args = parser.parse_args()

    # Calculate end date if not provided
    start_date_obj = datetime.strptime(args.start, "%Y-%m-%d")
    if args.end:
        end_date_obj = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end_date_obj = start_date_obj + timedelta(days=1)

    os.makedirs(args.out_dir, exist_ok=True)

    logger.info(f"🚀 Starting download for {args.symbol} from {args.exchange}")
    logger.info(f"📅 Range: {args.start} to {end_date_obj.strftime('%Y-%m-%d')}")
    logger.info(f"📂 Saving to: {args.out_dir}")

    try:
        await download_datasets_async(
            exchange=args.exchange,
            data_types=args.types,
            from_date=args.start,
            to_date=end_date_obj.strftime("%Y-%m-%d"),
            symbols=[args.symbol],
            download_dir=args.out_dir,
        )
        logger.info("✅ Download complete.")
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
