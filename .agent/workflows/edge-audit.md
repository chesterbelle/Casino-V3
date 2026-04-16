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
- **MFE / MAE Ratio**: > 1.2 (Implies structural advantage)
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
We run across multiple assets to prevent overfitting to a single regime.

### 1A: LTC (Volatility/Range)
```bash
.venv/bin/python backtest.py \
  --data tests/validation/ltc_24h_audit.csv \
  --symbol LTC/USDT:USDT \
  --depth-db data/historian.db \
  --audit \
  2>&1 | tee logs/edge_audit_ltc_$(date +%Y%m%d_%H%M%S).log
```

### 1B: SOL (Momentum/Trend)
```bash
.venv/bin/python backtest.py \
  --data tests/validation/sol_24h_audit.csv \
  --symbol SOL/USDT:USDT \
  --depth-db data/historian.db \
  --audit \
  2>&1 | tee logs/edge_audit_sol_$(date +%Y%m%d_%H%M%S).log
```

### 1C: ETH (High Liquidity/Volume)
```bash
.venv/bin/python backtest.py \
  --data tests/validation/eth_24h_audit.csv \
  --symbol ETH/USDT:USDT \
  --depth-db data/historian.db \
  --audit \
  2>&1 | tee logs/edge_audit_eth_$(date +%Y%m%d_%H%M%S).log
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

1. **Present a concise summary table** containing the Setup Types, Sample Size (n), MFE%, MAE%, and Ratio.
2. **Present the Theoretical Win-Rate Matrix** (TP/SL combinations) identically to the auditor output.
3. **Assign a Certification Status** for each setup based on the criteria below.
4. **List highly specific observations** (e.g., "Setup X has great MFE but awful MAE, needs better entry filters", or "Gate Y blocked Z signals, which indicates...").
5. **STOP and wait** for user input. Do not alter any strategy file or run another test without permission.

### Certification Matrix (Decision Logic)

| Setup Type | Condition | Status | Action Required |
|---|---|---|---|
| **Any** | n < 20 | **INSUFFICIENT DATA** | Needs longer backtest or looser baseline filters |
| **Any** | Ratio > 1.2 AND WR > 55% | **CERTIFIED** | Approve for Live Trading configuration |
| **Any** | Ratio > 1.0 AND WR < 50% | **WATCH** | Edge exists but consistency is poor. Optimize structural alignment (e.g., HTF gating). |
| **Any** | Ratio < 1.0 | **FAILED** | Setup is statistical noise. Rework entry logic (delta, imbalance) or deactivate. |
