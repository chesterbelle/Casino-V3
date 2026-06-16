#!/usr/bin/env python3
"""Build monthly datasets: download, concatenate, process to .db"""
import gzip
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BuildMonthly")

RAW_DIR = Path("data/datasets/raw")
OUT_DIR = Path("data/datasets/monthly_backtest_ready")
FETCHER = "utils/data/cryptohftdata_fetcher.py"
PROCESSOR = "utils/data/l2_processor.py"
VENV_PYTHON = ".venv/bin/python"
ENV_FILE = Path(".env")

MONTHS = {
    "2026_05": ("2026-05-01", "2026-05-31"),
    "2026_04": ("2026-04-01", "2026-04-30"),
    "2026_03": ("2026-03-01", "2026-03-31"),
}
SYMBOLS = ["LTCUSDT", "SOLUSDT"]
EXCHANGE = "binance-futures"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


def run(cmd: list[str], desc: str):
    logger.info(f"Running: {desc}")
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
        for line in proc.stdout:
            print(line, end="", flush=True)
            if any(kw in line for kw in ["ERROR", "Failed", "Missing", "Error"]):
                logger.warning(line.strip())
    if proc.returncode != 0:
        logger.error(f"Failed: {desc} (exit {proc.returncode})")
        sys.exit(1)


def concat_csv_gz(daily_pattern: str, monthly_file: Path):
    """Concatenate daily CSV.gz files into one monthly file, skipping duplicate headers."""
    daily_files = sorted(RAW_DIR.glob(daily_pattern))
    if not daily_files:
        logger.error(f"No files matching {daily_pattern}")
        return False

    logger.info(f"  Concatenating {len(daily_files)} files into {monthly_file.name}")
    first = True
    with gzip.open(monthly_file, "wt", newline="") as out:
        for f in daily_files:
            with gzip.open(f, "rt") as fh:
                lines = fh.readlines()
                if first:
                    out.writelines(lines)
                    first = False
                else:
                    out.writelines(lines[1:])  # skip header
    size_mb = monthly_file.stat().st_size / 1e6
    logger.info(f"  {monthly_file.name}: {size_mb:.1f} MB")
    return True


def clean_daily(symbol: str, month_start: str, month_end: str):
    """Remove daily files for a given month range."""
    start = datetime.strptime(month_start, "%Y-%m-%d")
    end = datetime.strptime(month_end, "%Y-%m-%d")
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        for suffix in ["trades", "incremental_book_L2"]:
            f = RAW_DIR / f"{EXCHANGE}_{suffix}_{date_str}_{symbol}.csv.gz"
            if f.exists():
                f.unlink()
        current += timedelta(days=1)


def build_month(symbol: str, month_label: str, month_start: str, month_end: str):
    """Download, concatenate, and process one month for one symbol."""
    short_sym = symbol.replace("USDT", "")
    monthly_name = f"{short_sym}_monthly_{month_label}"

    logger.info(f"\n{'='*60}")
    logger.info(f"Building {monthly_name} ({month_start} to {month_end})")
    logger.info(f"{'='*60}")

    # 1. Create output dir
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Download all days of the month
    run(
        [
            VENV_PYTHON,
            FETCHER,
            "--symbol",
            symbol,
            "--start",
            month_start,
            "--end",
            month_end,
            "--exchange",
            EXCHANGE,
        ],
        f"Download {symbol} {month_label}",
    )

    # 3. Concatenate daily files into monthly files
    trades_monthly = RAW_DIR / f"{monthly_name}_trades.csv.gz"
    ob_monthly = RAW_DIR / f"{monthly_name}_incremental_book_L2.csv.gz"

    trades_ok = concat_csv_gz(f"{EXCHANGE}_trades_????-??-??_{symbol}.csv.gz", trades_monthly)
    ob_ok = concat_csv_gz(f"{EXCHANGE}_incremental_book_L2_????-??-??_{symbol}.csv.gz", ob_monthly)

    if not trades_ok or not ob_ok:
        logger.error("Missing files, skipping")
        return

    # 4. Run l2_processor
    db_path = OUT_DIR / f"{monthly_name}.db"
    run(
        [
            VENV_PYTHON,
            PROCESSOR,
            "--name",
            monthly_name,
            "--symbol",
            symbol,
            "--raw-dir",
            str(RAW_DIR),
            "--out-dir",
            str(OUT_DIR),
        ],
        f"Process {monthly_name}",
    )

    # 5. Verify
    if db_path.exists():
        size_mb = db_path.stat().st_size / 1e6
        logger.info(f"✅ {db_path.name}: {size_mb:.1f} MB")
    else:
        logger.error(f"❌ db not created: {db_path}")

    # 6. Clean up daily + monthly raw files
    clean_daily(symbol, month_start, month_end)
    trades_monthly.unlink(missing_ok=True)
    ob_monthly.unlink(missing_ok=True)


def main():
    load_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for symbol in SYMBOLS:
        for month_label, (start, end) in MONTHS.items():
            build_month(symbol, month_label, start, end)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("📊 SUMMARY")
    logger.info(f"{'='*60}")
    if OUT_DIR.exists():
        for f in sorted(OUT_DIR.glob("*.db")):
            size_mb = f.stat().st_size / 1e6
            logger.info(f"  {f.name}: {size_mb:.1f} MB")
    logger.info("\n✅ All monthly datasets built!")


if __name__ == "__main__":
    main()
