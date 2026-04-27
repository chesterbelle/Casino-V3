---
description: Protocolo para certificar el Alpha/Edge de los Setups usando el Auditor de Interferencia Cero
---
# Phase 800 — Edge Audit Protocol (Zero-Interference Certification)

// turbo-all

## Overview
This protocol performs a rigorous, purely statistical validation of the **predictive power (Edge)**
of tactical setups in Casino-V3. It runs a zero-interference simulation (no active risk management exits)
to capture pristine price trajectories and compute MFE (Maximum Favorable Excursion) vs MAE (Maximum Adverse Excursion).

It follows a 4-step sequence: Nuclear Reset → Run Backtests (Multi-Asset) → Statistical Extraction → Decision.

**⛔ MANDATORY STOP RULE**: After Step 3 (Statistical Extraction), the agent **MUST STOP COMPLETELY**.
Present results + specific observations and **wait for explicit user approval** before any further action.
**No iterations, no auto-fixes, no follow-up backtests** without user instruction.

**Goals (Overall)**: Total Signals Audited ≥ 50
**Goals (Per setup_type)**:
- **Gross Expectancy**: > 0.36% (3× taker fees = viable with any order type)
- **Gross Expectancy**: > 0.12% (viable with maker orders / Limit Sniper)
- **MFE / MAE Ratio**: > 1.2 (Structural advantage indicator)
- **Theoretical Win Rate**: > 55% at 0.3% TP / 0.3% SL

---

## Step 0: Nuclear Reset (Clean Slate)
Wipe all databases and states to ensure zero data leakage.
```bash
.venv/bin/python reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Run Zero-Interference Backtests
Run the backtester with the `--audit` flag to record raw signals and price samples.
We run exclusively on the LTC audit dataset for consistent comparison.

### 1A: LTC (Primary Audit Dataset)
```bash
.venv/bin/python backtest.py \
  --data tests/validation/ltc_24h_audit.csv \
  --symbol LTC/USDT:USDT \
  --depth-db data/historian.db \
  --audit \
  2>&1 | tee logs/edge_audit_ltc_$(date +%Y%m%d_%H%M%S).log
```

## Step 2: Verify Data Collection
```bash
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian.db'); s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]; p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]; d = conn.execute('SELECT COUNT(*) FROM decision_traces').fetchone()[0] if conn.execute('''SELECT count(name) FROM sqlite_master WHERE type='table' AND name='decision_traces' ''').fetchone()[0] == 1 else 0; print(f'Signals: {s}, Price Samples: {p}, Traces: {d}')"
```
**Must output**: Signals >= 80. If fewer, mark as INSUFFICIENT DATA.

## Step 3: Statistical Extraction (MFE/MAE)
Run the Edge Auditor tool.
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 900
```
Review the output for **[1] SETUP EDGE BREAKDOWN**, **[2] THEORETICAL WIN-RATE**, and **[4] DECISION TRACE AUDIT**.

---

## ⛔ MANDATORY STOP — Present Results and Certification Status

After running Step 3, the agent MUST:

1. **Present Section [1B]: Gross Expectancy** - The PRIMARY metric for edge validation
2. **Present Section [5]: Overall Edge Summary** - Aggregate metrics and viability assessment
3. **Present the Theoretical Win-Rate Matrix** (Section [2]) with Net (Taker) and Net (Maker)
4. **Assign a Certification Status** for each setup based on the criteria below
5. **List highly specific observations** (e.g., "Setup X has Expectancy 0.15% but needs Limit Sniper", "MAE too high, tighten entry filters")
6. **STOP and wait** for user input. Do not alter any strategy file or run another test without permission.

### Certification Matrix (Decision Logic) — UPDATED Phase 800B

**PRIMARY METRIC: Gross Expectancy (%)** = (WR × Avg_Win) - (LR × Avg_Loss)

| Setup Type | Condition | Status | Action Required |
|---|---|---|---|
| **Any** | n < 20 | **INSUFFICIENT DATA** | Needs longer backtest or looser baseline filters |
| **Any** | Expectancy > 0.36% AND WR > 55% | **CERTIFIED** | Viable with any order type. Approve for Live Trading. |
| **Any** | Expectancy > 0.12% AND WR > 50% | **WATCH** | Viable ONLY with Limit Sniper (maker entries). Enable in config. |
| **Any** | Expectancy < 0.12% | **FAILED** | Not viable after fees. Rework entry filters (reduce MAE) or exit timing (capture more MFE). |

**SECONDARY METRICS** (for diagnosis):
- **Ratio > 1.2**: Structural advantage exists (but check Expectancy for viability)
- **MFE >> MAE**: Good signal quality, may need better exit timing
- **MAE high**: Entry filters too loose, add structural gates
