# Profile Validation Protocol — MID_LIQUID Profile

## Overview
Validates the MID_LIQUID profile using constituent assets: LTC, AVAX, BNB, LINK, OP, APT.

**Asset Cluster:**
| Asset | Symbol | Profile |
|-------|--------|---------|
| LTC | LTCUSDT | MID_LIQUID |
| AVAX | AVAXUSDT | MID_LIQUID |
| BNB | BNBUSDT | MID_LIQUID |
| LINK | LINKUSDT | MID_LIQUID |
| OP | OPUSDT | MID_LIQUID |
| APT | APTUSDT | MID_LIQUID |

## Step 2: Run Audit
```bash
# Ejecutar validación por cluster
PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol cluster_mid_liquid \
  > logs/orchestrator_mid_liquid.log 2>&1
```
