# 🥇 LINK Golden Parameters (V1)

> **Moneda**: LINKUSDT
> **Perfil**: `LINKUSDT` (mapeo 1:1)
> **Estado**: 3/4 escenarios Entry OK ✅ (FB, TACT, TA). LE: 0 señales.
> **Optimización**: 30 iteraciones Optuna v2 (Trial 41, score +0.6695) + LE-only 30 iteraciones
> **Validación**: Audit 6 datasets, 126 señales
> **Fecha**: 2026-07-20

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

| Escenario | n | WR | Net Taker | MFE/MAE | Entry | Targets |
|---|---|---|---|---|---|---|
| failed_breakout | 5 | 100% | +2.43% | 62.82 | ✅ | ✅ OK |
| tactical_absorption | 7 | 71.4% | +0.23% | 1.31 | ✅ | ✅ OK |
| trend_acceptance | 114 | 50.9% | +0.17% | 0.09 | ✅ | ✅ OK |
| liquidity_exhaustion | 0 | — | — | — | — | sin señales |
| **OVERALL** | **126** | **54.0%** | **+0.2618%** | — | **✅ EDGE CONFIRMED** |

## 🎯 Targets (Best Static Grid inyectados)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| failed_breakout | 2.50% | 2.50% | +2.43% |
| tactical_absorption | 0.70% | 0.70% | +0.23% |
| trend_acceptance | 1.20% | 1.20% | +0.17% |
| liquidity_exhaustion | 2.50% | 2.50% | sin señales |

---

## Perfil Completo (`config/coin_profiles.py` → `LINKUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 0.7 |
| `spread_max_ratio` | 3.2 |
| `l2_ratio_min_liquidity_exhaustion` | 3.0 |
| `spread_max_ratio_liquidity_exhaustion` | 2.1 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 1.7 |
| `z_block_liquidity_exhaustion` | 1.8 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.40 |
| liquidity | 0.30 |
| regime | 0.45 |
| structure | 0.25 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `z_score_min` | 2.9 |
| `cooldown` | 70.0 |
| `level_tolerance_pct` | 0.0021 |
| `absorption_score_min` | 0.25 |
| `book_bucket_pct` | 0.00225 |
| `displacement_z_max` | 3.0 |
| `stagnation_floor_pct` | 0.0013 |
| `volatility_z_max` | 3.6 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `exhaustion_z` | 3.7 |
| `divergence_z` | 0.9 |
| `min_break_distance_pct` | 0.005 |
| `cooldown` | 90.0 |
| `max_break_age` | 170.0 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.92 |
| `min_tests` | 4 |
| `min_bounce_pct` | 0.00125 |
| `test_memory_seconds` | 290.0 |
| `level_tolerance_pct` | 0.00065 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 390.0 |
| `min_candles_outside` | 7.0 |
| `cvd_confirmation_threshold` | 4.5 |
| `max_pullback_penetration_pct` | 0.0011 |
| `pullback_tolerance_pct` | 0.0016 |
| `regime_poc_migration_max` | 0.008 |
| `regime_vol_ratio_max` | 1.75 |
| `regime_va_expansion_max` | 1.35 |

---

## Análisis de Sensibilidad (Top 5 parámetros LE-only)

| Parámetro | Impacto |
|---|---|
| `test_memory_seconds` | ALTA (96%) |
| `l2_ratio_min_liquidity_exhaustion` | ALTA (96%) |
| `z_block_liquidity_exhaustion` | ALTA (93%) |
| `spread_max_ratio_liquidity_exhaustion` | ALTA (90%) |
| `min_tests` | ALTA (67%) |

---

## Notas

- LINK se re-optimizó desde cero con perfil ARB como seed (2 rondas, 44 trials v2).
- LE no produce señales en ningún dataset de LINK con ningún perfil probado.
- FB tiene n=5 pero edge sólido (100% WR, +2.43% Net).
- TACT tiene n=7 pero edge consistente (MFE/MAE 1.31).
- TA domina con 114 señales pero targets 1.20/1.20% fijos (inyectados manualmente desde best static grid).
- Pendiente: validación OOS mensual si se desea certificar.
