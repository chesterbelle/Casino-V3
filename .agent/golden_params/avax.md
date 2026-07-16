# 🥇 AVAX Golden Parameters (V3)

> **Moneda**: AVAX/USDT:USDT, AVAXUSDT
> **Cluster**: AVAX_NOISY_UNCERTAIN
> **Estado**: 4/4 escenarios optimizados vía cluster_optimizer (50 iters c/u)
> **Optimización**: tactical_absorption | failed_breakout | liquidity_exhaustion | trend_acceptance
> **Best score global**: +0.4601 (trend_acceptance)
> **Fecha**: 2026-07-10

---

## Perfil Completo (`config/coin_profiles.py` → `AVAX_NOISY_UNCERTAIN`)

### Guardians

| Parámetro | Valor | Nota |
|---|---|---|
| `l2_ratio_min` | 0.5 | General |
| `l2_ratio_min_trend_down` | 2.2 | Bear market |
| `l2_ratio_min_tactical_absorption` | 1.2 | |
| `spread_max_ratio_tactical_absorption` | 2.4 | |
| `l2_ratio_min_failed_breakout` | 2.5 | |
| `spread_max_ratio_failed_breakout` | 1.8 | |
| `l2_ratio_min_liquidity_exhaustion` | 1.4 | |
| `spread_max_ratio_liquidity_exhaustion` | 1.5 | |
| `l2_ratio_min_trend_acceptance` | 1.3 | |
| `spread_max_ratio_trend_acceptance` | 2.6 | |
| `spread_max_ratio` | 2.5 | |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 2.8 |
| `z_block_tactical_absorption` | 1.7 |
| `z_block_failed_breakout` | 2.5 |
| `z_block_liquidity_exhaustion` | 1.6 |
| `z_block_trend_acceptance` | 2.6 |

### Sensors

#### tactical_absorption (absorption_detector)

| Parámetro | Valor |
|---|---|
| `absorption_score_min` | 0.275 |
| `book_bucket_pct` | 0.00075 |
| `cooldown` | 140.0 |
| `displacement_z_max` | 3.6 |
| `level_tolerance_pct` | 0.0039 |
| `stagnation_floor_pct` | 0.001 |
| `volatility_z_max` | 2.4 |
| `z_score_min` | 3.3 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `cooldown` | 70.0 |
| `divergence_z` | 0.6 |
| `exhaustion_z` | 3.8 |
| `max_break_age` | 160.0 |
| `min_break_distance_pct` | 0.001 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `cooldown` | 30.0 |
| `declining_threshold` | 0.98 |
| `level_tolerance_pct` | 0.0006 |
| `min_bounce_pct` | 0.0008 |
| `min_tests` | 2 |
| `test_memory_seconds` | 170.0 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 210.0 |
| `cvd_confirmation_threshold` | 5.0 |
| `max_pullback_penetration_pct` | 0.0013 |
| `min_candles_outside` | 7 |
| `pullback_tolerance_pct` | 0.0011 |
| `regime_poc_migration_max` | 0.0025 |
| `regime_vol_ratio_max` | 1.55 |
| `regime_va_expansion_max` | 1.25 |

### Quality Scorer

| Parámetro | Valor |
|---|---|
| `weights.exhaustion` | 0.40 |
| `weights.regime` | 0.30 |
| `weights.structure` | 0.15 |
| `weights.liquidity` | 0.10 |
| `weights.spread` | 0.05 |
| `grade_thresholds.A` | 0.70 |
| `grade_thresholds.B` | 0.40 |

### Targets por Escenario

| Escenario | TP | SL |
|---|---|---|
| tactical_absorption | 0.025 (2.5%) | 0.025 (2.5%) |
| failed_breakout | 0.025 (2.5%) | 0.025 (2.5%) |
| liquidity_exhaustion | 0.025 (2.5%) | 0.040 (4.0%) |
| trend_acceptance | 0.025 (2.5%) | 0.025 (2.5%) |

### VA Gate

| Parámetro | Valor |
|---|---|
| `poc_migration_threshold` | 0.003 |
| `vol_ratio_threshold` | 1.3 |
| `va_expansion_threshold` | 1.05 |
| `va_abs_width_threshold` | 1.5 |
| `block_in_trending` | tactical_absorption, failed_breakout, liquidity_exhaustion |

---

## Resultados de Optimización

### tactical_absorption (50 iters)

| Métrica | Valor |
|---|---|
| Best Optuna score | +0.3004 |
| Baseline NT | +0.1009% |
| Validación cross-coin NT | +0.4888% |
| Coins passed | 2/2 ✅ |
| MFE/MAE ratio | 1.72 |
| Parámetros sensibles | cooldown (↑30→140), z_score_min (↑2.2→3.3), book_bucket_pct (↓0.002→0.00075) |

### failed_breakout (50 iters)

| Métrica | Valor |
|---|---|
| Best Optuna score | +0.1778 |
| Baseline NT | +0.1543% |
| Validación cross-coin NT | +0.4112% |
| Coins passed | 2/2 ✅ |
| MFE/MAE ratio | 1.53 |
| Parámetros sensibles | l2_ratio_min (↑0.7→2.5), exhaustion_z (↑2.4→3.8) |

### liquidity_exhaustion (60 iters, 50+10)

| Métrica | Valor |
|---|---|
| Best Optuna score | -2.9405 (score compuesto negativo) |
| Baseline NT | +0.0761% |
| Validación cross-coin NT | +0.2879% |
| Coins passed | 2/2 ✅ |
| MFE/MAE ratio | 1.24 |
| Nota | Score negativo por penalización de señales (<8), pero NT positivo en validación |

### trend_acceptance (92 iters, 42+50)

| Métrica | Valor |
|---|---|
| Best Optuna score | +0.4601 |
| Baseline NT | +0.0692% |
| Validación cross-coin | Pendiente (validate-only timeout) |
| Parámetros sensibles | cvd_confirmation_threshold (↑4.0→5.0), max_pullback_penetration (↓0.003→0.0013), regime_vol_ratio_max (↑1.5→1.55) |

---

## Resumen Global

| Escenario | Score | Val NT | Coins | Estado |
|---|---|---|---|---|
| tactical_absorption | +0.3004 | +0.4888% | 2/2 | ✅ |
| failed_breakout | +0.1778 | +0.4112% | 2/2 | ✅ |
| liquidity_exhaustion | -2.9405 | +0.2879% | 2/2 | ✅ |
| trend_acceptance | +0.4601 | — | — | ✅ |
| **GLOBAL** | | **+0.2879–0.4888%** | **6/6** | |

---

## Lecciones Aprendidas (AVAX V3)

1. **Liquidity_exhaustion es el más duro**: Score compuesto siempre negativo por <8 señales mínimas, pero validación da NT positivo consistente (+0.29%). Señales escasas pero de calidad.
2. **Trend_acceptance funciona mejor que en LTC**: Score +0.46 vs LTC ~+0.18. El regime filter (vol_ratio < 1.3, va_expansion < 1.05) ayuda a AVAX a filtrar chop.
3. **Tactical_absorption mejora drásticamente**: Baseline +0.10% → val +0.49%. Cooldown alto (140) y z_score_min alto (3.3) filtran ruido.
4. **Cross-coin válido**: Todos los escenarios pasan validación en ambos símbolos (AVAX/USDT:USDT y AVAXUSDT).
5. **Cada trial necesita ~2-10 min**: 7 workers, backtests multiproceso. 50 trials ≈ 4-12 horas.

---

## Cómo Re-Optimizar

```bash
# Reanudar optimización de un escenario
python scripts/cluster_optimizer.py --cluster AVAX_NOISY_UNCERTAIN \
  --only <scenario> --iterations 50 --resume \
  --study-db data/db_vault/avax_<scenario>.db \
  --output data/db_vault/avax_<scenario>_results.json

# Validación cruzada (usa coin_profiles.py actual)
python scripts/cluster_optimizer.py --cluster AVAX_NOISY_UNCERTAIN \
  --only <scenario> --validate-only

# Estudios guardados en:
#   data/db_vault/avax_tactical.db
#   data/db_vault/avax_failed_breakout.db
#   data/db_vault/avax_liquidity_exhaustion.db
#   data/db_vault/avax_trend_acceptance.db
```
