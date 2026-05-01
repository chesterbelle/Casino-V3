---
description: Audit the FootprintScalper strategy's execution metrics (Limit Sniper fill rates, TP/SL efficiency, slippage, and exit quality) from the historian database.
---

# Phase 650 — Execution Quality & Exit Engine Audit (Single Round)

// turbo-all

## Overview
This protocol performs a **Single Round** validation of the **Execution Quality and Exit Engine**
using the **backtester** against a historical dataset.

**IMPORTANT CONTEXT**: The underlying alpha/edge (the `SetupEngine`) has already been certified via the `edge-audit.md` protocol. Therefore, any deterioration in performance here is assumed to be an **execution or exit parameter issue**, NOT a signal generation issue. **DO NOT MODIFY SETUP ENGINE THRESHOLDS.**

It follows a 3-step sequence: Reset DB → Run Backtest → Analyze.

**⛔ MANDATORY STOP RULE**: After Step 2 (Analyse Results), the agent **MUST STOP COMPLETELY**.
Present results + possible fixes and **wait for explicit user approval** before any further action.
**No iterations, no auto-fixes, no follow-up backtests** without user instruction.

**Goals (overall)**: Win Rate > 55% | Profit Factor > 1.2
**Focus Areas**: Limit Sniper Fill Rate, TP/SL Ratio, Trailing Stop efficiency.

---

## Step 0: Reset DB (Clean Slate)
```bash
.venv/bin/python reset_data.py && .venv/bin/python utils/strategy_audit.py --reset-db
```
**Must output**: `🗑️ DB Reset: N trades removed. Starting clean.`

## Step 1: Run Backtest
Use the largest available dataset for maximum statistical power.
Ensuring the simulation respects the 60-minute warmup period is critical for accurate signal generation.

```bash
.venv/bin/python backtest.py \
  --data tests/validation/long_range/SOL_USDT_USDT_7d.csv \
  --symbol SOL/USDT:USDT \
  --depth-db data/historian.db \
  2>&1 | tee logs/strategy_audit_$(date +%Y%m%d_%H%M%S).log
```

**Expected output**: A BACKTEST V4 RESULTS SUMMARY at the end with trade count.
**Minimum viable sample**: At least 10 trades to proceed to analysis (otherwise mark as INSUFFICIENT DATA).



## Step 2: Analyse Results
```bash
.venv/bin/python utils/strategy_audit.py
```
**Review all 7 sections**:
1. **Edge Metrics** — Is WR ≥ 55% and PF ≥ 1.2? (If failing, check Exit Engine).
2. **Exit Breakdown** — What % are TP hits vs SL hits vs Shadow/VIRTUAL exits?
3. **Early Exit Audit** — Are Shadow SL / VIRTUAL_CLOSE exits eating > 20% of trades?
4. **Execution Quality** — Are trades being filled via Limit Sniper? Is slippage acceptable?
5. **Per-Symbol** — Which symbols are profitable?
6. **Latency** — Is T0→T4 latency < 500ms avg? (May be N/A in backtest)
7. **Verdict** — PASS or FAIL

---

## ⛔ MANDATORY STOP — Present Results and Proposed Fixes

After running Step 2, the agent MUST:

1. **Present a summary table** of all sections (PASS/FAIL per metric).
2. **List specific possible fixes** for each failing metric from the Success Criteria table below.
3. **STOP and wait** for user approval before making any code changes or running another round.

Do NOT auto-apply any fix. Do NOT run another backtest. Wait for explicit instruction.

---

## Execution & Exit Success Criteria (Phase 650)

**CRITICAL RULE**: Do not alter `SetupEngine` logic (e.g., `min_cluster_density`, `delta`, `z_score`, `prox_atr_mult`). The edge is proven. Adjust only Execution (`OrderManager`, `OCOManager`) and Exit (`PositionTracker`, `config.trading`) parameters.

| Metric | Goal | Action if failing (Execution/Exit fixes only) |
|---|---|---|
| **Win Rate** | ≥ 55% | Check if Limit Sniper `OFFSET_PCT` is too aggressive causing missed fills on winners. |
| **Profit Factor** | ≥ 1.2 | Adjust `DEFAULT_TP_PCT` / `DEFAULT_SL_PCT` ratio; Check if Trailing Stop triggers too early. |
| **Early Exit Rate** | ≤ 20% | Widen Shadow SL, disable premature breakeven, or increase cooldown before breakeven triggers. |
| **SL Hit Rate** | ≤ 40% | SL might be too tight for asset volatility. Consider widening structural SL buffer. |
| **Directional Bias** | < 15% gap | Exit logic may be asymmetric; check for directional bugs in trailing or breakeven calculations. |

**Sample size rule (Required)**:
- If total trades < 10: mark as **INSUFFICIENT DATA** — do not report PASS or FAIL.
- If a specific setup has fewer than 20 trades: mark that setup as **INSUFFICIENT DATA**.
