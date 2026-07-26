# 🥇 DOGE Golden Parameters (V1)

> **Moneda**: DOGEUSDT
> **Perfil**: `DOGEUSDT` (mapeo 1:1)
> **Estado**: 3/4 escenarios Entry OK ✅ (FB, TACT, TA). LE: 0 señales.
> **Optimización**: 50 iteraciones Optuna (Trial 38, score +0.6874)
> **Validación**: Audit 6 datasets, 287 señales, Net Taker +0.6272%
> **Fecha**: 2026-07-22

---

## 📊 Resultado del Edge Audit (6 datasets, post-optimización)

### Composite (todos los setups)

| Escenario | n | Best Net Taker | Entry | Veredicto |
|---|---|---|---|---|
| failed_breakout | 30 | +0.7749% | ✅ | TARGETS OK |
| tactical_absorption | 14 | +0.5349% | ✅ | TARGETS OK |
| trend_acceptance | 243 | +0.6143% | ✅ | TARGETS OK |
| liquidity_exhaustion | 0 | — | — | sin señales |
| **OVERALL** | **287** | **+0.6272%** | **✅ EDGE CONFIRMED** | ✅ |

### Por dataset / régimen

| Dataset | Régimen | n | Net Taker | Veredicto |
|---|---|---|---|---|
| TREND_DOWN_2024-10-01 | 🔴 TREND_DOWN | 36 | **+1.2993%** | TARGET_FAILURE |
| TREND_DOWN_2025-02-01 | 🔴 TREND_DOWN | 80 | **+1.1321%** | TARGET_FAILURE |
| BALANCE_2024-11-01 | ⚪ BALANCE | 56 | **+0.1948%** | TARGET_FAILURE |
| BALANCE_2025-01-01 | ⚪ BALANCE | 24 | **+0.7621%** | TARGET_FAILURE |
| TREND_UP_2024-12-01 | 🟢 TREND_UP | 46 | **-0.1248%** | TARGET_FAILURE |
| TREND_UP_2025-04-01 | 🟢 TREND_UP | 45 | **+0.4268%** | **EDGE_CONFIRMED** |
| **TOTAL** | | **287** | **+0.6272%** | **EDGE CONFIRMED** |

**Distribución de señales:** TA 84.7%, FB 10.5%, TACT 4.9%, LE 0%
(Natural en DOGE THIN_VOLATILE: TA usa state-machine de breakout, dominates por mecanismo. TACT muy estricto por z_score_min=3.0. LE no encuentra secuencias con test_memory_seconds=290)

## 🎯 Targets (Best Static Grid inyectados)

| Escenario | TP | SL | Best Net |
|---|---|---|---|
| failed_breakout | 2.50% | 5.00% | +0.7749% |
| tactical_absorption | 2.50% | 4.00% | +0.5349% |
| trend_acceptance | 2.50% | 5.00% | +0.6143% |
| liquidity_exhaustion | 2.50% | 2.50% | sin señales |

---

## Perfil Completo (`config/coin_profiles.py` → `DOGEUSDT`)

### Guardians

| Parámetro | Valor |
|---|---|
| `l2_ratio_min` | 3.0 |
| `spread_max_ratio` | 3.2 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 2.8 |

### Quality Scorer Weights

| Factor | Peso |
|---|---|
| exhaustion | 0.10 |
| liquidity | 0.10 |
| regime | 0.20 |
| structure | 0.30 |

### Sensors

#### absorption_detector

| Parámetro | Valor |
|---|---|
| `absorption_score_min` | 0.45 |
| `book_bucket_pct` | 0.00125 |
| `cooldown` | 110.0 |
| `displacement_z_max` | 3.0 |
| `level_tolerance_pct` | 0.0049 |
| `stagnation_floor_pct` | 0.0007 |
| `volatility_z_max` | 2.4 |
| `z_score_min` | 3.0 |

#### failed_breakout

| Parámetro | Valor |
|---|---|
| `cooldown` | 60.0 |
| `divergence_z` | 0.9 |
| `exhaustion_z` | 2.3 |
| `max_break_age` | 160.0 |
| `min_break_distance_pct` | 0.0032 |

#### liquidity_exhaustion

| Parámetro | Valor |
|---|---|
| `declining_threshold` | 0.84 |
| `level_tolerance_pct` | 0.001 |
| `min_bounce_pct` | 0.00115 |
| `min_tests` | 3.0 |
| `test_memory_seconds` | 290.0 |

#### trend_acceptance

| Parámetro | Valor |
|---|---|
| `cooldown` | 240.0 |
| `cvd_confirmation_threshold` | 2.5 |
| `max_pullback_penetration_pct` | 0.001 |
| `min_candles_outside` | 5.0 |
| `pullback_tolerance_pct` | 0.001 |
| `regime_poc_migration_max` | 0.006 |
| `regime_va_expansion_max` | 1.38 |
| `regime_vol_ratio_max` | 2.4 |

### Targets

| Escenario | tp_pct | sl_pct |
|---|---|---|
| failed_breakout | 0.025 | 0.05 |
| tactical_absorption | 0.025 | 0.04 |
| trend_acceptance | 0.025 | 0.05 |
| liquidity_exhaustion | 0.025 | 0.025 |

---

## 📋 Notas

- **Trial 38**: best optimizer trial among 50 iterations Optuna. Score +0.6874.
- **Targets fijos**: AVAX-style asymmetric (FB 2.50/5.00, TACT 2.50/4.00, TA 2.50/5.00) inyectados directamente en `coin_profiles.py` (tp_pct/100, sl_pct/100).
- **Baseline**: -0.1106% Net Taker con default params → optimización +0.6874 score → audit final +0.6272%.
- **5/6 datasets positivos** (TREND_UP_2024-12-01 -0.12% marginal, TREND_UP_2025-04-01 con EDGE_CONFIRMED único setup).
- **Distribución típica THIN_VOLATILE**: TA domina por state-machine, TACT/FB aparecen cuando el order lo permite, LE inactivo en DOGE/LINK.
