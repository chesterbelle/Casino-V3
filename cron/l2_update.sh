#!/usr/bin/env bash
set -e

# Daily L2 & Price Data Ingestion Cron Job
# Run at 02:00 UTC daily via crontab

ROOT_DIR="/home/chesterbelle/Casino-V3"
cd $ROOT_DIR

DB="data/historian.db"
SYMBOLS=("BTCUSDT" "LTCUSDT" "SOLUSDT")

# Use GNU date to get yesterday's date
YESTERDAY=$(date -u -d "yesterday" +"%Y-%m-%d")

echo "Starting daily ingestion for $YESTERDAY..."

for sym in "${SYMBOLS[@]}"; do
  echo "Ingesting $sym..."
  # Note: The download logic in l2_price_ingestor needs actual implementation
  # to fetch from the source URL.
  .venv/bin/python utils/data/l2_price_ingestor.py \
    --symbol "$sym" \
    --download \
    --start "$YESTERDAY" \
    --end   "$YESTERDAY" \
    --db-path "$DB" \
    --source-url "https://data.binance.vision/data/futures/umd/${sym}/depth/"
done

echo "Ingestion complete. Running quick parity check..."
.venv/bin/python scripts/run_workflow.py /paritycheck

echo "Daily update finished successfully."
