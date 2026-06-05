# Profile Validation Protocol — MEGA_LIQUID Profile

## Overview
Validates the MEGA_LIQUID profile using constituent assets: ADA, ARB, NEAR.

**Asset Cluster:**
| Asset | Symbol | Profile |
|-------|--------|---------|
| ADA | ADAUSDT | MEGA_LIQUID |
| ARB | ARBUSDT | MEGA_LIQUID |
| NEAR | NEARUSDT | MEGA_LIQUID |

## Step 2: Run Audit
```bash
# Ejecutar validación por cluster
PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol cluster_mega_liquid \
  > logs/orchestrator_mega_liquid.log 2>&1
```
