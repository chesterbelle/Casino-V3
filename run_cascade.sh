#!/bin/bash
set -e
export PYTHONPATH="/home/chesterbelle/Casino-V3/.venv/lib/python3.14/site-packages:/home/chesterbelle/Casino-V3"
cd /home/chesterbelle/Casino-V3

echo "=== LAYER 1.5: Fast-Track Execution (15m, No Drain Phase) ==="
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track --close-on-exit

echo "=== LAYER 2: Multi-Symbol Concurrency ==="
.venv/bin/python -m utils.validators.multi_symbol_validator --symbols LTCUSDT,DOGEUSDT,ETHUSDT --mode demo --size 500

echo "=== LAYER 3: HFT Latency Benchmark ==="
.venv/bin/python -m utils.validators.hft_latency_benchmark --symbols LTCUSDT,DOGEUSDT --mode demo --size 500 --iterations 3

echo "=== LAYER 4: Chaos Stress Test ==="
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --symbols BTCUSDT,ETHUSDT,LTCUSDT --mode demo --duration 300 --max-ops 15

echo "=== LAYER 4.1: Reactor Pressure Benchmark ==="
.venv/bin/python utils/validators/execution_pressure_benchmark.py --duration 30 --event-freq 2000

echo "=== LAYER 5: Decision Pipeline Data Integrity ==="
.venv/bin/python -m utils.validators.decision_pipeline_validator

echo "✅ ALL PIPELINE LAYERS PASSED SUCCESSFULLY"
