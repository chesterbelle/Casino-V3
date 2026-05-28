---
description: Progressive validation pipeline for Slim v8.5 architecture (Atomic → Integration → Orchestration → Edge)
---

# Validate-All: Slim v8.5 Integration Pipeline

## Overview
Validation from isolated component math → subsystem integration → orchestration → full edge sanity check.
Each layer must pass before proceeding to the next.

## Architecture Philosophy
- **Layer 0 (Atomic)**: Isolated math (No dependencies).
- **Layer 1 (Integration)**: Pairwise component communication.
- **Layer 2 (Pipeline)**: Subsystem signal/execution flow.
- **Layer 3 (Orchestration)**: Protocol automation via `scripts/orchestrator.py`.
- **Layer 4 (Stress)**: Concurrency and pressure benchmarks.
- **Layer 5 (Sanity)**: Pipeline end-to-end functionality check.

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

### Layer 0.D: Regime Guardian Decision Matrix
```bash
.venv/bin/python utils/validators/regime_guardian_validator.py
```
*Tests*: 7-case TREND matrix + BALANCE logic + Z-score disambiguation.

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
.venv/bin/python -m utils.validators.trading_flow_validator --execute-orders
```
*Tests*: Connection, order cancel, OCO bracket, position tracking, close, orphan cleanup, shutdown, error handling. **Requires Binance testnet credentials.**

---

## LAYER 3: ORCHESTRATION (The Slim Engine)

### Layer 3.1: Protocol Determinism
```bash
.venv/bin/python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT
```
*Success Criterion*: `data/historian_LTCUSDT.db` exists with signals and price samples.

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
.venv/bin/python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT
```
*Success Criterion*: Edge auditor completes without error, baseline report generated.

---

## Known Issues
- `minimal_math_validator.py` was deleted (broken import of deleted `decision.aggregator`).
- Layer 4.1 requires live exchange connection — skip in offline/CI environments.
- Layer 2.2 requires Binance testnet credentials — skip without `.env` configuration.

---

## Quick Validation (Offline Only)
For environments without exchange access, run Layers 0-2 only:
```bash
# Layer 0: All atomic math tests
.venv/bin/python utils/validators/absorption_footprint_validator.py
.venv/bin/python utils/validators/absorption_guardian_validator.py
.venv/bin/python utils/validators/exit_engine_validator.py
.venv/bin/python utils/validators/regime_guardian_validator.py
.venv/bin/python utils/validators/virtual_exchange_fee_validator.py

# Layer 1: Data integrity + exit integration
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian_LTCUSDT.db'); print(f'Signals: {conn.execute(\"SELECT COUNT(*) FROM signals\").fetchone()[0]}, Price Samples: {conn.execute(\"SELECT COUNT(*) FROM price_samples\").fetchone()[0]}')"
.venv/bin/python utils/validators/exit_engine_integration_validator.py

# Layer 2: Signal pipeline
.venv/bin/python -m utils.validators.decision_pipeline_validator
```
