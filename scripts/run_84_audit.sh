#!/bin/bash
cd /home/chesterbelle/Casino-V3

echo "=== Nuclear Reset ==="
rm -f data/historian*.db

echo "=== Running Audit on all 84 datasets (14 symbols) ==="
SYMBOLS=(ADAUSDT APTUSDT ARBUSDT AVAXUSDT BNBUSDT BTCUSDT DOGEUSDT ETHUSDT LINKUSDT LTCUSDT NEARUSDT OPUSDT SOLUSDT XRPUSDT)

for sym in "${SYMBOLS[@]}"; do
    echo "Processing $sym..."
    python scripts/backtest_runner.py --mode audit --symbol $sym
done

echo "=== Merging databases ==="
python utils/merge_historian.py

echo "=== Edge Audit Global ==="
python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin > logs/final_edge_audit.txt

echo "=== Per-Coin Quality Analysis ==="
python -c "
import sqlite3, statistics
conn = sqlite3.connect('data/historian.db')
signals = conn.execute('SELECT timestamp, symbol, side, price, metadata FROM signals ORDER BY timestamp').fetchall()

windows = [14400]
targets = [0.8, 1.0, 1.5, 2.0, 3.0, 5.0]

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
" > logs/final_quality_analysis.txt

echo "=== Done! ==="
