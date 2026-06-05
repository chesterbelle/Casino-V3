# Profile Validation Protocol — THIN_VOLATILE Profile

## Overview
Validates the THIN_VOLATILE profile using constituent assets: XRP, DOGE.

**Asset Cluster:**
| Asset | Symbol | Profile |
|-------|--------|---------|
| XRP | XRPUSDT | THIN_VOLATILE |
| DOGE | DOGEUSDT | THIN_VOLATILE |

## Step 2: Run Audit
```bash
# Ejecutar validación por cluster
PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol cluster_thin_volatile \
  > logs/orchestrator_thin_volatile.log 2>&1
```

## Step 6: Run Regime Validator
```bash
# Validar precisión del régimen de entrada de señales
python3 utils/regime_validator.py --db data/historian.db --by-coin
```
