# Profile Validation Protocol — ILLIQUID_SPEC Profile

## Overview
Validates the ILLIQUID_SPEC profile using constituent assets: BTC, ETH.

**Asset Cluster:**
| Asset | Symbol | Profile |
|-------|--------|---------|
| BTC | BTCUSDT | ILLIQUID_SPEC |
| ETH | ETHUSDT | ILLIQUID_SPEC |

## Step 2: Run Audit
```bash
# Ejecutar validación por cluster
PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol cluster_illiqid_spec \
  > logs/orchestrator_illiqid_spec.log 2>&1
```
