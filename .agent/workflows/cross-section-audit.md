# Cross-Section Edge Audit — 10 Coins × 24h (Generalizability Test)

// turbo-all

## Overview
This protocol tests whether the LTA V4 Structural Reversion edge **generalizes across instruments**.
A reversion strategy based on Auction Market Theory should work on ANY liquid instrument, not just 3 coins.
If the edge only exists on a subset, it's likely overfitting, not a real market microstructure property.

**Statistical Goal**: n ≥ 300 signals total (cross-instrument), SE on WR ≤ ±2.8%
**Per-Coin Minimum**: n ≥ 10 signals (flags coins with insufficient data)

### Coin Selection (10 Pairs — Diverse Liquidity & Volatility)
| Tier | Coins | Rationale |
|------|-------|-----------|
| **Mega-cap** | BTC, ETH | Highest liquidity, tightest spreads |
| **Large-cap** | SOL, BNB, XRP | High volume, different volatility profiles |
| **Mid-cap** | AVAX, LINK, DOGE | Medium liquidity, wider spreads |
| **Small-cap** | LTC, SUI | Lower liquidity, tests strategy robustness |

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Download 24h Datasets (if not already cached)
Use the most recent 24h window ending ~6h ago (to ensure data completeness).
Calculate timestamps dynamically.

```bash
END_TS=$(($(date +%s) - 21600))
START_TS=$((END_TS - 86400))
echo "Window: $START_TS → $END_TS ($(date -d @$START_TS) → $(date -d @$END_TS))"

COINS=("BTC/USDT:USDT" "ETH/USDT:USDT" "SOL/USDT:USDT" "BNB/USDT:USDT" "XRP/USDT:USDT" "AVAX/USDT:USDT" "LINK/USDT:USDT" "DOGE/USDT:USDT" "LTC/USDT:USDT" "SUI/USDT:USDT")

for COIN in "${COINS[@]}"; do
  SAFE_NAME=$(echo $COIN | tr '/:' '_')
  OUT="tests/validation/cross_section/${SAFE_NAME}_24h.csv"
  if [ -f "$OUT" ]; then
    echo "⏭️ $COIN already cached"
  else
    echo "📥 Downloading $COIN..."
    .venv/bin/python tests/validation/parity_data_fetcher.py \
      --symbol "$COIN" --start $START_TS --end $END_TS --out "$OUT"
  fi
done
```

## Step 2: Run Backtests (All 10 Coins)
```bash
.venv/bin/python reset_data.py > /dev/null 2>&1

COINS=("BTC/USDT:USDT" "ETH/USDT:USDT" "SOL/USDT:USDT" "BNB/USDT:USDT" "XRP/USDT:USDT" "AVAX/USDT:USDT" "LINK/USDT:USDT" "DOGE/USDT:USDT" "LTC/USDT:USDT" "SUI/USDT:USDT")

for COIN in "${COINS[@]}"; do
  SAFE_NAME=$(echo $COIN | tr '/:' '_')
  DATA="tests/validation/cross_section/${SAFE_NAME}_24h.csv"
  echo "▶ $COIN..."
  .venv/bin/python backtest.py \
    --data "$DATA" --symbol "$COIN" \
    --depth-db data/historian.db --audit \
    > /dev/null 2>&1 && echo "✅ $COIN" || echo "❌ $COIN"
done
echo "🏁 ALL 10 BACKTESTS COMPLETE"
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

# Per-coin breakdown
rows = conn.execute('SELECT symbol, COUNT(*) FROM signals GROUP BY symbol ORDER BY COUNT(*) DESC').fetchall()
print('Per-Coin Breakdown:')
for sym, cnt in rows:
    flag = '⚠️' if cnt < 10 else '✅'
    print(f'  {flag} {sym:20s}: {cnt} signals')
"
```
**Minimum**: Total Signals ≥ 300. Per-coin ≥ 10 (flag if less).

## Step 4: Edge Audit
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 900
```

## Step 5: Per-Coin Quality Analysis
```bash
.venv/bin/python -c "
import sqlite3, ast, statistics
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price, metadata FROM signals ORDER BY timestamp').fetchall()

print('PER-COIN EDGE BREAKDOWN (0.3%/0.3%)')
print(f'{\"Coin\":20s} {\"n\":>4}  {\"WR%\":>6}  {\"MFE%\":>7}  {\"MAE%\":>7}  {\"Ratio\":>6}  {\"Verdict\":>10}')
print('-' * 75)

coin_data = {}
for ts, sym, side, price, meta in signals:
    ps = conn.execute('SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp', (sym, ts, ts+900)).fetchall()
    if not ps:
        continue
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
        coin_data[sym] = {'mfe': [], 'mae': [], 'wins': 0, 'losses': 0, 'timeouts': 0}
    coin_data[sym]['mfe'].append(max_f)
    coin_data[sym]['mae'].append(max_a)
    if hit_tp and (not hit_sl): coin_data[sym]['wins'] += 1
    elif hit_sl: coin_data[sym]['losses'] += 1
    else: coin_data[sym]['timeouts'] += 1

for sym in sorted(coin_data.keys()):
    d = coin_data[sym]
    n = len(d['mfe'])
    mfe = statistics.mean(d['mfe'])
    mae = statistics.mean(d['mae'])
    ratio = mfe / (mae + 1e-9)
    resolved = d['wins'] + d['losses']
    wr = d['wins'] / resolved * 100 if resolved > 0 else 0
    verdict = 'CERTIFIED' if ratio > 1.2 and wr > 55 else ('WATCH' if ratio > 1.0 else 'FAILED')
    if n < 10: verdict = 'LOW_N'
    print(f'{sym:20s} {n:>4}  {wr:>5.1f}%  {mfe:>6.3f}%  {mae:>6.3f}%  {ratio:>6.2f}  {verdict:>10}')
"
```

---

## ⛔ MANDATORY STOP — Present Results

After Step 5, the agent **MUST STOP** and present:

1. **Aggregate table** (all 10 coins combined): n, WR%, MFE/MAE, Expectancy
2. **Per-coin breakdown table** with individual Verdicts
3. **Generalizability Score**: How many coins CERTIFIED / WATCH / FAILED
4. **Specific observations** per coin (e.g., "BTC has tight spreads producing higher WR", "DOGE has wider spreads killing edge")

### Certification Matrix

| Result | Condition | Interpretation |
|--------|-----------|----------------|
| **GENERALIZED** | ≥ 7/10 coins CERTIFIED or WATCH | Edge is real, based on market microstructure |
| **PARTIAL** | 4-6/10 coins CERTIFIED or WATCH | Edge exists but instrument-dependent |
| **FAILED** | ≤ 3/10 coins CERTIFIED or WATCH | Edge is likely overfitting to specific instruments |

**Do NOT proceed to further optimization without user approval.**
