# 🥇 NEAR Golden Parameters (V1)

> **Moneda**: NEARUSDT
> **Perfil**: `NEARUSDT` (mapeo 1:1)
> **Estado**: 4/4 escenarios Entry OK ✅. Target Failure corregido con targets estáticos.
> **Optimización**: 50 iteraciones Optuna (score best +1.6997, Trial 48)
> **Validación**: Audit 6 datasets (2 TREND_UP + 2 TREND_DOWN + 2 BALANCE), 282 señales
> **Fecha**: 2026-07-17

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

| Escenario | n | WR | Net Taker | MFE/MAE | Entry |
|---|---|---|---|---|---|
| trend_acceptance | 215 | 18.6% | +0.6706% | 1.27 | ✅ |
| liquidity_exhaustion | 36 | 25.0% | +1.2090% | 6.05 | ✅ (TARGETS OK) |
| tactical_absorption | 20 | 40.0% | +0.7164% | 19.12 | ✅ |
| failed_breakout | 11 | 9.1% | +0.6216% | 28.65 | ✅ |
| **OVERALL** | **282** | **20.6%** | **+0.7407%** | — | **✅ EDGE** |

## 🎯 Targets (Best Static Grid)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| failed_breakout | 2.50% | 4.00% | +2.1858% |
| liquidity_exhaustion | 2.50% | 4.00% | +0.6405% |
| tactical_absorption | 2.50% | 4.00% | +0.9475% |
| trend_acceptance | 2.50% | 2.50% | +0.4979% |

---

## Perfil Completo (`config/coin_profiles.py` → `NEARUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 1.7 |
| `spread_max_ratio` | 2.2 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 2.1 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.20 |
| liquidity | 0.25 |
| regime | 0.25 |
| structure | 0.20 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `z_score_min` | 4.9 |
| `cooldown` | 210.0 |
| `level_tolerance_pct` | 0.0049 |
| `absorption_score_min` | 0.375 |
| `book_bucket_pct` | 0.00275 |
| `displacement_z_max` | 3.1 |
| `stagnation_floor_pct` | 0.0008 |
| `volatility_z_max` | 3.9 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `exhaustion_z` | 2.8 |
| `divergence_z` | 1.7 |
| `min_break_distance_pct` | 0.0032 |
| `cooldown` | 35.0 |
| `max_break_age` | 100.0 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.84 |
| `min_tests` | 2 |
| `min_bounce_pct` | 0.00095 |
| `test_memory_seconds` | 190.0 |
| `level_tolerance_pct` | 0.001 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 390.0 |
| `min_candles_outside` | 5 |
| `cvd_confirmation_threshold` | 2.5 |
| `max_pullback_penetration_pct` | 0.0021 |
| `pullback_tolerance_pct` | 0.0017 |
| `regime_poc_migration_max` | 0.0055 |
| `regime_vol_ratio_max` | 1.7 |
| `regime_va_expansion_max` | 1.3 |

---

## Análisis de Sensibilidad (Top 5 parámetros)

| Parámetro | Rango usado |
|---|---|
| `failed_breakout.cooldown` | 83% (ALTA) |
| `trend_acceptance.cooldown` | 62% (ALTA) |
| `liquidity_exhaustion.test_memory_seconds` | 58% (ALTA) |
| `absorption_detector.cooldown` | 19% (MEDIA) |
| `failed_breakout.max_break_age` | 25% (MEDIA) |

---

## Notas

- NEAR es muy activo (282 señales, el doble que LTC/AVAX). trend_acceptance domina con 215 señales (76%).
- Baseline ya era fuerte (+1.3362%). Optimización mejoró score a +1.6997.
- Targets simétricos 2.50% generalizan bien para todos los escenarios.
- failed_breakout solo 11 señales pero MFE/MAE 28.65 — edge direccional extremadamente limpio.
- Pendiente: validación OOS mensual (descargar datasets mensuales NEAR).
