# Long-Range Edge Audit Results — LTC 2024 (Phase 800B)

**Date**: 2026-04-26
**Protocol**: `.agent/workflows/long-range-edge-audit.md`
**Datasets**: 9 backtests (3 conditions × 3 days)
**Total Signals**: 232
**Auditor Version**: Phase 800B (with Gross Expectancy metrics)

---

## Overall Results (Aggregate)

### Section [5]: Overall Edge Summary

```
Total Signals:        232
Decided (W+L):        105
Overall Win Rate:     49.5%
Avg Win (MFE):        0.403%
Avg Loss (MAE):       0.430%

Gross Expectancy:     -0.0176%
Net (Taker 0.12%):    -0.1376% ❌
Net (Maker 0.08%):    -0.0976% ❌
```

**Veredicto Global**: ❌ **NO EDGE**
- Gross Expectancy negativa (-0.0176%)
- Estrategia NO viable en condiciones de 2024
- MAE (0.430%) > MFE (0.403%) → Pérdidas promedio mayores que ganancias

---

## Section [1]: Setup Edge Breakdown

| Setup Type | n | Avg MFE% | Avg MAE% | Ratio |
|------------|---|----------|----------|-------|
| reversion | 232 | 0.189% | 0.174% | 1.09 |

- Ratio 1.09 indica ventaja estructural mínima
- MFE/MAE muy cercanos → edge delgado

---

## Section [1B]: Gross Expectancy (Pre-Fee Edge)

| Setup Type | n | WR% | Avg Win% | Avg Loss% | Expectancy% | Viable? |
|------------|---|-----|----------|-----------|-------------|---------|
| reversion | 232 | 49.5% | 0.403% | 0.430% | **-0.0176%** | ❌ NO |

**Análisis**:
- WR 49.5% < 50% → Más pérdidas que ganancias
- Avg Loss (0.430%) > Avg Win (0.403%)
- Expectancy negativa ANTES de fees
- **Conclusión**: No hay edge real en 2024

---

## Section [2]: Theoretical Win-Rate (First Touch)

| TP/SL | Wins | Losses | Timeout | WR% | Expectancy% | Net (Taker) | Net (Maker) |
|-------|------|--------|---------|-----|-------------|-------------|-------------|
| 0.1%/0.1% | 108 | 86 | 38 | **55.7%** | +0.0170% | -0.1030% ❌ | -0.0630% ❌ |
| 0.2%/0.2% | 84 | 78 | 70 | 51.9% | +0.0074% | -0.1126% ❌ | -0.0726% ❌ |
| 0.3%/0.3% | 52 | 53 | 127 | 49.5% | -0.0029% | -0.1229% ❌ | -0.0829% ❌ |
| 0.4%/0.4% | 19 | 30 | 183 | 38.8% | -0.0898% | -0.2098% ❌ | -0.1698% ❌ |
| 0.5%/0.5% | 7 | 12 | 213 | 36.8% | -0.1316% | -0.2516% ❌ | -0.2116% ❌ |

**Observaciones**:
- Mejor WR en 0.1%/0.1% (55.7%) pero Expectancy muy baja (+0.0170%)
- Todos los TP/SL son negativos después de fees
- A mayor TP/SL, peor el WR (38.8% en 0.4%, 36.8% en 0.5%)
- **Conclusión**: Targets más amplios no capturan el edge

---

## Per-Condition Breakdown

| Condition | n | WR% | MFE% | MAE% | Ratio | Expectancy* | Verdict |
|-----------|---|-----|------|------|-------|-------------|---------|
| **RANGE (Aug 2024)** | 85 | **53.2%** | 0.213% | 0.194% | 1.10 | **+0.0101%** | ⚠️ WATCH |
| **BEAR (Sep 2024)** | 57 | 44.4% | 0.210% | 0.226% | 0.93 | **-0.0329%** | ❌ FAILED |
| **BULL (Oct 2024)** | 90 | 50.0% | 0.154% | 0.133% | 1.16 | **0.0000%** | ❌ FAILED |

*Expectancy calculada: `(WR × MFE) - ((1-WR) × MAE)`

### Análisis por Condición:

#### RANGE (Aug 2024) — ⚠️ WATCH
- **WR 53.2%** → Único con WR > 50%
- **Expectancy +0.0101%** → Positiva pero < 0.12% (fees)
- **Ratio 1.10** → Ventaja estructural mínima
- **Veredicto**: Edge marginal, NO viable después de fees

#### BEAR (Sep 2024) — ❌ FAILED
- **WR 44.4%** → Muy bajo
- **MAE (0.226%) > MFE (0.210%)** → Pérdidas mayores que ganancias
- **Expectancy -0.0329%** → Negativa
- **Veredicto**: Guardians NO están filtrando correctamente en bear

#### BULL (Oct 2024) — ❌ FAILED
- **WR 50.0%** → Breakeven en cantidad
- **MFE 0.154%** → Muy bajo (el más bajo de las 3 condiciones)
- **Expectancy 0.0000%** → Neutral (pero negativo después de fees)
- **Veredicto**: Reversiones fallan en mercado alcista

---

## Section [4]: Decision Trace Audit (Guardian Activity)

| Gate | Reason | Count |
|------|--------|-------|
| POC_MIGRATION | Healthy migration | 2156 |
| REGIME_ALIGNMENT_V2 | Local consensus overrides Macro BALANCE | 2084 |
| DELTA_DIVERGENCE | Orderflow supportive/neutral | 1641 |
| VA_INTEGRITY | Acceptable VA density | 1094 |
| VA_INTEGRITY | Soft VA density (sizing reduced) | 595 |
| VA_INTEGRITY | Critically low VA density | 472 |
| REGIME_ALIGNMENT_V2 | Local consensus overrides Macro TREND_UP | 86 |
| DELTA_DIVERGENCE | Orderflow pressure too high | 46 |
| POC_MIGRATION | Hard migration against side | 8 |

**Observaciones**:
- Guardians están activos (2084 + 86 = 2170 regime checks)
- Pero NO están bloqueando suficientes señales malas en BEAR/BULL
- VA_INTEGRITY rechazó 472 señales por baja densidad (correcto)
- DELTA_DIVERGENCE solo rechazó 46 por presión alta (muy poco)

---

## Comparación vs Edge Audit Normal (2026)

| Métrica | Long-Range 2024 | Normal 2026 | Delta |
|---------|-----------------|-------------|-------|
| Total Signals | 232 | ~80 | +152 |
| Win Rate | 49.5% | ~60-65% | -10 a -15% |
| Gross Expectancy | -0.0176% | +0.09% (estimado) | -0.11% |
| Ratio MFE/MAE | 1.09 | 1.44 | -0.35 |
| Verdict | FAILED | WATCH/MARGINAL | Degradación |

**Interpretación**:
- Edge en 2024 es significativamente más débil que en 2026
- Posibles causas:
  1. Condiciones de mercado diferentes (2024 más volátil)
  2. LTA V6 optimizado para condiciones recientes (2026)
  3. Guardians calibrados con datos de 2026

---

## Certification Status (Phase 800B Criteria)

### Overall System Verdict: ❌ **BROKEN**

| Condition | Criteria | Status | Interpretation |
|-----------|----------|--------|----------------|
| **Range** | Expectancy > 0.36% | ❌ FAILED | +0.0101% << 0.36% |
| **Range** | Expectancy > 0.12% | ❌ FAILED | +0.0101% < 0.12% |
| **Bear** | Expectancy > 0% | ❌ FAILED | -0.0329% |
| **Bull** | Expectancy > 0% | ⚠️ NEUTRAL | 0.0000% (breakeven) |

### Guardian Effectiveness: ⚠️ **WEAK**

- RANGE: 85 señales (más que BEAR 57) → ✅ Correcto
- BEAR: WR 44.4% → ❌ Guardians dejando pasar malas señales
- BULL: WR 50.0% → ⚠️ Guardians no bloqueando suficiente

---

## Recomendaciones (Phase 800B)

### 1. **Tighter Entry Filters** (Reduce MAE)
- MAE promedio 0.430% es demasiado alto
- Agregar filtros de:
  - Volume profile quality (VA density mínima más alta)
  - Delta divergence threshold más estricto
  - Proximity gate más ajustado en BEAR/BULL

### 2. **Better Exit Timing** (Capture more MFE)
- MFE promedio 0.403% indica que el precio se mueve a favor
- Pero solo capturamos 0.3% en TP
- Considerar:
  - Valentino scale-out más agresivo (50% @ 0.2% en vez de 0.21%)
  - Trailing stop más cercano en RANGE

### 3. **Regime-Specific Calibration**
- RANGE: Edge marginal (+0.0101%) → Aumentar tamaño de posición si Limit Sniper
- BEAR: Edge negativo → Bloquear más señales (threshold de delta más alto)
- BULL: Edge neutral → Considerar desactivar reversiones en TREND_UP

### 4. **Limit Sniper OBLIGATORIO**
- Todos los Net (Taker) son negativos
- Fees de 0.12% consumen todo el edge
- Sin Limit Sniper (maker 0.02%), la estrategia NO es viable

---

## Conclusión Final

**LTA V6 en condiciones de 2024**: ❌ **NO VIABLE**

- Gross Expectancy negativa (-0.0176%)
- Solo RANGE muestra edge marginal (+0.0101%) pero insuficiente
- BEAR y BULL tienen expectancy negativa o neutral
- Guardians NO están filtrando suficientemente en trending markets

**Posibles explicaciones**:
1. LTA V6 fue optimizado con datos de 2026 (más recientes)
2. Condiciones de mercado en 2024 eran diferentes
3. Guardians calibrados para 2026, no generalizan a 2024

**Acción requerida**:
- Validar edge en datos de 2025-2026 (más recientes)
- Si edge existe en 2026 pero no en 2024 → Estrategia NO es robusta
- Considerar recalibración de guardians con datos históricos más amplios

---

*Generated: 2026-04-26*
*Auditor Version: Phase 800B (Gross Expectancy metrics)*
