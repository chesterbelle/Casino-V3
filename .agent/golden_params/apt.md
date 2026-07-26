# 🥇 APT Golden Parameters (V1)

> **Moneda**: APTUSDT
> **Perfil**: `APTUSDT` (mapeo 1:1)
> **Estado**: 3/3 escenarios con señales Entry OK ✅ (TA, FB, TACT). LE: 0 señales.
> **Optimización**: 50 iteraciones Optuna (score best +1.6571, Trial 19)
> **Validación**: Audit 6 datasets, 145 señales
> **Fecha**: 2026-07-17

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

| Escenario | n | WR | Net Taker | MFE/MAE | Entry |
|---|---|---|---|---|---|
| trend_acceptance | 133 | 30.1% | +1.5733% | 2.11 | ✅ (TARGETS OK) |
| tactical_absorption | 9 | 33.3% | -0.7367% | 0.67 | ✅ (n insuficiente) |
| failed_breakout | 3 | 0.0% | -0.5700% | 0.52 | ✅ (n insuficiente) |
| liquidity_exhaustion | 0 | — | — | — | Sin datos |
| **OVERALL** | **145** | **29.7%** | **+1.3856%** | — | **✅ EDGE FUERTE** |

## 🎯 Targets (Best Static Grid)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| trend_acceptance | 2.50% | 2.50% | +0.8768% |
| failed_breakout | 2.50% | 2.50% | +0.3236% |
| tactical_absorption | 1.00% | 0.30% | +0.2078% |
| liquidity_exhaustion | — | — | Sin señales |

---

## Perfil Completo (`config/coin_profiles.py` → `APTUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 0.9 |
| `spread_max_ratio` | 2.8 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 1.9 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.35 |
| liquidity | 0.10 |
| regime | 0.35 |
| structure | 0.10 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `z_score_min` | 2.4 |
| `cooldown` | 40.0 |
| `level_tolerance_pct` | 0.0017 |
| `absorption_score_min` | 0.225 |
| `book_bucket_pct` | 0.002 |
| `displacement_z_max` | 1.7 |
| `stagnation_floor_pct` | 0.0012 |
| `volatility_z_max` | 1.7 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `exhaustion_z` | 3.7 |
| `divergence_z` | 0.7 |
| `min_break_distance_pct` | 0.0046 |
| `cooldown` | 55.0 |
| `max_break_age` | 140.0 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.54 |
| `min_tests` | 4 |
| `min_bounce_pct` | 0.00145 |
| `test_memory_seconds` | 190.0 |
| `level_tolerance_pct` | 0.00035 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 810.0 |
| `min_candles_outside` | 3 |
| `cvd_confirmation_threshold` | 1.5 |
| `max_pullback_penetration_pct` | 0.002 |
| `pullback_tolerance_pct` | 0.0019 |
| `regime_poc_migration_max` | 0.0075 |
| `regime_vol_ratio_max` | 1.7 |
| `regime_va_expansion_max` | 1.17 |

---

## Análisis de Sensibilidad (Top 5 parámetros)

| Parámetro | Rango usado |
|---|---|
| `failed_breakout.max_break_age` | 100% (ALTA) |
| `absorption_detector.cooldown` | 71% (ALTA) |
| `failed_breakout.cooldown` | 67% (ALTA) |
| `liquidity_exhaustion.test_memory_seconds` | 67% (ALTA) |
| `trend_acceptance.cooldown` | 35% (ALTA) |

---

## Notas

- APT es el mejor resultado hasta ahora: **+1.3856% Net Taker**.
- trend_acceptance domina con 91.7% señales (133/145) y MFE/MAE 2.11 — edge direccional muy limpio.
- FB y TACT tienen muestras muy pequeñas (n=3 y n=9). LE no generó señales.
- Pendiente: validación OOS mensual.
