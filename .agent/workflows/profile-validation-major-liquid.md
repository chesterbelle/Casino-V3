---
description: Profile Validation Protocol (MAJOR_LIQUID Profile — SOL × BTC × ETH)
---

# Profile Validation Protocol — MAJOR_LIQUID Profile (Set A)

// turbo-all

## Overview
Validates that the coin profile system works correctly for the MAJOR_LIQUID profile using its constituent assets (SOL, BTC, ETH) across multiple market conditions.
Runs backtests across distinct conditions using Set A and validates:
- Profile assignment correctness (MAJOR_LIQUID via 4-dim institutional clustering)
- Performance consistency
- L2 depth predictive power

**Asset Cluster:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **SOL** | SOL/USDT:USDT | MAJOR_LIQUID | Alta relación volumen/volatilidad |
| **BTC** | BTC/USDT:USDT | MAJOR_LIQUID | Alta relación volumen/volatilidad |
| **ETH** | ETH/USDT:USDT | MAJOR_LIQUID | Alta relación volumen/volatilidad |

**Market Conditions & Datasets (Set A):**
| Asset | Datasets | Protocol |
|-------|----------|----------|
| **SOL** | 2024-05-01_SOLUSDT.db, 2024-11-01_SOLUSDT.db, 2025-01-01_SOLUSDT.db, 2025-02-01_SOLUSDT.db, 2025-09-01_SOLUSDT.db, 2025-11-01_SOLUSDT.db | `set_a_sol` |
| **BTC** | 2024-11-01_BTCUSDT.db, 2025-02-01_BTCUSDT.db, 2025-04-01_BTCUSDT.db, 2025-10-01_BTCUSDT.db, 2025-11-01_BTCUSDT.db, 2026-05-01_BTCUSDT.db | `set_a_btc` |
| **ETH** | 2024-08-01_ETHUSDT.db, 2024-09-01_ETHUSDT.db, 2024-10-01_ETHUSDT.db, 2024-11-01_ETHUSDT.db, 2025-02-01_ETHUSDT.db, 2025-07-01_ETHUSDT.db | `set_a_eth` |

**Statistical Goal**: n ≥ 100 signals total per asset, n ≥ 25 per condition

---

## Step 0: Nuclear Reset
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

---

## Step 1: Verify Datasets Exist
```bash
echo "=== MAJOR_LIQUID Set A Datasets ==="
for f in \
  data/datasets/backtest_ready/2024-05-01_SOLUSDT.db \
  data/datasets/backtest_ready/2024-11-01_SOLUSDT.db \
  data/datasets/backtest_ready/2025-01-01_SOLUSDT.db \
  data/datasets/backtest_ready/2025-02-01_SOLUSDT.db \
  data/datasets/backtest_ready/2025-09-01_SOLUSDT.db \
  data/datasets/backtest_ready/2025-11-01_SOLUSDT.db \
  data/datasets/backtest_ready/2024-11-01_BTCUSDT.db \
  data/datasets/backtest_ready/2025-02-01_BTCUSDT.db \
  data/datasets/backtest_ready/2025-04-01_BTCUSDT.db \
  data/datasets/backtest_ready/2025-10-01_BTCUSDT.db \
  data/datasets/backtest_ready/2025-11-01_BTCUSDT.db \
  data/datasets/backtest_ready/2026-05-01_BTCUSDT.db \
  data/datasets/backtest_ready/2024-08-01_ETHUSDT.db \
  data/datasets/backtest_ready/2024-09-01_ETHUSDT.db \
  data/datasets/backtest_ready/2024-10-01_ETHUSDT.db \
  data/datasets/backtest_ready/2024-11-01_ETHUSDT.db \
  data/datasets/backtest_ready/2025-02-01_ETHUSDT.db \
  data/datasets/backtest_ready/2025-07-01_ETHUSDT.db; do
  [ -f "$f" ] && echo "✅ $(basename $f): $(du -h $f | cut -f1)" || echo "❌ MISSING: $f"
done
```
**⛔ STOP if any dataset is missing.** Re-download + process with:
```bash
# .venv/bin/python utils/data/tardis_fetcher.py --symbol <SYM> --start YYYY-MM-01
# .venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYM>
```

---

## Step 2: Setup Environment & Run Audit

```bash
mkdir -p logs
```

> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> El protocolo corre de manera autónoma. El agente DEBE actuar de manera 100% autónoma y reportar el progreso periódicamente.
>
> **① SOL — set_a_sol** (6 datasets, ~3 workers)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a_sol \
>   > logs/orchestrator_sol.log 2>&1
> ```
>
> **② BTC — set_a_btc** (6 datasets, ~3 workers)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a_btc \
>   > logs/orchestrator_btc.log 2>&1
> ```
>
> **③ ETH — set_a_eth** (6 datasets, ~3 workers)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a_eth \
>   > logs/orchestrator_eth.log 2>&1
> ```
>
> **④ Merge final**
> ```bash
> .venv/bin/python utils/merge_historian.py
> ```
>
> En cada revisión (cada 5 min), haz `tail -n 20 logs/orchestrator_*.log` y reporta al usuario el progreso activo.

---

## Step 3: Verify Data Collection

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/historian.db')
s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]
print(f'Signals: {s}, Price Samples: {p}')

# Por moneda
rows = conn.execute('SELECT symbol, COUNT(*) FROM signals GROUP BY symbol').fetchall()
for sym, cnt in rows:
    print(f'  {sym}: {cnt} signals')

print()
print('✅ OK' if s >= 100 else '⚠️ INSUFFICIENT DATA')
"
```
**Minimum**: Signals ≥ 100 total, ≥ 25 per condition per asset.

---

## Step 4: Profile Diagnostic (Post-audit — Confirm)

```bash
.venv/bin/python utils/profile_diagnostic.py --db data/historian.db --all
```
**Output**: Real metrics vs profile characteristics, verdict (MATCH/REASSIGN/CREATE)

**What to look for:**
- ¿SOLUSDT, BTCUSDT, ETHUSDT → asignado a MAJOR_LIQUID?
- ¿Las métricas reales están dentro de los rangos del perfil?

---

## Step 5: Edge Audit (Performance)
```bash
.venv/bin/python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin
```
**Output**: Win Rate, MFE/MAE, Net Taker per condition, por moneda

**What to look for:**
- ¿Net Taker positivo?
- ¿MFE/MAE > 1.0?
- ¿Varía el performance por condición de mercado?

---

## Step 6: L2 Depth Audit (Validar l2_ratio_min)
```bash
.venv/bin/python utils/l2_depth_auditor.py
```
**Output**: ¿El L2 depth predice el performance?

**What to look for:**
- ¿High Wall (>2.0) tiene mejor MFE/MAE que Thin Wall (<1.0)?
- ¿Es el threshold `l2_ratio_min` del perfil predictivo?

---

## Step 7: Multi-Window Target Grid
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

## Step 8: Correlation Analysis
Compare results from all steps:

| Question | Answer Source |
|----------|---------------|
| ¿SOL/BTC/ETH → MAJOR_LIQUID? | Step 4 (post-audit) |
| ¿Performance positivo? | Step 6 |
| ¿L2 depth predictivo? | Step 7 |
| ¿Targets óptimos consistentes? | Step 8 |

---

## ⛔ MANDATORY STOP — Present Results

After Step 9, the agent **MUST STOP COMPLETELY** and present:

1. **Profile Validation** (Step 4):
   - Assigned profile: MAJOR_LIQUID
   - Real metrics: tick_size_efficiency, book_density, volume_vol_ratio, speed
   - Match status: ✅ or ❌

2. **Performance Results** (Step 5):
   - Win Rate: X%
   - MFE/MAE: X.XX
   - Net Taker: +X.XX%
   - Per-condition breakdown

3. **L2 Depth Analysis** (Step 6):
   - High Wall vs Thin Wall MFE/MAE
   - ¿l2_ratio_min validado?

4. **Target Optimization** (Step 7):
   - Optimal target: X.X%
   - Optimal window: Xh

5. **Correlation Analysis** (Step 9):
   - Profile correct + Performance good → System working
   - Profile correct + Performance bad → Strategy issue
   - Profile wrong → Adjust profile
   - L2 depth predictive → l2_ratio_min validated

6. **Recommendations**:
   - Keep profile as-is
   - Adjust parameters
   - Create new profile
   - Investigate strategy further

**Do NOT proceed to next phase without user approval.**

---

## Certification Matrix

| Asset | Condition | Profile Match | Performance | L2 Depth | Verdict |
|-------|-----------|---------------|-------------|----------|---------|
| SOL | BALANCE | ✅ | Expectancy > 0.12% | High Wall > Thin Wall | **CERTIFIED** |
| BTC | BALANCE | ✅ | Expectancy > 0.12% | — | **WATCH** |
| ETH | BALANCE | ✅ | Expectancy > 0.12% | — | **WATCH** |
| * | BALANCE | ❌ | Any | — | **PROFILE WRONG** |
| * | TREND_UP / TREND_DOWN | ✅ | Expectancy > 0.12% | — | **GUARDIAN OK** |
| * | TREND_UP / TREND_DOWN | ❌ | Any | — | **PROFILE INCONSISTENT** |

---

## Appendix: MAJOR_LIQUID Profile (current)

4-dim institutional microstructure (per `config/clusters_fixed.json`):
```python
"tick_size_efficiency": 0.45   # How fast spread clears
"book_density": 20.0          # Total volume / spread
"volume_vol_ratio": 11.0      # Energy to move price
"speed": 26.0                 # Trades per second
```

Current parameters (per `config/coin_profiles.py`):
```python
# Sensors
z_score_min: 3.5
concentration_min: 0.40
noise_max: 0.40
# Targets (per-regime for TacticalAbsorptionV2)
TREND_UP:   TP 1.0% / SL 0.8%
TREND_DOWN: TP 1.5% / SL 1.2%
BALANCE:    TP 1.2% / SL 1.0%
Fallback:   TP 2.4% / SL 2.5%
# Guardians
l2_ratio_min: 0.5
l2_ratio_min_trend_down: 2.0
spread_max_ratio: 2.0
```

**Membership**: SOL, BTC, ETH (from clusters_fixed.json).
