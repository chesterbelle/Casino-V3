---
description: Progressive validation pipeline for Slim v8.3 architecture (Atomic → Integration → Orchestration → Edge)
---

# Validate-All: Slim v8.3 Integration Pipeline

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
### Layer 0.B: Absorption Quality Filters Math
```bash
.venv/bin/python utils/validators/absorption_guardian_validator.py
```
### Layer 0.C: SlimExitEngine Pillar Math
```bash
.venv/bin/python utils/validators/exit_engine_validator.py
```
*Validated Pillars*: Scale Out, Micro-Z Reversal.

---

## LAYER 1: PAIRWISE INTEGRATION
### Layer 1.1: Sensor + Footprint (Data Quality)
```bash
# Validates data quality from historical historian.db instead of live memory
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian.db'); print(conn.execute('SELECT COUNT(*) FROM price_samples').fetchone())"
```
*Note: Replaced live integration check with post-mortem data integrity check.*

### Layer 1.2: SlimExitEngine + Croupier (Exit Execution)
```bash
.venv/bin/python utils/validators/exit_engine_integration_validator.py
```

---

## LAYER 2: SUBSYSTEM INTEGRATION
### Layer 2.1: Signal Pipeline
```bash
.venv/bin/python -m utils.validators.decision_pipeline_validator
```
### Layer 2.2: Execution Pipeline (VirtualExchange)
```bash
.venv/bin/python -m utils.validators.trading_flow_validator --execute-orders
```

---

## LAYER 3: ORCHESTRATION (The Slim Engine)
### Layer 3.1: Protocol Determinism
Verify that `orchestrator.py` correctly cleans, executes, and merges.
```bash
# Run a dry-run or quick test of the orchestrator
python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT
```
*Success Criterion*: The historian db `data/historian_LTCUSDT.db` exists, is merged to `data/historian.db`, and `exit_edge_auditor.py` executes successfully.

---

## LAYER 4: STRESS & CHAOS
### Layer 4.1: Chaos Stress Test
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --mode demo
```

---

## LAYER 5: SANITY CHECK
### Layer 5.1: Pipeline Sanity (Single Dataset Audit)
Verify that the complete auditing pipeline (Orchestrator + ExitEdgeAuditor) is functional.
```bash
# Run one single-coin audit to confirm the entire end-to-end pipeline
python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT
```
*Success Criterion*: The auditor completes without error, and a baseline report is generated.
*Note*: Full strategy certification (all assets/datasets) is an independent procedure, not part of this atomic integration test.
