# Profile Validation Protocol — MAJOR_LIQUID Profile

## Overview
Validates the MAJOR_LIQUID profile using constituent assets: SOL.

**Asset Cluster:**
| Asset | Symbol | Profile |
|-------|--------|---------|
| SOL | SOLUSDT | MAJOR_LIQUID |

## Step 2: Run Audit
```bash
# Ejecutar validación por cluster
PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol cluster_major_liquid \
  > logs/orchestrator_major_liquid.log 2>&1
```
