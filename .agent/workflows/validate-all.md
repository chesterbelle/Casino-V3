---
description: Multi-layered validation pipeline for Phase 800 TP/SL architecture (4 layers, ~20 min total)
---

# Multi-Layered Validation Pipeline

// turbo-all

## Overview
Progressive validation from basic sanity → latency benchmarks → chaos stress.
Each layer must pass before proceeding to the next.

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

## Layer 4: Chaos Stress Test
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --symbols BTCUSDT,ETHUSDT,LTCUSDT --mode demo --duration 300 --max-ops 15
```
**Must pass**: 0 UNMATCHED events, Error Recovery = $0, Integrity ✅

### Layer 4 Verification (Protocol V2)
// turbo
```bash
.venv/bin/python utils/audit_logs.py logs/chaos_test_$(ls -t logs/ | head -1)
```

## Success Criteria
- [x] Layer 1: 8/8 preflight tests pass
- [x] Layer 2: Multi-symbol concurrency + integrity pass
- [x] Layer 3: Bracket latency < 500ms avg, TP/SL parallel
- [x] Layer 4: 0 UNMATCHED, 0 error trades, clean integrity
- [x] Statistical Health: Audit V2 PASS (Ratio < 1.5, 0 Ghosts)
