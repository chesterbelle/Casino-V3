#!/usr/bin/env python3
"""
CryptoHFTData Validator for Casino-V3
Compares CryptoHFTData downloads against Tardis data to validate integrity.

Usage:
    python utils/data/validate_cryptohftdata.py \
        --tardis-file data/datasets/raw/binance-futures_incremental_book_L2_2024-01-01_LTCUSDT.csv.gz \
        --crypto-file data/datasets/raw/binance-futures_incremental_book_L2_2024-01-01_LTCUSDT.csv.gz
"""

import argparse
import gzip
import logging
from pathlib import Path

import pandas as pd

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message>s")
logger = logging.getLogger("CryptoHFTDataValidator")


def load_csv_gz(filepath: str) -> pd.DataFrame:
    """Load a gzipped CSV file."""
    with gzip.open(filepath, "rt") as f:
        return pd.read_csv(f)


def compare_orderbook(tardis_file: str, crypto_file: str) -> dict:
    """
    Compare two order book files.

    Returns:
        Dictionary with comparison metrics
    """
    logger.info(f"Loading Tardis file: {tardis_file}")
    df_tardis = load_csv_gz(tardis_file)

    logger.info(f"Loading CryptoHFTData file: {crypto_file}")
    df_crypto = load_csv_gz(crypto_file)

    metrics = {
        "tardis_rows": len(df_tardis),
        "crypto_rows": len(df_crypto),
        "row_diff": abs(len(df_tardis) - len(df_crypto)),
        "row_diff_pct": abs(len(df_tardis) - len(df_crypto)) / len(df_tardis) * 100 if len(df_tardis) > 0 else 0,
    }

    # Check column names
    tardis_cols = set(df_tardis.columns)
    crypto_cols = set(df_crypto.columns)
    metrics["tardis_cols"] = list(tardis_cols)
    metrics["crypto_cols"] = list(crypto_cols)
    metrics["cols_match"] = tardis_cols == crypto_cols
    metrics["cols_missing_in_crypto"] = list(tardis_cols - crypto_cols)
    metrics["cols_extra_in_crypto"] = list(crypto_cols - tardis_cols)

    # If timestamps exist, compare coverage
    if "timestamp" in df_tardis.columns and "timestamp" in df_crypto.columns:
        tardis_start = df_tardis["timestamp"].min()
        tardis_end = df_tardis["timestamp"].max()
        crypto_start = df_crypto["timestamp"].min()
        crypto_end = df_crypto["timestamp"].max()

        metrics["tardis_time_range"] = f"{tardis_start} to {tardis_end}"
        metrics["crypto_time_range"] = f"{crypto_start} to {crypto_end}"
        metrics["time_range_match"] = tardis_start == crypto_start and tardis_end == crypto_end

    # Sample comparison (first 100 rows)
    if len(df_tardis) > 0 and len(df_crypto) > 0:
        sample_tardis = df_tardis.head(100).to_dict()
        sample_crypto = df_crypto.head(100).to_dict()

        # Count matching values
        matching = 0
        total = 0
        for col in tardis_cols & crypto_cols:
            if col in sample_tardis and col in sample_crypto:
                for i in range(min(100, len(df_tardis), len(df_crypto))):
                    total += 1
                    if sample_tardis[col].get(i) == sample_crypto[col].get(i):
                        matching += 1

        metrics["sample_match_pct"] = matching / total * 100 if total > 0 else 0

    return metrics


def compare_trades(tardis_file: str, crypto_file: str) -> dict:
    """
    Compare two trade files.

    Returns:
        Dictionary with comparison metrics
    """
    return compare_orderbook(tardis_file, crypto_file)  # Same logic works for trades


def print_report(metrics: dict, data_type: str):
    """Print a formatted comparison report."""
    print("\n" + "=" * 60)
    print(f"📊 {data_type.upper()} COMPARISON REPORT")
    print("=" * 60)

    print(f"\n📏 Row Counts:")
    print(f"   Tardis:       {metrics['tardis_rows']:,}")
    print(f"   CryptoHFT:    {metrics['crypto_rows']:,}")
    print(f"   Difference:   {metrics['row_diff']:,} ({metrics['row_diff_pct']:.2f}%)")

    print(f"\n📋 Columns:")
    print(f"   Match:        {'✅' if metrics['cols_match'] else '❌'}")
    if metrics["cols_missing_in_crypto"]:
        print(f"   Missing:      {metrics['cols_missing_in_crypto']}")
    if metrics["cols_extra_in_crypto"]:
        print(f"   Extra:        {metrics['cols_extra_in_crypto']}")

    if "time_range_match" in metrics:
        print(f"\n⏱️  Time Range:")
        print(f"   Tardis:       {metrics['tardis_time_range']}")
        print(f"   CryptoHFT:    {metrics['crypto_time_range']}")
        print(f"   Match:        {'✅' if metrics['time_range_match'] else '⚠️'}")

    if "sample_match_pct" in metrics:
        match_emoji = "✅" if metrics["sample_match_pct"] > 95 else "⚠️" if metrics["sample_match_pct"] > 80 else "❌"
        print(f"\n🔍 Sample Match: {metrics['sample_match_pct']:.1f}% {match_emoji}")

    # Verdict
    print("\n" + "-" * 60)
    if metrics["row_diff_pct"] < 5 and metrics.get("sample_match_pct", 0) > 95:
        print("✅ VERDICT: Data appears VALID and consistent with Tardis")
    elif metrics["row_diff_pct"] < 10 and metrics.get("sample_match_pct", 0) > 80:
        print("⚠️  VERDICT: Data has minor differences - review before use")
    else:
        print("❌ VERDICT: Data has significant differences - do not use")
    print("-" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Validate CryptoHFTData downloads against Tardis reference data")
    parser.add_argument(
        "--tardis-file",
        required=True,
        help="Path to Tardis reference file (.csv.gz)",
    )
    parser.add_argument(
        "--crypto-file",
        required=True,
        help="Path to CryptoHFTData file to validate (.csv.gz)",
    )
    parser.add_argument(
        "--type",
        choices=["orderbook", "trades"],
        default="orderbook",
        help="Data type being compared",
    )

    args = parser.parse_args()

    # Validate files exist
    if not Path(args.tardis_file).exists():
        logger.error(f"Tardis file not found: {args.tardis_file}")
        return

    if not Path(args.crypto_file).exists():
        logger.error(f"CryptoHFTData file not found: {args.crypto_file}")
        return

    # Run comparison
    if args.type == "orderbook":
        metrics = compare_orderbook(args.tardis_file, args.crypto_file)
    else:
        metrics = compare_trades(args.tardis_file, args.crypto_file)

    # Print report
    print_report(metrics, args.type)


if __name__ == "__main__":
    main()
