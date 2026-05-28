---
description: Auditoría de Borde Generalizada (10 Coins × 24h)
---

# Generalized Edge Audit — 10 Coins × 24h (Cross-Instrument Validation)

// turbo-all

## Overview
Tests whether the strategy edge **generalizes across instruments**.
A reversion strategy based on Auction Market Theory should work on ANY liquid instrument.
If the edge only exists on a subset, it's likely overfitting, not a real market property.

**Prerequisites**: 24h datasets must exist in `data/datasets/backtest_ready/`.
Download them with `utils/data/tardis_fetcher.py` before running this protocol.

**Expected files** (one per coin):
```
data/datasets/backtest_ready/2024-01-01_ADAUSDT.db
data/datasets/backtest_ready/2024-01-01_ETHUSDT.db
data/datasets/backtest_ready/2024-01-01_SOLUSDT.db
data/datasets/backtest_ready/2024-01-01_BNBUSDT.db
data/datasets/backtest_ready/2024-01-01_BTCUSDT.db
data/datasets/backtest_ready/2024-01-01_AVAXUSDT.db
data/datasets/backtest_ready/2024-01-01_LINKUSDT.db
data/datasets/backtest_ready/2024-01-01_DOGEUSDT.db
data/datasets/backtest_ready/2024-01-01_LTCUSDT.db
data/datasets/backtest_ready/2024-01-01_SUIUSDT.db
```

**Statistical Goal**: n ≥ 300 signals total, SE on WR ≤ ±2.8%
**Per-Coin Minimum**: n ≥ 10 signals (flag if less)

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Setup Environment & Verify Datasets
```bash
mkdir -p logs
echo "=== Dataset Verification ==="
for f in \
  data/datasets/backtest_ready/2024-01-01_ADAUSDT.db \
  data/datasets/backtest_ready/2024-01-01_ETHUSDT.db \
  data/datasets/backtest_ready/2024-01-01_SOLUSDT.db \
  data/datasets/backtest_ready/2024-01-01_BNBUSDT.db \
  data/datasets/backtest_ready/2024-01-01_BTCUSDT.db \
  data/datasets/backtest_ready/2024-01-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2024-01-01_LINKUSDT.db \
  data/datasets/backtest_ready/2024-01-01_DOGEUSDT.db \
  data/datasets/backtest_ready/2024-01-01_LTCUSDT.db \
  data/datasets/backtest_ready/2024-01-01_SUIUSDT.db; do
  if [ -f "$f" ]; then
    echo "✅ $(basename $f): $(du -h $f | cut -f1)"
  else
    echo "❌ MISSING: $f"
  fi
done
```
**⛔ STOP if any datasets are missing.** Inform the user which files need to be downloaded.

## Step 2: Run Audit

> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> Como este proceso puede durar horas procesando Gigabytes de datos, el agente **DEBE** actuar de manera 100% autónoma y reportar el progreso periódicamente al usuario, sin que este deba pedirlo o ejecutar comandos manualmente.
>
> Sigue EXACTAMENTE esta secuencia:
> 1. Lanza el orquestador en **segundo plano** redirigiendo la salida para poder monitorearla:
>    ```bash
>    PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol generalized > logs/orchestrator_run.log 2>&1
>    ```
> 2. Implementa un mecanismo de monitoreo en segundo plano (ej. un script de loop, tarea programada o revisión periódica) para leer el log cada 5 minutos.
> 3. En cada revisión, haz `tail -n 20 logs/orchestrator_run.log`, extrae qué dataset está procesándose y su tamaño, e **imprime un reporte en el chat para el usuario** (Ej: "📊 Progreso: ETHUSDT - 2/10 completados. DB Size: 45MB").
> 4. Cuando el log indique que el proceso ha finalizado, detén tu monitoreo y continúa al Step 3.


## Step 3: Merge Databases & Verify Data Collection
```bash
# Consolidate all historian_<symbol>.db into master historian.db
.venv/bin/python utils/merge_historian.py
```
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

## Step 4: Edge Audit
Evaluate current strategy performance:
```bash
.venv/bin/python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin
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

---

## ⛔ MANDATORY STOP — Present Results

After Step 5, the agent **MUST STOP** and present:

1. **Aggregate table** (all 10 coins combined): n, WR%, Gross Expectancy%, Net (Taker), Net (Maker)
2. **Per-coin breakdown table** with individual Verdicts based on Expectancy
3. **Generalizability Score**: How many coins CERTIFIED / WATCH / FAILED
4. **Specific observations** per coin (e.g., "ETH has high MAE, needs tighter filters")

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
