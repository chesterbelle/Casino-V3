---
description: Auditoría de Borde Generalizada (10 Coins × 24h)
---

# Generalized Edge Audit — 10 Coins × 24h (Cross-Instrument Validation)

// turbo-all

## Overview
Tests whether the LTA V4 Structural Reversion edge **generalizes across instruments**.
A reversion strategy based on Auction Market Theory should work on ANY liquid instrument.
If the edge only exists on a subset, it's likely overfitting, not a real market property.

**Prerequisites**: 24h datasets must already exist in `tests/validation/cross_section/`.
Download them manually before running this protocol.

**Expected files** (one per coin):
```
tests/validation/cross_section/ADA_USDT_USDT_24h.csv
tests/validation/cross_section/ETH_USDT_USDT_24h.csv
tests/validation/cross_section/SOL_USDT_USDT_24h.csv
tests/validation/cross_section/BNB_USDT_USDT_24h.csv
tests/validation/cross_section/XRP_USDT_USDT_24h.csv
tests/validation/cross_section/AVAX_USDT_USDT_24h.csv
tests/validation/cross_section/LINK_USDT_USDT_24h.csv
tests/validation/cross_section/DOGE_USDT_USDT_24h.csv
tests/validation/cross_section/LTC_USDT_USDT_24h.csv
tests/validation/cross_section/SUI_USDT_USDT_24h.csv
```

**Statistical Goal**: n ≥ 300 signals total, SE on WR ≤ ±2.8%
**Per-Coin Minimum**: n ≥ 10 signals (flag if less)

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Verify Datasets Exist
```bash
echo "=== Dataset Verification ==="
COINS=("ADA_USDT_USDT" "ETH_USDT_USDT" "SOL_USDT_USDT" "BNB_USDT_USDT" "XRP_USDT_USDT" "AVAX_USDT_USDT" "LINK_USDT_USDT" "DOGE_USDT_USDT" "LTC_USDT_USDT" "SUI_USDT_USDT")
MISSING=0
for COIN in "${COINS[@]}"; do
  FILE="tests/validation/cross_section/${COIN}_24h.csv"
  if [ -f "$FILE" ]; then
    ROWS=$(wc -l < "$FILE")
    echo "✅ $COIN: $ROWS rows"
  else
    echo "❌ MISSING: $FILE"
    MISSING=$((MISSING + 1))
  fi
done
if [ $MISSING -gt 0 ]; then
  echo "⛔ $MISSING datasets missing. Download them before running this protocol."
fi
```
**⛔ STOP if any datasets are missing.** Inform the user which files need to be downloaded.

## Step 2: Run Backtests (All 10 Coins in Parallel)
```bash
# Zombie prevention shield: kill all background jobs on Ctrl+C or termination
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_ADAUSDT.db --symbol ADAUSDT --historian-db data/historian_ADAUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_AVAXUSDT.db --symbol AVAXUSDT --historian-db data/historian_AVAXUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_BNBUSDT.db --symbol BNBUSDT --historian-db data/historian_BNBUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_DOGEUSDT.db --symbol DOGEUSDT --historian-db data/historian_DOGEUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_ETHUSDT.db --symbol ETHUSDT --historian-db data/historian_ETHUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_LINKUSDT.db --symbol LINKUSDT --historian-db data/historian_LINKUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_LTCUSDT.db --symbol LTCUSDT --historian-db data/historian_LTCUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_SOLUSDT.db --symbol SOLUSDT --historian-db data/historian_SOLUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_SUIUSDT.db --symbol SUIUSDT --historian-db data/historian_SUIUSDT.db --audit &
// turbo
.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_XRPUSDT.db --symbol XRPUSDT --historian-db data/historian_XRPUSDT.db --audit &

echo "⏳ Waiting for parallel backtests to complete..."
wait

echo "🏁 ALL 10 BACKTESTS COMPLETE"

# Consolidate isolated databases into master historian.db
.venv/bin/python utils/merge_historian.py

find data/ -type f -name "*.csv*" -delete
.venv/bin/python utils/update_memory.py --workflow generalized-edge-audit
```

## Step 3: Verify Data Collection
```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/historian.db')
s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]

print(f'Total Signals: {s}, Price Samples: {p}')
print()

rows = conn.execute('SELECT symbol, COUNT(*) FROM signals GROUP BY symbol ORDER BY COUNT(*) DESC').fetchall()
print('Per-Coin Breakdown:')
for sym, cnt in rows:
    flag = '⚠️' if cnt < 10 else '✅'
    print(f'  {flag} {sym:20s}: {cnt} signals')
"
```
**Minimum**: Total Signals ≥ 300. Per-coin ≥ 10 (flag if less).

## Step 4: Edge Audit & Target Calibration
Evaluate current strategy performance:
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 14400
```
Run the Calibration grid sweeper to discover and verify optimal AMT target multipliers:
```bash
.venv/bin/python utils/setup_edge_auditor.py --calibrate
```

## Step 5: Per-Coin Quality Analysis
```bash
.venv/bin/python -c "
import sqlite3, statistics
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price, metadata FROM signals ORDER BY timestamp').fetchall()

windows = [3600, 7200, 14400]
targets = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]

for window in windows:
    print(f'\n{\"=\" * 90}')
    print(f'  WINDOW: {window}s ({window//3600}h)')
    print(f'{\"=\" * 90}')

    coin_signals = {}
    for ts, sym, side, price, meta in signals:
        ps = conn.execute('SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp', (sym, ts, ts+window)).fetchall()
        if not ps: continue
        trajectory = []
        for (p,) in ps:
            m = (p - price)/price*100
            if side == 'SHORT': m = -m
            trajectory.append(m)
        if sym not in coin_signals:
            coin_signals[sym] = []
        coin_signals[sym].append(trajectory)

    for sym in sorted(coin_signals.keys()):
        n = len(coin_signals[sym])
        if n < 5: continue  # skip LOW_N
        print(f'\n  【 {sym} 】 (n={n})')
        print(f'  {\"Target\":>8}  {\"WR%\":>6}  {\"W\":>3}  {\"L\":>3}  {\"TO\":>4}  {\"TO%\":>5}  {\"Net Taker%\":>12}')
        print(f'  {\"-\" * 60}')
        for tgt in targets:
            wins = losses = timeouts = 0
            for traj in coin_signals[sym]:
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

## Step 6: L2 Microstructure Audit (Liquidity Wall)
Verify if the edge is supported by L2 limits across the multiple instruments.
```bash
.venv/bin/python utils/l2_depth_auditor.py
```

---

## ⛔ MANDATORY STOP — Present Results

After Step 5, the agent **MUST STOP** and present:

1. **Aggregate table** (all 10 coins combined): n, WR%, Gross Expectancy%, Net (Taker), Net (Maker)
2. **Per-coin breakdown table** with individual Verdicts based on Expectancy
3. **Generalizability Score**: How many coins CERTIFIED / WATCH / FAILED
4. **L2 Correlation Result**: Does the L2 Auditor confirm that "High Wall" setups exhibit MFE/MAE > 1.2 across all assets?
5. **Specific observations** per coin (e.g., "ETH has high MAE, needs tighter filters")

### Certification Matrix — UPDATED Phase 800B

**PRIMARY METRIC: Gross Expectancy (%)** per coin

| Result | Condition | Interpretation |
|--------|-----------|----------------|
| **GENERALIZED** | ≥ 7/10 coins with Expectancy > 0.12% | Edge is real, based on market microstructure |
| **PARTIAL** | 4-6/10 coins with Expectancy > 0.12% | Edge exists but instrument-dependent |
| **FAILED** | ≤ 3/10 coins with Expectancy > 0.12% | Edge is likely overfitting to specific instruments |

**Per-Coin Verdicts:**
- **CERTIFIED**: Expectancy > 0.36% (viable with any order type)
- **WATCH**: Expectancy 0.12%-0.36% (requires Limit Sniper)
- **FAILED**: Expectancy < 0.12% (not viable)
- **LOW_N**: n < 10 (insufficient data)

**Do NOT proceed to further optimization without user approval.**
