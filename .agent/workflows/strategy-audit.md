---
description: Audit the FootprintScalper strategy's edge metrics (Win Rate, Profit Factor, MFE/MAE proxy) from the historian database.
---

# Phase 650 — Strategy Audit Protocol (Single Round)

// turbo-all

## Overview
This protocol performs a **Single Round** validation of the **FootprintScalper strategy edge**
using the **backtester** against a historical dataset. No live/demo exchange connection required.

It follows a 3-step sequence: Reset DB → Run Backtest → Analyze.

**⛔ MANDATORY STOP RULE**: After Step 2 (Analyse Results), the agent **MUST STOP COMPLETELY**.
Present results + possible fixes and **wait for explicit user approval** before any further action.
**No iterations, no auto-fixes, no follow-up backtests** without user instruction.

**Goals (overall)**: Win Rate > 55% | Profit Factor > 1.2
**Goals (per setup_type)**:
- **reversion**: WR ≥ 55% | PF ≥ 1.2
- **continuation**: WR ≥ 52% | PF ≥ 1.1

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
  --data tests/validation/ltc_24h_audit.csv \
  --symbol LTC/USDT:USDT \
  --depth-db data/historian.db \
  2>&1 | tee logs/strategy_audit_$(date +%Y%m%d_%H%M%S).log
```

**Expected output**: A BACKTEST V4 RESULTS SUMMARY at the end with trade count.
**Minimum viable sample**: At least 10 trades to proceed to analysis (otherwise mark as INSUFFICIENT DATA).

> If `ltc_24h_audit.csv` yields fewer than 10 trades, re-run with `eth_24h_audit.csv`:
> ```bash
> .venv/bin/python backtest.py --data tests/validation/eth_24h_audit.csv --symbol ETH/USDT:USDT --depth-db data/historian.db 2>&1 | tee logs/strategy_audit_$(date +%Y%m%d_%H%M%S).log
> ```

## Step 2: Analyse Results
```bash
.venv/bin/python utils/strategy_audit.py
```
**Review all 7 sections**:
1. **Edge Metrics** — Is WR ≥ 55% and PF ≥ 1.2?
2. **Exit Breakdown** — What % are TP hits vs SL hits vs Shadow/VIRTUAL exits?
3. **Early Exit Audit** — Are Shadow SL / VIRTUAL_CLOSE exits eating > 20% of trades?
4. **Directional Bias** — Is LONG or SHORT significantly better? Consider direction filter.
5. **Per-Symbol** — Which symbols are profitable? Consider disabling underperformers.
6. **Latency** — Is T0→T4 latency < 500ms avg? (May be N/A in backtest)
7. **Verdict** — PASS or FAIL

**Additional required review (setup segmentation)**:
- Report separately for `setup_type=reversion` and `setup_type=continuation`.
- Confirm per-setup goals are met (or mark as FAIL/INSUFFICIENT DATA).
- Confirm confirmation-gate attribution is visible:
  - `confirm_level=True/False` distribution
  - `confirm_micro=True/False` distribution
  - `level_ref` distribution (POC/VAH/VAL/IBH/IBL/None)

---

## ⛔ MANDATORY STOP — Present Results and Proposed Fixes

After running Step 2, the agent MUST:

1. **Present a summary table** of all 7 sections (PASS/FAIL per metric).
2. **List specific possible fixes** for each failing metric (from the Success Criteria table below).
3. **STOP and wait** for user approval before making any code changes or running another round.

Do NOT auto-apply any fix. Do NOT run another backtest. Wait for explicit instruction.

---

## Success Criteria (Phase 650 Goals)

**Important**: Edge metrics (WR, PF, Expectancy) are calculated from **Active Strategy trades only**.
Virtual/drain phase exits (VIRTUAL_CLOSE, DRAIN_*) are excluded as they represent forced exits,
not strategy performance.

| Metric | Goal | Action if failing |
|---|---|---|
| **Win Rate** | ≥ 55% | Tighten entry filters (`min_cluster_density`, delta thresholds) |
| **Profit Factor** | ≥ 1.2 | Adjust TP/SL ratio; check if Shadow SL triggers too early |
| **Early Exit Rate** | ≤ 20% | Widen Shadow SL or increase cooldown before breakeven triggers |
| **Directional Bias** | < 15% gap LONG vs SHORT WR | Add trend filter (HTF alignment) |
| **Latency T0→T4** | < 500ms avg | N/A in backtest mode |

### Setup-Specific Success Criteria (Required)

| Setup Type | Metric | Goal | Action if failing |
|---|---|---|---|
| **reversion** | WR / PF | WR ≥ 55% and PF ≥ 1.2 | Tighten level proximity; increase `prox_atr_mult` strictness; require `level_ref` not None |
| **continuation** | WR / PF | WR ≥ 52% and PF ≥ 1.1 | Tighten microstructure thresholds (`count`, `cluster_density`, `size_ratio`); consider HTF alignment |

**Sample size rule (Required)**:
- If total trades < 10: mark as **INSUFFICIENT DATA** — do not report PASS or FAIL.
- If a specific setup has fewer than 20 trades: mark that setup as **INSUFFICIENT DATA**.
