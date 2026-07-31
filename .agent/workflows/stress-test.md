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

### Objetivo
Correr el bot real (`main.py`) durante un periodo prolongado para detectar fugas de memoria (memory leaks), degradación de rendimiento, o errores intermitentes.

La Fase B se divide en dos sub-fases:
- **B.1 Mini-Endurance (4h)**: Detección temprana de fugas groseras o crashes sin esperar 24h.
- **B.2 Full Endurance (24h) / B.3 Multi (48h)**: Validación definitiva de estabilidad a largo plazo.

**Nota:** Con los filtros estrictos de la v9.2.0 (VA_GATE, TrendAcceptance, Z-Scores), el bot ejecuta muy pocos trades por sesión. El objetivo aquí NO es volumen de trades, sino estabilidad de proceso.

### Paso B.1: Mini-Endurance (4 horas, Single Coin)
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
  2>&1 | tee logs/mini_endurance_$(date +%Y%m%d_%H%M%S).log
```
*Corre 4 horas. Monitorear RAM con `htop`. Si hay fugas groseras o crashes, se manifiestan aquí.*

### Paso B.2: Full Endurance (24 horas, Single Coin)
*Ejecutar solo si B.1 pasa.*
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
  2>&1 | tee logs/endurance_test_$(date +%Y%m%d_%H%M%S).log
```
*Dejar correr mínimo 24 horas. Monitorear RAM con `htop` periódicamente.*

### Paso B.3 (Opcional): Endurance Multi-Coin (48h)
*Ejecutar solo si B.2 pasa.*
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

### Paso B.4: Auditoría Post-Endurance
```bash
.venv/bin/python utils/audit_logs.py logs/endurance_test_$(ls -t logs/endurance_* | head -1 | xargs basename)
```

### Criterios de Éxito (Endurance)

**Mini-Endurance (B.1)**:
- [ ] **Error Recovery = $0.00 (0 error trades)** ← CRÍTICO
- [ ] **Proceso no crasheó** durante las 4h
- [ ] **RAM estable** (No creció >50% respecto al inicio)
- [ ] **Event Integrity = 100%** (0 logs de `WS Event UNMATCHED`)
- [ ] **Airlock Latency = 100%** (0 warnings de `🐢 High Airlock Latency`)
- [ ] **Full Exit**: Tracker vacío después de `--close-on-exit`
- [ ] Los trades ejecutados (si los hay) cerraron limpiamente

**Full Endurance (B.2/B.3)** — mismos criterios + :
- [ ] **API Stability = 100%** (0 logs de error `(-4120)`) — solo exigible en 24h+

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
