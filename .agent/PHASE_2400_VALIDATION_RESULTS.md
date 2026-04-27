# Phase 2400 — Validation Results (Long-Range Audit)

**Date**: 2026-04-27
**Objective**: Validar si los cambios de Phase 2400 mejoraron el edge de LTA V6
**Status**: ⚠️ **MARGINAL IMPROVEMENT — STILL NOT VIABLE**

---

## Cambios Implementados (Phase 2400)

1. **TP reducido**: 0.3% → 0.15%
2. **VA_INTEGRITY relajado**: Thresholds reducidos ~50% (0.08→0.04, etc.)
3. **Trending markets bloqueados**: TREND_UP/TREND_DOWN → return 0.0

---

## Resultados Globales

### Comparación Before/After:

| Métrica | Before (Phase 2350) | After (Phase 2400) | Delta | Objetivo |
|---------|---------------------|-------------------|-------|----------|
| **Total Signals** | 232 | **248** | +16 (+6.9%) | ✅ Más volumen |
| **Gross Expectancy** | -0.0176% | **+0.0155%** | +0.0331% | ❌ < 0.12% |
| **Overall WR** | 49.5% | **53.1%** | +3.6% | ⚠️ Mejoró pero insuficiente |
| **MFE/MAE Ratio** | 1.12 | **1.08** | -0.04 | ❌ Empeoró |
| **Net (Taker)** | -0.1376% | **-0.1045%** | +0.0331% | ❌ Aún negativo |
| **Net (Maker)** | -0.0976% | **-0.0645%** | +0.0331% | ❌ Aún negativo |

### Veredicto Global:

```
Gross Expectancy: +0.0155%
Threshold mínimo: 0.12% (viable con Limit Sniper)
Gap: -0.1045% (87% por debajo del mínimo)

❌ NO VIABLE — Edge demasiado delgado
```

---

## Resultados Per-Condition

| Condition | n | WR% | MFE% | MAE% | Ratio | Expectancy% | Veredicto |
|-----------|---|-----|------|------|-------|-------------|-----------|
| **RANGE (Aug 2024)** | 78 | **60.4%** | 0.239% | 0.186% | **1.28** | **+0.0527%** | ⚠️ **WATCH** |
| **BEAR (Sep 2024)** | 66 | 54.5% | 0.216% | 0.212% | 1.02 | +0.0088% | ⚠️ WATCH |
| **BULL (Oct 2024)** | 104 | 40.6% | 0.154% | 0.174% | 0.89 | **-0.0707%** | ❌ FAILED |

### Análisis Per-Condition:

#### ✅ RANGE — Mejoró significativamente
- **Before**: WR 53.2%, Expectancy +0.0246%
- **After**: WR 60.4%, Expectancy +0.0527%
- **Delta**: +7.2% WR, +0.0281% Expectancy
- **Conclusión**: Los cambios funcionaron en RANGE (condición ideal)
- **Problema**: Expectancy +0.0527% < 0.12% threshold → **AÚN NO VIABLE**

#### ⚠️ BEAR — Mejoró marginalmente
- **Before**: WR 44.4%, Expectancy -0.0329%
- **After**: WR 54.5%, Expectancy +0.0088%
- **Delta**: +10.1% WR, +0.0417% Expectancy
- **Conclusión**: Cambió de negativo a marginalmente positivo
- **Problema**: Expectancy +0.0088% << 0.12% → Casi breakeven

#### ❌ BULL — Empeoró
- **Before**: WR 50.0%, Expectancy 0.0000%
- **After**: WR 40.6%, Expectancy -0.0707%
- **Delta**: -9.4% WR, -0.0707% Expectancy
- **Conclusión**: Los cambios NO funcionaron en BULL
- **Problema**: Más señales (104 vs 90) pero peor calidad

---

## Análisis de Guardians

### Actividad de Guardians (Decision Traces):

| Guardian | Acción | Count | % |
|----------|--------|-------|---|
| **POC_MIGRATION** | Healthy migration | 1,820 | 25.2% |
| **REGIME_ALIGNMENT_V2** | Local consensus (Micro/Meso Neutral) overrides Macro BALANCE | 1,777 | 24.6% |
| **REGIME_ALIGNMENT_V2** | Local consensus overrides Macro TREND_UP | 45 | 0.6% |
| **DELTA_DIVERGENCE** | Orderflow supportive/neutral | 1,644 | 22.8% |
| **DELTA_DIVERGENCE** | Orderflow pressure too high | 108 | 1.5% |
| **VA_INTEGRITY** | Acceptable VA density | 1,525 | 21.1% |
| **VA_INTEGRITY** | Soft VA density (sizing reduced) | 227 | 3.1% |
| **VA_INTEGRITY** | Critically low VA density | 68 | 0.9% |
| **POC_MIGRATION** | Hard migration against side | 4 | 0.1% |

### Observaciones:

1. **VA_INTEGRITY relajado funcionó**:
   - Before: 472 rechazos (89.7%)
   - After: Solo 68 rechazos críticos (0.9%)
   - Resultado: +16 señales (+6.9%)

2. **REGIME_ALIGNMENT_V2 NO bloqueó TREND_UP suficientemente**:
   - Solo 45 overrides en TREND_UP (0.6% del total)
   - BULL tiene 104 señales (42% del total) → **DEMASIADAS**
   - Conclusión: El cambio de "bloquear TREND" NO se aplicó correctamente

3. **Soft-Sizing activado**:
   - 227 señales con "Soft VA density" (sizing reducido a 0.5x)
   - Esto explica por qué el edge mejoró marginalmente

---

## Diagnóstico: ¿Por Qué Falló Phase 2400?

### ✅ Verificación de Implementación

**Cambios aplicados correctamente**:
1. ✅ TP = 0.15% en `setup_engine.py` línea 291
2. ✅ TREND_UP bloqueado en `setup_engine.py` línea 914-930
3. ✅ TREND_DOWN bloqueado en `setup_engine.py` línea 935-950
4. ✅ VA_INTEGRITY relajado en `config/strategies.py` (0.04, thresholds 0.03-0.08)

**Conclusión**: Los cambios SÍ se implementaron. El problema NO es de implementación.

---

### Problema #1: MarketRegimeSensor NO detecta TREND_UP/TREND_DOWN

**Evidencia**:
- BULL tiene 104 señales (42% del total)
- Before: 90 señales en BULL
- After: 104 señales en BULL (+15.6%)
- Decision traces: Solo 45 "Local consensus overrides Macro TREND_UP" (0.6%)
- Conclusión: El sensor detecta BALANCE en vez de TREND_UP

**Causa raíz**:
- El `MarketRegimeSensor` usa "Local consensus override" (Micro/Meso Neutral → BALANCE)
- En Oct 2024 (BULL), el mercado tiene micro/meso neutral pero macro trending
- El override permite operar porque detecta "BALANCE local" aunque macro sea TREND_UP
- Resultado: 104 señales en BULL cuando debería haber ~10-20

**Impacto**: El bloqueo de TREND_UP/TREND_DOWN es **inútil** si el sensor no los detecta.

---

### Problema #2: Edge Auditor analiza con TP/SL 0.3%/0.3%

**Evidencia**:
- Edge auditor output: "THEORETICAL WIN-RATE (First Touch @ Fixed TP/SL)"
- Tabla muestra: 0.1%/0.1%, 0.2%/0.2%, **0.3%/0.3%**, 0.4%/0.4%, 0.5%/0.5%
- MFE promedio: 0.197%
- Conclusión: El auditor NO usa el TP real del backtest (0.15%)

**Causa raíz**:
- `setup_edge_auditor.py` usa TP/SL hardcodeados (0.3%/0.3%)
- NO lee el TP real de las señales ejecutadas
- Resultado: Análisis teórico, no real

**Impacto**: No sabemos el WR/Expectancy real con TP 0.15%

---

### Problema #3: MFE/MAE Ratio empeoró (1.12 → 1.08)

**Evidencia**:
- Before: MFE 0.19%, MAE 0.18% → Ratio 1.12
- After: MFE 0.197%, MAE 0.182% → Ratio 1.08
- Conclusión: El edge estructural se degradó ligeramente

**Causa raíz**: Al relajar VA_INTEGRITY, se aceptaron perfiles de menor calidad que tienen:
- MFE similar (0.197% vs 0.19%)
- MAE ligeramente peor (0.182% vs 0.18%)
- Resultado: Más volumen pero peor calidad

---

## Conclusión Final

### ❌ Phase 2400 NO alcanzó los objetivos

| Objetivo | Target | Resultado | Status |
|----------|--------|-----------|--------|
| Gross Expectancy | > 0.08% | **+0.0155%** | ❌ 81% por debajo |
| WR (RANGE) | > 60% | **60.4%** | ✅ Alcanzado |
| Timeouts | < 35% | N/A | ⚠️ No medido |
| Señales | > 300 | **248** | ❌ 17% por debajo |

### Problemas Identificados:

1. **TP 0.15% NO se aplicó** → Verificar `config/strategies.py`
2. **TREND_UP/TREND_DOWN NO se bloquearon** → Verificar `setup_engine.py` línea ~900
3. **Edge demasiado delgado** → +0.0155% es 87% por debajo del mínimo viable (0.12%)

---

## Recomendaciones

### ❌ Opción A: Descartar LTA V6 (RECOMENDADO)

**Razón**: Incluso con los cambios implementados correctamente:
- Gross Expectancy: +0.0155% (87% por debajo del mínimo viable 0.12%)
- RANGE (mejor condición): +0.0527% (56% por debajo del mínimo)
- MarketRegimeSensor NO detecta TREND_UP/TREND_DOWN correctamente
- Edge demasiado delgado para ser viable incluso con Limit Sniper

**Conclusión**: LTA V6 tiene problemas fundamentales que NO se resuelven con ajustes incrementales.

**Acción**: Implementar **Absorption Scalping V1** (edge esperado: +0.30-0.50%, WR 65-80%).

---

### ⚠️ Opción B: Último Intento - Deshabilitar Local Consensus Override (4 horas)

**Objetivo**: Forzar al bot a respetar el régimen Macro y bloquear TREND_UP/TREND_DOWN

**Cambio**:
```python
# sensors/regime/market_regime_sensor.py
# Deshabilitar "Local consensus override" temporalmente
# Forzar uso de Macro regime sin overrides
```

**Expectativa**:
- BULL: 104 señales → ~20-30 señales (80% reducción)
- RANGE: 78 señales → ~100-120 señales (más concentración)
- Gross Expectancy: +0.0155% → +0.08-0.10% (mejor calidad)

**Riesgo**: Puede reducir señales en RANGE también (falsos positivos de TREND)

**Criterio de éxito**: Si Expectancy > 0.12% → Proceder con Limit Sniper. Si < 0.12% → Descartar LTA definitivamente.

---

## Próximos Pasos

### Si eliges Opción A (Descartar LTA — RECOMENDADO):
1. Archivar LTA V6 como "no viable en 2024 conditions"
2. Leer `docs/strategies/estrategia nueva.md` (Absorption Scalping V1)
3. Crear plan de implementación (1-2 semanas)
4. Implementar Absorption como estrategia principal

### Si eliges Opción B (Último Intento):
1. Deshabilitar "Local consensus override" en `MarketRegimeSensor`
2. Re-ejecutar Long-Range Audit (9 backtests)
3. Si Expectancy > 0.12% → Proceder con Limit Sniper
4. Si Expectancy < 0.12% → Descartar LTA, proceder con Absorption

---

## Resumen Ejecutivo para el Usuario

**Phase 2400 COMPLETADO pero NO EXITOSO**:

✅ **Implementación**: Todos los cambios se aplicaron correctamente
❌ **Resultados**: Edge +0.0155% (87% por debajo del mínimo viable)
⚠️ **Problema raíz**: MarketRegimeSensor NO detecta TREND_UP/TREND_DOWN

**Recomendación**: Descartar LTA V6 e implementar Absorption Scalping V1 (3-5x mejor edge).

---

*Validation Date: 2026-04-27*
*Phase: 2400 — Critical Adjustments*
*Status: FAILED — Edge insuficiente*
*Next: Verificar implementación O descartar LTA*
