---
description: Protocolo para certificar el Edge en múltiples condiciones de mercado (Range, Bear, Bull) con LTC
---
# Long-Range Edge Audit — LTC × 3 Market Conditions × 3 Days

// turbo-all

## Overview
Tests whether the LTA edge **persists across different market regimes** using LTC.
Runs 9 backtests across three distinct conditions (3 days each).

**Asset:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **LTC** | LTC/USDT:USDT | Range-bound, moderate volume | Baseline asset, naturally mean-reverting |

**Market Conditions & Datasets:**

### LTC (Day 1s from Tardis Free Tier)
| Condition | Datasets |
|-----------|----------|
| **RANGE** | LTC_RANGE_2024-02-01.db, LTC_RANGE_2024-05-01.db, LTC_RANGE_2024-08-01.db |
| **BEAR**  | LTC_BEAR_2024-04-01.db, LTC_BEAR_2024-10-01.db, LTC_BEAR_2025-02-01.db |
| **BULL**  | LTC_BULL_2024-03-01.db, LTC_BULL_2024-12-01.db, LTC_BULL_2025-05-01.db |

**Statistical Goal**: n ≥ 100 signals total, n ≥ 25 per condition
**Certification Criteria**:
- **PRIMARY METRIC**: Gross Expectancy (%) = (WR × Avg_Win) - (LR × Avg_Loss)
- Range:  Expectancy > 0.36% → CERTIFIED | > 0.12% → WATCH | < 0.12% → FAILED
- Bear:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK
- Bull:   Expectancy > 0.12% AND signal_count < Range → GUARDIAN OK
- **Note**: Multi-asset validation deferred to future `/multi-asset-edge-audit` protocol

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

---

## Step 1: Verify Datasets Exist
```bash
echo "=== LTC Datasets ==="
for f in \
  data/datasets/backtest_ready/LTC_RANGE_2024-02-01.db \
  data/datasets/backtest_ready/LTC_RANGE_2024-05-01.db \
  data/datasets/backtest_ready/LTC_RANGE_2024-08-01.db \
  data/datasets/backtest_ready/LTC_BEAR_2024-04-01.db \
  data/datasets/backtest_ready/LTC_BEAR_2024-10-01.db \
  data/datasets/backtest_ready/LTC_BEAR_2025-02-01.db \
  data/datasets/backtest_ready/LTC_BULL_2024-03-01.db \
  data/datasets/backtest_ready/LTC_BULL_2024-12-01.db \
  data/datasets/backtest_ready/LTC_BULL_2025-05-01.db; do
  if [ -f "$f" ]; then
    echo "✅ $(basename $f): $(du -h $f | cut -f1)"
  else
    echo "❌ MISSING: $f"
  fi
done
```
**⛔ STOP if any dataset is missing.** Re-download with:
```bash
# .venv/bin/python utils/data/tardis_fetcher.py --symbol LTCUSDT --start YYYY-MM-01
# .venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol LTCUSDT
```

---

## Step 2: Run Backtests (9 total in Parallel)
```bash
# Zombie prevention shield: kill all background jobs on Ctrl+C or termination
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

# 2A: LTC RANGE
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_RANGE_2024-02-01.db --symbol LTCUSDT --historian-db data/historian_LTC_RANGE_2024-02-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_RANGE_2024-05-01.db --symbol LTCUSDT --historian-db data/historian_LTC_RANGE_2024-05-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_RANGE_2024-08-01.db --symbol LTCUSDT --historian-db data/historian_LTC_RANGE_2024-08-01.db --audit &

# 2B: LTC BEAR
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BEAR_2024-04-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BEAR_2024-04-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BEAR_2024-10-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BEAR_2024-10-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BEAR_2025-02-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BEAR_2025-02-01.db --audit &

# 2C: LTC BULL
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BULL_2024-03-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BULL_2024-03-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BULL_2024-12-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BULL_2024-12-01.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/LTC_BULL_2025-05-01.db --symbol LTCUSDT --historian-db data/historian_LTC_BULL_2025-05-01.db --audit &

echo "⏳ Waiting for parallel backtests to complete..."
wait

echo "🏁 ALL 9 BACKTESTS COMPLETE"

# Consolidate isolated databases into master historian.db
.venv/bin/python utils/merge_historian.py
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
**Minimum**: Signals ≥ 100 total. If fewer, mark as INSUFFICIENT DATA.

---

## Step 4: Statistical Extraction & Target Calibration
Evaluate current strategy performance:
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 14400
```
Run the Calibration grid sweeper to discover and verify optimal AMT target multipliers:
```bash
.venv/bin/python utils/setup_edge_auditor.py --calibrate
```

---

## Step 5: Multi-Window Target Grid Evaluation
Run a comprehensive matrix evaluation (1h, 2h, 4h windows across 0.6% to 1.2% targets) to ensure we don't blind ourselves to timeouts on a single window.
```bash
.venv/bin/python -c "
import sqlite3, collections
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price, setup_type FROM signals ORDER BY timestamp').fetchall()

windows = [3600, 7200, 14400]
targets = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]

setup_signals = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))

for window in windows:
    for ts, sym, side, price, setup_type in signals:
        ps = conn.execute('SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp', (sym, ts, ts+window)).fetchall()
        if not ps: continue
        trajectory = []
        for (p,) in ps:
            m = (p - price)/price*100
            if side == 'SHORT': m = -m
            trajectory.append(m)
        setup_signals[window][setup_type][sym].append(trajectory)

for window in windows:
    print(f'\n{\"=\" * 90}')
    print(f'  WINDOW: {window}s ({window//3600}h)')
    print(f'{\"=\" * 90}')

    for setup_type in sorted(setup_signals[window].keys()):
        total_setup_n = sum(len(trajs) for trajs in setup_signals[window][setup_type].values())
        if total_setup_n < 2: continue

        print(f'\n  🔹 SETUP: {setup_type} 🔹')
        for sym in sorted(setup_signals[window][setup_type].keys()):
            n = len(setup_signals[window][setup_type][sym])
            if n < 3: continue
            print(f'\n  【 {sym} 】 (n={n})')
            print(f'  {\"Target\":>8}  {\"WR%\":>6}  {\"W\":>3}  {\"L\":>3}  {\"TO\":>4}  {\"TO%\":>5}  {\"Net Taker%\":>12}')
            print(f'  {\"-\" * 60}')
            for tgt in targets:
                wins = losses = timeouts = 0
                for traj in setup_signals[window][setup_type][sym]:
                    hit_tp = hit_sl = False
                    for m in traj:
                        if not hit_tp and m >= tgt: hit_tp = True
                        if not hit_sl and m <= -tgt: hit_sl = True
                    if hit_tp and not hit_sl: wins += 1
                    elif hit_sl: losses += 1
                    else: timeouts += 1
                resolved = wins + losses
                wr = wins / resolved * 100 if resolved > 0 else 0
                to_pct = timeouts / n * 100
                gross_exp = ((wins * tgt) - (losses * tgt)) / n if n > 0 else 0
                net_taker = gross_exp - 0.12
                marker = ' ✅' if net_taker > 0 else ''
                print(f'  {tgt:>7.1f}%  {wr:>5.1f}%  {wins:>3}  {losses:>3}  {timeouts:>4}  {to_pct:>4.0f}%  {net_taker:>11.4f}%{marker}')
"
```

---

## Step 6: Per-Condition Breakdown
```bash
.venv/bin/python utils/analysis/per_condition_audit.py
```
Note: `per_condition_audit.py` uses timestamp ranges derived from the 9 datasets.

---

## Step 7: L2 Microstructure Audit (Liquidity Wall)
Run the L2 Depth Auditor to verify passive liquidity support across all 3 market conditions.
```bash
.venv/bin/python utils/l2_depth_auditor.py
```

---

## ⛔ MANDATORY STOP — Present Results and Certification Status

After Step 6, the agent **MUST STOP COMPLETELY** and present:

1. **Section [7]: Overall Edge Summary** from the auditor (Gross Expectancy, Net Taker/Maker)
2. **Section [4]: Decision Trace Audit** (Forensic reasons for rejections)
3. **Multi-Window Target Grid Evaluation** (Step 5) - Determine the optimal target and holding window.
4. **Per-condition table** (Step 6): All 3 conditions (Range, Bear, Bull) with Expectancy% and Verdicts
5. **Guardian effectiveness**: Compare signal counts across conditions
   - Range should have the MOST signals (balance = our edge zone)
   - Bear/Bull should have FEWER signals (guardians blocking counter-trend)
6. **L2 Correlation Result**: Present the L2 Depth Ratio Audit results (Step 7).
7. **STOP and wait** for user input

### Certification Matrix

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
| **ROBUST** | Range CERTIFIED + Bear/Bull GUARDIAN OK | Production ready |
| **FRAGILE** | Range WATCH + Bear/Bull GUARDIAN WEAK | Enable Limit Sniper + tighten regime thresholds |
| **BROKEN** | Range FAILED | Rework entry logic |

**Note**: Multi-asset cross-validation deferred to future `/multi-asset-edge-audit` protocol.

**Do NOT proceed without user approval.**
