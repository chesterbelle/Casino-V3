# 🥇 SOL Golden Parameters

> **Moneda**: SOL/USDT:USDT
> **Cluster original**: SOL_BEHAVIOR
> **Estado**: ✅ 4/4 escenarios con Entry + Targets
> **Net Taker global**: +0.1832%
> **Backtest DB**: `data/sol-goldstandard.db`
> **Fecha**: 2026-06-10

---

## Perfil Completo (`config/coin_profiles.py` → `SOL_BEHAVIOR`)

### Sensors

#### absorption_detector
| Parámetro | Valor | Nota |
|---|---|---|
| `z_score_min` | 2.0 | Filtro de absorción |
| `stagnation_floor_pct` | 0.10 | Piso de estancamiento |
| `cooldown` | 120.0s | Enfriamiento entre señales |
| `volatility_z_max` | 2.5 | Volatilidad máxima permitida |
| `displacement_z_max` | 3.0 | Desplazamiento máximo |
| `level_tolerance_pct` | 0.003 | Tolerancia de nivel |

#### failed_breakout
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 60.0s | |
| `min_break_distance_pct` | 0.0001 | Distancia mínima de breakout |
| `max_break_age` | 60.0s | Edad máxima del breakout |
| `cvd_divergence_threshold` | 0.30 | Divergencia CVD |

#### liquidity_exhaustion
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 30.0s | |
| `level_tolerance_pct` | 0.0005 | |
| `min_tests` | 3 | Tests mínimos de nivel |
| `declining_threshold` | 0.72 | |
| `min_bounce_pct` | 0.0007 | ↑ desde 0.0005 en iter 2 |
| `test_memory_seconds` | 100.0s | |

#### trend_acceptance
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 600.0s | |
| `min_candles_outside` | 5 | Velas fuera del rango |
| `cvd_confirmation_threshold` | 4.0 | Confirmación CVD (↓ desde 6.0 en iter 6) |
| `pullback_tolerance_pct` | 0.0008 (8 bps) | Entrada cerca de VAH (iter 6→8→9) |
| `max_pullback_penetration_pct` | 0.0025 (25 bps) | Breakout distance >> pullback (clave en iter 6) |

### Quality Scorer

| Parámetro | Valor |
|---|---|
| `weights.exhaustion` | 0.40 |
| `weights.regime` | 0.28 |
| `weights.structure` | 0.12 |
| `weights.liquidity` | 0.12 |
| `weights.spread` | 0.08 |
| `grade_thresholds.A` | 0.70 |
| `grade_thresholds.B` | 0.45 |
| `thresholds.exhaustion.block` | 1.5 |
| `thresholds.exhaustion.perfect` | 0.5 |
| `thresholds.exhaustion.vol_bonus` | 0.4 |
| `thresholds.liquidity.strong` | 2.0 |
| `thresholds.liquidity.adequate` | 1.5 |
| `thresholds.liquidity.weak` | 1.0 |
| `thresholds.structure.excess_multiplier` | 0.5 |

### Pressure Thresholds

| Parámetro | Valor |
|---|---|
| `z_block` | 2.0 |

### Targets por Escenario

| Escenario | TP | SL |
|---|---|---|
| tactical_absorption | 0.025 (2.5%) | 0.050 (5.0%) |
| failed_breakout | 0.010 (1.0%) | 0.010 (1.0%) |
| liquidity_exhaustion | 0.025 (2.5%) | 0.050 (5.0%) |
| trend_acceptance | 0.025 (2.5%) | 0.040 (4.0%) |

### Guardians

| Parámetro | Valor | Nota |
|---|---|---|
| `l2_ratio_min` | 1.5 | General |
| `l2_ratio_min_trend_down` | 2.0 | Bear market |
| `l2_ratio_min_trend_acceptance` | **2.0** | Hard block para TA (iter 9 — clave) |
| `spread_max_ratio` | 1.8 | |

---

## Historial de Sintonía (9 iteraciones)

Ver `.agent/perfil_changelog.md` → sección `SOL_BEHAVIOR` para el detalle causal completo.

### Hitos

| Iter | Logro | Cambio clave |
|---|---|---|
| 1 | D1 fix — recovery de señales | Classification resolution bug |
| 2 | LE recupera señales | `min_bounce_pct` 0.001→0.003 |
| 3 | T_ACC 0→1862 señales | `noise_max` 0.30→0.40 |
| 4 | TA empieza a generar | Filtros de absorción más estrictos |
| 5-8 | Ciclo de ajuste TA | Breakout >> pullback descubierto como clave |
| **9** | **TA 2.41 MFE/MAE, 100% TP** | `l2_ratio_min_trend_acceptance: 2.0` + hard block |

### Diagnóstico Final (Iter 9)

| Escenario | Señales | MFE/MAE | Entry | Targets | Net Taker |
|---|---|---|---|---|---|
| tactical_absorption | 1862 | 1.12 | ✅ | ✅ | +0.1465% |
| failed_breakout | 338 | 1.24 | ✅ | ✅ | +0.2429% |
| liquidity_exhaustion | 402 | 1.32 | ✅ | ✅ | +0.2966% |
| trend_acceptance | 3 | 2.41 | ✅ | ✅ | +1.0245% |
| **GLOBAL** | **2605** | | | | **+0.1832%** |

---

## Lecciones Aprendidas (SOL DNA)

1. **SOL necesita L2 High Wall para TA**: L2 ratio ≥2.0 bloquea señales falsas en Thin Wall. Las 3 señales que pasaron el filtro alcanzaron TP.
2. **Breakout >> Pullback es ley**: `max_pullback_penetration_pct` debe ser 2-3× `pullback_tolerance_pct` para filtrar micro-velas. SOL: 25 bps breakout vs 8 bps pullback.
3. **TA no es estructural para SOL**: El diagnóstico inicial de "estructura" era erróneo — era falta de hard filter L2 + breakout insuficiente.
4. **`noise_max=0.40`** vs 0.30 de perfiles thin: SOL es líquido y ruidoso; filtros más estrictos matan señales.

---

## Cómo Usar Este Golden Parameter

```bash
# Respaldo de resultados de backtest
cp data/sol-goldstandard.db data/historian.db

# Ver diagnóstico
python utils/setup_edge_auditor.py --window 21600 --coin SOL/USDT:USDT

# Ejecutar backtest completo
timeout 14400000 python scripts/orchestrator.py --protocol cluster_sol_behavior
```
