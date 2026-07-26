---
description: Progressive validation pipeline for Post-Refactor architecture (OrderFlowEngine + Instant/Confirmation)
---

# Validate-All: Integration Pipeline (v9.3)

## Overview
Validation from isolated component math → subsystem integration → orchestration → edge sanity check.
Each layer must pass before proceeding to the next.

## Architecture Philosophy
- **Layer 0 (Atomic)**: Isolated math (No dependencies).
- **Layer 1 (Integration)**: Pairwise component communication.
- **Layer 2 (Pipeline)**: Subsystem signal/execution flow.
- **Layer 3 (Orchestration)**: Protocol automation via `scripts/orchestrator.py`.
- **Layer 4 (Stress)**: Concurrency and pressure benchmarks.
- **Layer 5 (Sanity)**: Pipeline end-to-end functionality check.
- **Layer 6 (Optimization)**: Parameter search validation via `scripts/cluster_optimizer.py`.

---

## LAYER 0: ISOLATED COMPONENT MATH

### Layer 0.A: FootprintRegistry Math
```bash
.venv/bin/python utils/validators/absorption_footprint_validator.py
```
*Tests*: BUY/SELL accumulation, delta calculation, round_price, volume profile, pruning, CVD.

### Layer 0.B: Absorption Quality Filters Math
```bash
.venv/bin/python utils/validators/absorption_guardian_validator.py
```
*Tests*: Z-score, concentration (volume-based), noise ratio, price stagnation (SELL + BUY).

### Layer 0.C: SlimExitEngine Pillar Math
```bash
.venv/bin/python utils/validators/exit_engine_validator.py
```
*Tests*: Profile resolution, Micro-Z Reversal (4 scenarios), Scale Out (4 scenarios), grace period, pending guard.

### Layer 0.D: SignalArbitrator Regime Gating
```bash
.venv/bin/python utils/validators/signal_arbitrator_validator.py
```
*Tests*: TRENDING vs RANGE regime gating, TacticalAbsorption blocking, TrendAcceptance blocking, conflict resolution.

### Layer 0.E: VirtualExchange Fee Accounting
```bash
.venv/bin/python utils/validators/virtual_exchange_fee_validator.py
```
*Tests*: Market/limit fees, entry/exit fee storage, Phase 1200 fix, maker vs taker rates.

---

## LAYER 1: PAIRWISE INTEGRATION

### Layer 1.1: Data Integrity Check
```bash
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian_LTCUSDT.db'); print(f'Signals: {conn.execute(\"SELECT COUNT(*) FROM signals\").fetchone()[0]}, Price Samples: {conn.execute(\"SELECT COUNT(*) FROM price_samples\").fetchone()[0]}')"
```
*Note*: Validates historian database has data from previous backtest run.

### Layer 1.2: SlimExitEngine + Croupier (Exit Execution)
```bash
.venv/bin/python utils/validators/exit_engine_integration_validator.py
```
*Tests*: Pillar priority (one action per tick), status filtering, grace period, callback wiring.

---

## LAYER 2: SUBSYSTEM INTEGRATION

### Layer 2.1: Signal Pipeline (TradeProposal Flow)
```bash
.venv/bin/python -m utils.validators.decision_pipeline_validator
```
*Tests*: 25 concurrent TradeProposals, trace completeness, math correctness, topological correctness, sizing consistency.

### Layer 2.2: Execution Pipeline (VirtualExchange)
```bash
.venv/bin/python -m utils.validators.trading_flow_validator --exchange binance --symbol MULTI
```
*Tests*: Connection, order cancel, OCO bracket, position tracking, close, orphan cleanup, shutdown, error handling. **Requires Binance testnet credentials.**

---

## LAYER 3: ORCHESTRATION (OrderFlowEngine + SignalArbitrator)

### Layer 3.1: Single Coin Audit (Backtest Runner)
```bash
.venv/bin/python scripts/backtest_runner.py --mode audit --symbol LTCUSDT
```
*Success Criterion*: `data/historian.db` exists with signals and price samples.

### Layer 3.2: Multi-Coin Audit (Cluster)
```bash
# All certified symbols via run_non_regression.sh
.venv/bin/bash scripts/run_non_regression.sh
```
*Success Criterion*: All symbols complete without errors, edge maintained.

---

## LAYER 4: STRESS & CHAOS

### Layer 4.1: Chaos Stress Test
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --mode demo
```
*Note*: Requires live exchange connection.

---

## LAYER 5: SANITY CHECK

### Layer 5.1: Pipeline Sanity (Single Dataset Audit)
```bash
.venv/bin/python scripts/backtest_runner.py --mode audit --symbol LTCUSDT
```
*Success Criterion*: Edge auditor completes without error, baseline report generated.

---

## LAYER 6: OPTIMIZATION (Cluster Optimizer Validation)

### Layer 6.1: Param Optimizer (Validate Mode)
```bash
# MID_LIQUID cluster validation via param_optimizer
.venv/bin/python scripts/param_optimizer.py --symbol LTCUSDT --validate-only

# THIN_VOLATILE cluster validation
.venv/bin/python scripts/param_optimizer.py --symbol XRPUSDT --validate-only
```
*Success Criterion*: Optimizer loads profiles and validates without import errors.

### Layer 6.2: Backtest Runner (Full Audit)
```bash
# Full audit via backtest_runner (replaces old cluster_optimizer)
.venv/bin/python scripts/backtest_runner.py --mode audit --symbol LTCUSDT
```
*Success Criterion*: Audit completes, edge auditor generates report, historian DB populated.

---

## PRE-MERGE CHECKLIST (Before merging to `main`)

- [ ] **Layer 0**: All atomic validators pass (0.A through 0.E).
- [ ] **Layer 1**: Data integrity + exit integration pass.
- [ ] **Layer 2**: Signal pipeline validator passes.
- [ ] **Layer 3**: Backtest runner audit passes (single-coin).
- [ ] **Layer 6**: Param optimizer validate mode passes.
- [ ] **No import errors** related to `PressureEngine` (should be `OrderFlowEngine`).
- [ ] **No import errors** related to `decision.scenarios.*` (should use `instant/` and `confirmation/` submodules).

---

## Known Issues
- `minimal_math_validator.py` was deleted (broken import of deleted `decision.aggregator`).
- Layer 4.1 requires live exchange connection — skip in offline/CI environments.
- Layer 2.2 requires Binance testnet credentials — skip without `.env` configuration.

---

## Quick Validation (Offline Only - Pre-Merge)
For environments without exchange access, run Layers 0-3 + Layer 6 (validate-only):
```bash
# Layer 0: All atomic math tests
.venv/bin/python utils/validators/absorption_footprint_validator.py
.venv/bin/python utils/validators/absorption_guardian_validator.py
.venv/bin/python utils/validators/exit_engine_validator.py
.venv/bin/python utils/validators/signal_arbitrator_validator.py
.venv/bin/python utils/validators/virtual_exchange_fee_validator.py

# Layer 1: Data integrity + exit integration
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian_LTCUSDT.db'); print(f'Signals: {conn.execute(\"SELECT COUNT(*) FROM signals\").fetchone()[0]}, Price Samples: {conn.execute(\"SELECT COUNT(*) FROM price_samples\").fetchone()[0]}')"
.venv/bin/python utils/validators/exit_engine_integration_validator.py

# Layer 2: Signal pipeline
.venv/bin/python -m utils.validators.decision_pipeline_validator

# Layer 3: Backtest runner audit (single-coin)
.venv/bin/python scripts/backtest_runner.py --mode audit --symbol LTCUSDT

# Layer 6: Param optimizer (validate)
.venv/bin/python scripts/param_optimizer.py --symbol LTCUSDT --validate-only
```

**All layers must pass before merge.**
