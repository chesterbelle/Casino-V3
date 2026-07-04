# 🥇 LTC Golden Parameters V3 (Post-Regime Filter + SBR)

> **Moneda**: LTC/USDT:USDT
> **Cluster**: `LTC_NOISY_UNCERTAIN_1`
> **Estado**: FB + LE + TAV + TA edge confirmed ✅ — **Todos los escenarios optimizados y positivos + Regime Filter interno**
> **Fecha**: 2026-07-04
> **Tipo de Arquitectura**: Parámetros Aislados (Sufijos) + Regime Filter Interno + SBR
> **Validación**: Single-Coin Edge Audit Protocol (Zero-Interference) + 6 Daily Datasets + Monthly May 2026

---

## Resultados Oficiales del Edge Audit (Zero-Interference)

La prueba pura de MFE/MAE de la estrategia demostró que **los 4 escenarios poseen ventaja estadística explotable (Edge) con Net Taker positivo**, validando la optimización en cascada + regime filter + SBR.

| Escenario | Señales (n) | Mejor Grid (TP/SL) | Expectativa Bruta | Net Taker | Veredicto Entry |
|---|---|---|---|---|---|
| **failed_breakout** | 8 | 0.50% / 0.80% | +0.3375% | **+0.2675%** | ✅ EDGE CONFIRMADO |
| **liquidity_exhaustion** | 13 | 1.20% / 0.30% | +0.3923% | **+0.3223%** | ✅ EDGE CONFIRMADO |
| **tactical_absorption** | 29 | 1.20% / 0.30% | +0.1655% | **+0.0955%** | ✅ EDGE CONFIRMADO |
| **trend_acceptance** | 29 | 0.90% / 0.90% | +0.3975% | **+0.3275%** | ✅ EDGE CONFIRMADO |

> **Overall**: Net Taker **+0.2354%** (Taker 0.07%), Gross Expectancy **+0.3054%**

---

## Perfil Completo y Aislado (`config/coin_profiles.py` → `LTC_NOISY_UNCERTAIN_1`)

Bajo la nueva arquitectura, los parámetros globales ahora tienen sobreescrituras específicas (sufijos) por escenario, evitando la contaminación cruzada.

### 1. Parámetros Globales Base

- **Guardians Base:** `l2_ratio_min = 0.5`, `spread_max_ratio = 2.5`
- **Pressure Base:** `z_block = 2.8`
- **VA Gate:** `integrity_threshold = 0.15`
  - *Bloqueados en Tendencia:* `tactical_absorption`, `failed_breakout`, `liquidity_exhaustion`
  - *Permitidos en Tendencia:* `trend_acceptance`

---

### 2. Parámetros Específicos por Escenario

#### 🛡️ tactical_absorption
| Módulo | Parámetro | Valor |
|---|---|---|
| **Sensors** | `z_score_min` | 2.2 |
| **Sensors** | `absorption_score_min` | 0.225 |
| **Sensors** | `displacement_z_max` | 1.7 |
| **Sensors** | `stagnation_floor_pct` | 0.0009 |
| **Sensors** | `cooldown` | 30.0s |
| **Sensors** | `book_bucket_pct` | 0.002 |
| **Sensors** | `level_tolerance_pct` | 0.0033 |
| **Sensors** | `volatility_z_max` | 2.6 |
| **Guardians** | `l2_ratio_min_tactical_absorption` | 0.6 |
| **Guardians** | `spread_max_ratio_tactical_absorption`| 1.7 |
| **Pressure** | `z_block_tactical_absorption` | 2.4 |

#### 📉 failed_breakout
| Módulo | Parámetro | Valor |
|---|---|---|
| **Sensors** | `exhaustion_z` | 2.4 |
| **Sensors** | `divergence_z` | 0.8 |
| **Sensors** | `min_break_distance_pct` | 0.0022 |
| **Sensors** | `max_break_age` | 150.0s |
| **Sensors** | `cooldown` | 30.0s |
| **Guardians** | `l2_ratio_min_failed_breakout` | 0.7 |
| **Guardians** | `spread_max_ratio_failed_breakout` | 2.2 |
| **Pressure** | `z_block_failed_breakout` | 2.4 |

#### 💧 liquidity_exhaustion
| Módulo | Parámetro | Valor |
|---|---|---|
| **Sensors** | `min_tests` | 2 |
| **Sensors** | `declining_threshold` | 0.50 |
| **Sensors** | `min_bounce_pct` | 0.0007 |
| **Sensors** | `test_memory_seconds` | 220.0s |
| **Sensors** | `cooldown` | 30.0s |
| **Sensors** | `level_tolerance_pct` | 0.0009 |
| **Guardians** | `l2_ratio_min_liquidity_exhaustion` | 0.6 |
| **Guardians** | `spread_max_ratio_liquidity_exhaustion`| 3.1 |
| **Pressure** | `z_block_liquidity_exhaustion` | 2.4 |

#### 🌊 trend_acceptance (con Regime Filter Interno)
| Módulo | Parámetro | Valor |
|---|---|---|
| **Sensors** | `cvd_confirmation_threshold` | 4.0 |
| **Sensors** | `min_candles_outside` | 7 |
| **Sensors** | `pullback_tolerance_pct` | 0.0012 |
| **Sensors** | `max_pullback_penetration_pct` | 0.003 |
| **Sensors** | `cooldown` | 240.0s |
| **Regime Filter** | `regime_poc_migration_max` | **0.005** |
| **Regime Filter** | `regime_vol_ratio_max` | **1.5** |
| **Regime Filter** | `regime_va_expansion_max` | **1.1** |
| **Guardians** | `l2_ratio_min_trend_acceptance` | 1.2 |
| **Guardians** | `spread_max_ratio_trend_acceptance` | 2.1 |
| **Pressure** | `z_block_trend_acceptance` | 2.7 |

---

### 3. Regime Filter Logic (Interno en TrendAcceptanceDetector)

```python
def _is_regime_favorable(self, symbol: str) -> bool:
    # 1. HARD BLOCK: vol_ratio > 1.5 → chop/expansion
    # 2. POC Migration: solo bloquea si ALTA migration Y alta vol (chop)
    #    Permite alta POC migration si vol_ratio < 1.3 (trend limpio)
    # 3. VA Expansion: solo bloquea si RÁPIDA expansión Y alta vol
    #    Permite VA expansion si vol_ratio < 1.3 (trend limpio)
    # NOTA: NO bloquea por va_integrity baja (esperado en trends)
```

---

## 📈 Quality Scorer (Configuración Actualizada)

| Componente | Valor |
|---|---|
| **Pesos (`weights`)** | `exhaustion: 0.40`, `regime: 0.30`, `structure: 0.15`, `liquidity: 0.10`, `spread: 0.05` |
| **Grados** | `A: 0.7`, `B: 0.4` |
| **Thresholds Exhaustion** | `block: 1.5`, `perfect: 0.5`, `vol_bonus: 0.4` |
| **Thresholds Liquidity** | `strong: 2.0`, `adequate: 1.5`, `weak: 1.0` |

---

## 📚 Lecciones Aprendidas de Arquitectura V3 (LTC DNA)

1. **Aislamiento Funcional (Sufijos):** LTC demostró que obligar a todos los setups a compartir un solo `l2_ratio_min` era un error fatal. Mientras que `trend_acceptance` necesita alta confirmación del libro (1.2), `liquidity_exhaustion` y `tactical_absorption` pueden operar con filtros más relajados (0.6).

2. **CVD Confirmation (Trend Acceptance):** Se mantuvo alto en `4.0`, demostrando que para seguir la tendencia, LTC requiere explosiones direccionales genuinas en CVD.

3. **Paciencia en Tendencia:** `min_candles_outside` subió a 7, obligando al sistema a confirmar la verdadera aceptación del precio fuera del área de valor antes de unirse al movimiento, lo que ayudó a que el escenario arrojara un **Net Taker de +0.3275%**.

4. **Regime Filter (NUEVO):
5. **Regime Awareness Interno:** El regime filter interno en TrendAcceptanceDetector permite que TA dispare en trends limpios (vol_ratio < 1.3) y lo bloquea en chop (vol_ratio > 1.5), sin bloquear por POC migration ni VA expansion durante trends direccionales limpios. Esto solucionó el **ENTRY FAILURE** estructural de TA en monthly.

6. **SBR (Session Boundary Reset):** Reset diario de estado (CVD, z-scores, MarketProfile, detectores) a medianoche UTC garantiza paridad backtest↔live y elimina contaminación estado entre días.

7. **Targets Conservadores pero Precisos:** La precisión de la entrada es altísima, pero el protocolo purista confirmó que los rebotes no siempre son extensos. El uso de Stop-Loss apretados (0.3% - 0.9%) y Take-Profits asimétricos son la clave de la rentabilidad pasiva de LTC.

---

## 💾 Respaldo y Reproducción

- Base de Datos Purista Certificada: `data/db_vault/ltc-goldstandard.db`
- Perfil Generador: `coin_profiles_LTC_NOISY_UNCERTAIN_1_optimized.py`
- Study DB Regime Filter: `data/db_vault/ltc_ta_regime.db`
- Study DB Daily: `data/db_vault/ltc_ta_regime_daily.db`

---

## 📊 Validación Cross-Regime

| Dataset | Net Taker | TA WR | Notas |
|---|---|---|---|
| **6 Daily (2023-2025)** | **+0.2354%** | **69%** | Edge confirmado todos los setups |
| **Monthly May 2026** | **+0.09%** | — | Regime filter bloquea chop (días 11-17), permite clean trends |

SBR + Regime Filter = **Producción-ready para monthly**.
