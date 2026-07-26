# 🥇 OP Golden Parameters (V1)

> **Moneda**: OPUSDT
> **Perfil**: `OPUSDT` (mapeo 1:1)
> **Estado**: 2/4 escenarios Entry OK ✅ (TA, TACT). FB y LE: ENTRY FAILURE (n<5).
> **Optimización**: 50 iteraciones Optuna (score best +0.3932, Trial 22)
> **Validación**: Audit 6 datasets, 107 señales
> **Fecha**: 2026-07-17

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

| Escenario | n | WR | Net Taker | MFE/MAE | Entry |
|---|---|---|---|---|---|
| trend_acceptance | 98 | 9.2% | +0.3607% | 1.62 | ✅ |
| tactical_absorption | 3 | 33.3% | -0.7367% | 0.96 | ✅ (n insuficiente) |
| liquidity_exhaustion | 3 | 0.0% | -0.8172% | 0.37 | ❌ ENTRY FAILURE |
| failed_breakout | 3 | 0.0% | -0.5700% | 0.18 | ❌ ENTRY FAILURE |
| **OVERALL** | **107** | **9.3%** | **+0.2708%** | — | **✅ EDGE MARGINAL** |

## 🎯 Targets (Best Static Grid)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| tactical_absorption | 2.50% | 4.00% | +1.2755% |
| trend_acceptance | 2.00% | 2.00% | +0.4041% |
| failed_breakout | — | — | ENTRY FAILURE |
| liquidity_exhaustion | — | — | ENTRY FAILURE |

---

## Perfil Completo (`config/coin_profiles.py` → `OPUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 2.0 |
| `spread_max_ratio` | 2.0 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 2.3 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.30 |
| liquidity | 0.25 |
| regime | 0.15 |
| structure | 0.05 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `z_score_min` | 4.8 |
| `cooldown` | 190.0 |
| `level_tolerance_pct` | 0.0017 |
| `absorption_score_min` | 0.4 |
| `book_bucket_pct` | 0.0005 |
| `displacement_z_max` | 2.5 |
| `stagnation_floor_pct` | 0.0015 |
| `volatility_z_max` | 2.3 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `exhaustion_z` | 4.0 |
| `divergence_z` | 1.5 |
| `min_break_distance_pct` | 0.0058 |
| `cooldown` | 80.0 |
| `max_break_age` | 160.0 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.57 |
| `min_tests` | 2 |
| `min_bounce_pct` | 0.00195 |
| `test_memory_seconds` | 200.0 |
| `level_tolerance_pct` | 0.00055 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 540.0 |
| `min_candles_outside` | 8 |
| `cvd_confirmation_threshold` | 5.0 |
| `max_pullback_penetration_pct` | 0.0022 |
| `pullback_tolerance_pct` | 0.0016 |
| `regime_poc_migration_max` | 0.0065 |
| `regime_vol_ratio_max` | 1.85 |
| `regime_va_expansion_max` | 1.06 |

---

## Análisis de Sensibilidad (Top 5 parámetros)

| Parámetro | Rango usado |
|---|---|
| `failed_breakout.max_break_age` | 88% (ALTA) |
| `trend_acceptance.cooldown` | 58% (ALTA) |
| `liquidity_exhaustion.test_memory_seconds` | 50% (ALTA) |
| `absorption_detector.cooldown` | 48% (ALTA) |
| `failed_breakout.cooldown` | 33% (ALTA) |

---

## Notas

- OP es la moneda más débil hasta ahora. Solo trend_acceptance (n=98) produce edge consistente (MFE/MAE 1.62).
- FB, LE, TACT tienen solo 3 señales cada uno — muestra insuficiente para concluir (n<5).
- Baseline era negativo (-0.1643%). Optimización llevó a +0.2708% Net Taker — mejora pero marginal.
- TA domina con 91.6% de las señales (98/107).
- Pendiente: validación OOS mensual si se desea certificar.
