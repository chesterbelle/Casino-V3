---
description: Protocolo para certificar el Alpha/Edge de los Setups usando el Auditor de Interferencia Cero
---
# Phase 800 — Edge Audit Protocol (Zero-Interference Certification)

// turbo-all

## Overview
This protocol performs a rigorous, purely statistical validation of the **predictive power (Edge)**
of tactical setups in Casino-V3. It runs a zero-interference simulation (no active risk management exits)
to capture pristine price trajectories and compute MFE (Maximum Favorable Excursion) vs MAE (Maximum Adverse Excursion).

It follows a 4-step sequence: Nuclear Reset → Run Backtests (Multi-Asset) → Statistical Extraction → Decision.

**⛔ MANDATORY STOP RULE**: After Step 3 (Statistical Extraction), the agent **MUST STOP COMPLETELY**.
Present results + specific observations and **wait for explicit user approval** before any further action.
**No iterations, no auto-fixes, no follow-up backtests** without user instruction.

**Goals (Overall)**: Total Signals Audited ≥ 50
**Goals (Per setup_type)**:
- **Gross Expectancy**: > 0.36% (3× taker fees = viable with any order type)
- **Gross Expectancy**: > 0.12% (viable with maker orders / Limit Sniper)
- **MFE / MAE Ratio**: > 1.2 (Structural advantage indicator)
- **Theoretical Win Rate**: > 55% at 0.3% TP / 0.3% SL

---

## Step 0: Nuclear Reset (Clean Slate)
Wipe all databases and states to ensure zero data leakage.
```bash
.venv/bin/python utils/reset_data.py
```
**Must output**: `✨ Sistema limpio.`

## Step 1: Setup Environment & Run Zero-Interference Backtest

```bash
mkdir -p logs
```
> **🤖 REGLA DE EJECUCIÓN AUTÓNOMA PARA EL AGENTE (No Negociable):**
> Como este proceso puede durar horas, el agente **DEBE** actuar de manera 100% autónoma y reportar el progreso periódicamente al usuario, sin que este deba pedirlo o ejecutar comandos manualmente.
>
> Sigue EXACTAMENTE esta secuencia:
> 1. Lanza el orquestador en **segundo plano** redirigiendo la salida para poder monitorearla:
>    ```bash
>    PYTHONUNBUFFERED=1 .venv/bin/python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT > logs/orchestrator_run.log 2>&1
>    ```
> 2. Implementa un mecanismo de monitoreo en segundo plano (ej. un script de loop, tarea programada o revisión periódica) para leer el log cada 5 minutos.
> 3. En cada revisión, haz `tail -n 20 logs/orchestrator_run.log`, extrae el progreso actual y **reporta el estado al usuario** en el chat.
> 4. Cuando el log indique que el proceso ha finalizado, detén tu monitoreo y continúa al Step 2.


## Step 2: Verify Data Collection
```bash
.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/historian.db'); s = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]; p = conn.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]; d = conn.execute('SELECT COUNT(*) FROM decision_traces').fetchone()[0] if conn.execute('''SELECT count(name) FROM sqlite_master WHERE type='table' AND name='decision_traces' ''').fetchone()[0] == 1 else 0; print(f'Signals: {s}, Price Samples: {p}, Traces: {d}')"
```
**Must output**: Signals >= 80. If fewer, mark as INSUFFICIENT DATA.

## Step 3: Statistical Extraction & Calibration
Run the Edge Auditor tool to evaluate current strategy performance.
```bash
.venv/bin/python utils/setup_edge_auditor.py --window 14400 --by-coin
```
Run the Calibration grid sweeper to discover and verify optimal AMT target multipliers.
```bash
.venv/bin/python utils/setup_edge_auditor.py --calibrate
```
Review the output for **[1] SETUP EDGE BREAKDOWN**, **[2] PRIMARY METRIC**, and **[4] DECISION TRACE AUDIT**, as well as the **🎯 TOP 15 GEOMETRIC AMT TARGET CONFIGURATIONS**.

## Step 4: Multi-Window Target Grid Evaluation
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

## Step 5: L2 Microstructure Audit (Liquidity Wall)
Run the L2 Depth Auditor to verify passive liquidity support.
```bash
.venv/bin/python utils/l2_depth_auditor.py
```
Review the **[L2 DEPTH RATIO AUDIT RESULTS]** to ensure "High Wall" setups have a Ratio > 1.2.

---

## ⛔ MANDATORY STOP — Present Results and Certification Status

After running Step 3, the agent MUST:

1. **Present Section [1B]: Gross Expectancy** - (Inside Section [2/7])
2. **Present Section [7]: Overall Edge Summary** - Aggregate metrics and viability assessment
3. **Present the Theoretical Win-Rate Matrix** (Section [2/5]) with Net (Taker) and Net (Maker)
4. **Present the Decision Trace Audit** (Section [4])
5. **Present the Multi-Window Target Grid Evaluation** (Step 4) - Verify at which window/target combo Net Taker Expectancy peaks.
6. **Present the L2 Microstructure Certification** (Step 5) - Does the High Wall (>2.0) category correlate with higher expectancy?
6. **Assign a Certification Status** for each setup based on the criteria below
7. **List highly specific observations** (e.g., "Setup X has Expectancy 0.15% but needs Limit Sniper", "MAE too high, tighten entry filters")
8. **STOP and wait** for user input. Do not alter any strategy file or run another test without permission.

### Certification Matrix (Decision Logic) — UPDATED Phase 800B

**PRIMARY METRIC: Gross Expectancy (%)** = (WR × Avg_Win) - (LR × Avg_Loss)

| Setup Type | Condition | Status | Action Required |
|---|---|---|---|
| **Any** | n < 20 | **INSUFFICIENT DATA** | Needs longer backtest or looser baseline filters |
| **Any** | Expectancy > 0.36% AND WR > 55% | **CERTIFIED** | Viable with any order type. Approve for Live Trading. |
| **Any** | Expectancy > 0.12% AND WR > 50% | **WATCH** | Viable ONLY with Limit Sniper (maker entries). Enable in config. |
| **Any** | Expectancy < 0.12% | **FAILED** | Not viable after fees. Rework entry filters (reduce MAE) or exit timing (capture more MFE). |

**SECONDARY METRICS** (for diagnosis):
- **Ratio > 1.2**: Structural advantage exists (but check Expectancy for viability)
- **MFE >> MAE**: Good signal quality, may need better exit timing
- **MAE high**: Entry filters too loose, add structural gates
