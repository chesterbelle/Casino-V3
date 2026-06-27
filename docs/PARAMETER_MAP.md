# 🎚️ Parameter Map — Trazabilidad de los 49 Parámetros

> **Propósito:** Este documento es la **fuente de verdad** para la optimización de parámetros.
> Si estás "stuck" y no sabes qué parámetro ajustar, este mapa te dice:
> 1. Dónde está definido.
> 2. Dónde se usa.
> 3. Qué impacto tiene en el edge.

---

## 📊 Estructura de Parámetros

Los 49 parámetros están organizados en **8 grupos funcionales**:

| Grupo | # Parámetros | Propósito | Archivos Clave |
|-------|--------------|-----------|----------------|
| **Absorption** | 8 | Detección de absorción institucional (TacticalAbsorption). | `config/coin_profiles.py`, `sensors/absorption/absorption_detector.py` |
| **Failed Breakout** | 4 | Detección de breakouts fallidos. | `config/coin_profiles.py`, `decision/scenarios/failed_breakout.py` |
| **Liquidity Exhaustion** | 6 | Detección de agotamiento en niveles. | `config/coin_profiles.py`, `decision/scenarios/liquidity_exhaustion.py` |
| **Trend Acceptance** | 5 | Detección de tendencias confirmadas. | `config/coin_profiles.py`, `decision/scenarios/trend_acceptance.py` |
| **Targets** | 8 | Definición de TP/SL por escenario. | `config/coin_profiles.py`, `decision/engine/targets.py` |
| **Quality** | 14 | Scoring y filtrado de calidad de señales. | `config/coin_profiles.py`, `decision/engine/quality_scorer.py` |
| **Guardians** | 3 | Filtros de protección (L2 ratio, spread). | `config/coin_profiles.py`, `decision/engine/guardians.py` |
| **Pressure** | 1 | Thresholds de presión del mercado (z_block). | `config/coin_profiles.py`, `core/pressure/engine.py` |

**Total:** 49 parámetros.

---

## 🔍 Trazabilidad Detallada por Parámetro

### **Grupo 1: Absorption (TacticalAbsorption)**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `z_score_min` | `config/coin_profiles.py` (por perfil) | `profile_manager.get_sensor_params()` | `AbsorptionDetector._get_params()` | **ALTO:** Filtra señales de baja convicción. Subir → menos señales, más calidad. | 1.5 - 3.5 |
| `absorption_score_min` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `AbsorptionDetector._get_params()` | **MEDIO:** Threshold mínimo del score v2. | 0.5 - 0.7 |
| `cooldown_seconds` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `AbsorptionDetector.on_tick()` | **BAJO:** Evita señales duplicadas. | 60 - 300s |
| `volatility_z_max` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `AbsorptionDetector._get_params()` | **MEDIO:** Bloquea en volatilidad extrema. | 3.0 - 5.0 |
| `displacement_z_max` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `AbsorptionDetector._get_params()` | **BAJO:** Filtra movimientos de precio anómalos. | 3.0 - 5.0 |
| `concentration_min` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `PressureEngine.update()` | **NULO (Legacy):** No afecta el edge real. Solo para cálculo del score legacy. | 0.50 (fijo) |
| `noise_max` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `PressureEngine.update()` | **NULO (Legacy):** No afecta el edge real. | 0.35 (fijo) |
| `book_bucket_pct` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `PressureEngine._consolidate_l2()` | **ALTO:** Agrupa niveles de orderbook en libros delgados. | 0.00 - 0.10 |

### **Grupo 2: Failed Breakout**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `cooldown` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `FailedBreakoutDetector._get_params()` | **MEDIO:** Evita re-entradas rápidas. | 45 - 120s |
| `max_break_age` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `FailedBreakoutDetector.on_tick()` | **ALTO:** Tiempo máximo para que el fallo ocurra. | 30 - 90s |
| `min_break_distance_pct` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `FailedBreakoutDetector.on_tick()` | **MEDIO:** Distancia mínima para considerar breakout. | 0.0003 (3 bps) |
| `divergence_z` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `FailedBreakoutDetector._check_divergence()` | **ALTO:** Threshold de divergencia de CVD. | 0.5 - 1.5 |
| `exhaustion_z` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `FailedBreakoutDetector._check_exhaustion()` | **ALTO:** Threshold para descartar si hay demasiada fuerza. | 2.0 - 3.0 |

### **Grupo 3: Liquidity Exhaustion**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `cooldown` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector._get_params()` | **MEDIO:** Evita re-entradas. | 20 - 60s |
| `level_tolerance_pct` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector.on_tick()` | **ALTO:** Tolerancia para considerar "mismo nivel". | 0.0003 - 0.0008 |
| `test_memory_seconds` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector._prune_old_tests()` | **MEDIO:** Ventana de tiempo para los tests. | 60 - 180s |
| `min_tests` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector.on_tick()` | **ALTO:** Número mínimo de tests para disparar. | 3 - 5 |
| `declining_threshold` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector._check_declining()` | **ALTO:** Ratio de declinación de delta requerido. | 0.6 - 0.8 |
| `min_bounce_pct` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `LiquidityExhaustionDetector.on_tick()` | **BAJO:** Rebote mínimo requerido entre tests. | 0.0002 - 0.0005 |

### **Grupo 4: Trend Acceptance**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `cooldown` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `TrendAcceptanceDetector._get_params()` | **BAJO:** Evita re-entradas en la misma tendencia. | 300 - 900s |
| `cvd_confirmation_threshold` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `TrendAcceptanceDetector.on_tick()` | **CRÍTICO:** Threshold de confirmación de CVD para el breakout. | 2.0 - 5.0 |
| `pullback_bps` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `TrendAcceptanceDetector._process_breakout()` | **ALTO:** Profundidad del pullback para entrada. | 8 - 20 bps |
| `min_breakout_distance_bps` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `TrendAcceptanceDetector._check_breakout()` | **MEDIO:** Distancia mínima del breakout. | 15 - 30 bps |
| `max_pullback_penetration_pct` | `config/coin_profiles.py` | `profile_manager.get_sensor_params()` | `TrendAcceptanceDetector._check_pullback()` | **ALTO:** Qué tan profundo puede ser el pullback sin invalidar. | 0.001 - 0.003 |

### **Grupo 5: Targets (TP/SL)**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `tp_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **CRÍTICO:** Take Profit dinámico. | 0.020 - 0.035 |
| `sl_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **CRÍTICO:** Stop Loss dinámico. | 0.020 - 0.035 |
| `failed_breakout_tp_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** TP específico para FB. | 0.015 - 0.025 |
| `failed_breakout_sl_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** SL específico para FB. | 0.020 - 0.030 |
| `liquidity_exhaustion_tp_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** TP específico para LE. | 0.015 - 0.025 |
| `liquidity_exhaustion_sl_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** SL específico para LE. | 0.020 - 0.030 |
| `trend_acceptance_tp_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** TP específico para TA. | 0.025 - 0.040 |
| `trend_acceptance_sl_pct` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `decision/engine/targets.py` | **ALTO:** SL específico para TA. | 0.020 - 0.030 |

### **Grupo 6: Quality Scorer**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `scoring_threshold_A` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **ALTO:** Threshold para Grade A. | 0.75 - 0.85 |
| `scoring_threshold_B` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **MEDIO:** Threshold para Grade B. | 0.50 - 0.65 |
| `weight_l2_ratio` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **MEDIO:** Peso del factor L2. | 0.15 - 0.25 |
| `weight_spread` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **BAJO:** Peso del factor spread. | 0.10 - 0.20 |
| `weight_volatility` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **MEDIO:** Peso del factor volatilidad. | 0.15 - 0.25 |
| `weight_pressure` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **ALTO:** Peso del factor presión. | 0.20 - 0.30 |
| `weight_cvd` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **ALTO:** Peso del factor CVD. | 0.20 - 0.30 |
| *(... y 7 pesos más)* | `config/coin_profiles.py` | `profile_manager.get_profile()` | `QualityScorer.evaluate_quality()` | **MEDIO:** Pesos normalizados a 1.0. | - |

### **Grupo 7: Guardians**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `l2_ratio_min` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `Guardians._check_l2_ratio()` | **CRÍTICO:** Filtro de salud del orderbook (mean-reversion). | 1.5 - 3.0 |
| `l2_ratio_min_trend_acceptance` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `Guardians._check_l2_ratio_trend()` | **CRÍTICO:** Filtro de salud del orderbook (trend-following). | 1.0 - 1.5 |
| `spread_max_ratio` | `config/coin_profiles.py` | `profile_manager.get_profile()` | `Guardians._check_spread()` | **MEDIO:** Filtro de spread máximo. | 0.001 - 0.003 |

### **Grupo 8: Pressure**

| Parámetro | Fuente de Verdad | Se Lee En | Se Usa En | Impacto en Edge | Rango Típico |
|-----------|------------------|-----------|-----------|-----------------|--------------|
| `z_block` | `config/coin_profiles.py` | `profile_manager.get_pressure_thresholds()` | `PressureEngine._check_block()` | **ALTO:** Threshold para bloqueo por desplazamiento de precio. | 2.0 - 3.5 |

---

## 🗺️ Flujo de Resolución de Parámetros

Cuando un detector necesita un parámetro, sigue esta ruta:

```
1. Detector._get_params(symbol)
   ↓
2. ProfileManager.get_sensor_params(symbol, sensor_name)
   ↓
3. ProfileManager.get_profile_name(symbol) → "MID_LIQUID"
   ↓
4. ProfileManager.get_profile("MID_LIQUID") → Lee config/coin_profiles.py
   ↓
5. ProfileManager._resolve_params() → Aplica overrides, valida con Pydantic
   ↓
6. Detector._cluster_cache[symbol] = params → Cachea para el siguiente tick
   ↓
7. Detector usa params[param_name]
```

**Nota:** El paso 6 (cache) es crítico para performance. Si cambias un parámetro en runtime, el detector no lo verá hasta que se reinicie el cache (o se reinicie el bot).

---

## 📝 Notas de Optimización

1.  **Fuente de Verdad:** `config/coin_profiles.py` es la única fuente de verdad. No ajustes parámetros en los detectores directamente.
2.  **Validación:** `decision/engine/param_validation.py` valida que los parámetros estén en rangos aceptables antes de usarlos.
3.  **Legacy:** Los parámetros `concentration_min` y `noise_max` son legacy. No los optimices; no afectan el edge real.
4.  **Clusters:** Los parámetros están agrupados por cluster (`MID_LIQUID`, `THIN_VOLATILE`, etc.). Ajustar un perfil afecta a todas las coins de ese cluster.

---

## 🔄 Historial de Cambios

- **2026-06-27:** Creado `PARAMETER_MAP.md` como parte de la refactorización de arquitectura (Deuda Técnica #3).
