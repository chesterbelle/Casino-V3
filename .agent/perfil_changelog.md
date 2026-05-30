# Perfil Changelog — VOLATIL_BAJO_FLOW

> Registro de iteraciones y hallazgos para evitar repetir trabajo en otros perfiles (SUI, AVAX).

## Parámetros Actuales (Óptimos — Mayo 2026)

### Sensores
```python
"absorption_detector": {
    "z_score_min": 3.5,           # Original: 2.5 → Mejorado: menos ruido
    "concentration_min": 0.40,    # Sin cambio
    "noise_max": 0.40,            # Sin cambio
    "stagnation_floor_pct": 0.08, # Sin cambio
}
```

### Quality Scorer
```python
"weights": {
    "exhaustion": 0.40,   # Original: 0.35 → Subido
    "regime": 0.30,       # Original: 0.25 → Subido
    "structure": 0.15,    # Original: 0.20 → Bajado
    "liquidity": 0.10,    # Original: 0.15 → Bajado
    "spread": 0.05,       # Sin cambio
}
"grade_thresholds": {"A": 0.70, "B": 0.40}  # Original: 0.65/0.35
```

### Targets
```python
"TacticalAbsorptionV2": {"tp_pct": 0.009, "sl_pct": 0.009},  # 0.90%
"failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},        # 1.00%
"liquidity_exhaustion": {"tp_pct": 0.006, "sl_pct": 0.006},   # 0.60%
"trend_acceptance": {"tp_pct": 0.009, "sl_pct": 0.009},       # 0.90%
```

### Guardians
```python
"l2_ratio_min": 0.5,       # Original: 1.5 → Bajado (Thin Wall mejor)
"spread_max_ratio": 2.0,   # Original: 2.5 → Bajado
```

---

## Historial de Iteraciones

| # | Cambio | Config | Net Taker (9 datasets) | Conclusión |
|---|--------|--------|------------------------|------------|
| 0 | Baseline original | z=2.5, A:0.65, 0.90% | -0.0625% | Punto de partida |
| 1 | +weights, +grades | z=2.5, A:0.70, 0.80% | -0.0464% | Mejor config hasta ahora |
| 2 | +grade estricto | z=2.5, A:0.75, 0.80% | -0.0492% | Marginal, sin cambio significativo |
| 3 | +sensor estricto | z=3.5, conc=0.60 | -0.0646% | PEOR — overfitting |
| 4 | +best uniform | 0.80/0.90/0.60/0.80 | -0.0626% | Auditor grid no siempre óptimo |
| 5 | z=3.5 + l2=0.5 + 0.90% | z=3.5, l2=0.5, 0.90% | -0.0479% | ≈ Iteración 1 |

**Mejor resultado**: Iteración 1 (-0.0464%) — weights 0.40/0.30, grade A:0.70, targets 0.80/1.00/0.60/1.10, spread_max 2.0

---

## Hallazgos Clave

### 1. Quality Scorer tiene impacto marginal
Los weights (0.40/0.30 vs 0.35/0.25) producen diferencia < 0.01% en Net Taker.
**Acción**: No gastar tiempo ajustando weights como primer paso.

### 2. Thin Wall > High Wall (L2 Depth Auditor)
```
L2 Ratio        | Trades | MFE/MAE
Thin Wall (<1.0) |   59   |  2.21  ✅ MEJOR
Balanced (1-2)   |   71   |  1.18
High Wall (>2.0) |   13   |  1.88
```
**Acción**: `l2_ratio_min` bajo (0.5) es mejor que alto (1.5+).

### 3. Mercado BEAR es el problema fundamental
| Condición | Net Taker | MFE/MAE |
|-----------|-----------|---------|
| RANGE (n=129) | **+0.2236%** ✅ | 1.47 |
| BULL (n=180) | **+0.1105%** ✅ | 2.30 |
| BEAR (n=120) | **-0.0822%** ❌ | 1.57 |

**Conclusión**: Los parámetros del perfil no resuelven esto. Necesita mejora en la estrategia (market regime filter, targets dinámicos por condición).

### 4. El dataset individual NO es representativo
LTC_RANGE_2024-02-01 mostró +0.2236%, pero el promedio de 9 datasets fue -0.0479%.
**Acción**: Siempre validar con 9+ datasets (3 RANGE + 3 BULL + 3 BEAR).

### 5. Auditor grid vs Performance real
El auditor recomienda 1.00% para TAV (best uniform), pero 0.90% performa mejor en AMT targets reales.
**Acción**: Usar auditor como guía inicial, pero validar con AMT targets del sistema.

### 6. z_score_min=3.5 es mejor que 2.5
En test individual: WR 69.1% (z=3.5) vs ~54% (z=2.5). Pero en 9 datasets la diferencia se diluye.
**Acción**: Empezar con z=3.5 para nuevos perfiles.

---

## Recomendaciones para Otras Monedas (SUI, AVAX)

1. **Empezar con z_score_min: 3.5** (menos ruido, mejor WR en individual)
2. **l2_ratio_min: 0.5** (Thin Wall tiene mejor edge)
3. **Validar en RANGE primero**, luego BULL,最后 BEAR
4. **Si BEAR arrastra el resultado**, el problema es la estrategia, no el perfil
5. **No overfittear a 1 dataset** — siempre usar 9+ datasets
6. **Auditor grid es punto de partida**, pero validar con AMT targets reales
7. **Los weights del quality scorer tienen impacto marginal** — enfocarse en sensores y targets primero

---

## Problema Pendiente: BEAR Market

La estrategia mean-reversion falla en tendencias bajistas fuertes. Soluciones posibles:
1. Market regime filter en Guardian (MA20 < MA50 → reducir sizing)
2. Targets dinámicos por regime (BEAR → TP más amplio, SL más ajustado)
3. Nuevo sensor de regime que ajuste parámetros dinámicamente
