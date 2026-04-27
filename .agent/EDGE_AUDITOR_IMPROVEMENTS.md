# Edge Auditor Improvements — Phase 800B

## Problema Identificado

**Gemini tenía razón parcialmente**: La métrica correcta para medir el edge puro (antes de fees) es la **Expectancia Bruta en porcentaje**, no solo el Ratio MFE/MAE o el Profit Factor.

### Fórmula Correcta del Edge:
```
Gross Expectancy (%) = (Win Rate × Avg Win %) - (Loss Rate × Avg Loss %)
```

### Criterio de Viabilidad:
```
Gross Expectancy > 3 × Fee_Round_Trip
```

Para Casino-V3:
- **Taker Round-Trip**: 0.12% (0.06% entry + 0.06% exit)
- **Maker Round-Trip**: 0.08% (0.02% entry + 0.06% exit con Limit Sniper)
- **Threshold mínimo viable**: 0.36% (3× taker fees)

---

## Cambios Implementados

### 1. Nueva Sección [1B]: Gross Expectancy (Pre-Fee Edge)

Calcula la expectancia bruta por setup usando:
- Win Rate real (first touch 0.3%/0.3%)
- Avg MFE de winners (no el TP teórico)
- Avg MAE de losers (no el SL teórico)

**Output:**
```
[1B] GROSS EXPECTANCY (Pre-Fee Edge in %)
Setup Type                n      WR%      Avg Win%    Avg Loss%   Expectancy%   Viable?
-----------------------------------------------------------------------------------------------
TacticalTrappedTraders    45     62.2%    0.312%      0.198%      +0.1189%      MARGINAL (>0.12%)
TacticalDivergence        35     58.6%    0.289%      0.215%      +0.0803%      NO (<0.12%)
```

**Interpretación:**
- `Expectancy > 0.36%` → **YES** (viable con taker orders)
- `Expectancy > 0.12%` → **MARGINAL** (requiere maker orders)
- `Expectancy < 0.12%` → **NO** (no viable, rework necesario)

---

### 2. Sección [2] Mejorada: Net Expectancy por TP/SL

Ahora muestra:
- Gross Expectancy (asume captura full TP/SL)
- Net (Taker): Gross - 0.12%
- Net (Maker): Gross - 0.08%

**Output:**
```
[2] THEORETICAL WIN-RATE (First Touch @ Fixed TP/SL)
TP/SL        Wins     Losses   Timeout  WR%      Expectancy%   Net (Taker)   Net (Maker)
---------------------------------------------------------------------------------------------------------
0.3%/0.3%    56       34       10       62.2%    +0.1866%      +0.0666%      +0.1066%
0.4%/0.4%    48       42       10       53.3%    +0.0268%      -0.0932%      -0.0532%
```

**Interpretación:**
- Si Net (Taker) > 0 → Edge fuerte, market orders OK
- Si Net (Maker) > 0 pero Net (Taker) < 0 → Limit Sniper obligatorio
- Si ambos < 0 → Edge demasiado delgado, no viable

---

### 3. Sección [3] Mejorada: Per-Setup con Expectancy

Ahora incluye la Expectancy% calculada con MFE/MAE real:

**Output:**
```
[3] PER-SETUP FIRST TOUCH (0.3%/0.3%) + GROSS EXPECTANCY
Setup Type                n      Wins   WR%      Expectancy%   Verdict
-------------------------------------------------------------------------------------
TacticalTrappedTraders    45     28     62.2%    +0.1189%      WATCH
TacticalDivergence        35     20     57.1%    +0.0803%      FAILED
```

**Veredicto actualizado:**
- `Expectancy > 0.36% AND WR > 55%` → **CERTIFIED**
- `Expectancy > 0.12% AND WR > 50%` → **WATCH** (requiere Limit Sniper)
- `Expectancy < 0.12%` → **FAILED**
- `n < 20` → **INSUFFICIENT**

---

### 4. Nueva Sección [5]: Overall Edge Summary

Resumen agregado con recomendaciones accionables:

**Output:**
```
[5] OVERALL EDGE SUMMARY
----------------------------------------------------------------------
Total Signals:        80
Decided (W+L):        70
Overall Win Rate:     60.0%
Avg Win (MFE):        0.289%
Avg Loss (MAE):       0.206%

Gross Expectancy:     +0.0910%
Net (Taker 0.12%):    -0.0290% ❌
Net (Maker 0.08%):    +0.0110% ✅

⚠️  MARGINAL EDGE: Gross expectancy > fees but < 3× threshold
   Requires maker orders (limit sniper) to be profitable.

Recommendation:
  → ENABLE Limit Sniper (maker entries) to capture the edge
```

**Posibles veredictos:**
1. **EDGE CONFIRMED** (Gross > 0.36%)
   - "Strategy is viable even with taker orders"

2. **MARGINAL EDGE** (0.12% < Gross < 0.36%)
   - "Requires maker orders (limit sniper) to be profitable"

3. **NO EDGE** (Gross < 0.12%)
   - "Strategy is not viable. Rework entry logic or exit management"

**Recomendaciones específicas:**
- Si Net (Maker) > 0 pero Net (Taker) ≤ 0 → "ENABLE Limit Sniper"
- Si Net (Taker) > 0 → "Edge is strong enough for market orders"
- Si ambos < 0 → Sugerencias de optimización:
  - Tighter entry filters (reduce MAE)
  - Better exit timing (capture more MFE)
  - Wider TP targets if MFE supports it

---

## Por Qué Esto Es Correcto

### Antes (Incorrecto):
- Usábamos **Ratio MFE/MAE** como métrica principal
- Ratio > 1.2 no garantiza profitabilidad después de fees
- Ejemplo: MFE=0.15%, MAE=0.10%, Ratio=1.5 → parece bueno
  - Pero con WR=50%: Expectancy = 0.025% < 0.12% fees → NO VIABLE

### Ahora (Correcto):
- Usamos **Gross Expectancy** como métrica definitiva
- Comparamos directamente con fees (0.12% taker, 0.08% maker)
- Threshold de 3× fees (0.36%) asegura margen de seguridad
- Recomendaciones específicas según Net (Taker) vs Net (Maker)

---

## Impacto en Protocolos

Los 3 protocolos de edge audit ahora deben interpretar resultados usando:

1. **Gross Expectancy** como métrica primaria (no Ratio)
2. **Net Expectancy** para determinar viabilidad con/sin Limit Sniper
3. **Threshold de 0.36%** para certificación (no solo WR > 55%)

### Matriz de Certificación Actualizada:

| Gross Expectancy | Net (Maker) | Net (Taker) | Veredicto | Acción |
|------------------|-------------|-------------|-----------|--------|
| > 0.36% | > 0 | > 0 | **CERTIFIED** | Production ready (cualquier order type) |
| 0.12% - 0.36% | > 0 | < 0 | **WATCH** | Viable solo con Limit Sniper |
| 0.12% - 0.36% | > 0 | > 0 | **CERTIFIED** | Production ready (edge marginal pero positivo) |
| < 0.12% | < 0 | < 0 | **FAILED** | Rework entry/exit logic |
| n < 20 | - | - | **INSUFFICIENT** | Más datos necesarios |

---

## Archivos Modificados

- `utils/setup_edge_auditor.py` — Nuevas secciones [1B], [2], [3], [5]
- `.agent/memory.md` — Documentación del protocolo `/edge-audit` actualizada

---

*Last Updated: 2026-04-26*
