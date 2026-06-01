---
description: Profile Validation Protocol (MID_LIQUID Profile — LTC, AVAX × Set A, no SUI)
---

# Profile Validation Protocol — MID_LIQUID Profile (Set A)

// turbo-all

## Overview
Validates that the coin profile system works correctly for the MID_LIQUID profile using its constituent assets (LTC, AVAX) across multiple market conditions.
Runs backtests across distinct conditions using Set A and validates:
- Profile assignment correctness (MID_LIQUID via 5-dim microstructure)
- Performance consistency
- L2 depth predictive power

**Asset Cluster:**
| Asset | Symbol | Profile | Why |
|-------|--------|---------|-----|
| **LTC** | LTC/USDT:USDT | MID_LIQUID | Baseline asset, validated iter 3 |
| **AVAX** | AVAX/USDT:USDT | MID_LIQUID | Borderline (vol 1.06%), included for coverage |

> **Note**: SUI excluded — TAV entry failure (MFE/MAE 0.83), separately classified THIN_VOLATILE.

**Market Conditions & Datasets (Set A):**
| Asset | Datasets | Protocol |
|-------|----------|----------|
| **LTC** | LTC_TREND_UP_2023-02-01.db, LTC_TREND_UP_2025-05-01.db, LTC_TREND_DOWN_2024-04-01.db, LTC_TREND_DOWN_2024-10-01.db, LTC_BALANCE_2024-02-01.db, LTC_BALANCE_2024-05-01.db | `set_a` |
| **AVAX** | 2023-02-01_AVAXUSDT.db, 2024-02-01_AVAXUSDT.db, 2024-04-01_AVAXUSDT.db, 2024-05-01_AVAXUSDT.db, 2024-10-01_AVAXUSDT.db, 2025-05-01_AVAXUSDT.db | `set_a_avax` |

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
```
**⛔ STOP if any dataset is missing.** Re-download + process with:
```bash
# .venv/bin/python utils/data/tardis_fetcher.py --symbol <SYM> --start YYYY-MM-01
# .venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYM>
```

---

## Step 2: Profile Diagnostic (Pre-flight — Validate MID_LIQUID Assignment)

Run exchange-based diagnostic for each test coin BEFORE the audit. Both should match MID_LIQUID.

```bash
mkdir -p logs

for sym in LTC/USDT:USDT AVAX/USDT:USDT; do
  echo "═════════════════════════════════════════════════════════════════"
  echo "  DIAGNOSTIC: $sym"
  echo "═════════════════════════════════════════════════════════════════"
  .venv/bin/python utils/profile_diagnostic.py --symbol "$sym" --exchange
  echo ""
done
```

**What to look for:**
- ¿Ambos coins → `✅ MATCH: MID_LIQUID`?
- ¿Las 5 dimensiones reales (spread_bps, depth_ratio, speed, avg_trade_size, vol_realized_4h) están dentro de los rangos MID_LIQUID?
- Si AVAX no matchea MID, **STOP** — reconsiderar si AVAX pertenece a este workflow (probablemente debería ir a un workflow `profile-validation-thin-volatile.md`).

**Mid-flight stop criteria:**
- ❌ Cualquier coin sin `MATCH: MID_LIQUID` → STOP y discutir con el usuario
- ⚠️ Métricas borderline (ej. AVAX vol ~1.0%) → continuar con nota

---

## Step 3: Setup Environment & Run Audit (2 Assets, No SUI)

```bash
mkdir -p logs
```

> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> Los dos protocolos corren secuencialmente. Ambos tienen `skip_merge=True` — el merge se hace UNA SOLA VEZ al final. El agente DEBE actuar de manera 100% autónoma y reportar el progreso periódicamente.
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
> **③ Merge único final** (una vez que los 2 protocolos hayan terminado exitosamente)
> ```bash
> .venv/bin/python utils/merge_historian.py
> ```
>
> En cada revisión (cada 5 min), haz `tail -n 20 logs/orchestrator_<asset>.log` y reporta al usuario el progreso activo.

---

## Step 4: Verify Data Collection

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

## Step 5: Profile Diagnostic (Post-audit — Confirm)

```bash
.venv/bin/python utils/profile_diagnostic.py --db data/historian.db --all
```
**Output**: Real metrics vs profile characteristics, verdict (MATCH/REASSIGN/CREATE)

**What to look for:**
- ¿LTCUSDT, AVAXUSDT → todos asignados a MID_LIQUID?
- ¿Las métricas reales (spread_bps, depth_ratio, speed, avg_trade_size, vol_realized_4h) están dentro de los rangos MID?
- Si no, ¿cuál es la acción recomendada?

---

## Step 6: Edge Audit (Performance)
```bash
.venv/bin/python utils/setup_edge_auditor.py --db data/historian.db --window 14400 --by-coin
```
**Output**: Win Rate, MFE/MAE, Net Taker per condition, por moneda

**What to look for:**
- ¿Net Taker positivo en cada activo?
- ¿MFE/MAE > 1.0?
- ¿Varía el performance por condición de mercado?

---

## Step 7: L2 Depth Audit (Validar depth_ratio)
```bash
.venv/bin/python utils/l2_depth_auditor.py
```
**Output**: ¿El L2 depth predice el performance?

**What to look for:**
- ¿High Wall (>2.0) tiene mejor MFE/MAE que Thin Wall (<1.0)?
- ¿Es el threshold `l2_ratio_min` del perfil predictivo?

---

## Step 8: Multi-Window Target Grid
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

## Step 9: Correlation Analysis
Compare results from all steps:

| Question | Answer Source |
|----------|---------------|
| ¿LTC/AVAX → MID_LIQUID? | Step 2 (pre-flight) + Step 5 (post-audit) |
| ¿Performance positivo en los 2 activos? | Step 6 |
| ¿L2 depth predictivo? | Step 7 |
| ¿Targets óptimos consistentes entre activos? | Step 8 |

---

## ⛔ MANDATORY STOP — Present Results

After Step 9, the agent **MUST STOP COMPLETELY** and present:

1. **Profile Validation** (Steps 2 + 5) — por activo:
   - Assigned profile: MID_LIQUID
   - Real metrics: spread_bps, depth_ratio, speed, avg_trade_size, vol_realized_4h
   - Match status: ✅ or ❌

2. **Performance Results** (Step 6) — por activo:
   - Win Rate: X%
   - MFE/MAE: X.XX
   - Net Taker: +X.XX%
   - Per-condition breakdown

3. **L2 Depth Analysis** (Step 7):
   - High Wall vs Thin Wall MFE/MAE
   - ¿depth_ratio validado?

4. **Target Optimization** (Step 8) — por activo:
   - Optimal target: X.X%
   - Optimal window: Xh

5. **Correlation Analysis** (Step 9):
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
| LTC/AVAX | BALANCE | ✅ | Expectancy > 0.12% | High Wall > Thin Wall | **CERTIFIED** |
| LTC/AVAX | BALANCE | ✅ | Expectancy > 0.12% | — | **WATCH** |
| LTC/AVAX | BALANCE | ❌ | Any | — | **PROFILE WRONG** |
| LTC/AVAX | TREND_UP / TREND_DOWN | ✅ | Expectancy > 0.12% | — | **GUARDIAN OK** |
| LTC/AVAX | TREND_UP / TREND_DOWN | ❌ | Any | — | **PROFILE INCONSISTENT** |

---

## Appendix: MID_LIQUID Profile (current characteristics)

5-dim microstructure characteristics (per `config/coin_profiles.py`):
```python
"spread_bps":      {"min": 0.0, "max": 15.0}
"depth_ratio":     {"min": 0.0, "max": 100.0}
"speed":           {"min": 0.0, "max": 100.0}
"avg_trade_size":  {"min": 500, "max": 10000}
"vol_realized_4h": {"min": 0.0, "max": 1.2}
```

Current parameters (iter 3 validated, per `config/coin_profiles.py`):
```python
# Sensors
z_score_min: 3.5
concentration_min: 0.50   # Iter2: 0.40→0.50
noise_max: 0.40
# Targets (per-regime for TacticalAbsorptionV2)
TP:  per-regime (UP=1.2%, DOWN=2.0%, BALANCE=0.8%)
SL:  per-regime (UP=2.5%, DOWN=3.0%, BALANCE=2.5%)   # Iter3: 4-5%→2.5-3%
# Guardians
l2_ratio_min: 0.5
l2_ratio_min_trend_down: 2.0
spread_max_ratio: 2.0
```

**Membership**: LTC, ADA, LINK, DOGE.
**Excluded**: SUI (THIN_VOLATILE, TAV entry failure), AVAX borderline but included for coverage.
