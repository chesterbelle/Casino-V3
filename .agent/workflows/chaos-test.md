---
description: Protocolo para validar integridad de eventos WebSocket (0 eventos perdidos)
---

# Chaos Test Protocol

## Objetivo Principal
Validar que **0 eventos UNMATCHED** y **Error Recovery = $0.00**.
Este test es más rápido que el stress-test (10 min vs 150 min).

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

### 2. Ejecutar Chaos Test (10 minutos)
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester \
    --symbols BTCUSDT,ETHUSDT,LTCUSDT,SOLUSDT,BNBUSDT \
    --mode demo \
    --duration 600 \
    --max-ops 30 \
    2>&1 | tee logs/chaos_test_$(date +%Y%m%d_%H%M%S).log
```

### 3. Verificar Eventos Perdidos
// turbo
```bash
grep -c "UNMATCHED" logs/chaos_test_*.log 2>/dev/null || echo "0 unmatched"
```

## Criterio de Éxito
- [x] **0 eventos UNMATCHED en logs** ← CRÍTICO
- [ ] Error Recovery = $0.00 (0 error trades)
- [ ] Integrity Check PASS
- [ ] Test completa sin hang (máx 11 minutos)

## Si Falla
1. Revisar logs buscando `UNMATCHED|Error Recovery`
2. Si hay eventos perdidos → Bug en PositionTracker alias matching
3. Si hay Error Recovery → Bug en OCOManager bracket lifecycle
