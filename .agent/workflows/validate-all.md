---
description: Multi-layered validation pipeline for Phase 800 TP/SL architecture (5 layers, ~20 min total)
---

# Multi-Layered Validation Pipeline

// turbo-all

## Overview
Progressive validation from basic sanity → latency benchmarks → chaos stress.
Each layer must pass before proceeding to the next.

## Layer 0: Static Math & Regime Gating (Strategy 2.0)
```bash
.venv/bin/python utils/validators/sensor_math_validator.py
```
**Must pass**: All regime scenarios (TREND/RANGE) must calculate correct multipliers and targets without math inversion.

## Layer 0.1: Z-Score Math Precision (Strategy 2.0)
```bash
.venv/bin/python utils/validators/zscore_math_validator.py
```
**Must pass**: Z-Score calculation, sliding window, and outlier logic must stay robust.

## Layer 0.2: Micro-Exits Logic (Strategy 2.0)
```bash
.venv/bin/python utils/validators/micro_exits_validator.py
```
**Must pass**: Liquidity pull and Delta inversion burst detection must target exits properly.

## Layer 0.3: Setup Data Integrity (Phase 975)
```bash
.venv/bin/python utils/validators/setup_data_validator.py
```
**Must pass**: All setup playbooks (DeltaDivergence, TrappedTraders, FadeExtreme, TrendContinuation) must produce valid `tp_price` and `sl_price` in metadata. No setup should return with missing or zero TP/SL values.

## Layer 1: Preflight (Single-Symbol Lifecycle)
```bash
.venv/bin/python -m utils.validators.trading_flow_validator --exchange binance --symbol LTCUSDT --mode demo --size 0.05 --execute-orders
```
**Must pass**: 8/8 tests (CONNECTION → ORDER → OCO → TRACKING → CLOSE → ORPHAN → SHUTDOWN → ERROR)

## Layer 2: Multi-Symbol Concurrency
```bash
.venv/bin/python -m utils.validators.multi_symbol_validator --symbols LTCUSDT,DOGEUSDT,ETHUSDT --mode demo --size 500
```
**Must pass**: CONCURRENCY ✅ + INTEGRITY ✅

## Layer 3: HFT Latency Benchmark (Phase 240)
```bash
.venv/bin/python -m utils.validators.hft_latency_benchmark --symbols LTCUSDT,DOGEUSDT --mode demo --size 500 --iterations 3
```
**Must pass**: BRACKET_LATENCY ✅ (avg < 500ms), TP_SL_PARALLEL ✅, CACHE_HIT ✅

## Layer 4: Chaos Stress Test (Stall-Aware)
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --symbols BTCUSDT,ETHUSDT,LTCUSDT --mode demo --duration 300 --max-ops 15
```
**Must pass**: 0 UNMATCHED events, 0 Task Stalls (Watchdog), Error Recovery = $0, Integrity ✅

## Layer 4.1: Reactor Pressure Benchmark (Execution Health)
```bash
.venv/bin/python utils/validators/execution_pressure_benchmark.py --duration 30 --event-freq 2000
```
**Must pass**: Max Jitter < 100ms, 0 Systemic Stalls.

### Layer 4 Verification (Protocol V2)
// turbo
```bash
.venv/bin/python utils/audit_logs.py logs/chaos_test_$(ls -t logs/ | head -1)
```

## Layer 5: Decision Pipeline Data Integrity (Zero-Lag Check)
```bash
.venv/bin/python -m utils.validators.decision_pipeline_validator
```
**Must pass**: 0 FATAL MATH INVERSION, 0 PIPELINE LEAK DETECTED, Context Mirror Integrity ✅.

## Success Criteria
- [x] Layer 0: Strategy 2.0 Math & Regime logic verified.
- [x] Layer 0.1: Z-Score Math and Outlier logic verified.
- [x] Layer 0.2: Micro-Exits Logic verified.
- [x] Layer 1: 8/8 preflight tests pass.
- [x] Layer 2: Multi-symbol concurrency + integrity pass.
- [x] Layer 3: Bracket latency < 500ms avg, TP/SL parallel.
- [x] Layer 4: 0 UNMATCHED, 0 Task Stalls, clean integrity.
- [/] Layer 4.1: Reactor Pressure < 100ms jitter.
- [x] Layer 5: 0 Mutations under chaos (Zero-Lag Mirror verified).
- [x] Statistical Health: Audit V2 PASS (Ratio < 1.5, 0 Ghosts)
