# Phase 1200 — Monthly Backtest Protocol (30-Day Edge Validation)

// turbo-all

## Overview
This protocol performs a **Long-Range** validation of the LTA V4 strategy edge using a full month of historical data. To ensure system stability and performance, it disables the `--audit` price sampling while maintaining high-fidelity order execution.

Goal: Validate consistent Win Rate and Profit Factor across diverse market regimes.

---

## Step 0: Nuclear Reset (Clean Slate)
Wipe the historian database to ensure statistics only reflect the monthly session.
```bash
.venv/bin/python reset_data.py
```

## Step 1: Run 30-Day Simulation
Run the backtester against the monthly trade dataset.
**IMPORTANT**: Do NOT add `--audit`. Ensure the CSV data contains at least 60-120 minutes of pre-trade history to allow for sensor warmup.

```bash
.venv/bin/python backtest.py \
  --data ./data/raw/LTCUSDT_trades_2026_01.csv \
  --symbol LTC/USDT:USDT \
  2>&1 | tee logs/monthly_backtest_$(date +%Y%m%d_%H%M%S).log
```

## Step 2: Extract Strategy Metrics
Run the Strategy Audit tool to compute active edge metrics.
```bash
.venv/bin/python utils/strategy_audit.py
```

---

## Success Criteria
- **Win Rate**: ≥ 55%
- **Profit Factor**: ≥ 1.2
- **Trade Count**: ≥ 50 (for statistical significance)
