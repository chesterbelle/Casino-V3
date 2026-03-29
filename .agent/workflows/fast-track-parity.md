---
description: Protocolo de Fast-Track Parity Check (15m Mechanical Proof)
---

Este workflow automatiza la validación de paridad mecánica entre Demo y Simulador en una ventana corta (15 min) forzando ejecuciones mediante el flag `--fast-track`.

> **⚠️ AI EXECUTION DIRECTIVE:**
> **OBJETIVO:** Este protocolo es exclusivamente para encontrar y arreglar bugs de infraestructura (fugas de simulación, gaps de tiempo, etc.). **ESTÁ ESTRICTAMENTE PROHIBIDO MODIFICAR LA ESTRATEGIA (sensores, RR, thresholds)** basándose en los resultados de este test.
> **EJECUCIÓN POR RONDAS:** El protocolo se ejecuta en "Rondas". Una ronda consiste en completar las Fases 1 a 4.
> Al finalizar la **Fase 4**, la IA **DEBE DETENERSE TOTALMENTE**, presentar el reporte final de paridad/fugas al usuario, y **ESPERAR APROBACIÓN** antes de intentar realizar correcciones de código en el motor o iniciar una nueva Ronda. No automatices múltiples rondas ni asumas correcciones sin consultar.

## Phase 1: Fast-Track Demo
// turbo
1. Limpiar datos y capturar tiempo de inicio:
```bash
.venv/bin/python reset_data.py && mkdir -p tests/validation/
START_TS=$(date +%s)
echo $START_TS > tests/validation/ft_parity_start.txt
```

2. Ejecutar sesión corta (15 min) en modo Fast-Track:
```bash
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track --close-on-exit
```

## Phase 2: Data Extraction
// turbo
3. Guardar logs y descargar ticks (limitando estrictamente al tiempo exacto del Demo):
```bash
START=$(cat tests/validation/ft_parity_start.txt)
END_TS=$((START + 920))
echo $END_TS > tests/validation/ft_parity_end.txt
cp data/historian.db tests/validation/ft_demo_historian.db
cp data/historian.db-wal tests/validation/ft_demo_historian.db-wal 2>/dev/null || :

.venv/bin/python tests/validation/parity_data_fetcher.py --symbol LTC/USDT:USDT --start $START --end $END_TS --out tests/validation/ft_parity_data.csv
```

## Phase 3: Simulator Replay
// turbo
4. Replay en Simulador mapeando el comportamiento Fast-Track:
```bash
.venv/bin/python reset_data.py
.venv/bin/python backtest.py --data tests/validation/ft_parity_data.csv --symbol LTC/USDT:USDT --fast-track --depth-db tests/validation/ft_demo_historian.db
cp data/historian.db tests/validation/ft_backtest_historian.db
```

## Phase 4: Validation
// turbo
5. Reconciliar Results:
```bash
START=$(cat tests/validation/ft_parity_start.txt)
END_TS=$(cat tests/validation/ft_parity_end.txt)
.venv/bin/python tests/validation/parity_validator.py --demo tests/validation/ft_demo_historian.db --backtest tests/validation/ft_backtest_historian.db --start $START --end $END_TS
```
