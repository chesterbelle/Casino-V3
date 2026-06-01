---
description: Profile Validation Protocol (VOLATIL_BAJO_FLOW Profile — LTC, SUI, AVAX × Set A)
---

# Profile Validation Protocol — VOLATIL_BAJO_FLOW Profile (Set A)

// turbo-all

## Overview
Validates that the coin profile system works correctly for the VOLATIL_BAJO_FLOW profile using its constituent assets (LTC, SUI, AVAX) across multiple market conditions.
Runs backtests across three distinct conditions using Set A and validates:
- Profile assignment correctness
- Performance consistency
- L2 depth predictive power

**Asset Cluster:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **LTC** | LTC/USDT:USDT | VOLATIL_BAJO_FLOW | Baseline asset, naturally mean-reverting |
| **SUI** | SUI/USDT:USDT | VOLATIL_BAJO_FLOW | Mid-cap, clean volume flows and structural reversion |
| **AVAX** | AVAX/USDT:USDT | VOLATIL_BAJO_FLOW | Clean sub-minute trends, high structural level respect |

**Market Conditions & Datasets (Set A):**
| Asset | Datasets | Protocol |
|-------|----------|----------|
| **LTC** | LTC_TREND_UP_2023-02-01.db, LTC_TREND_UP_2025-05-01.db, LTC_TREND_DOWN_2024-04-01.db, LTC_TREND_DOWN_2024-10-01.db, LTC_BALANCE_2024-02-01.db, LTC_BALANCE_2024-05-01.db | `set_a` |
| **AVAX** | 2023-02-01_AVAXUSDT.db, 2024-02-01_AVAXUSDT.db, 2024-04-01_AVAXUSDT.db, 2024-05-01_AVAXUSDT.db, 2024-10-01_AVAXUSDT.db, 2025-05-01_AVAXUSDT.db | `set_a_avax` |
| **SUI** | 2024-02-01_SUIUSDT.db, 2024-05-01_SUIUSDT.db | `set_a_sui` |

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
echo "=== LTC Set A Datasets ==="
for f in \
  data/datasets/backtest_ready/LTC_TREND_UP_2023-02-01.db \
  data/datasets/backtest_ready/LTC_TREND_UP_2025-05-01.db \
  data/datasets/backtest_ready/LTC_TREND_DOWN_2024-04-01.db \
  data/datasets/backtest_ready/LTC_TREND_DOWN_2024-10-01.db \
  data/datasets/backtest_ready/LTC_BALANCE_2024-02-01.db \
  data/datasets/backtest_ready/LTC_BALANCE_2024-05-01.db; do
  [ -f "$f" ] && echo "✅ $(basename $f): $(du -h $f | cut -f1)" || echo "❌ MISSING: $f"
done

echo ""
echo "=== AVAX Set A Datasets ==="
for f in \
  data/datasets/backtest_ready/2023-02-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2024-02-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2024-04-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2024-05-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2024-10-01_AVAXUSDT.db \
  data/datasets/backtest_ready/2025-05-01_AVAXUSDT.db; do
  [ -f "$f" ] && echo "✅ $(basename $f): $(du -h $f | cut -f1)" || echo "❌ MISSING: $f"
done

echo ""
echo "=== SUI Set A Datasets ==="
for f in \
  data/datasets/backtest_ready/2024-02-01_SUIUSDT.db \
  data/datasets/backtest_ready/2024-05-01_SUIUSDT.db; do
  [ -f "$f" ] && echo "✅ $(basename $f): $(du -h $f | cut -f1)" || echo "❌ MISSING: $f"
done
```
**⛔ STOP if any dataset is missing.** Re-download + process with:
```bash
# .venv/bin/python utils/data/tardis_fetcher.py --symbol <SYM> --start YYYY-MM-01
# .venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYM>
```

---

## Step 2: Setup Environment & Run Audit (3 Assets en Sucesión)

```bash
mkdir -p logs
```

> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> Los tres protocolos corren secuencialmente. Los dos primeros (`set_a` y `set_a_avax`) tienen `skip_merge=True` — el merge se hace UNA SOLA VEZ al final, tras completar los tres. El agente DEBE actuar de manera 100% autónoma y reportar el progreso periódicamente.
>
> Sigue EXACTAMENTE esta secuencia:
>
> **① LTC — set_a** (6 datasets, ~3 workers, merge omitido internamente)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a \
>   > logs/orchestrator_ltc.log 2>&1
> ```
>
> **② AVAX — set_a_avax** (6 datasets, ~3 workers, merge omitido internamente)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a_avax \
>   > logs/orchestrator_avax.log 2>&1
> ```
>
> **③ SUI — set_a_sui** (2 datasets, ~2 workers, merge omitido internamente)
> ```bash
> PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol set_a_sui \
>   > logs/orchestrator_sui.log 2>&1
> ```
>
> **④ Merge único final** (una vez que los 3 protocolos hayan terminado exitosamente)
> ```bash
> .venv/bin/python utils/merge_historian.py
> ```
>
> En cada revisión (cada 5 min), haz `tail -n 20 logs/orchestrator_<asset>.log` y reporta al usuario el progreso activo.

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

## Step 4: Profile Diagnostic (Validar Perfil)
```bash
.venv/bin/python utils/profile_diagnostic.py --db data/historian.db --all --exchange
```
**Output**: Real metrics vs profile characteristics, verdict (MATCH/REASSIGN/CREATE)

**What to look for:**
- ¿LTCUSDT, AVAXUSDT, SUIUSDT → todos asignados a VOLATIL_BAJO_FLOW?
- ¿Las métricas reales (spread_ratio, depth_ratio, speed) están dentro de los rangos del perfil?
- Si no, ¿cuál es la acción recomendada?

---

## Step 5: Edge Audit (Performance)
```bash
.venv/bin/python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin
```
**Output**: Win Rate, MFE/MAE, Net Taker per condition, por moneda

**What to look for:**
- ¿Net Taker positivo en cada activo?
- ¿MFE/MAE > 1.0?
- ¿Varía el performance por condición de mercado?

---

## Step 6: L2 Depth Audit (Validar depth_ratio)
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
| ¿LTC/AVAX/SUI → VOLATIL_BAJO_FLOW? | Step 4 |
| ¿Performance positivo en los 3 activos? | Step 5 |
| ¿L2 depth predictivo? | Step 6 |
| ¿Targets óptimos consistentes entre activos? | Step 7 |

---

## ⛔ MANDATORY STOP — Present Results

After Step 8, the agent **MUST STOP COMPLETELY** and present:

1. **Profile Validation** (Step 4) — por activo:
   - Assigned profile: VOLATIL_BAJO_FLOW
   - Real metrics: spread_ratio, depth_ratio, speed
   - Match status: ✅ or ❌

2. **Performance Results** (Step 5) — por activo:
   - Win Rate: X%
   - MFE/MAE: X.XX
   - Net Taker: +X.XX%
   - Per-condition breakdown

3. **L2 Depth Analysis** (Step 6):
   - High Wall vs Thin Wall MFE/MAE
   - ¿depth_ratio validado?

4. **Target Optimization** (Step 7) — por activo:
   - Optimal target: X.X%
   - Optimal window: Xh

5. **Correlation Analysis** (Step 8):
   - Profile correct + Performance good → System working
   - Profile correct + Performance bad → Strategy issue
   - Profile wrong → Adjust profile
   - L2 depth predictive → depth_ratio validated

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
| LTC/AVAX/SUI | BALANCE | ✅ | Expectancy > 0.12% | High Wall > Thin Wall | **CERTIFIED** |
| LTC/AVAX/SUI | BALANCE | ✅ | Expectancy > 0.12% | — | **WATCH** |
| LTC/AVAX/SUI | BALANCE | ❌ | Any | — | **PROFILE WRONG** |
| LTC/AVAX/SUI | TREND_UP / TREND_DOWN | ✅ | Expectancy > 0.12% | — | **GUARDIAN OK** |
| LTC/AVAX/SUI | TREND_UP / TREND_DOWN | ❌ | Any | — | **PROFILE INCONSISTENT** |

---

## Appendix: VOLATIL_BAJO_FLOW Profile

Current characteristics:
```python
"spread_ratio": {"min": 0.0, "max": 2.0}
"depth_ratio":  {"min": 0.0, "max": 1.5}
"speed":        {"min": 0.0, "max": 0.04}
```

Current parameters:
```python
z_score_min: 3.5
concentration_min: 0.40
noise_max: 0.40
TP (TacticalAbsorption): per-regime (UP=1.2%, DOWN=2.0%, BALANCE=0.8%)
SL (TacticalAbsorption): per-regime (UP=4.0%, DOWN=5.0%, BALANCE=4.0%)
fallback TP/SL: 2.4%/2.5%
l2_ratio_min: 1.0
```
