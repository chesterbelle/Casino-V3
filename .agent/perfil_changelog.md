
---
# Perfil Changelog — THIN_VOLATILE (XRP, DOGE)

> **Iniciado**: 2026-06-02
> **Última actualización**: 2026-06-03

## Historial de Iteraciones

| # | Cambio | Configuración (Cambios) | Net Taker | Conclusión |
|---|--------|------------------------|-----------|------------|
| 1 | Baseline | z=3.8, conc=0.60, l2=1.0 | -0.068% | Entry Failure: Ruido en TacticalAbsorptionV2 |
| 2 | Sensorial + L2 | z=4.5, conc=0.55, l2=1.5 | **XRP: +0.1098%** DOGE: 0 trades | **XRP**: TAV 0.87→1.11. **DOGE**: parámetros demasiado restrictivos — 0 trades en todos los meses. |
| 3 | **ENTRY FILTER RELAX** | z=2.5, conc=0.45, stagn=0.15, quality_A=0.65, l2=1.0 | DOGE: -0.0121% XRP: +0.0320% | **TAV mejoró ~6%** (DOGE 0.85→0.91, XRP 0.89→0.94) pero sigue Entry Failure. Hipótesis parcialmente confirmada: menos z_score ayuda, pero no suficiente. trend_acceptance DOGE 2.42 sigue sólido. |

## DOGE — Resultados Detallados (Iteración 2)

| Mes | Trades | Nota |
|-----|--------|------|
| 2024-10 | 0 | Sin señales que pasaran filtros z=4.5/conc=0.55/l2=1.5 |
| 2024-11 | 0 | Igual |
| 2024-12 | 0 | Igual |
| 2025-01 | 0 | Igual |
| 2025-02 | 0 | Igual |
| 2025-04 | ❌ Fallo | depth_snapshots vacío (dataset corrupto) |

---

## Foundation Data — THIN_VOLATILE Audit (Edge Auditor, 2026-06-03)

### TAV MFE/MAE por rango de z_score (DOGE y XRP)
| Activo | Side | n | MFE | MAE | Ratio | Observación |
|--------|------|---|-----|-----|-------|-------------|
| DOGE | LONG | 610 | 1.143% | 1.637% | **0.70** | ❌ Tóxico |
| DOGE | SHORT | 575 | 1.423% | 1.358% | **1.05** | 🎯 Casi OK |
| XRP | LONG | 563 | 1.327% | 1.364% | **0.97** | ⚠️ Borderline |
| XRP | SHORT | 550 | 0.936% | 1.173% | **0.80** | ❌ |

### Descubrimiento: z_score alto es contraproducente en THIN_VOLATILE
- **DOGE SHORT**: z≥3 = 1.05, z≥4 = 0.97, z≥5 = 0.83
- **XRP**: z≥2 = 0.80, z≥4 = 0.71
- **Conclusión**: A mayor z_score, peor ratio. En libros delgados, absorción extrema (z≥4.5) es señal de trampa, no de soporte.

## Resultados Iteración 3 (Edge Auditor — 2659 señales, 12 meses)

| Setup | Coin | n | MFE% | MAE% | Ratio | Entry OK? | Net Taker |
|-------|------|---|------|------|-------|-----------|-----------|
| TAV | DOGE | 1106 | 1.231% | 1.347% | **0.91** → +7% vs I2 | ❌ | -0.0121% |
| TAV | XRP | 1139 | 1.158% | 1.226% | **0.94** → +5.6% vs I2 | ❌ | +0.0320% |
| failed_breakout | DOGE | 77 | 0.991% | 1.127% | **0.88** → +4.8% | ✅ (0.90/0.90%) | -0.5726%* |
| trend_acceptance | DOGE | 133 | 1.900% | 0.786% | **2.42** | ✅ | +0.9729% |
| trend_acceptance | XRP | 144 | 1.014% | 0.811% | **1.25** | ✅ | -0.3825%* |

*Target optimization needed — AMT underperforms best uniform.

**Overall (2625 señales con decisión):** Gross Exp +0.1516%, Net Taker +0.0316% ✅

**Conclusión:** La relajación de filtros de entrada (z 4.5→2.5) mejoró el ratio TAV DOGE de 0.85→0.91 y XRP 0.89→0.94. Sin embargo, ambos siguen en Entry Failure (<1.0). La mejora del 6% confirma que menor z_score ayuda, pero el core del problema de TAV en thin books no se resuelve solo con parámetros. Se requieren cambios arquitectónicos (filtro direccional DOGE LONG vs SHORT, o revisión del setup engine).

## Cambios en Iteración 3

| Parámetro | Iteración 2 | Iteración 3 | Razón AMT |
|-----------|-------------|-------------|-----------|
| `z_score_min` | 4.5 | **2.5** | z≥4 selecciona entradas con peor directional edge |
| `concentration_min` | 0.55 | **0.45** | Thin books no pueden concentrar como líquidos |
| `stagnation_floor_pct` | 0.10 | **0.15** | Más ruido en thin → más tolerancia |
| `grade_thresholds.A` | 0.75 | **0.65** | Quality scorer rechazaba demasiadas señales viables |
| `grade_thresholds.B` | 0.45 | **0.40** | Idem |
| `l2_ratio_min` | 1.5 | **1.0** | THIN books nunca tienen l2_ratio alto |
| `l2_ratio_min_trend_down` | 2.5 | **1.5** | Consistente |

---

# Perfil Changelog — MID_LIQUID (LTC, AVAX, OP, APT, BNB, LINK)

> **Iniciado**: 2026-06-05
> **Última actualización**: 2026-06-05

## Historial de Iteraciones

| # | Cambio | Configuración (Cambios) | Net Taker | Conclusión |
|---|--------|------------------------|-----------|------------|
| 1 | Baseline | failed_breakout: tp=2.2%/sl=2.0%, sensors: default | +0.85% | failed_breakout negativo (-0.44%), trend_acceptance positivo (+0.85%) |
| 2 | Ajuste targets failed_breakout | tp=1.5%/sl=1.5% | +1.66% | failed_breakout empeoró (-1.07%), trend_acceptance mejoró (+1.66%) |
| 3 | Ajuste sensores failed_breakout | min_break_distance=0.0012, max_break_age=60, cvd_divergence=0.35 | +1.66% | Sin cambio significativo (parámetros no se aplicaban) |
| 4 | **FIX: Detectores leen perfil** | FailedBreakoutDetector lee profile_manager | +1.66% | Parámetros ahora se usan correctamente |
| 5 | **Ajuste final targets** | failed_breakout: tp=1.2%/sl=1.2% | **+0.86%** | **EDGE CONFIRMED**: failed_breakout +0.57%, trend_acceptance +0.87% |

## Cambios Clave en Parámetros

| Parámetro | Antes | Después | Razón |
|-----------|-------|---------|-------|
| `failed_breakout.tp_pct` | 0.022 | **0.012** | MFE promedio es 1.136%, target demasiado alto |
| `failed_breakout.sl_pct` | 0.020 | **0.012** | Simétrico con TP para mejor R:R |
| `failed_breakout.min_break_distance_pct` | 0.0008 | **0.0012** | Más selectivo, breaks más limpios |
| `failed_breakout.max_break_age` | 90.0 | **60.0** | Requiere re-entry más rápido |
| `failed_breakout.cvd_divergence_threshold` | 0.25 | **0.35** | Requiere divergencia más fuerte |

## Resultados Finales (LTC_TREND_UP_2024-03-01)

| Métrica | Valor |
|---------|-------|
| Total Signals | 3903 |
| Win Rate | 75.4% |
| Net Taker | +0.8630% ✅ |
| Net Maker | +0.9030% ✅ |
| failed_breakout Net | +0.57% ✅ |
| trend_acceptance Net | +0.87% ✅ |

## Mejora Arquitectónica

Los detectores de escenarios ahora leen los parámetros del perfil en tiempo de ejecución:
- `FailedBreakoutDetector.on_tick()` → `profile_manager.get_sensor_params(symbol, "failed_breakout")`
- `LiquidityExhaustionDetector.on_tick()` → `profile_manager.get_sensor_params(symbol, "liquidity_exhaustion")`
- `TrendAcceptanceDetector.on_tick()` → `profile_manager.get_sensor_params(symbol, "trend_acceptance")`

Esto permite calibración por cluster sin modificar código.
