# L2 Depth Audit Protocol (Liquidity Wall Certification)

// turbo-all

## Overview
This protocol performs a structural validation of the **passive liquidity support** behind any tactical setup.
According to Auction Market Theory (AMT), a true absorption or reversal event requires aggressive market participants
to hit a massive passive limit order wall. If the wall is thin, the setup is likely a fakeout or statistical noise.

This workflow uses the `utils/l2_depth_auditor.py` script to correlate the L2 Imbalance Ratio (Bid/Ask Depth)
at the exact millisecond of the signal with the final MFE/MAE (Maximum Favorable/Adverse Excursion) of the trade.

**Goals**:
- Prove that trades with a high L2 Ratio (> 2.0) have a significant structural advantage (MFE/MAE Ratio > 1.2).
- Identify and filter out "Thin Wall" trades (< 1.0) that lead to negative expectancy.

---

## Step 0: Nuclear Reset
Wipe all databases to ensure a clean test environment.
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Generate Signals (Zero-Interference Backtest)
Run the backtester on the primary audit dataset (LTC) to generate pristine signals and MFE/MAE price samples.
```bash
.venv/bin/python backtest.py --run-type trade \
  --depth-db-path data/datasets/daily_backtest_ready/2024-01-01_LTCUSDT.db \
  --symbol LTC/USDT:USDT \
  --run-type audit \
  2>&1 | tee logs/l2_audit_ltc_$(date +%Y%m%d_%H%M%S).log
```

## Step 2: Run the L2 Depth Auditor
Execute the analytical script to correlate the signals with their historical L2 Depth.
```bash
.venv/bin/python utils/l2_depth_auditor.py
```

---

## ⛔ MANDATORY STOP — Present Results and Certification

After running Step 2, the agent MUST:

1. **Present the L2 Depth Ratio Audit Results Table**.
2. **Evaluate the Hypothesis**: Does the "High Wall" category significantly outperform the "Thin Wall" category?
3. **Assign a Status**:
   - **CERTIFIED**: If High Wall trades have an MFE/MAE Ratio > 1.2 and significantly outperform Thin Wall trades.
   - **FAILED**: If there is no correlation between L2 Depth and MFE/MAE.
4. **Propose Action**: If certified, propose integrating the `L2 Ratio > 1.5` requirement into the `LiquidityGuardian`.
5. **STOP and wait** for user input. Do not alter any strategy file without permission.
