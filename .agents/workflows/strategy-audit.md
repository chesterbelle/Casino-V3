---
description: Audit the FootprintScalper strategy's edge metrics (Win Rate, Profit Factor, MFE/MAE proxy) from the historian database.
---

# Phase 650 — Strategy Audit Protocol

// turbo-all

## Overview
This protocol validates whether the **FootprintScalper strategy has a positive edge**.
It resets the database first (clean session), runs the bot for a fixed window, then audits the results.

**Goals**: Win Rate > 55% | Profit Factor > 1.2

---

## Step 0: Reset DB (Clean Slate)
```bash
.venv/bin/python utils/strategy_audit.py --reset-db
```
**Must output**: `🗑️ DB Reset: N trades removed. Starting clean.`

## Step 1: Run the Bot (30-minute forward test)
```bash
.venv/bin/python main.py --mode demo --symbol MULTI --timeout 30 --close-on-exit 2>&1 | tee logs/strategy_audit_$(date +%Y%m%d_%H%M%S).log
```
Wait for the bot to run for **30 minutes** to collect at least 10-20 real FootprintScalper trades.
The bot will stop automatically after 30 minutes (1800 seconds).

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
7. **Verdict** — ✅ PASS or ❌ FAIL

---

## Success Criteria (Phase 650 Goals)

| Metric | Goal | Action if failing |
|---|---|---|
| **Win Rate** | ≥ 55% | Tighten entry filters (`min_cluster_density`, delta thresholds) |
| **Profit Factor** | ≥ 1.2 | Adjust TP/SL ratio; check if Shadow SL triggers too early |
| **Early Exit Rate** | ≤ 20% | Widen Shadow SL or increase cooldown before breakeven triggers |
| **Directional Bias** | < 15% gap LONG vs SHORT WR | Add trend filter (HTF alignment) |
| **Latency T0→T4** | < 500ms avg | Check DOM scan loop; review `absorption.py` cache size |
