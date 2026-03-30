---
description: Protocolo de Simulation Parity Check (Live Demo vs Backtest) para medir "Simulation Leaks".
---
# Simulation Parity Check (Paridad HFT 1:1)

Este workflow graba una sesión de Demo real en el exchange, descarga la metadata de los Ticks de Binance (aggTrades), y los inyecta en el Simulador para verificar matemáticamente si V4 Backtester miente o representa la realidad. Usaremos `LTC/USDT:USDT` por ser un par estable ideal para pruebas maduras.

## Phase 1: Live Demo (Golden Session)
// turbo
1. Preparar el entorno limpio y capturar el tiempo de inicio:
```bash
.venv/bin/python reset_data.py && mkdir -p tests/validation/
START_TS=$(date +%s)
echo $START_TS > tests/validation/parity_start.txt
```

2. Lanzar el bot en Demo durante **8 horas** (debe capturar métricas consistentes a lo largo de múltiples sesiones):
```bash
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 480 --drain-duration 0
```

## Phase 2: Extracción del Golden Dataset (AggTrades API)
// turbo
3. Terminando el bot, empaquetar la base de datos Demo y descargar de la API REST todos los ticks exactos de esa ventana desde Binance:
```bash
# Phase 1300: Add 60s offset to ignore initial L2 sensor warmup/initialization
START=$(( $(cat tests/validation/parity_start.txt) + 60 ))

# Calcular END_TS en base al timeout (8 horas = 28800s + 30s de gracia)
END_TS=$((START + 28830))
echo $END_TS > tests/validation/parity_end.txt

cp data/historian.db* tests/validation/demo_historian.db
cp data/historian.db-wal tests/validation/demo_historian.db-wal 2>/dev/null || :
cp data/historian.db-shm tests/validation/demo_historian.db-shm 2>/dev/null || :

# Descargar aggTrades (ticks crudos)
# Nota: La extracción usará --max-duration interno y lo limitará basado en el tamaño de la ventana
.venv/bin/python tests/validation/parity_data_fetcher.py --symbol LTC/USDT:USDT --start $START --end $END_TS --max-duration 29000 --out tests/validation/ltc_parity.csv
```

## Phase 3: Simulator Replay (Mirror Test)
// turbo
4. Limpiar el entorno para inyectar los ticks en el Backtester con las mismas configuraciones exactas (Balance y Tamaño de Posición de Demo):
```bash
.venv/bin/python reset_data.py
.venv/bin/python backtest.py --data tests/validation/ltc_parity.csv --symbol LTC/USDT:USDT --balance 3400.0 --bet-size 0.01 --depth-db tests/validation/demo_historian.db
cp data/historian.db* tests/validation/backtest_historian.db
cp data/historian.db-wal tests/validation/backtest_historian.db-wal 2>/dev/null || :
cp data/historian.db-shm tests/validation/backtest_historian.db-shm 2>/dev/null || :
```

## Phase 4: The Micro/Macro Reconciliation
// turbo
5. Ejecutar el orquestador de Paridad para verificar Ghost Trades (Falsos Positivos) y Fugas de Spread (Profit diferente entre real y simulación):
```bash
START=$(cat tests/validation/parity_start.txt)
END_TS=$(cat tests/validation/parity_end.txt)
.venv/bin/python tests/validation/parity_validator.py --demo tests/validation/demo_historian.db --backtest tests/validation/backtest_historian.db --start $START --end $END_TS
```
