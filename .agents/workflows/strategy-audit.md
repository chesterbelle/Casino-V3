---
description: Audit the FootprintScalper strategy's edge metrics (Win Rate, Profit Factor, MFE/MAE proxy) from the historian database.
---

# Phase 650 — Strategy Audit Protocol (Single Round)

// turbo-all

## Overview
This protocol performs a **Single Round** validation of the **FootprintScalper strategy edge**.
It follows a 4-step sequence: Clean Exchange → Reset → Run → Analyze.
After Step 3, the agent **MUST STOP** and report the result. No further actions or iterations without user approval.

**Goals (overall)**: Win Rate > 55% | Profit Factor > 1.2
**Goals (per setup_type)**:
- **reversion**: WR ≥ 55% | PF ≥ 1.2
- **continuation**: WR ≥ 52% | PF ≥ 1.1

---

## Step -1: Clean Exchange (Remove Orphans)
**CRITICAL**: This step prevents orphan positions from triggering PortfolioGuard CRITICAL state.

```bash
.venv/bin/python utils/emergency_cleanup.py
```
**Must output**: `✨ Cleanup complete!`

This script:
1. Fetches ALL active symbols with positions/orders
2. Cancels ALL open orders
3. Closes ALL open positions (market)

**Why**: Orphan positions from previous runs are processed as losses by Reconciliation, incrementing the PortfolioGuard loss streak counter and potentially triggering CRITICAL state before the audit even starts.

## Step 0: Reset DB (Clean Slate)
```bash
.venv/bin/python utils/strategy_audit.py --reset-db
```
**Must output**: `🗑️ DB Reset: N trades removed. Starting clean.`

## Step 1: Run the Bot (150-minute forward test)
```bash
.venv/bin/python main.py --mode demo --symbol MULTI --timeout 150 --close-on-exit 2>&1 | tee logs/strategy_audit_$(date +%Y%m%d_%H%M%S).log
```
Wait for the bot to run for **150 minutes** to collect real FootprintScalper trades.
The bot will stop automatically after 150 minutes.

## Step 2: Analyse Results
```bash
.venv/bin/python utils/strategy_audit.py
```
**Review all 7 sections**:
1. **Edge Metrics** — Is WR ≥ 55% and PF ≥ 1.2?
2. **Exit Breakdown** — What % are TP hits vs SL hits vs Recon/Shadow exits?
3. **Early Exit Audit** — Are Shadow SL / Recon exits eating > 20% of trades?
4. **Directional Bias** — Is LONG or SHORT significantly better? Consider direction filter.
5. **Per-Symbol** — Which symbols are profitable? Consider disabling underperformers.
6. **Latency** — Is T0→T4 latency still < 500ms avg?
7. **Verdict** — PASS or FAIL

**Additional required review (setup segmentation)**:
- Confirm results are reported separately for `setup_type=reversion` and `setup_type=continuation`.
- Confirm the per-setup goals above are met (or mark as FAIL/INSUFFICIENT DATA).
- Confirm confirmation-gate attribution is visible:
  - `confirm_level=True/False` distribution
  - `confirm_micro=True/False` distribution
  - `level_ref` distribution (POC/VAH/VAL/IBH/IBL/None)

## Step 3: Execution Cleanliness Log Scan (Regression Guard)
This step is mandatory to ensure that strategy changes did not break execution telemetry or introduce noisy/wrong behavior.

1) Scan `bot.log` for key regression signatures:
```bash
rg -n "missing price metadata for level confirmation|Fast-track confirmed|continuation_requires_micro|reversion_requires_level|Traceback|ERROR|CRITICAL" bot.log | tail -n 200
```

1b) Summarize `bot.log` using the Strategy Log Audit helper (parses fast-track confirmations + regression signatures):
```bash
.venv/bin/python utils/strategy_audit.py --log "bot.log"
```

2) Scan the most recent strategy audit run log for errors and shutdown cleanliness:
```bash
rg -n "Traceback|ERROR|CRITICAL|Exception|leaked semaphore|resource_tracker" logs/strategy_audit_*.log | tail -n 200
```

2b) Summarize the most recent strategy audit run logs using the Strategy Log Audit helper:
```bash
.venv/bin/python utils/strategy_audit.py --log "logs/strategy_audit_*.log"
```

**Must pass**:
- No `Signal <Sensor> missing price metadata for level confirmation.` occurrences.
- No Python tracebacks.
- No repeated CRITICAL execution errors.

---

## Success Criteria (Phase 650 Goals)

| Metric | Goal | Action if failing |
|---|---|---|
| **Win Rate** | ≥ 55% | Tighten entry filters (`min_cluster_density`, delta thresholds) |
| **Profit Factor** | ≥ 1.2 | Adjust TP/SL ratio; check if Shadow SL triggers too early |
| **Early Exit Rate** | ≤ 20% | Widen Shadow SL or increase cooldown before breakeven triggers |
| **Directional Bias** | < 15% gap LONG vs SHORT WR | Add trend filter (HTF alignment) |
| **Latency T0→T4** | < 500ms avg | Check DOM scan loop; review `absorption.py` cache size |

### Setup-Specific Success Criteria (Required)

| Setup Type | Metric | Goal | Action if failing |
|---|---|---|---|
| **reversion** | WR / PF | WR ≥ 55% and PF ≥ 1.2 | Tighten level proximity; increase `prox_atr_mult` strictness; require `level_ref` not None |
| **continuation** | WR / PF | WR ≥ 52% and PF ≥ 1.1 | Tighten microstructure thresholds (`count`, `cluster_density`, `size_ratio`); consider HTF alignment |

**Sample size rule (Required)**:
- If a setup has fewer than 20 trades, mark that setup as **INSUFFICIENT DATA** (not PASS).
