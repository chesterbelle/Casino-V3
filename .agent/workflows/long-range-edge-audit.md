---
description: Protocolo para certificar el Edge en múltiples condiciones de mercado (Range, Bear, Bull)
---
# Long-Range Edge Audit — LTC × 3 Market Conditions × 3 Days

// turbo-all

## Overview
Tests whether the LTA edge **persists across different market regimes** using LTC/USDT
in three distinct conditions over 3 days each.

**Why LTC?**
LTC is naturally more range-bound than SOL/ETH, making it the ideal asset for a
POC reversion strategy. SOL is too trending/momentum-driven and generates too few
signals per day (~15) for statistically meaningful results.

**Market Conditions & Datasets:**

| Condition | Dates | Price Range | Files |
|-----------|-------|-------------|-------|
| **RANGE** | Aug 14-16, 2024 | $62.52 - $66.75 | ltc_range_2024-08-14.csv, ltc_range_24h.csv, ltc_range_2024-08-16.csv |
| **BEAR**  | Sep 05-07, 2024 | $61.15 - $68.50 | ltc_bear_2024-09-05.csv, ltc_bear_24h.csv, ltc_bear_2024-09-07.csv |
| **BULL**  | Oct 13-15, 2024 | $64.06 - $72.00 | ltc_bull_2024-10-13.csv, ltc_bull_24h.csv, ltc_bull_2024-10-15.csv |

**Statistical Goal**: n ≥ 150 signals total, n ≥ 50 per condition
**Certification Criteria (UPDATED Phase 800B)**:
- **PRIMARY METRIC**: Gross Expectancy (%) = (WR × Avg_Win) - (LR × Avg_Loss)
- Range:  Expectancy > 0.36% → CERTIFIED | > 0.12% → WATCH (primary edge zone)
- Bear:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK
- Bull:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK

**Baseline Results (LTA V5, April 2025)**:
- Edge Audit Normal: Ratio 1.62, WR 69.4%, 80 signals
- Long-Range 2024: Ratio 1.10, WR 50.0%, 151 signals
- Interpretation: Edge is real but weaker in 2024 conditions. LTA V5 improvements
  are validated against recent market conditions.

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python reset_data.py
```
**Must output**: `✨ Sistema limpio.`

---

## Step 1: Verify Datasets Exist
```bash
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
```
**⛔ STOP if any dataset is missing.** Re-generate with:
```bash
# Download monthly data first if needed:
# .venv/bin/python utils/data/download_trades.py --symbol LTCUSDT --year 2024 --month 08
# .venv/bin/python utils/data/download_trades.py --symbol LTCUSDT --year 2024 --month 09
# .venv/bin/python utils/data/download_trades.py --symbol LTCUSDT --year 2024 --month 10

# Then slice:
for date in 2024-08-14 2024-08-15 2024-08-16; do
  .venv/bin/python utils/data/slice_audit_dataset.py \
    --input data/raw/LTCUSDT_trades_2024_08.csv \
    --date $date --out tests/validation/ltc_range_${date}.csv
done
# (rename ltc_range_2024-08-15.csv → ltc_range_24h.csv)

for date in 2024-09-05 2024-09-06 2024-09-07; do
  .venv/bin/python utils/data/slice_audit_dataset.py \
    --input data/raw/LTCUSDT_trades_2024_09.csv \
    --date $date --out tests/validation/ltc_bear_${date}.csv
done
# (rename ltc_bear_2024-09-06.csv → ltc_bear_24h.csv)

for date in 2024-10-13 2024-10-14 2024-10-15; do
  .venv/bin/python utils/data/slice_audit_dataset.py \
    --input data/raw/LTCUSDT_trades_2024_10.csv \
    --date $date --out tests/validation/ltc_bull_${date}.csv
done
# (rename ltc_bull_2024-10-14.csv → ltc_bull_24h.csv)
```

---

## Step 2: Run Backtests (9 total — 3 conditions × 3 days)

### 2A: RANGE (Aug 14-16)
```bash
for f in tests/validation/ltc_range_2024-08-14.csv tests/validation/ltc_range_24h.csv tests/validation/ltc_range_2024-08-16.csv; do
  .venv/bin/python backtest.py --data $f --symbol LTC/USDT:USDT --depth-db data/historian.db --audit > /dev/null 2>&1 \
    && echo "✅ $(basename $f)" || echo "❌ $(basename $f)"
done
```

### 2B: BEAR (Sep 05-07)
```bash
for f in tests/validation/ltc_bear_2024-09-05.csv tests/validation/ltc_bear_24h.csv tests/validation/ltc_bear_2024-09-07.csv; do
  .venv/bin/python backtest.py --data $f --symbol LTC/USDT:USDT --depth-db data/historian.db --audit > /dev/null 2>&1 \
    && echo "✅ $(basename $f)" || echo "❌ $(basename $f)"
done
```

### 2C: BULL (Oct 13-15)
```bash
for f in tests/validation/ltc_bull_2024-10-13.csv tests/validation/ltc_bull_24h.csv tests/validation/ltc_bull_2024-10-15.csv; do
  .venv/bin/python backtest.py --data $f --symbol LTC/USDT:USDT --depth-db data/historian.db --audit > /dev/null 2>&1 \
    && echo "✅ $(basename $f)" || echo "❌ $(basename $f)"
done
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
"
```
**Minimum**: Signals ≥ 150. If fewer, mark as INSUFFICIENT DATA.

---

## Step 4: Statistical Extraction (MFE/MAE Aggregate)
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 900
```

---

## Step 5: Per-Condition Breakdown
```bash
.venv/bin/python utils/analysis/per_condition_audit.py
```
Note: `per_condition_audit.py` uses these timestamp ranges:
- RANGE (Aug 14-16): 1723593600 - 1723852800
- BEAR  (Sep 05-07): 1725494400 - 1725753600
- BULL  (Oct 13-15): 1728777600 - 1729036800

---

## ⛔ MANDATORY STOP — Present Results and Certification Status

After Step 5, the agent **MUST STOP COMPLETELY** and present:

1. **Section [5]: Overall Edge Summary** from the auditor (Gross Expectancy, Net Taker/Maker, Recommendations)
2. **Per-condition table** (Step 5): Range / Bear / Bull breakdown with Expectancy% and Verdicts
3. **Guardian effectiveness**: Compare signal counts across conditions
   - Range should have the MOST signals (balance = our edge zone)
   - Bear/Bull should have FEWER signals (guardians blocking counter-trend reversions)
4. **Comparison vs Edge Audit Normal** (baseline: check current certified values)
5. **STOP and wait** for user input

### Certification Matrix — UPDATED Phase 800B

**PRIMARY METRIC: Gross Expectancy (%)**

| Condition | Criteria | Status | Interpretation |
|-----------|----------|--------|----------------|
| **Range** | Expectancy > 0.36% AND WR > 55% | **CERTIFIED** | Primary edge confirmed, viable with any order type |
| **Range** | Expectancy > 0.12% AND WR > 50% | **WATCH** | Edge exists, requires Limit Sniper |
| **Range** | Expectancy < 0.12% | **FAILED** | No edge — strategy broken |
| **Bear/Bull** | Signal count < Range AND Expectancy > 0.12% | **GUARDIAN OK** | Guardians filtering correctly |
| **Bear/Bull** | Signal count ≈ Range | **GUARDIAN WEAK** | Guardians not blocking enough |
| **Bear/Bull** | Expectancy < 0% | **GUARDIAN FAIL** | Guardians letting bad trades through |

### Overall System Verdict

| Result | Condition | Action |
|--------|-----------|--------|
| **ROBUST** | Range Expectancy > 0.36% + Bear/Bull GUARDIAN OK | Production ready |
| **FRAGILE** | Range Expectancy > 0.12% + Bear/Bull GUARDIAN WEAK | Enable Limit Sniper + tighten regime thresholds |
| **BROKEN** | Range Expectancy < 0.12% | Rework entry logic |

**Do NOT proceed without user approval.**
