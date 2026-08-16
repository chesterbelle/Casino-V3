---
description: Protocolo para validar que el bot opera sin errores de ejecución (Error Recovery = $0)
---

# Stress Test Protocol (V9.2.0)

## Objetivo Principal
Validar que **Error Recovery = $0.00** (0 error trades) y que la infraestructura de ejecución es resiliente bajo carga y en operación prolongada.

Cada error que aparece en "Error Recovery" representa un fallo en la arquitectura de ejecución.
El objetivo es eliminarlos completamente.

---

## FASE A: Chaos Test (Mecánico — Fuerza Bruta)

### Objetivo
Saturar el motor de ejecución (`Croupier`, `OCOManager`, WebSockets) con órdenes sintéticas inyectadas directamente, sin depender de señales de la estrategia. Esto prueba que las tuberías de ejecución no se rompen bajo presión.

### Pre-requisitos
```bash
.venv/bin/python -m utils.validators.multi_symbol_validator --mode demo --size 500
```
**Debe pasar**: CONCURRENCY ✅ PASS, INTEGRITY ✅ PASS

### Paso A.1: Limpiar Estado
```bash
.venv/bin/python utils/reset_data.py
```

### Paso A.2: Ejecutar Chaos Test (10 minutos, 9 monedas)
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester \
  --symbols LTCUSDT,BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT,XRPUSDT,AVAXUSDT,LINKUSDT \
  --mode demo \
  --size 200 \
  --duration 600 \
  --max-ops 50 \
  2>&1 | tee logs/chaos_test_$(date +%Y%m%d_%H%M%S).log
```

### Paso A.3: Analizar Resultado
El script imprime su propio `CHAOS TEST SUMMARY`. Verificar:

### Criterios de Éxito (Chaos)
- [ ] **Error Trades = 0** ← CRÍTICO
- [ ] **Integrity = ✅ PASS** (Tracker vacío, Exchange limpio)
- [ ] **Stall Detected = False** (Watchdog sin colgar)
- [ ] **Event Integrity = 100%** (0 logs de `WS Event UNMATCHED`)
- [ ] **Total Ops > 30** (Suficiente volumen de estrés)

---

## FASE B: Endurance Test (Estratégico — Resistencia Real)

### Paso B.0: Pre-Flight de Exchange (OBLIGATORIO — antes de CADA corrida)

**⚠️ Un run de endurance solo es válido si el exchange arranca en cero.** El bot
reconcilia/adopta posiciones existentes al arrancar (diseño intencional para resiliencia
ante crashes), pero eso CONTAMINA los datos de la prueba si quedó residuo de una corrida
anterior (posición fantasma, órdenes huérfanas). `reset_data.py` solo limpia estado LOCAL.

```bash
# 1. Limpiar exchange a cero (órdenes + posiciones de TODOS los símbolos)
.venv/bin/python utils/emergency_cleanup.py

# 2. VERIFICAR 0 posiciones y 0 órdenes (criterio de paso)
.venv/bin/python -c "
import asyncio, sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector
async def main():
    conn = BinanceNativeConnector(api_key=os.getenv('BINANCE_TESTNET_API_KEY'),
        secret=os.getenv('BINANCE_TESTNET_SECRET'), mode='demo')
    await conn.connect()
    pos = [p for p in await conn.fetch_positions() if abs(p['contracts']) > 0]
    orders = await conn.fetch_open_orders(None)
    print('POSICIONES:', len(pos), '| ORDENES:', len(orders))
    assert len(pos) == 0 and len(orders) == 0, 'EXCHANGE NO ESTA EN CERO — ABORTAR'
    await conn.close()
asyncio.run(main())
"
# 3. Limpiar estado local
.venv/bin/python utils/reset_data.py
```

**CRITERIO**: Si el paso 2 falla (residuo en exchange), NO lanzar `main.py` — investigar antes.

### Objetivo
Correr el bot real (`main.py`) durante un periodo prolongado para detectar fugas de memoria (memory leaks), degradación de rendimiento, o errores intermitentes.

La Fase B se divide en tres sub-fases:
- **B.1 Mini-Endurance (4h)**: Detección temprana de fugas groseras o crashes sin esperar 24h.
- **B.2 Debug-Gate (12h × 2)**: Gate de depuración iterativo. Se corre en loops de 12h; si aparece error se repara y se vuelve a correr. Se exige **2 runs consecutivos limpios** antes de proceder. Esto permite iterar 2× más rápido que con 24h.
- **B.3 Debug-Gate Multi-Coin (12h)**: Gate de depuración para concurrencia. 3 símbolos (LTC, SOL, AVAX) para estresar race conditions.
- **B.4 Full Endurance (24h)**: Certificación formal. Valida cobertura completa de sesiones (Asia + Europa + US) y eventos de baja frecuencia.
- **B.5 Multi-Coin (48h)** *(opcional)*: Validación definitiva multi-activo.

**Nota:** Con los filtros estrictos de la v9.2.0 (VA_GATE, TrendAcceptance, Z-Scores), el bot ejecuta muy pocos trades por sesión. El objetivo aquí NO es volumen de trades, sino estabilidad de proceso.

### Paso B.1: Mini-Endurance (4 horas, Multi-Coin)
*Corre 4 horas. Usar `setsid` para sesión detached y `--timeout 240` (graceful shutdown interno, no `timeout` shell — ver GOTCHA 21).*
```bash
.venv/bin/python utils/reset_data.py
```
```bash
setsid .venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol LTCUSDT,SOLUSDT,AVAXUSDT \
  --close-on-exit \
  --timeout 240 \
  2>&1 | tee logs/mini_endurance_$(date +%Y%m%d_%H%M%S).log
```
*Monitorear RAM con `htop`. Si hay fugas groseras o crashes, se manifiestan aquí.*

> **⏱️ GOTCHA B.1 (2026-08-14)**: El run NUNCA es válido si aparece un `EXTERNAL_CLOSE` (Error Recovery ≠ $0). Antes de dar el run por bueno, correr SIEMPRE `audit_trade_flow.py` (Paso B.5). Un run de 4h con `Error Recovery = -0.0419` por 1 EXTERNAL_CLOSE FALLÓ el criterio crítico aunque el proceso aguantara las 4h.

### Paso B.2: Debug-Gate 12h (Single Coin — repetir hasta 2× limpios)
*Ejecutar solo si B.1 pasa. Repetir este paso hasta tener 2 runs consecutivos sin errores.*
```bash
.venv/bin/python utils/reset_data.py
```
```bash
.venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol LTCUSDT \
  --close-on-exit \
  2>&1 | tee logs/debug_gate_12h_$(date +%Y%m%d_%H%M%S).log
```
*Dejar correr mínimo 12 horas. Si aparece un error → fix → volver al Pre-Flight B.0 y repetir.*
*Gate de paso: 2 runs consecutivos con Error Recovery = $0.00.*

### Paso B.3: Debug-Gate Multi-Coin 12h (LTC, SOL, AVAX)
*Ejecutar solo si B.2 tiene 2 runs limpios consecutivos.*
```bash
.venv/bin/python utils/reset_data.py
```
```bash
.venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol LTCUSDT,SOLUSDT,AVAXUSDT \
  --close-on-exit \
  2>&1 | tee logs/debug_gate_multi_12h_$(date +%Y%m%d_%H%M%S).log
```
*Dejar correr mínimo 12 horas. Revisa PnL y errores cruzados.*

### Paso B.4: Full Endurance (24 horas, Single Coin o Multi — Certificación Formal)
*Ejecutar solo si B.3 termina limpio.*
```bash
.venv/bin/python utils/reset_data.py
```
```bash
.venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol LTCUSDT,SOLUSDT,AVAXUSDT \
  --close-on-exit \
  2>&1 | tee logs/endurance_test_$(date +%Y%m%d_%H%M%S).log
```
*Dejar correr mínimo 24 horas. Monitorear RAM con `htop` periódicamente.*

### Paso B.5 (Opcional): Endurance Multi-Coin (48h)
*Ejecutar solo si B.4 pasa.*
```bash
.venv/bin/python utils/reset_data.py
```
```bash
.venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol MULTI \
  --close-on-exit \
  2>&1 | tee logs/endurance_multi_$(date +%Y%m%d_%H%M%S).log
```

### Paso B.5: Auditoría Post-Endurance (OBLIGATORIO — sin excepción)
```bash
.venv/bin/python utils/audit_logs.py logs/mini_endurance_$(ls -t logs/mini_endurance_* | head -1 | xargs basename)
```
```bash
.venv/bin/python utils/audit_trade_flow.py --db data/historian.db
```
*El auditor auto-detecta la sesión más reciente y cruza el `exit_reason` de la tabla `trades`. **VERDICT FAIL** si hay trades con exit no limpio (ej. `EXTERNAL_CLOSE`, `SAFETY_CLOSE`, `OCO_ABORT`). Para auditar una sesión específica: `--session <session_id>`.*

> **🔬 GOTCHA B.5 (2026-08-14)**: El auditor anterior solo leía `trade_lifecycle_events` y daba **falso PASS** ante `EXTERNAL_CLOSE` (el Sheriff registra directo en `trades`, sin evento de cierre). Fix: audita la tabla `trades` por `session_id` (fuente de verdad del `exit_reason`). Un run de 4h con 1 EXTERNAL_CLOSE ahora da **VERDICT FAIL** (33.3% poor execution), coherente con Error Recovery ≠ $0.

### Criterios de Éxito (Endurance)

**Mini-Endurance (B.1)**:
- [ ] **Error Recovery = $0.00 (0 error trades)** ← CRÍTICO
- [ ] **`audit_trade_flow.py` → VERDICT PASS** (0 poor executions, exit no limpio)
- [ ] **Proceso no crasheó** durante las 4h
- [ ] **RAM estable** (No creció >50% respecto al inicio)
- [ ] **Event Integrity = 100%** (0 logs de `WS Event UNMATCHED`)
- [ ] **Airlock Latency = 100%** (0 warnings de `🐢 High Airlock Latency`)
- [ ] **Full Exit**: Tracker vacío después de `--close-on-exit`
- [ ] **Trade Flow Observability = 100%** (Verificar en `trade_lifecycle_events` trazabilidad completa: OCO_SUBMITTED → ENTRY_FILLED → STOP_FILLED → CLOSED)
- [ ] Los trades ejecutados (si los hay) cerraron limpiamente

**Debug-Gate 12h (B.2)** — mismos criterios que B.1 + :
- [ ] **2 runs consecutivos** con todos los criterios en verde
- [ ] Cada error encontrado tiene su fix documentado antes de re-correr

**Full Endurance 24h (B.3)** — mismos criterios + :
- [ ] **API Stability = 100%** (0 logs de error `(-4120)`) — solo exigible en 24h+
- [ ] **Trade Flow Observability = 100%** (Verificar en `trade_lifecycle_events` que los trades tienen trazabilidad completa: CREATED, FILLED, RECON_*, CLOSED)

---

## SESSION SUMMARY (Referencia)
Al finalizar cualquiera de las fases, el bot imprime:
```
==========================================
🏁 SESSION SUMMARY (Persistent Historian)
   📈 Strategy PnL: +X.XX USDT (XX clean trades)
   🔧 Error Recovery: +X.XX USDT (XX error trades)  ← DEBE SER $0.00 (0 trades)
   🧹 Audit Adjust: +X.XX USDT
   --------------------------------------
   ⏱️ HFT PERFORMANCE (Phase 240)
      • Strat Aggregation (T0-T1): XX.Xms
      • Signal-to-Wire   (T1-T2): XX.Xms
      • Tick-to-Order    (T0-T2): XX.Xms  ← OBJETIVO < 50ms
      • HFT Core Efficiency: XX.X%
==========================================
```

## Resilience Performance (Phase 160)
- [ ] **Healing Efficiency > 90%** (`Healed / (Healed + Force-Closed)`)
- [ ] **Orphan Hygiene < 2%** (`Orphans Killed / Total Trades`)
- [ ] **False Positive Orphans = 0** (`Orphans Saved` count should align with high-load bursts, but 0 young orphans should be killed)

## Pre-requisito para Phase 2
Antes de pasar a Paper Trading (Phase 2 del roadmap), ejecutar el **Internal Event Bus Refactor** (Fase 1.4) para eliminar condiciones de carrera en el ruteo interno del Croupier. Ver `docs/ROADMAP_PRODUCCION.md#14-internal-event-bus-refactor-pre-fase-2`.

## Si Falla
1. Revisar logs buscando `ERROR|Exception`
2. Identificar qué tipo de error causó los trades de "Error Recovery"
3. Corregir el bug y repetir el ciclo
