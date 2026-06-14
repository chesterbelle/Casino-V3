# 🥇 LTC Golden Parameters

> **Moneda**: LTC/USDT:USDT
> **Cluster**: `LTC_NOISY_UNCERTAIN_1`
> **Estado**: FB+LE+TAV+TA edge confirmed ✅ — todos los escenarios positivos
> **Net Taker (12 datasets)**: +0.2646%
> **Gross Expectancy**: +0.3346%
> **Señales**: 1982
> **Root Cause**: TARGET_FAILURE (LE targets AMT 2.5/4.0 vs best uniform 1.0/2.0)
> **Origen**: CVD flip fix en `liquidity_exhaustion.py` — confirmación de defensa en vez de filtro de ataque
> **Fecha**: 2026-06-14

---

## Perfil Completo (`config/coin_profiles.py` → `LTC_NOISY_UNCERTAIN_1`)

### Sensors

#### absorption_detector
| Parámetro | Valor | Nota |
|---|---|---|
| `z_score_min` | 4.0 | Filtro estricto — LTC necesita absorción fuerte |
| `absorption_score_min` | 0.2 | Permisivo en calidad de absorción |
| `stagnation_floor_pct` | 0.0018 | Ajustado fino para LTC |
| `cooldown` | 60.0s | Respuesta rápida |
| `volatility_z_max` | 3.1 | Tolerante a volatilidad |
| `displacement_z_max` | 2.9 | |
| `level_tolerance_pct` | 0.002 | |
| `book_bucket_pct` | 0.001 | |

#### failed_breakout
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 50.0s | |
| `min_break_distance_pct` | 0.0047 | Filtra micro-breaks |
| `max_break_age` | 150.0s | |
| `divergence_z` | 1.0 | |
| `exhaustion_z` | 2.9 | |

#### liquidity_exhaustion
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 30.0s | |
| `level_tolerance_pct` | 0.0005 | |
| `min_tests` | 3 | Significancia de nivel |
| `declining_threshold` | 0.80 | Declive moderado — 80% de tests deben mostrar volumen declinante |
| `min_bounce_pct` | 0.00075 (7.5 bps) | Rebote mínimo para confirmar nivel |
| `test_memory_seconds` | 300.0s | 5 min para encontrar tests incluso en regímenes lentos |

#### trend_acceptance
| Parámetro | Valor | Nota |
|---|---|---|
| `cooldown` | 600.0s | |
| `min_candles_outside` | 3 | |
| `cvd_confirmation_threshold` | 4.0 | |
| `pullback_tolerance_pct` | 0.001 (10 bps) | |
| `max_pullback_penetration_pct` | 0.001 (10 bps) | |

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
| `z_block` | 2.8 |

### Targets por Escenario

| Escenario | TP | SL | Nota |
|---|---|---|---|
| tactical_absorption (TAV) | 0.025 (2.5%) | 0.040 (4.0%) | Edge consistente ratio 1.37 |
| failed_breakout | 0.025 (2.5%) | 0.040 (4.0%) | Edge fuerte ratio 4.59 |
| liquidity_exhaustion | **0.010 (1.0%)** | **0.020 (2.0%)** | Best uniform: TP 1.0/SL 2.0, WR 73.7% |
| trend_acceptance | 0.009 (0.9%) | 0.009 (0.9%) | Edge débil ratio 1.13 pero positivo |

### Guardians

| Parámetro | Valor | Nota |
|---|---|---|
| `l2_ratio_min` | 0.5 | Permisivo — LTC no necesita filtro L2 fuerte |
| `l2_ratio_min_trend_down` | 2.2 | Bear market |
| `l2_ratio_min_trend_acceptance` | 1.5 | Hard block para TA |
| `spread_max_ratio` | 2.5 | Tolerante |

---

## Cambio Estructural: CVD Flip Fix

### Problema Original
El filtro CVD bloqueaba tests en VAL cuando CVD > 0 (compradores activos). Esto impedía registrar el patrón completo de agotamiento:

```
Test 1: CVD = -20 (vendedores atacan) → registrado ✅
Test 2: CVD =  -5 (vendedores se agotan) → registrado ✅
Test 3: CVD = +10 (compradores defienden) → BLOQUEADO ❌
```

El test 3 se bloqueaba porque CVD >= 0 en VAL, pero justamente cuando CVD se vuelve positiva es la CONFIRMACIÓN de que la defensa ganó.

### Fix (`decision/scenarios/liquidity_exhaustion.py`)
- **Eliminado** el filtro CVD del registro de tests (líneas 138-142): ahora se registran TODOS los toques al nivel
- **Agregado** filtro CVD al momento de disparar la señal: requiere CVD en dirección de la defensa
  - VAL (LONG): `raw_cvd_velocity > 0` → compradores defendiendo
  - VAH (SHORT): `raw_cvd_velocity < 0` → vendedores defendiendo

### Resultado
| Métrica | Antes (filtro ataque) | Después (confirmación defensa) |
|---|---|---|
| LE señales | 16 | 19 |
| MFE/MAE Ratio | 0.50 | 0.71 |
| Best Uniform | 0.10/0.10% → Net -0.08% ❌ | **1.00/2.00% → Net +0.17% ✅** |
| Entry OK? | ❌ ENTRY FAILURE | ✅ ENTRY OK |

---

## Diagnóstico por Escenario (12 datasets)

| Escenario | n | Ratio | Best Net | Veredicto |
|---|---|---|---|---|
| failed_breakout | 17 | 4.59 | +1.36% | ✅ TARGETS OK |
| liquidity_exhaustion | 19 | 0.71 | +0.17% | ✅ TARGET OPTIMIZATION (1.0/2.0) |
| tactical_absorption | 1907 | 1.37 | +0.26% | ✅ TARGETS OK |
| trend_acceptance | 39 | 1.13 | +0.22% | ✅ TARGETS OK |
| **TOTAL** | **1982** | — | **+0.26%** | **✅** |

---

## Lecciones Aprendidas (LTC DNA)

1. **LE funciona con CVD flip fix**: La clave no es filtrar por "atacantes agotándose" sino esperar a que la defensa confirme. Registrar todos los tests permite capturar el patrón completo de agotamiento → defensa.
2. **LE targets deben ser conservadores**: TP 1.0%/SL 2.0% (vs 2.5/4.0 para FB/TAV). LE tiene menos convicción direccional.
3. **FB domina en ratio direccional**: Ratio 4.59 — señales escasas (17) pero extremadamente direccionales.
4. **TA tiene edge frágil**: Ratio 1.13 (justo bajo 1.2) pero sigue siendo positivo. Usar TP/SL apretados (0.9/0.9).
5. **L2 gate casi irrelevante para TAV**: `l2_ratio_min=0.5` indica que LTC no necesita filtro L2 fuerte.

---

## Cómo Usar Este Golden Parameter

```bash
# Ver diagnóstico de edge
python utils/setup_edge_auditor.py --window 21600 --coin LTC/USDT:USDT

# Ejecutar backtest completo (cluster LTC)
timeout 14400000 python scripts/orchestrator.py --protocol cluster_ltc_noisy_uncertain_1

# Respaldo DB golden
cp data/historian.db data/db_vault/ltc-goldstandard.db
```
