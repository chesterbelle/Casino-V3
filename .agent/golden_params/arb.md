# 🥇 ARB Golden Parameters (V1)

> **Moneda**: ARBUSDT
> **Perfil**: `ARBUSDT` (mapeo 1:1)
> **Estado**: 4/4 escenarios Entry OK ✅. Target Failure corregido con targets asimétricos.
> **Optimización**: 50 iteraciones Optuna (score best +0.4915, Trial 28)
> **Validación**: Audit 6 datasets (2 TREND_UP + 2 TREND_DOWN + 2 BALANCE), 105 señales
> **Fecha**: 2026-07-17

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

| Escenario | n | WR | Net Taker | MFE/MAE | Entry |
|---|---|---|---|---|---|
| trend_acceptance | 66 | 77.3% | +0.4288% | 4.83 | ✅ |
| tactical_absorption | 25 | 60.0% | +0.8635% | 0.45 | ✅ (TARGETS OK) |
| liquidity_exhaustion | 11 | 45.5% | +0.6893% | 0.12 | ✅ (TARGETS OK) |
| failed_breakout | 3 | 66.7% | +0.2300% | 0.04 | ✅ |
| **OVERALL** | **105** | **69.5%** | **+0.5539%** | — | **✅ EDGE** |

## 🎯 Targets (Best Static Grid)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| trend_acceptance | 2.50% | 5.00% | +1.1402% |
| tactical_absorption | 2.00% | 2.00% | +0.8635% |
| liquidity_exhaustion | 2.50% | 2.50% | +0.6893% |
| failed_breakout | 2.00% | 2.00% | +1.9300% |

---

## Perfil Completo (`config/coin_profiles.py` → `ARBUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 3.0 |
| `spread_max_ratio` | 2.6 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 3.0 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.30 |
| liquidity | 0.25 |
| regime | 0.10 |
| structure | 0.25 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `z_score_min` | 2.1 |
| `cooldown` | 80.0 |
| `level_tolerance_pct` | 0.0039 |
| `absorption_score_min` | 0.05 |
| `book_bucket_pct` | 0.00175 |
| `displacement_z_max` | 1.8 |
| `stagnation_floor_pct` | 0.0019 |
| `volatility_z_max` | 2.0 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `exhaustion_z` | 3.7 |
| `divergence_z` | 1.2 |
| `min_break_distance_pct` | 0.0048 |
| `cooldown` | 35.0 |
| `max_break_age` | 140.0 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.78 |
| `min_tests` | 2 |
| `min_bounce_pct` | 0.00195 |
| `test_memory_seconds` | 280.0 |
| `level_tolerance_pct` | 0.00075 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 840.0 |
| `min_candles_outside` | 2 |
| `cvd_confirmation_threshold` | 1.5 |
| `max_pullback_penetration_pct` | 0.0023 |
| `pullback_tolerance_pct` | 0.0007 |
| `regime_poc_migration_max` | 0.008 |
| `regime_vol_ratio_max` | 1.45 |
| `regime_va_expansion_max` | 1.18 |

---

## Análisis de Sensibilidad (Top 5 parámetros)

| Parámetro | Rango usado |
|---|---|
| `absorption_detector.cooldown` | 86% (ALTA) |
| `failed_breakout.max_break_age` | 75% (ALTA) |
| `trend_acceptance.cooldown` | 54% (ALTA) |
| `failed_breakout.cooldown` | 50% (ALTA) |
| `liquidity_exhaustion.test_memory_seconds` | 46% (ALTA) |

---

## Notas

- ARB es el perfil más liviano (107 MB datasets, ~16-30 MB cada uno).
- trend_acceptance domina con 66/105 señales (62.9%), MFE/MAE 4.83 — edge direccional muy limpio.
- Targets asimétricos en TA (TP 2.5% / SL 5.0%) capturan el best static grid.
- failed_breakout solo 3 señales — muestra insuficiente, pero entry OK.
- Pendiente: validación OOS mensual (descargar datasets mensuales ARB).
