#!/bin/bash
echo "Starting Reset Data..."
.venv/bin/python reset_data.py

LOGFILE="logs/stress_test_$(date +%Y%m%d_%H%M%S).log"
echo "Starting 120-minute Multi-Symbol Stress Test (Fast-Track)... Logging to $LOGFILE"
.venv/bin/python main.py --mode demo --symbol MULTI --timeout 120 --fast-track --close-on-exit 2>&1 | tee $LOGFILE

echo "Starting Audit..."
.venv/bin/python utils/audit_logs.py $LOGFILE > logs/stress_test_audit_report.txt 2>&1
echo "Stress Test Pipeline Complete!"
