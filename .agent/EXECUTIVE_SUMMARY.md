# Executive Summary — LTA V6 Strategy Analysis

**Date**: 2026-04-26
**Status**: 🔴 **CRITICAL ISSUES IDENTIFIED**

---

## TL;DR

**La estrategia NO es viable en su estado actual. Tiene edge teórico pero está mal calibrada.**

**3 problemas críticos**:
1. **Targets inalcanzables**: TP 0.3% pero MFE real 0.19% (58% más alto)
2. **Guardian demasiado estricto**: VA_INTEGRITY rechaza 90% de señales
3. **Opera en trending markets**: 75% timeouts en BULL, expectancy negativa en BEAR

**Solución**: 3 cambios críticos (2 horas de trabajo) pueden recuperar edge marginal.

---

## Datos Duros (232 señales, 2024)

| Métrica | Valor | Problema |
|---------|-------|----------|
| **Gross Expectancy** | -0.0176% | ❌ Negativo |
| **Win Rate** | 49.5% | ❌ < 50% |
| **MFE Promedio** | 0.19% | ⚠️ < TP 0.3% |
| **Timeouts** | 55% | ❌ Mayoría no resuelve |
| **Sesgo LONG** | 67.7% | ⚠️ Debería ser 50% |

### Por Condición:

| Condición | WR% | Expectancy% | Veredicto |
|-----------|-----|-------------|-----------|
| RANGE | 53.2% | +0.0246% | ❌ < fees |
| BEAR | 44.4% | -0.0313% | ❌ Negativo |
| BULL | 50.0% | +0.0125% | ❌ < fees |

---

## Causa Raíz

### 1. **Targets Inalcanzables** (Crítico)

```
MFE real:     0.19%
TP config:    0.30%
Gap:          +58%
```

**Por qué**: El precio se mueve HACIA el POC pero NO lo alcanza. La reversión es parcial.

**Solución**: Reducir TP a 0.15% (alineado con MFE real).

---

### 2. **VA_INTEGRITY Demasiado Estricto** (Crítico)

```
Rechazos:     472 (89.7% del total)
Threshold:    0.08-0.12
Problema:     Perfiles reales son más dispersos
```

**Por qué**: Los perfiles de volumen en 2024 son naturalmente dispersos (especialmente en Asian session con baja liquidez).

**Solución**: Reducir thresholds a 0.04-0.08.

---

### 3. **Mean-Reversion Débil en Trending** (Crítico)

```
BULL timeouts:  75.6%
BEAR WR:        44.4%
Problema:       POC no tiene "gravedad" en trends
```

**Por qué**: En trending markets, el precio NO regresa al POC, continúa la tendencia.

**Solución**: Bloquear TODAS las reversiones en TREND_UP/TREND_DOWN.

---

## Plan de Acción (Fase 1: Quick Wins)

### Cambio #1: Reducir TP a 0.15%

```python
# config/strategies.py
LTA_TP_TARGET = 0.0015  # Antes: 0.003 (0.3%)
```

**Impacto**: WR 49.5% → 60%+, Timeouts 55% → 35%

---

### Cambio #2: Relajar VA_INTEGRITY

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

**Impacto**: Señales 232 → 400-500, más volumen en Asian

---

### Cambio #3: Bloquear Trending Markets

```python
# decision/setup_engine.py - _check_regime_alignment()
# Línea ~900

if regime_v2 == "TREND_UP":
    return 0.0  # Bloquear TODO (antes: permitía LONG)

if regime_v2 == "TREND_DOWN":
    return 0.0  # Bloquear TODO (antes: permitía SHORT)
```

**Impacto**: Solo opera en BALANCE (donde está el edge real)

---

## Expectativas Realistas

### Después de Fase 1:

| Métrica | Actual | Esperado | Delta |
|---------|--------|----------|-------|
| Gross Expectancy | -0.0176% | **+0.08%** | +0.10% |
| WR (RANGE) | 53.2% | **60%** | +6.8% |
| Timeouts | 55% | **35%** | -20% |

### Viabilidad:

```
Net (Taker): +0.08% - 0.12% = -0.04% ❌ (aún negativo)
Net (Maker): +0.08% - 0.08% =  0.00% ⚠️ (breakeven)
```

**Conclusión**: Con Fase 1, el bot será **marginalmente viable con Limit Sniper**.

---

## Recomendación Final

### ✅ Implementar Fase 1 (2 horas)

1. Reducir TP a 0.15%
2. Relajar VA_INTEGRITY (0.04-0.08)
3. Bloquear TREND_UP/TREND_DOWN

### ✅ Validar (2 horas)

4. Ejecutar Long-Range Audit con cambios
5. Verificar Expectancy > 0.12%

### ⚠️ Si no funciona:

- **Plan B**: Reducir TP a 0.10% (ultra-scalping)
- **Plan C**: Cambiar a momentum (trend following)
- **Plan D**: Hybrid (range + momentum)

---

## Archivos a Modificar

1. `config/strategies.py` — TP, VA_INTEGRITY thresholds
2. `decision/setup_engine.py` — Regime alignment logic (línea ~900)

**Tiempo estimado**: 2 horas (cambios) + 2 horas (validación) = **4 horas total**

---

## Documentación Completa

- **Análisis profundo**: `.agent/DEEP_STRATEGY_ANALYSIS.md`
- **Datos del audit**: `.agent/LONG_RANGE_AUDIT_RESULTS_2024.md`
- **Código del análisis**: `utils/analysis/deep_strategy_analysis.py`

---

*Date: 2026-04-26*
*Status: READY FOR IMPLEMENTATION*
