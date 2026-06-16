# 🥇 AVAX Golden Parameters

> **Moneda**: AVAX/USDT:USDT
> **Cluster original**: AVAX_BEHAVIOR
> **Estado**: 3/4 escenarios con Entry + Targets (T_ACC sin edge direccional en AVAX)
> **Net Taker global**: +0.3823% (iter 5 — solo FB/LE/TA activas)
> **Net actual (iter 10)**: -0.2372% (T_ACC domina 96% de señales sin edge)
> **Backtest DB**: `data/avax-goldstandard.db`
> **Fecha**: 2026-06-11

---

## Perfil Completo (`config/coin_profiles.py` → `AVAX_BEHAVIOR`)

### Sensors

#### absorption_detector
| Parámetro | Valor | Nota |
|---|---|---|
| `z_score_min` | 5.4 | Filtro de absorción estricto |
| `stagnation_floor_pct` | 0.0008 | Fijado desde 0.08 (roto) en iter 6 |
| `cooldown` | 130.0s | Enfriamiento entre señales |
| `volatility_z_max` | 2.5 | Volatilidad máxima permitida |
| `displacement_z_max` | 3.0 | Desplazamiento máximo |

#### failed_breakout
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 60.0s | |
| `min_break_distance_pct` | 0.002 | Distancia mínima de breakout |
| `max_break_age` | 60.0s | Edad máxima del breakout |
| `cvd_divergence_threshold` | 0.40 | Divergencia CVD |

#### liquidity_exhaustion
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 30.0s | |
| `level_tolerance_pct` | 0.0005 | |
| `min_tests` | 4 | Tests mínimos de nivel |
| `declining_threshold` | 0.80 | |
| `min_bounce_pct` | 0.002 | ↑ desde default |
| `test_memory_seconds` | 120.0s | |

#### trend_acceptance
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 600.0s | |
| `min_candles_outside` | 5 | Velas fuera del rango |
| `cvd_confirmation_threshold` | 4.0 | Confirmación CVD |
| `pullback_tolerance_pct` | 0.001 (10 bps) | |
| `max_pullback_penetration_pct` | 0.003 (30 bps) | |

### Quality Scorer

| Parámetro | Valor |
|---|---|
| `weights.exhaustion` | **0.10** (↓ desde 0.40 en iter 10) |
| `weights.regime` | **0.45** (↑ desde 0.30 en iter 10) |
| `weights.structure` | **0.30** (↑ desde 0.15 en iter 10) |
| `weights.liquidity` | 0.10 |
| `weights.spread` | 0.05 |
| `grade_thresholds.A` | 0.70 |
| `grade_thresholds.B` | **0.55** (↑ desde 0.40 en iter 10) |
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
| tactical_absorption | 0.025 (2.5%) | 0.040 (4.0%) |
| failed_breakout | 0.020 (2.0%) | 0.040 (4.0%) |
| liquidity_exhaustion | 0.020 (2.0%) | 0.030 (3.0%) |
| trend_acceptance | 0.025 (2.5%) | 0.050 (5.0%) |

### Guardians

| Parámetro | Valor | Nota |
|---|---|---|
| `l2_ratio_min` | 0.8 | General (AVAX book delgado) |
| `l2_ratio_min_trend_down` | 2.2 | Bear market |
| `l2_ratio_min_trend_acceptance` | 1.5 | Hard block para TA |
| `spread_max_ratio` | 2.0 | |

---

## Historial de Sintonía (10 iteraciones)

Ver `.agent/perfil_changelog.md` → sección `AVAX_BEHAVIOR` para el detalle causal completo.

### Hitos

| Iter | Logro | Cambio clave |
|---|---|---|
| 1 | Baseline 3/4 (T_ACC entry failure) | Pre-tuned con SOL learnings |
| 2 | FB/LE Entry ✅ | Tightened entry sensors |
| 3 | FB/LE Targets OK | Fixed FB/LE targets |
| 4 | T_ACC ratio 1.02 (mejor ratio histórico) | Extreme tighten z=4, conc=0.95, noise=0.15 |
| 5 | FB+LE+TA 4/4, T_ACC 0 señales | L2 gate `l2_ratio_min_tactical_absorption: 1.0` |
| 6 | T_ACC 1180 señales pero ratio 0.97 | stagnation_floor_pct fijo 0.08→0.0008 |
| 7-9 | Tight medio, T_ACC 0-1422 señales | Variación de abs_score_min cooldown |
| **10** | **Quality reweight** | exhaustion 0.40→0.10, regime 0.30→0.45 |

### Diagnóstico Final (Iter 10)

| Escenario | Señales | MFE/MAE | Entry | Targets | Net Taker |
|---|---|---|---|---|---|
| tactical_absorption | 1451 | 0.98 | ❌ | ❌ | -0.2605% |
| failed_breakout | 28 | 0.93 | ✅ | ✅ | +0.3974% |
| liquidity_exhaustion | 18 | 1.11 | ✅ | ✅ | +0.0110% |
| trend_acceptance | 12 | 1.19 | ✅ | ✅ | +0.7237% |
| **GLOBAL** | **1509** | | | | **-0.2372%** |

---

## Lecciones Aprendidas (AVAX DNA)

1. **T_ACC no funciona en AVAX**: El microstructura de book delgado no soporta absorción como predictor direccional. Ratio consistentemente 0.97-1.02 en 10 iteraciones.
2. **L2 gate no ayuda**: Thin Wall ratio 1.00, High Wall 0.78 — al revés que SOL. La absorción en AVAX no correlaciona con profundidad L2.
3. **FB/LE/TA funcionan**: Con parámetros derivados de SOL, los 3 escenarios tienen edge positivo consistente.
4. **`stagnation_floor_pct` estaba roto**: Valor 0.08 (8%) en perfiles legacy — nunca detectaba estancamiento. Fijado a 0.0008 (pressure engine default).
5. **Quality reweight ayuda a LE/TA**: exhaustion 0.40→0.10, regime 0.45, structure 0.30 — mejora LE de 0.0836%→0.0110%.

---

## Cómo Usar Este Golden Parameter

```bash
# Respaldo de resultados de backtest
cp data/avax-goldstandard.db data/historian.db

# Ver diagnóstico
python utils/setup_edge_auditor.py --window 21600 --coin AVAX/USDT:USDT

# Ejecutar backtest completo
timeout 14400000 python scripts/orchestrator.py --protocol cluster_avax_behavior
```
