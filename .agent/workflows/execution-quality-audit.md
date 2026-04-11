---
description: Protocolo de Auditoría de Calidad de Ejecución asíncrona (15m Execution Funnel check)
---
Este workflow ejecuta una ronda de Demo y otra de Simulador (Backtest) en periodos de 15 minutos exactos para verificar la **calidad del pipeline de ejecución** (VirtualExchange, OCOManager, ExitManager) y garantizar cero latencia zombie o caídas asíncronas de la infraestructura.

> **⚠️ AI EXECUTION DIRECTIVE:**
> **OBJETIVO:** Garantizar cero Tracebacks, cero CancelledErrors, y cero Stalls en las colas del Croupier y ExitManager durante ejecuciones intensivas.
> **MODO DE USO:** Se usa posterior a `validate-all` para estresar la capa asíncrona (asyncio loop).

## Phase 1: Fast-Track Demo Logging
// turbo
1. Preparar logs y ejecutar Demo (15 min):
```bash
mkdir -p logs/
rm -f logs/demo_exec.log logs/bt_exec.log
.venv/bin/python main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track > logs/demo_exec.log 2>&1
```

## Phase 2: Simulator Replay Logging
// turbo
2. Ejecutar Simulación Fast-Track sobre el sample recién creado / predefinido:
```bash
# Nota: Utilizamos el sample real local (ej. 1week data pero limitado en eventos equivalentes a ~15m reales o 15,000 eventos).
.venv/bin/python backtest.py --data data/raw/LTCUSDT_trades_1week.csv --symbol LTC/USDT:USDT --limit 5000 --fast-track > logs/bt_exec.log 2>&1
```

## Phase 3: Execution Quality Validation
// turbo
3. Evaluar los logs en busca de errores asíncronos y confirmar limpieza:
```bash
echo -e "\n====================== AUDITORÍA DEMO ======================"
.venv/bin/python utils/validators/execution_quality_validator.py logs/demo_exec.log
```
