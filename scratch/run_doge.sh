#!/bin/bash
echo "Resetting historian DB..."
rm -f data/historian.db

echo "Running DOGE RANGE..."
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_RANGE_2024-02-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_RANGE_2024-06-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_RANGE_2024-11-01.db --symbol DOGEUSDT --audit

echo "Running DOGE BEAR..."
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BEAR_2024-04-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BEAR_2024-09-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BEAR_2025-02-01.db --symbol DOGEUSDT --audit

echo "Running DOGE BULL..."
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BULL_2024-03-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BULL_2025-01-01.db --symbol DOGEUSDT --audit
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/DOGE_BULL_2025-05-01.db --symbol DOGEUSDT --audit

echo "Running Audit..."
.venv/bin/python utils/analysis/per_condition_audit.py > logs/doge_audit.log
