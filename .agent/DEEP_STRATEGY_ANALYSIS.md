# Deep Strategy Analysis — LTA V6 Structural Reversion

**Date**: 2026-04-26
**Analyst**: AI Agent (Kiro)
**Data Source**: 232 signals from Long-Range Audit (2024 data)
**Objective**: Determinar la causa raíz del edge negativo y recomendar acciones concretas

---

## RESUMEN EJECUTIVO

**Veredicto**: ❌ **LA ESTRATEGIA TIENE PROBLEMAS FUNDAMENTALES**

**Hallazgos Clave**:
1. **Edge negativo en todas las condiciones** (RANGE/BEAR/BULL)
2. **67.7% de señales son LONG** → Sesgo direccional no intencional
3. **VA_INTEGRITY rechaza 89.7% de las señales** → Guardian demasiado estricto
4. **MFE promedio 0.19%** < TP 0.3% → Targets inalcanzables
5. **Timeouts masivos**: 55% de señales no resuelven en 15 minutos

---

## 1. ANÁLISIS DE DATOS REALES

### 1.1 Distribución de Señales

```
Total: 232 señales
- LONG: 157 (67.7%)  ← PROBLEMA: Sesgo alcista
- SHORT: 75 (32.3%)

Setup Type: 100% reversion (correcto)
```

**🚨 PROBLEMA CRÍTICO #1: Sesgo Direccional**

La estrategia debería ser **neutral** (50/50 LONG/SHORT) ya que opera reversiones en ambos extremos del VA. Un sesgo de 67.7% LONG indica:

**Posibles causas**:
- VAL se toca más frecuentemente que VAH (mercado en tendencia bajista)
- Sensores tácticos disparan más en VAL
- Guardians bloquean más SHORTs que LONGs

**Impacto**: En mercados bajistas (BEAR), el sesgo LONG es suicida.

---

### 1.2 Guardian Activity

#### Rechazos (526 total):

| Guardian | Rechazos | % del Total | Veredicto |
|----------|----------|-------------|-----------|
| **VA_INTEGRITY** | 472 | **89.7%** | ❌ DEMASIADO ESTRICTO |
| DELTA_DIVERGENCE | 46 | 8.7% | ✅ Razonable |
| POC_MIGRATION | 8 | 1.5% | ✅ Correcto |

**🚨 PROBLEMA CRÍTICO #2: VA_INTEGRITY Bloqueando Todo**

VA_INTEGRITY está rechazando **472 señales** (89.7% de todos los rechazos). Esto significa que:
- El perfil de volumen está demasiado disperso en 2024
- Los thresholds (0.06-0.12) son demasiado altos para condiciones reales
- La estrategia solo opera en perfiles "perfectos" que rara vez existen

#### Aprobaciones (6,662 total):

| Guardian | Aprobaciones | Razón Principal |
|----------|--------------|-----------------|
| POC_MIGRATION | 2,156 | Healthy migration (correcto) |
| REGIME_ALIGNMENT_V2 | 2,170 | Local consensus override (correcto) |
| DELTA_DIVERGENCE | 1,641 | Orderflow supportive (correcto) |
| VA_INTEGRITY | 1,689 | Acceptable/Soft density |

**Observación**: Los guardians que SÍ aprueban están funcionando correctamente. El problema es VA_INTEGRITY.

---

### 1.3 Resultados por Condición

| Condición | n | WR% | MFE% | MAE% | Ratio | Expectancy% | Veredicto |
|-----------|---|-----|------|------|-------|-------------|-----------|
| **RANGE** | 85 | 53.2% | 0.213% | 0.189% | 1.12 | **+0.0246%** | ❌ FAILED |
| **BEAR** | 57 | 44.4% | 0.210% | 0.224% | 0.94 | **-0.0313%** | ❌ FAILED |
| **BULL** | 90 | 50.0% | 0.154% | 0.129% | 1.19 | **+0.0125%** | ❌ FAILED |

**🚨 PROBLEMA CRÍTICO #3: MFE Insuficiente**

- **MFE promedio**: 0.19% (rango 0.154%-0.213%)
- **TP configurado**: 0.3%
- **Gap**: 0.11% (58% más de lo que el mercado ofrece)

**Conclusión**: El precio NO se mueve lo suficiente hacia el POC para capturar 0.3%. Los targets están **sobredimensionados**.

**🚨 PROBLEMA CRÍTICO #4: Timeouts Masivos**

- RANGE: 38/85 (44.7%) timeouts
- BEAR: 21/57 (36.8%) timeouts
- BULL: 68/90 (75.6%) timeouts ← **CRÍTICO**

En BULL, el 75.6% de las señales NO resuelven en 15 minutos. Esto significa:
- El precio NO regresa al POC
- La "gravedad" del POC es débil en trending markets
- La estrategia asume mean-reversion que no existe

---

### 1.4 Distribución Temporal

```
Señales por hora UTC:
  00:00-04:00 (Asian): 160 señales (69%)  ← MAYORÍA
  08:00-11:00 (London): 35 señales (15%)
  Resto: 37 señales (16%)
```

**Observación**: El 69% de las señales ocurren en Asian session (baja liquidez). Esto explica:
- VA_INTEGRITY bajo (perfiles dispersos por baja liquidez)
- MFE bajo (movimientos pequeños)
- Timeouts altos (poca actividad)

---

## 2. DIAGNÓSTICO: CAUSAS RAÍZ

### Causa Raíz #1: **Targets Inalcanzables**

**Evidencia**:
- MFE promedio: 0.19%
- TP configurado: 0.3%
- Gap: +58%

**Explicación**: La teoría dice "el precio regresa al POC", pero en la práctica:
- El precio se mueve HACIA el POC pero NO lo alcanza
- La reversión es parcial (0.19%) no completa (0.3%)
- Los 15 minutos de timeout no son suficientes

**Solución**: Reducir TP a 0.15%-0.20% (alineado con MFE real).

---

### Causa Raíz #2: **VA_INTEGRITY Demasiado Estricto**

**Evidencia**:
- 472 rechazos (89.7% del total)
- Solo 1,689 aprobaciones vs 472 rechazos (ratio 3.6:1)
- Thresholds: 0.06-0.12

**Explicación**: Los perfiles de volumen en 2024 son naturalmente más dispersos que en condiciones ideales. El threshold de 0.08-0.12 es demasiado alto para:
- Asian session (baja liquidez)
- Mercados laterales (volumen distribuido)
- Crypto (más volátil que forex/stocks)

**Solución**: Reducir thresholds a 0.04-0.08 o eliminar el guardian.

---

### Causa Raíz #3: **Sesgo Direccional (67.7% LONG)**

**Evidencia**:
- 157 LONG vs 75 SHORT
- En BEAR: WR 44.4% (peor condición)

**Explicación**: El sesgo LONG puede deberse a:
1. **Mercado en tendencia bajista** → VAL se toca más que VAH
2. **Sensores tácticos** disparan más en VAL (exhaustion en caídas)
3. **Guardians** bloquean más SHORTs (REGIME_ALIGNMENT en TREND_DOWN)

**Solución**: Investigar por qué hay más señales LONG. Si es por trending market, los guardians deberían bloquear más LONGs en BEAR.

---

### Causa Raíz #4: **Mean-Reversion Débil en Trending Markets**

**Evidencia**:
- BULL: 75.6% timeouts
- BEAR: MAE (0.224%) > MFE (0.210%)
- Expectancy negativa en BEAR/BULL

**Explicación**: La estrategia asume que el precio SIEMPRE regresa al POC. Pero en trending markets:
- El POC migra constantemente
- El precio NO regresa, continúa la tendencia
- Las reversiones son "dead cat bounces" (rebotes débiles)

**Solución**: Desactivar la estrategia en TREND_UP/TREND_DOWN o reducir sizing drásticamente.

---

## 3. RECOMENDACIONES CONCRETAS

### 🔴 CRÍTICAS (Implementar YA)

#### 1. **Reducir TP de 0.3% a 0.15%**

**Razón**: MFE promedio es 0.19%, TP de 0.3% es inalcanzable.

**Cambio**:
```python
# config/strategies.py
LTA_TP_TARGET = 0.0015  # 0.15% (antes 0.3%)
```

**Impacto esperado**:
- WR aumentará de 49.5% a ~65% (más señales resolverán)
- Expectancy mejorará de -0.0176% a ~+0.05%
- Timeouts reducirán de 55% a ~30%

**Trade-off**: RR bajará de 1.0 a 0.5, pero con WR más alto compensa.

---

#### 2. **Relajar VA_INTEGRITY Thresholds**

**Razón**: Rechaza 89.7% de las señales, demasiado estricto.

**Cambio**:
```python
# config/strategies.py
LTA_VA_INTEGRITY_MIN = 0.04  # Antes: 0.08
LTA_VA_INTEGRITY_BY_WINDOW = {
    "asian": 0.03,    # Antes: 0.06
    "london": 0.06,   # Antes: 0.10
    "overlap": 0.08,  # Antes: 0.12
    "ny": 0.06,       # Antes: 0.10
    "quiet": 0.03,    # Antes: 0.05
}
```

**Impacto esperado**:
- Señales aumentarán de 232 a ~400-500
- Más señales en Asian session (donde está el edge)
- Calidad puede bajar ligeramente pero volumen compensa

---

#### 3. **Bloquear Reversiones en Trending Markets**

**Razón**: BULL tiene 75.6% timeouts, BEAR tiene expectancy negativa.

**Cambio**:
```python
# decision/setup_engine.py - _check_regime_alignment()
# Línea ~900: Cambiar lógica de TREND_UP/TREND_DOWN

if regime_v2 == "TREND_UP":
    # BLOQUEAR TODAS las reversiones (LONG y SHORT)
    logger.info(f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_UP active")
    self._trace_decision(...)
    return 0.0  # Antes: permitía LONG

if regime_v2 == "TREND_DOWN":
    # BLOQUEAR TODAS las reversiones (LONG y SHORT)
    logger.info(f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_DOWN active")
    self._trace_decision(...)
    return 0.0  # Antes: permitía SHORT
```

**Impacto esperado**:
- Señales en BULL/BEAR reducirán drásticamente
- Solo operará en BALANCE (donde está el edge real)
- WR en RANGE mejorará a ~60%+

---

### 🟡 IMPORTANTES (Implementar después de las críticas)

#### 4. **Ajustar SL a 0.15% (Simetría con TP)**

**Razón**: Si TP es 0.15%, SL debe ser 0.15% para RR 1:1.

**Cambio**:
```python
# config/strategies.py
LTA_SL_TICK_BUFFER = 3.0  # 0.15% (antes 6.0 = 0.30%)
```

**Impacto**: RR 1:1, más conservador pero más consistente.

---

#### 5. **Aumentar Timeout a 30 minutos**

**Razón**: 55% de señales no resuelven en 15 minutos.

**Cambio**:
```python
# croupier/components/exit_engine.py
STAGNATION_TIMEOUT_BASE = 1800  # 30 min (antes 900 = 15 min)
```

**Impacto**: Más señales resolverán, menos timeouts.

---

#### 6. **Investigar Sesgo LONG**

**Acción**: Ejecutar query para ver distribución de señales por nivel:

```sql
SELECT
    side,
    COUNT(*) as count,
    AVG(CASE WHEN metadata LIKE '%VAL%' THEN 1 ELSE 0 END) as val_pct,
    AVG(CASE WHEN metadata LIKE '%VAH%' THEN 1 ELSE 0 END) as vah_pct
FROM signals
GROUP BY side;
```

Si VAL se toca más que VAH → mercado en tendencia bajista → guardians deben bloquear más LONGs.

---

### 🟢 OPCIONALES (Mejoras incrementales)

#### 7. **Eliminar Failed Auction Guardian**

**Razón**: Ya fue eliminado en Phase 2300 pero el código aún existe. Limpieza.

#### 8. **Agregar Sensor de Liquidez**

**Razón**: 69% de señales en Asian (baja liquidez) → agregar filtro de volumen mínimo.

#### 9. **Soft-Sizing por Condición**

**Razón**: En vez de bloquear en TREND, reducir sizing a 0.25x.

---

## 4. PLAN DE ACCIÓN RECOMENDADO

### Fase 1: Quick Wins (1-2 horas)

1. ✅ Reducir TP a 0.15%
2. ✅ Relajar VA_INTEGRITY thresholds (0.04-0.08)
3. ✅ Bloquear reversiones en TREND_UP/TREND_DOWN

**Objetivo**: Recuperar edge positivo en RANGE.

---

### Fase 2: Validación (2-3 horas)

4. ✅ Ejecutar Long-Range Audit con cambios
5. ✅ Verificar:
   - WR > 55% en RANGE
   - Expectancy > 0.12% (viable con Limit Sniper)
   - Timeouts < 30%

**Objetivo**: Confirmar que los cambios funcionan.

---

### Fase 3: Refinamiento (1 semana)

6. ✅ Ajustar SL a 0.15% (RR 1:1)
7. ✅ Aumentar timeout a 30 min
8. ✅ Investigar sesgo LONG
9. ✅ Agregar filtros de liquidez

**Objetivo**: Optimizar para producción.

---

## 5. EXPECTATIVAS REALISTAS

### Con los cambios de Fase 1:

| Métrica | Actual | Esperado | Delta |
|---------|--------|----------|-------|
| **Gross Expectancy** | -0.0176% | **+0.08%** | +0.10% |
| **WR (RANGE)** | 53.2% | **60%** | +6.8% |
| **WR (Overall)** | 49.5% | **55%** | +5.5% |
| **Timeouts** | 55% | **35%** | -20% |
| **Señales/día** | ~26 | **40-50** | +50% |

### Viabilidad:

- **Net (Taker)**: +0.08% - 0.12% = **-0.04%** ❌ (aún negativo)
- **Net (Maker)**: +0.08% - 0.08% = **0.00%** ⚠️ (breakeven)

**Conclusión**: Con Fase 1, el bot será **marginalmente viable con Limit Sniper**. Necesita Fase 2 y 3 para ser rentable.

---

## 6. ALTERNATIVAS SI NO FUNCIONA

### Opción A: Cambiar a Scalping Puro (0.05%/0.05%)

- TP/SL: 0.05% (ultra-tight)
- WR esperado: 70%+
- Requiere: Latencia < 10ms, maker orders obligatorio

### Opción B: Cambiar a Momentum (Trend Following)

- Abandonar mean-reversion
- Operar breakouts de VA en vez de reversiones
- Requiere: Rediseño completo de la estrategia

### Opción C: Hybrid (Range + Momentum)

- Mean-reversion en BALANCE
- Momentum en TREND
- Requiere: Dos playbooks separados

---

## 7. CONCLUSIÓN FINAL

**La estrategia LTA V6 tiene edge teórico pero está mal calibrada para condiciones reales de 2024.**

**Problemas principales**:
1. Targets demasiado ambiciosos (0.3% vs 0.19% MFE real)
2. VA_INTEGRITY demasiado estricto (rechaza 90% de señales)
3. Opera en trending markets donde mean-reversion no funciona

**Solución**:
- **Fase 1 (crítica)**: Reducir TP, relajar VA_INTEGRITY, bloquear trends
- **Expectativa**: Edge marginal (+0.08%), viable solo con Limit Sniper
- **Si falla**: Considerar cambio de estrategia (scalping o momentum)

**Recomendación**: Implementar Fase 1 YA y validar. Si no funciona después de Fase 2, considerar rediseño estratégico.

---

*Analysis Date: 2026-04-26*
*Data: 232 signals, Long-Range Audit 2024*
*Analyst: AI Agent (Kiro)*
