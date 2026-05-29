---
description: Profile Validation Protocol (LTC × 3 Market Conditions × 3 Days)
---

# Profile Validation Protocol — LTC × 3 Conditions × 3 Days

// turbo-all

## Overview
Validates that the coin profile system works correctly using LTCUSDT across multiple market conditions.
Runs 9 backtests across three distinct conditions (3 days each) and validates:
- Profile assignment correctness
- Performance consistency
- L2 depth predictive power

**Asset:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **LTC** | LTC/USDT:USDT | VOLATIL_BAJO_FLOW | Baseline asset, naturally mean-reverting |

**Market Conditions & Datasets:**

### LTC (Day 1s from Tardis Free Tier)
| Condition | Datasets |
|-----------|----------|
| **RANGE** | LTC_RANGE_2024-02-01.db, LTC_RANGE_2024-05-01.db, LTC_RANGE_2024-08-01.db |
| **BEAR**  | LTC_BEAR_2024-04-01.db, LTC_BEAR_2024-10-01.db, LTC_BEAR_2025-02-01.db |
| **BULL**  | LTC_BULL_2024-03-01.db, LTC_BULL_2024-12-01.db, LTC_BULL_2025-05-01.db |

**Statistical Goal**: n ≥ 100 signals total, n ≥ 25 per condition

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

## Step 2: Setup Environment & Run Audit

```bash
mkdir -p logs
```
> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> Como este proceso puede durar horas procesando 9 meses de datos, el agente **DEBE** actuar de manera 100% autónoma y reportar el progreso periódicamente al usuario, sin que este deba pedirlo o ejecutar comandos manualmente.
>
> Sigue EXACTAMENTE esta secuencia:
> 1. Lanza el orquestador en **segundo plano** redirigiendo la salida para poder monitorearla:
>    ```bash
>    PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol long-range > logs/orchestrator_run.log 2>&1
>    ```
> 2. Implementa un mecanismo de monitoreo en segundo plano (ej. un script de loop, tarea programada o revisión periódica) para leer el log cada 5 minutos.
> 3. En cada revisión, haz `tail -n 20 logs/orchestrator_run.log`, extrae qué dataset está procesándose y su tamaño, e **imprime un reporte en el chat para el usuario** (Ej: "📊 Progreso: LTC_BEAR - 2/9 completados").
> 4. Cuando el log indique que el proceso ha finalizado, detén tu monitoreo y continúa al Step 3.


---

## Step 3: Merge Databases & Verify Data Collection
```bash
# Consolidate all historian_<condition>_<date>.db into master historian.db
.venv/bin/python utils/merge_historian.py
```
```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/historian.db')
s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]
print(f'Signals: {s}, Price Samples: {p}')
print('✅ OK' if s >= 100 else '⚠️ INSUFFICIENT DATA')
"
```
**Minimum**: Signals ≥ 100 total. If fewer, mark as INSUFFICIENT DATA.

---

## Step 4: Profile Diagnostic (Validar Perfil)
```bash
.venv/bin/python utils/profile_diagnostic.py --db data/historian.db --all
```
**Output**: Real metrics vs profile characteristics, verdict (MATCH/REASSIGN/CREATE)

**What to look for:**
- Does LTCUSDT match VOLATIL_BAJO_FLOW?
- Are the real metrics within the profile's characteristics?
- If not, what's the recommended action?

---

## Step 5: Edge Audit (Performance)
```bash
.venv/bin/python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin
```
**Output**: Win Rate, MFE/MAE, Net Taker per condition

**What to look for:**
- Is Net Taker positive?
- Is MFE/MAE > 1.0?
- Does performance vary by market condition?

---

## Step 6: L2 Depth Audit (Validar depth_ratio)
```bash
.venv/bin/python utils/l2_depth_auditor.py
```
**Output**: Is L2 depth predictive of performance?

**What to look for:**
- High Wall (>2.0) has better MFE/MAE than Thin Wall (<1.0)?
- Is the l2_ratio_min threshold in the profile predictive?
- Does this validate the depth_ratio characteristic?

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
| Does LTCUSDT match VOLATIL_BAJO_FLOW? | Step 4 |
| Is performance positive? | Step 5 |
| Is L2 depth predictive? | Step 6 |
| Are optimal targets consistent? | Step 7 |

---

## ⛔ MANDATORY STOP — Present Results

After Step 8, the agent **MUST STOP COMPLETELY** and present:

1. **Profile Validation** (Step 4):
   - Assigned profile: VOLATIL_BAJO_FLOW
   - Real metrics: spread_ratio, depth_ratio, speed
   - Match status: ✅ or ❌

2. **Performance Results** (Step 5):
   - Win Rate: X%
   - MFE/MAE: X.XX
   - Net Taker: +X.XX%
   - Per-condition breakdown

3. **L2 Depth Analysis** (Step 6):
   - High Wall vs Thin Wall MFE/MAE
   - Is depth_ratio characteristic predictive?

4. **Target Optimization** (Step 7):
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

**Do NOT proceed to multi-coin without user approval.**

---

## Certification Matrix

| Condition | Profile Match | Performance | L2 Depth | Verdict |
|-----------|---------------|-------------|----------|---------|
| Range | ✅ | Expectancy > 0.36% | High Wall > Thin Wall | **CERTIFIED** |
| Range | ✅ | Expectancy > 0.12% | — | **WATCH** |
| Range | ❌ | Any | — | **PROFILE WRONG** |
| Bear/Bull | ✅ | Expectancy > 0.12% | — | **GUARDIAN OK** |
| Bear/Bull | ❌ | Any | — | **PROFILE INCONSISTENT** |

---

## Appendix: LTCUSDT Profile (VOLATIL_BAJO_FLOW)

Current characteristics:
```python
"spread_ratio": {"min": 0.0, "max": 2.0}
"depth_ratio": {"min": 0.0, "max": 1.5}
"speed": {"min": 0.0, "max": 0.04}
```

Current parameters:
```python
z_score_min: 2.5
concentration_min: 0.40
noise_max: 0.40
TP (TacticalAbsorption): 0.90%
SL (TacticalAbsorption): 0.90%
l2_ratio_min: 1.5
```
