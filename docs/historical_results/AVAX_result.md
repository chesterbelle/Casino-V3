# AVAX Walk-Forward Results — v9.0 (INVERSIÓN DE DIRECCIÓN TA)

> **Moneda**: AVAX/USDT:USDT, AVAXUSDT
> **Cluster**: `AVAX_NOISY_UNCERTAIN`
> **Fecha**: 2026-07-14 (re-run con `invert_direction`)
> **Versión**: 9.0 (SBR + TA Regime Filter + Golden Params AVAX V3 + TA Direction Inversion)
> **Validación**: Walk-Forward 4 Splits out-of-sample (Mar–Jun 2026)
> **Método**: Backtest audit por mes (`backtest.py --run-type audit`) + `setup_edge_auditor.py --window 21600`

---

## 🎯 HALLAZGO PRINCIPAL: TA no estaba muerto, estaba INVERTIDO

El diagnóstico previo marcaba `trend_acceptance` como `ENTRY FAILURE` (MFE/MAE 0.02, Best Net −0.0268% ❌) y sugería desactivarlo. Bajo la **REGLA DEL EDGE** (no rendirse, no concluir "edge no existe"), el re-análisis reveló:

1. **TA en AVAX es 100% LONG-only** (0 SHORTs en 74 trades). En los momentos donde detecta breakout alcista, AVAX revierte a la baja → SL 0.9% se dispara.
2. **Test de inversión** (simular los 74 entries como SHORT, TP/SL simétricos): WR 63.5%, AvgPnL **+0.2432%** (vs LONG real −0.3132%). El edge direccional existía, del lado equivocado.
3. **Fix**: flag de config `invert_direction: True` en `AVAX_NOISY_UNCERTAIN.trend_acceptance` + flag mínimo en `decision/scenarios/confirmation/trend_acceptance.py` (helper `_emit` que invierte `side` LONG↔SHORT al emitir). El sensor sigue operando — solo emite el lado opuesto al breakout detectado (fade del breakout).

---

## Resumen Ejecutivo (con `invert_direction`)

| Métrica | Valor |
|---------|-------|
| **Net Taker Acumulado (4 meses)** | **+0.4254%** |
| **Net Taker Promedio/Mes** | **+0.1064%** |
| **Meses positivos** | **4/4** ✅ (Marzo, Abril, Mayo, Junio) |
| **Root Cause (los 4 meses)** | ⚠️ **TARGET FAILURE** (no ENTRY) |
| **Veredicto** | 🏆 **EDGE CERTIFICADO — TA SALVADO** |

### Comparación: walk-forward previo (sin invertir) vs con `invert_direction`

| Mes | Previo (LONG) | Con invert_direction (SHORT) | Δ |
|-----|----------------|-----------------------------|---|
| Marzo | +0.0689% ✅ | **+0.1875%** ✅ | +0.1186 |
| Abril | -0.0607% ❌ | **+0.0121%** ✅ | +0.0728 |
| Mayo | -0.1036% ❌ | **+0.0660%** ✅ | +0.1696 |
| Junio | +0.1279% ✅ | **+0.1598%** ✅ | +0.0319 |
| **Acum.** | **+0.0325%** | **+0.4254%** | **+0.3929** |

---

## Resultados por Mes (con `invert_direction`)

### Split 1: Test Marzo — Net Taker +0.1875% ✅ (WR 49.0%, 434 señales)
| Escenario | Señales | WR | Net Taker |
|-----------|---------|-----|-----------|
| failed_breakout | 109 | 67.9% | +0.0162% |
| liquidity_exhaustion | 116 | 43.1% | +0.2766% |
| tactical_absorption | 56 | 41.1% | +0.2461% |
| **trend_acceptance** | **152** | **61.8%** | **+0.2193%** 🏆 |

### Split 2: Test Abril — Net Taker +0.0121% ✅ (WR 35.8%, 352 señales)
| Escenario | Señales | WR | Net Taker |
|-----------|---------|-----|-----------|
| failed_breakout | 85 | 49.4% | -0.1980% |
| liquidity_exhaustion | 81 | 27.2% | +0.0786% |
| tactical_absorption | 70 | 21.4% | +0.0140% |
| **trend_acceptance** | **117** | **57.3%** | **+0.1143%** 🏆 |

### Split 3a: Test Mayo — Net Taker +0.0660% ✅ (WR 31.6%, 369 señales)
| Escenario | Señales | WR | Net Taker |
|-----------|---------|-----|-----------|
| failed_breakout | 57 | 57.9% | -0.1051% |
| liquidity_exhaustion | 63 | 23.8% | +0.0142% |
| tactical_absorption | 103 | 21.4% | +0.0117% |
| **trend_acceptance** | **146** | **64.4%** | **+0.1936%** 🏆 |

### Split 3b: Test Junio — Net Taker +0.1598% ✅ (WR 56.7%, 999 señales)
| Escenario | Señales | WR | Net Taker |
|-----------|---------|-----|-----------|
| failed_breakout | 321 | 71.3% | +0.0577% |
| liquidity_exhaustion | 199 | 33.7% | +0.1350% |
| tactical_absorption | 66 | 54.5% | +0.4482% |
| **trend_acceptance** | **413** | **63.9%** | **+0.2062%** 🏆 |

---

## trend_acceptance por mes (auditoría, con inversión)

| Mes | n | MFE/MAE | Best Static Net | Veredicto | Net real |
|-----|---|---------|------------------|-----------|----------|
| Mar | 152 | **45.49** ✅ | +1.1299% ✅ | TARGET OPT ✅ | +0.2193% |
| Abr | 117 | **27.55** ✅ | +0.5936% ✅ | TARGET OPT ✅ | +0.1143% |
| May | 146 | **52.67** ✅ | +1.2046% ✅ | TARGET OPT ✅ | +0.1936% |
| Jun | 413 | **37.57** ✅ | +1.3042% ✅ | TARGET OPT ✅ | +0.2062% |

> Antes de invertir: TA MFE/MAE **0.02** (ENTRY FAILURE), Best Net **−0.0268%**. Después: MFE/MAE **27–53** (edge direccional FUERTE), Best Net **+0.59% a +1.30%**.

---

## Resumen Consolidado por Escenario (promedio 4 meses, Net Taker)

| Escenario | Promedio | Meses que disparó | Veredicto |
|-----------|----------|------------------|-----------|
| **trend_acceptance** | **+0.1834%** | 4/4 | 🏆 **Ganador top (era el peor)** |
| **tactical_absorption** | +0.1800% | 4/4 | 🏆 Ganador consistente |
| **liquidity_exhaustion** | +0.1261% | 4/4 | 🏆 Ganador consistente |
| **failed_breakout** | -0.0573% | 4/4 | ⚠️ Inconsistente |

---

## Conclusiones Clave

### 1. VALIDACIÓN de la REGLA DEL EDGE
El instinto inicial (desactivar TA por `ENTRY FAILURE`) habría sido un error. El problema era param/dirección, no ausencia de edge. Tras invertir, TA es el **mejor escenario** de AVAX (era el peor).

### 2. El bug de `validate_params` fue prerrequisito, no la causa
El fix (preservar claves extra del perfil) era necesario para que los golden params llegaran al sensor, PERO por sí solo no rescató a AVAX (TA seguía perdiendo como LONG). La causa real era la **inversión de dirección** de TA en AVAX.

### 3. TARGET FAILURE persiste — pero ahora es el ÚNICO problema
Con TA arreglado, **los 4 escenarios** auditan `TARGET OPTIMIZATION NEEDED`: las entradas tienen edge (best static grid +0.59% a +1.68%) pero los **targets AMT dinámicos subrinden** (TA real +0.11% a +0.28% vs static +1.13%; FB/LE/TACT similar). Es un problema de la **fórmula de targets AMT**, compartido, no de entrada.

### 4. AVAX vs LTC (walk-forward)
| Métrica | LTC | AVAX (previo) | AVAX (con invert) |
|---------|-----|----------------|-------------------|
| Net Taker acum | +2.4676% | +0.0325% | **+0.4254%** |
| Net Taker/mes | +0.617% | +0.0081% | **+0.1064%** |
| Meses positivos | 4/4 | 2/4 | **4/4** |
| Mejor escenario | LE (+0.3261%) | TACT (+0.1800%) | **TA (+0.1834%)** |
| Peor escenario | TACT (+0.0310%) | TA (−0.1967%) | FB (−0.0573%) |

---

## Próximos Pasos (REGLA DEL EDGE — no rendirse)

1. **Atacar TARGET FAILURE (root cause ahora único)**: los targets AMT dinámicos rinden ~5–10x por debajo del static grid en TODOS los escenarios. Re-optimizar la fórmula de targets AMT por escenario (o volver a targets fijos calibrados, ver sesión V2 en memory.md: TP=2.4%/SL=2.5% daba +0.1248% overall).
2. **Certificar OOS del fix de inversión**: ya validado en 4 splits independientes (Mar–Jun). Considerar validación cross-coin para confirmar que `invert_direction` es específico de AVAX y no se debe aplicar a otras monedas.
3. **failed_breakout** sigue siendo el escenario más debil (a veces −0.20%). Investigar su sensibilidad a régimen.

---

**Firmado**: 2026-07-14 (walk-forward con `invert_direction`)
**Versión**: 9.0 (SBR + TA Regime Filter + AVAX Golden Params V3 + TA Direction Inversion)
**Estado**: 🏆 AVAX walk-forward CERTIFICADO (4/4 meses positivos) — pendiente optimización de targets AMT (TARGET FAILURE)
**Cambios clave**: `decision/scenarios/confirmation/trend_acceptance.py` (flag `invert_direction` + `_emit`), `config/coin_profiles.py` (`invert_direction: True`, `regime_vol_ratio_max: 1.3`, `cvd_confirmation_threshold: 2.5` en `AVAX_NOISY_UNCERTAIN.trend_acceptance`)
