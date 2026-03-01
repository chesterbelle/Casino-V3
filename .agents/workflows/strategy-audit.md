---
description: Audit the FootprintScalper strategy's edge metrics (Win Rate, Profit Factor, MFE/MAE proxy) from the historian database.
---

# Phase 650 — Strategy Audit Protocol

// turbo-all

## Overview
This protocol validates whether the FootprintScalper strategy has a **positive edge**.
It must be run periodically during live forward-testing to measure progress towards the Phase 650 goals:
- **Win Rate > 55%**
- **Profit Factor > 1.2**

> **Important:** This is NOT an infrastructure test. It tests if the **strategy makes money**.
> Run `/validate-all` first to confirm the engine is healthy. Then run this to assess profitability.

---

## Step 1: Quick Overview (Last 50 trades)
```bash
.venv/bin/python utils/strategy_audit.py --last 50
```
**Check**: Win Rate ≥ 55% and Profit Factor ≥ 1.2? If YES, edge is confirmed. If NO, proceed to next steps.

## Step 2: Full Historical Audit
```bash
.venv/bin/python utils/strategy_audit.py
```
**Check**: Review all 7 sections carefully:
1. **Edge Metrics** — Is WR > 55% and PF > 1.2?
2. **Exit Breakdown** — What % are TP hits vs SL hits vs Recon/Shadow exits?
3. **Early Exit Audit** — Are Shadow SL or Recon exits eating more than 20% of trades?
4. **Directional Bias** — Is LONG or SHORT significantly better? Consider direction filter.
5. **Per-Symbol** — Which symbols are profitable? Consider disabling underperformers.
6. **Latency** — Is T0→T4 latency still < 500ms avg?
7. **Verdict** — ✅ PASS or ❌ FAIL

## Step 3: Per-Session Audit (After a specific run)
```bash
.venv/bin/python utils/strategy_audit.py --session <SESSION_ID>
```
Use this to isolate metrics from a specific live-run session.

---

## Success Criteria (Phase 650 Goals)

| Metric | Goal | Action if failing |
|---|---|---|
| **Win Rate** | ≥ 55% | Tighten entry filters (min_cluster_density, delta thresholds) |
| **Profit Factor** | ≥ 1.2 | Adjust TP/SL ratio; check if Shadow SL is triggering too early |
| **Early Exit Rate** | ≤ 20% | Widen Shadow SL or increase cooldown before breakeven triggers |
| **Directional Bias** | < 15% gap LONG vs SHORT WR | Add trend filter (HTF alignment) |
| **Latency T0→T4** | < 500ms avg | Check DOM scan loop; review absorption.py cache size |
