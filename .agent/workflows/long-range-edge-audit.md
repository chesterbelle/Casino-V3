# Long-Range Edge Audit — 10 Coins × 7 Days (Temporal Stability Test)

// turbo-all

## Overview
Tests whether the LTA V4 edge **persists across different market conditions over time**.
A 7-day window captures trending days, ranging days, volatile sessions, and quiet periods.

**Prerequisites**:
1. Run `/generalized-edge-audit` first. Only include coins that scored CERTIFIED or WATCH.
2. 7-day datasets must already exist in `tests/validation/long_range/`.
   Download them manually before running this protocol.

**Expected files** (one per coin):
```
tests/validation/long_range/BTC_USDT_USDT_7d.csv
tests/validation/long_range/ETH_USDT_USDT_7d.csv
tests/validation/long_range/SOL_USDT_USDT_7d.csv
tests/validation/long_range/BNB_USDT_USDT_7d.csv
tests/validation/long_range/XRP_USDT_USDT_7d.csv
tests/validation/long_range/AVAX_USDT_USDT_7d.csv
tests/validation/long_range/LINK_USDT_USDT_7d.csv
tests/validation/long_range/DOGE_USDT_USDT_7d.csv
tests/validation/long_range/LTC_USDT_USDT_7d.csv
tests/validation/long_range/SUI_USDT_USDT_7d.csv
```

**Statistical Goal**: n ≥ 1000 signals total, SE on WR ≤ ±1.5%
**Per-Coin Minimum**: n ≥ 50 signals

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python reset_data.py
```

## Step 1: Verify Datasets Exist
```bash
echo "=== Dataset Verification (7-Day) ==="
COINS=("BTC_USDT_USDT" "ETH_USDT_USDT" "SOL_USDT_USDT" "BNB_USDT_USDT" "XRP_USDT_USDT" "AVAX_USDT_USDT" "LINK_USDT_USDT" "DOGE_USDT_USDT" "LTC_USDT_USDT" "SUI_USDT_USDT")
MISSING=0
for COIN in "${COINS[@]}"; do
  FILE="tests/validation/long_range/${COIN}_7d.csv"
  if [ -f "$FILE" ]; then
    ROWS=$(wc -l < "$FILE")
    SIZE=$(du -h "$FILE" | cut -f1)
    echo "✅ $COIN: $ROWS rows ($SIZE)"
  else
    echo "❌ MISSING: $FILE"
    MISSING=$((MISSING + 1))
  fi
done
if [ $MISSING -gt 0 ]; then
  echo "⛔ $MISSING datasets missing. Download them before running this protocol."
fi
```
**⛔ STOP if any datasets are missing.**

## Step 2: Run Backtests (All Coins, Sequential)
Each 7-day backtest takes ~5-10 min per coin.

```bash
SYMBOLS=("BTC/USDT:USDT" "ETH/USDT:USDT" "SOL/USDT:USDT" "BNB/USDT:USDT" "XRP/USDT:USDT" "AVAX/USDT:USDT" "LINK/USDT:USDT" "DOGE/USDT:USDT" "LTC/USDT:USDT" "SUI/USDT:USDT")
NAMES=("BTC_USDT_USDT" "ETH_USDT_USDT" "SOL_USDT_USDT" "BNB_USDT_USDT" "XRP_USDT_USDT" "AVAX_USDT_USDT" "LINK_USDT_USDT" "DOGE_USDT_USDT" "LTC_USDT_USDT" "SUI_USDT_USDT")

for i in "${!SYMBOLS[@]}"; do
  SYM="${SYMBOLS[$i]}"
  DATA="tests/validation/long_range/${NAMES[$i]}_7d.csv"
  echo "▶ $SYM (7d)..."
  .venv/bin/python backtest.py \
    --data "$DATA" --symbol "$SYM" \
    --depth-db data/historian.db --audit \
    > /dev/null 2>&1 && echo "✅ $SYM" || echo "❌ $SYM"
done
echo "🏁 ALL 7-DAY BACKTESTS COMPLETE"
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
print('Per-Coin Breakdown (7d):')
for sym, cnt in rows:
    flag = '⚠️' if cnt < 50 else '✅'
    print(f'  {flag} {sym:20s}: {cnt} signals')
"
```
**Minimum**: Total Signals ≥ 1000. Per-coin ≥ 50.

## Step 4: Edge Audit (Aggregate)
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 900
```

## Step 5: Temporal Stability Analysis
Check if the edge is consistent day-by-day (no single-day spikes driving the average).

```bash
.venv/bin/python -c "
import sqlite3, statistics
from datetime import datetime, timezone
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price FROM signals ORDER BY timestamp').fetchall()

day_data = {}
for ts, sym, side, price in signals:
    day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
    ps = conn.execute('SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp', (sym, ts, ts+900)).fetchall()
    if not ps: continue

    hit_tp = hit_sl = False
    for (p,) in ps:
        m = (p - price)/price*100
        if side == 'SHORT': m = -m
        if m >= 0.3: hit_tp = True; break
        if m <= -0.3: hit_sl = True; break

    if day not in day_data:
        day_data[day] = {'wins': 0, 'losses': 0, 'timeouts': 0, 'n': 0}
    day_data[day]['n'] += 1
    if hit_tp: day_data[day]['wins'] += 1
    elif hit_sl: day_data[day]['losses'] += 1
    else: day_data[day]['timeouts'] += 1

print('DAY-BY-DAY EDGE STABILITY (0.3%/0.3%)')
print(f'{\"Day\":12s} {\"n\":>4}  {\"W\":>3}  {\"L\":>3}  {\"T\":>3}  {\"WR%\":>6}  {\"Status\":>8}')
print('-' * 50)

daily_wrs = []
for day in sorted(day_data.keys()):
    d = day_data[day]
    resolved = d['wins'] + d['losses']
    wr = d['wins'] / resolved * 100 if resolved > 0 else 0
    daily_wrs.append(wr)
    status = '✅' if wr > 55 else ('⚠️' if wr > 45 else '❌')
    print(f'{day:12s} {d[\"n\"]:>4}  {d[\"wins\"]:>3}  {d[\"losses\"]:>3}  {d[\"timeouts\"]:>3}  {wr:>5.1f}%  {status:>8}')

if len(daily_wrs) > 1:
    print(f'\nDaily WR — Mean: {statistics.mean(daily_wrs):.1f}%, StdDev: {statistics.stdev(daily_wrs):.1f}%, Min: {min(daily_wrs):.1f}%, Max: {max(daily_wrs):.1f}%')
    consistency = sum(1 for w in daily_wrs if w > 50) / len(daily_wrs) * 100
    print(f'Profitable Days: {consistency:.0f}%')
"
```

## Step 6: Per-Coin Quality
```bash
.venv/bin/python -c "
import sqlite3, statistics
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price FROM signals ORDER BY timestamp').fetchall()

print('PER-COIN EDGE BREAKDOWN — 7 DAY (0.3%/0.3%)')
print(f'{\"Coin\":20s} {\"n\":>4}  {\"WR%\":>6}  {\"MFE%\":>7}  {\"MAE%\":>7}  {\"Ratio\":>6}  {\"Verdict\":>10}')
print('-' * 75)

coin_data = {}
for ts, sym, side, price in signals:
    ps = conn.execute('SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp', (sym, ts, ts+900)).fetchall()
    if not ps: continue
    max_f = max_a = 0.0
    hit_tp = hit_sl = False
    for (p,) in ps:
        m = (p - price)/price*100
        if side == 'SHORT': m = -m
        if m > max_f: max_f = m
        if m < 0 and abs(m) > max_a: max_a = abs(m)
        if not hit_tp and m >= 0.3: hit_tp = True
        if not hit_sl and m <= -0.3: hit_sl = True
    if sym not in coin_data:
        coin_data[sym] = {'mfe': [], 'mae': [], 'wins': 0, 'losses': 0}
    coin_data[sym]['mfe'].append(max_f)
    coin_data[sym]['mae'].append(max_a)
    if hit_tp and not hit_sl: coin_data[sym]['wins'] += 1
    elif hit_sl: coin_data[sym]['losses'] += 1

for sym in sorted(coin_data.keys()):
    d = coin_data[sym]
    n = len(d['mfe'])
    mfe = statistics.mean(d['mfe'])
    mae = statistics.mean(d['mae'])
    ratio = mfe / (mae + 1e-9)
    resolved = d['wins'] + d['losses']
    wr = d['wins'] / resolved * 100 if resolved > 0 else 0
    verdict = 'CERTIFIED' if ratio > 1.2 and wr > 55 else ('WATCH' if ratio > 1.0 else 'FAILED')
    if n < 50: verdict = 'LOW_N'
    print(f'{sym:20s} {n:>4}  {wr:>5.1f}%  {mfe:>6.3f}%  {mae:>6.3f}%  {ratio:>6.2f}  {verdict:>10}')
"
```

---

## ⛔ MANDATORY STOP — Present Results

After Step 6, the agent **MUST STOP** and present:

1. **Aggregate metrics**: n, WR%, MFE/MAE, Expectancy (all coins)
2. **Per-coin table** with Verdicts (compare vs generalized-edge-audit)
3. **Temporal stability**: Day-by-day WR, consistency %, losing days
4. **Generalized vs Long-Range comparison**: Did the edge hold over 7 days?

### Certification Matrix

| Result | Condition | Interpretation |
|--------|-----------|----------------|
| **ROBUST** | WR > 55% AND ≥ 5/7 days profitable AND ≥ 7/10 coins WATCH+ | Production ready |
| **FRAGILE** | WR > 55% BUT < 5/7 days profitable | Regime-dependent |
| **DEGRADED** | WR dropped > 5% vs generalized-edge-audit | Overfitting to short windows |
| **FAILED** | WR < 50% or negative expectancy | No real edge |

**Do NOT proceed without user approval.**
