---
description: Protocolo para certificar el Edge en múltiples condiciones de mercado (Range, Bear, Bull) con 2+ activos
---
# Long-Range Edge Audit — Multi-Asset × 3 Market Conditions × 3 Days

// turbo-all

## Overview
Tests whether the LTA edge **persists across different market regimes AND different assets**.
Uses 2+ assets in three distinct conditions over 3 days each (18+ backtests total).

**Why Multi-Asset?**
A single-asset edge audit cannot distinguish alpha from asset-specific noise.
The strategy is agnostic by design — if edge only exists in one asset, it's overfitting.
Two assets with different microstructure (LTC range-bound, DOGE meme-driven) provide
orthogonal validation.

**Assets & Rationale:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **LTC** | LTC/USDT:USDT | Range-bound, moderate volume | Baseline asset, naturally mean-reverting |
| **DOGE** | DOGE/USDT:USDT | Meme-driven, high volume | Stress test: volatile, sentiment-driven |

**Market Conditions & Datasets:**

### LTC (Aug-Oct 2024, Futures)
| Condition | Dates | Files |
|-----------|-------|-------|
| **RANGE** | Aug 14-16, 2024 | ltc_range_2024-08-14.csv, ltc_range_24h.csv, ltc_range_2024-08-16.csv |
| **BEAR**  | Sep 05-07, 2024 | ltc_bear_2024-09-05.csv, ltc_bear_24h.csv, ltc_bear_2024-09-07.csv |
| **BULL**  | Oct 13-15, 2024 | ltc_bull_2024-10-13.csv, ltc_bull_24h.csv, ltc_bull_2024-10-15.csv |

### DOGE (May 2025, Futures)
| Condition | Dates | Files |
|-----------|-------|-------|
| **RANGE** | May 1-3, 2025 | doge_range_2025-05-01.csv, doge_range_2025-05-02.csv, doge_range_2025-05-03.csv |
| **BEAR**  | May 28-30, 2025 | doge_bear_2025-05-28.csv, doge_bear_2025-05-29.csv, doge_bear_2025-05-30.csv |
| **BULL**  | May 16-18, 2025 | doge_bull_2025-05-16.csv, doge_bull_2025-05-17.csv, doge_bull_2025-05-18.csv |

**Statistical Goal**: n ≥ 250 signals total (across all assets), n ≥ 50 per condition per asset
**Certification Criteria**:
- **PRIMARY METRIC**: Gross Expectancy (%) = (WR × Avg_Win) - (LR × Avg_Loss)
- **CROSS-ASSET REQUIREMENT**: Edge must be positive in BOTH assets for certification
- Range:  Expectancy > 0.36% → CERTIFIED | > 0.12% → WATCH | < 0.12% → FAILED
- Bear:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK
- Bull:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python reset_data.py
```
**Must output**: `✨ Sistema limpio.`

---

## Step 1: Verify Datasets Exist
```bash
echo "=== LTC Datasets ==="
for f in \
  tests/validation/ltc_range_2024-08-14.csv \
  tests/validation/ltc_range_24h.csv \
  tests/validation/ltc_range_2024-08-16.csv \
  tests/validation/ltc_bear_2024-09-05.csv \
  tests/validation/ltc_bear_24h.csv \
  tests/validation/ltc_bear_2024-09-07.csv \
  tests/validation/ltc_bull_2024-10-13.csv \
  tests/validation/ltc_bull_24h.csv \
  tests/validation/ltc_bull_2024-10-15.csv; do
  if [ -f "$f" ]; then
    echo "✅ $(basename $f): $(wc -l < $f) rows"
  else
    echo "❌ MISSING: $f"
  fi
done

echo "=== DOGE Datasets ==="
for f in \
  tests/validation/doge_range_2025-05-01.csv \
  tests/validation/doge_range_2025-05-02.csv \
  tests/validation/doge_range_2025-05-03.csv \
  tests/validation/doge_bear_2025-05-28.csv \
  tests/validation/doge_bear_2025-05-29.csv \
  tests/validation/doge_bear_2025-05-30.csv \
  tests/validation/doge_bull_2025-05-16.csv \
  tests/validation/doge_bull_2025-05-17.csv \
  tests/validation/doge_bull_2025-05-18.csv; do
  if [ -f "$f" ]; then
    echo "✅ $(basename $f): $(wc -l < $f) rows"
  else
    echo "❌ MISSING: $f"
  fi
done
```
**⛔ STOP if any dataset is missing.** Re-download with:
```bash
# LTC (Futures, 2024 data — must be pre-existing or from archival source)
# .venv/bin/python tests/validation/parity_data_fetcher.py --symbol LTC/USDT:USDT --start EPOCH --end EPOCH --out tests/validation/ltc_XXX.csv

# DOGE (Futures, May 2025+ — available from Binance fapi)
# .venv/bin/python tests/validation/parity_data_fetcher.py --symbol DOGE/USDT:USDT --start EPOCH --end EPOCH --out tests/validation/doge_XXX.csv
```

---

## Step 2: Run Backtests (18 total — 2 assets × 3 conditions × 3 days)

### 2A: LTC RANGE (Aug 14-16)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol LTCUSDT --download --start 2024-08-14 --end 2024-08-16 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol LTC/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ LTC RANGE" || echo "❌ LTC RANGE"
```

### 2B: LTC BEAR (Sep 05-07)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol LTCUSDT --download --start 2024-09-05 --end 2024-09-07 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol LTC/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ LTC BEAR" || echo "❌ LTC BEAR"
```

### 2C: LTC BULL (Oct 13-15)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol LTCUSDT --download --start 2024-10-13 --end 2024-10-15 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol LTC/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ LTC BULL" || echo "❌ LTC BULL"
```

### 2D: DOGE RANGE (May 1-3)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol DOGEUSDT --download --start 2025-05-01 --end 2025-05-03 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol DOGE/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ DOGE RANGE" || echo "❌ DOGE RANGE"
```

### 2E: DOGE BEAR (May 28-30)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol DOGEUSDT --download --start 2025-05-28 --end 2025-05-30 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol DOGE/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ DOGE BEAR" || echo "❌ DOGE BEAR"
```

### 2F: DOGE BULL (May 16-18)
```bash
.venv/bin/python utils/data/l2_price_ingestor.py --symbol DOGEUSDT --download --start 2025-05-16 --end 2025-05-18 --db-path data/historian.db
.venv/bin/python backtest.py --depth-db-path data/historian.db --symbol DOGE/USDT:USDT --audit > /dev/null 2>&1 && echo "✅ DOGE BULL" || echo "❌ DOGE BULL"

find data/ -type f -name "*.csv*" -delete
.venv/bin/python utils/update_memory.py --workflow long-range-edge-audit
```

---

## Step 3: Verify Data Collection
```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/historian.db')
s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]
d = conn.execute('SELECT COUNT(*) FROM decision_traces').fetchone()[0] if conn.execute('''SELECT count(name) FROM sqlite_master WHERE type='table' AND name='decision_traces' ''').fetchone()[0] == 1 else 0
print(f'Signals: {s}, Price Samples: {p}, Traces: {d}')
# Per-asset breakdown
for sym in ['LTC/USDT:USDT', 'DOGE/USDT:USDT']:
    n = conn.execute('SELECT COUNT(*) FROM signals WHERE symbol=?', (sym,)).fetchone()[0]
    print(f'  {sym}: {n} signals')
"
```
**Minimum**: Signals ≥ 250 total, ≥ 50 per asset. If fewer, mark as INSUFFICIENT DATA.

---

## Step 4: Statistical Extraction (MFE/MAE Aggregate)
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 1800
```

---

## Step 5: Per-Condition Breakdown
```bash
.venv/bin/python utils/analysis/per_condition_audit.py
```
Note: `per_condition_audit.py` uses these timestamp ranges:
- LTC RANGE (Aug 14-16): 1723593600 - 1723852800
- LTC BEAR  (Sep 05-07): 1725494400 - 1725753600
- LTC BULL  (Oct 13-15): 1728777600 - 1729036800
- DOGE RANGE (May 1-3):  1746057600 - 1746316800
- DOGE BEAR  (May 28-30): 1748390400 - 1748649600
- DOGE BULL  (May 16-18): 1747353600 - 1747612800

---

## ⛔ MANDATORY STOP — Present Results and Certification Status

After Step 5, the agent **MUST STOP COMPLETELY** and present:

1. **Section [5]: Overall Edge Summary** from the auditor (Gross Expectancy, Net Taker/Maker)
2. **Per-condition table** (Step 5): All 6 conditions (3 LTC + 3 DOGE) with Expectancy% and Verdicts
3. **Cross-Asset Consistency**: Does edge exist in BOTH assets?
   - If yes → alpha is likely real (agnostic)
   - If only LTC → possible overfitting to LTC microstructure
   - If only DOGE → investigate LTC-specific failure
4. **Guardian effectiveness**: Compare signal counts across conditions
   - Range should have the MOST signals (balance = our edge zone)
   - Bear/Bull should have FEWER signals (guardians blocking counter-trend)
5. **STOP and wait** for user input

### Certification Matrix

**PRIMARY METRIC: Gross Expectancy (%)**
**CROSS-ASSET REQUIREMENT: Edge must be positive in BOTH assets for CERTIFIED**

| Condition | Criteria | Status | Interpretation |
|-----------|----------|--------|----------------|
| **Range (any asset)** | Expectancy > 0.36% AND WR > 55% | **CERTIFIED** | Primary edge confirmed, viable with any order type |
| **Range (any asset)** | Expectancy > 0.12% AND WR > 50% | **WATCH** | Edge exists, requires Limit Sniper |
| **Range (any asset)** | Expectancy < 0.12% | **FAILED** | No edge — strategy broken for this asset |
| **Bear/Bull (any asset)** | Signal count < Range AND Expectancy > 0.12% | **GUARDIAN OK** | Guardians filtering correctly |
| **Bear/Bull (any asset)** | Signal count ≈ Range | **GUARDIAN WEAK** | Guardians not blocking enough |
| **Bear/Bull (any asset)** | Expectancy < 0% | **GUARDIAN FAIL** | Guardians letting bad trades through |

### Overall System Verdict

| Result | Condition | Action |
|--------|-----------|--------|
| **ROBUST** | Range CERTIFIED in BOTH assets + Bear/Bull GUARDIAN OK | Production ready |
| **FRAGILE** | Range WATCH in BOTH assets + Bear/Bull GUARDIAN WEAK | Enable Limit Sniper + tighten regime thresholds |
| **ASSET-SPECIFIC** | Edge in only ONE asset | Investigate asset-specific failure, NOT production ready |
| **BROKEN** | Range FAILED in BOTH assets | Rework entry logic |

**Do NOT proceed without user approval.**
