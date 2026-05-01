#!/bin/bash
# Phase 1200: Monthly Edge Validation (LTC/USDT January 2026)

set -e

# Phase 1205: Stability fix for Python 3.14 on Zen 2 (No AVX-512)
export PYTHON_JIT=0

DATASET="./data/raw/LTCUSDT_trades_2026_01.csv"
DB="data/historian.db"
LOG="monthly_audit.log"

echo "🧹 [1/3] Resetting environment..."
.venv/bin/python reset_data.py
.venv/bin/python utils/strategy_audit.py --reset-db

echo "🚀 [2/3] Starting Monthly Backtest (3.0M trades)..."
echo "Note: This may take 15-25 minutes."
.venv/bin/python backtest.py \
    --data "$DATASET" \
    --symbol LTC/USDT:USDT \
    --depth-db "$DB" \
    --fast-track 2>&1 | tee "$LOG"

echo "📊 [3/3] Generating Monthly Strategy Audit Report..."
.venv/bin/python utils/strategy_audit.py 2>&1 | tee monthly_audit_results.txt

echo "✅ Monthly Audit Complete. Results in monthly_audit_results.txt"
