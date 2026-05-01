#!/bin/bash
echo "Starting Execution Quality Audit..."
mkdir -p logs/
rm -f logs/demo_exec.log logs/bt_exec.log

echo "Phase 1: Running Demo for 15 minutes..."
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track --close-on-exit > logs/demo_exec.log 2>&1

echo "Phase 2: Running Simulator Replay..."
.venv/bin/python backtest.py --data data/raw/LTCUSDT_trades_1week.csv --symbol LTC/USDT:USDT --limit 5000 --fast-track > logs/bt_exec.log 2>&1

echo "Phase 3: Validating Quality..."
echo -e "\n====================== AUDITORÍA DEMO ======================" > logs/audit_report.txt
.venv/bin/python utils/validators/execution_quality_validator.py logs/demo_exec.log >> logs/audit_report.txt

echo -e "\n==================== AUDITORÍA BACKTEST ====================" >> logs/audit_report.txt
.venv/bin/python utils/validators/execution_quality_validator.py logs/bt_exec.log >> logs/audit_report.txt

echo "Audit Complete. Check logs/audit_report.txt"
