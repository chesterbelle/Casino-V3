#!/bin/bash
set -e

echo "=== PHASE 1: Fast-Track Demo (15 minutes) ==="
.venv/bin/python reset_data.py
mkdir -p tests/validation/
START_TS=$(date +%s)
echo $START_TS > tests/validation/ft_parity_start.txt
echo "Starting main.py for 15 minutes at $START_TS..."
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track --close-on-exit || true
echo "main.py finished."

echo "=== PHASE 2: Data Extraction ==="
START=$(cat tests/validation/ft_parity_start.txt)
END_TS=$((START + 920))
echo $END_TS > tests/validation/ft_parity_end.txt
cp data/historian.db tests/validation/ft_demo_historian.db
cp data/historian.db-wal tests/validation/ft_demo_historian.db-wal 2>/dev/null || :

.venv/bin/python tests/validation/parity_data_fetcher.py --symbol LTC/USDT:USDT --start $START --end $END_TS --out tests/validation/ft_parity_data.csv

echo "=== PHASE 3: Simulator Replay ==="
.venv/bin/python reset_data.py
.venv/bin/python backtest.py --data tests/validation/ft_parity_data.csv --symbol LTC/USDT:USDT --fast-track --depth-db tests/validation/ft_demo_historian.db
cp data/historian.db tests/validation/ft_backtest_historian.db

echo "=== PHASE 4: Validation ==="
START=$(cat tests/validation/ft_parity_start.txt)
END_TS=$(cat tests/validation/ft_parity_end.txt)
.venv/bin/python tests/validation/parity_validator.py --demo tests/validation/ft_demo_historian.db --backtest tests/validation/ft_backtest_historian.db --start $START --end $END_TS > tests/validation/ft_parity_report.txt
echo "=== WORKFLOW COMPLETE ==="
