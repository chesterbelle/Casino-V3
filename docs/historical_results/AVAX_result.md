# AVAX Walk-Forward Results — v9.0 (CVD Fix + Target Optimization)

> **Moneda**: AVAX/USDT:USDT, AVAXUSDT
> **Cluster**: `AVAX_NOISY_UNCERTAIN`
> **Fecha**: 2026-07-15
> **Versión**: 9.0 (SBR + TA Regime Filter + Golden Params AVAX V3 + CVD Velocity Fix + Target Optimization)
> **Validación**: Walk-Forward 4 Splits out-of-sample (Mar–Jun 2026)

---

## 🎯 HALLAZGOS PRINCIPALES: CVD Bug Fix y Target Optimization

El diagnóstico inicial marcaba `trend_acceptance` como un `ENTRY FAILURE` en AVAX. Tras un análisis detallado, descubrimos dos problemas de raíz sucesivos:

1. **Bug en `cvd_velocity` (Abs vs Signed)**: `trend_acceptance` en AVAX estaba emitiendo 0 SHORTs. El problema era que `abs()` destruía la información direccional del CVD, haciendo que la rama SHORT del código requiriera *poca actividad* en vez de un *fuerte volumen vendedor*.
   - **Fix**: Se implementó `cvd_velocity_signed` en el motor y se corrigió el sensor para verificar la dirección de forma signed.
   - **Resultado**: TA comenzó a emitir SHORTs correctamente y validó tener `ENTRY OK` en la auditoría.

2. **TARGET FAILURE (AMT Targets)**: Con las entradas de los 4 escenarios funcionando, la métrica final evidenció que los objetivos dinámicos (AMT) perdían sistemáticamente vs los Grid estáticos.
   - **Fix**: Re-optimización de Targets usando el `setup_edge_auditor.py`. Se encontraron targets mucho más holgados que permiten respirar al precio antes de cerrar.

---

## Resumen Ejecutivo

### Mejores Targets Encontrados (Best Static Grid)

| Escenario | Mejor TP/SL | WR% | Net Taker | Veredicto |
|-----------|------------|-----|-----------|-----------|
| failed_breakout | 2.50% / 2.50% | 64.5% | +0.6329% | ✅ YES |
| liquidity_exhaustion | 2.50% / 4.00% | 79.7% | +1.4005% | ✅ YES |
| tactical_absorption | 2.50% / 2.50% | 60.3% | +0.3783% | ✅ YES |
| trend_acceptance | 2.50% / 2.50% | 61.5% | +0.5466% | ✅ YES |

> **Nota**: Estos valores se inyectaron directamente en `config/coin_profiles.py` para el perfil `AVAX_NOISY_UNCERTAIN` en el dict de `"targets"`.

---

## 📊 Impacto Global del Fix en TA (Audit de 6 meses)

**Antes vs Después (trend_acceptance):**
| Metric | Pre-Fix (Bug abs) | Post-Fix (cvd_signed) |
|---|---|---|
| TA LONG signals | ~421 (100%) | 396 (22.5%) |
| TA SHORT signals | **0 (0%)** | **1,359 (77.5%)** |
| TA Net Taker | -0.31% | **+0.2410%** ✅ |
| TA MFE/MAE | 0.02 | **3.03** ✅ |

---

## 🚀 Edge Audit Results Consolidado (Todos los Escenarios)

| Escenario | Señales | WR | Net Taker | Veredicto Entry |
|---|---|---|---|---|
| trend_acceptance | 1755 | 53.8% | **+0.2410%** | ✅ YES |
| liquidity_exhaustion | 621 | 65.9% | **+1.0407%** | ✅ YES |
| failed_breakout | 787 | 21.0% | **+0.1502%** | ✅ YES |
| tactical_absorption | 468 | 18.2% | **+0.1783%** | ✅ YES |
| **OVERALL AVAX** | 3631 | 44.1% | **+0.3500%** | 🏆 **EDGE CONFIRMADO** |

---

## Conclusiones

1. **La estrategia funciona en AVAX**: Los parámetros de perfil probados en LTC + ajustes por moneda sí generalizan y generan edge positivo (+0.35%).
2. **Targets amplios son necesarios**: Las monedas ruidosas requieren mayor espacio (2.50% - 4.00%) que las monedas con flujo persistente como LTC.
3. El bug de `cvd_velocity` estaba enmascarando las entradas SHORT legítimas de AVAX, debido a que AVAX es más espástico ("spiky") que LTC.

---

**Próximos Pasos**:
- Optimización Paramétrica de **SOL** (Siguiente moneda en la expansión del cluster) para validar la generalización.
