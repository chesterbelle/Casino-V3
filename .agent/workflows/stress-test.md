---
description: Protocolo para validar que el bot opera sin errores de ejecución (Error Recovery = $0)
---

# Stress Test Protocol

## Objetivo Principal
Validar que **Error Recovery = $0.00** (0 error trades).

Cada error que aparece en "Error Recovery" representa un fallo en la arquitectura de ejecución.
El objetivo es eliminarlos completamente.

## Pre-requisitos
// turbo
```bash
.venv/bin/python -m utils.validators.multi_symbol_validator --mode demo --size 500
```
**Debe pasar**: CONCURRENCY ✅ PASS, INTEGRITY ✅ PASS

## Pasos

### 1. Limpiar Estado
// turbo
```bash
.venv/bin/python reset_data.py
```

### 2. Ejecutar Test (150 minutos)
```bash
.venv/bin/python main.py --mode demo --symbol MULTI --timeout 150 --close-on-exit 2>&1 | tee logs/stress_test_$(date +%Y%m%d_%H%M%S).log
```

### 3. Analizar SESSION SUMMARY
Al finalizar, revisar:
```
==========================================
🏁 SESSION SUMMARY (Persistent Historian)
   📈 Strategy PnL: +X.XX USDT (XX clean trades)
   🔧 Error Recovery: +X.XX USDT (XX error trades)  ← DEBE SER $0.00 (0 trades)
   🧹 Audit Adjust: +X.XX USDT
==========================================
```

## Criterio de Éxito
- [ ] **Error Recovery = $0.00 (0 error trades)** ← CRÍTICO
- [ ] **Event Integrity = 100%** (0 logs de `WS Event UNMATCHED`)
- [ ] **API Stability = 100%** (0 logs de error `(-4120)`)
- [ ] **Airlock Latency = 100%** (0 warnings de `🐢 High Airlock Latency`)
- [ ] **Audit Adjust < $1.00**
- [ ] **Volume > 50 trades** ejecutados
- [ ] **Full Exit**: Tracker vacío después de `--close-on-exit`

## Resilience Performance (Phase 160)
- [ ] **Healing Efficiency > 90%** (`Healed / (Healed + Force-Closed)`)
- [ ] **Orphan Hygiene < 2%** (`Orphans Killed / Total Trades`)
- [ ] **False Positive Orphans = 0** (`Orphans Saved` count should align with high-load bursts, but 0 young orphans should be killed)

## Si Falla
1. Revisar logs buscando `ERROR|Exception`
2. Identificar qué tipo de error causó los trades de "Error Recovery"
3. Corregir el bug y repetir el ciclo
