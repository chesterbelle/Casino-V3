# 🥇 LTC Golden Parameters V2 (Post-Cascade Optimization)

> **Moneda**: LTC/USDT:USDT
> **Cluster**: `LTC_NOISY_UNCERTAIN_1`
> **Estado**: FB + LE + TAV + TA edge confirmed ✅ — **Todos los escenarios optimizados y positivos**
> **Fecha**: 2026-06-30
> **Tipo de Arquitectura**: Parámetros Aislados (Sufijos)
> **Validación**: Single-Coin Edge Audit Protocol (Zero-Interference)

---

## Resultados Oficiales del Edge Audit (Zero-Interference)

La prueba pura de MFE/MAE de la estrategia demostró que **los 4 escenarios poseen ventaja estadística explotable (Edge) con Net Taker positivo**, validando la optimización en cascada.

| Escenario | Señales (n) | Mejor Grid (TP/SL) | Expectativa Bruta | Net Taker | Veredicto Entry |
|---|---|---|---|---|---|
| **failed_breakout** | 8 | 0.50% / 0.80% | +0.3375% | **+0.2675%** | ✅ EDGE CONFIRMADO |
| **liquidity_exhaustion** | 200 | 1.20% / 0.30% | +0.1479% | **+0.0779%** | ✅ EDGE CONFIRMADO |
| **tactical_absorption** | 35 | 1.20% / 0.30% | +0.1714% | **+0.1014%** | ✅ EDGE CONFIRMADO |
| **trend_acceptance** | 32 | 0.90% / 0.90% | +0.3884% | **+0.3184%** | ✅ EDGE CONFIRMADO |

> *Nota: Los "AMT Targets" mostraron ser inferiores a estos Static Grids en el test purista, lo que sugiere que usar Limit Sniper o afinar la fórmula dinámica es el paso a seguir, pero las entradas son de altísima precisión.*

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
| **Guardians** | `l2_ratio_min_liquidity_exhaustion` | 0.6 |
| **Guardians** | `spread_max_ratio_liquidity_exhaustion`| 3.1 |
| **Pressure** | `z_block_liquidity_exhaustion` | 2.4 |

#### 🌊 trend_acceptance
| Módulo | Parámetro | Valor |
|---|---|---|
| **Sensors** | `cvd_confirmation_threshold` | 4.0 |
| **Sensors** | `min_candles_outside` | 7 |
| **Sensors** | `pullback_tolerance_pct` | 0.0012 |
| **Sensors** | `max_pullback_penetration_pct` | 0.003 |
| **Sensors** | `cooldown` | 240.0s |
| **Guardians** | `l2_ratio_min_trend_acceptance` | 1.2 |
| **Guardians** | `spread_max_ratio_trend_acceptance` | 2.1 |
| **Pressure** | `z_block_trend_acceptance` | 2.7 |

---

## 📈 Quality Scorer (Configuración Actualizada)

| Componente | Valor |
|---|---|
| **Pesos (`weights`)** | `exhaustion: 0.40`, `regime: 0.30`, `structure: 0.15`, `liquidity: 0.10`, `spread: 0.05` |
| **Grados** | `A: 0.7`, `B: 0.4` |
| **Thresholds Exhaustion** | `block: 1.5`, `perfect: 0.5`, `vol_bonus: 0.4` |
| **Thresholds Liquidity** | `strong: 2.0`, `adequate: 1.5`, `weak: 1.0` |

---

## 📚 Lecciones Aprendidas de Arquitectura V2 (LTC DNA)

1. **Aislamiento Funcional (Sufijos):** LTC demostró que obligar a todos los setups a compartir un solo `l2_ratio_min` era un error fatal. Mientras que `trend_acceptance` necesita alta confirmación del libro (1.2), `liquidity_exhaustion` y `tactical_absorption` pueden operar con filtros más relajados (0.6).
2. **CVD Confirmation (Trend Acceptance):** Se mantuvo alto en `4.0`, demostrando que para seguir la tendencia, LTC requiere explosiones direccionales genuinas en CVD.
3. **Paciencia en Tendencia:** `min_candles_outside` subió a 7, obligando al sistema a confirmar la verdadera aceptación del precio fuera del área de valor antes de unirse al movimiento, lo que ayudó a que el escenario arrojara un **Net Taker de +0.3184%**.
4. **Targets Conservadores pero Precisos:** La precisión de la entrada es altísima, pero el protocolo purista confirmó que los rebotes no siempre son extensos. El uso de Stop-Loss apretados (0.3% - 0.9%) y Take-Profits asimétricos son la clave de la rentabilidad pasiva de LTC.

---

## 💾 Respaldo y Reproducción

- Base de Datos Purista Certificada: `data/db_vault/ltc-goldstandard.db`
- Perfil Generador: `coin_profiles_LTC_NOISY_UNCERTAIN_1_optimized.py`
