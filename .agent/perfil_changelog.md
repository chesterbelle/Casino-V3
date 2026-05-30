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

### 2. Thin Wall vs High Wall es OPUESTO por régimen
| Condición | High Wall MFE/MAE | Thin Wall MFE/MAE | Ganador |
|-----------|-------------------|-------------------|---------|
| RANGE | 1.23 | 2.16 | Thin Wall |
| BULL | 0.59 | 1.61 | Thin Wall |
| BEAR | 1.49 | 0.48 | High Wall |

**Acción**: Usar macro direction directo para l2_ratio_min (no esperar clasificación TREND_DOWN).

### 3. Mercado BEAR es el problema fundamental
- **388 LONGs tóxicos** en BEAR con MFE/MAE 0.39
- La estrategia mean-reversion falla en tendencias bajistas
- **Mejora implementada**: Macro direction + slow drift 60c mejoró Net Taker de -0.0625% a -0.0321%

### 4. MarketRegimeSensor tiene defecto estructural
- **Síntesis diluye señal macro**: Macro score 0.73 pero síntesis da confidence 0.40
- **Slow drift 60c detecta TREND_UP** (por rebotes) en vez de TREND_DOWN
- **Solución actual**: Usar macro direction directo en liquidity_guardian
- **Mejora futura**: Revisar síntesis del MarketRegimeSensor

### 5. El dataset individual NO es representativo
LTC_RANGE_2024-02-01 mostró +0.2236%, pero el promedio de 9 datasets fue -0.0321%.
**Acción**: Siempre validar con 9+ datasets (3 RANGE + 3 BULL + 3 BEAR).

### 6. Auditor grid vs Performance real
El auditor recomienda 1.00% para TAV (best uniform), pero 0.90% performa mejor en AMT targets reales.
**Acción**: Usar auditor como guía inicial, pero validar con AMT targets reales.

### 7. Configuración ganadora identificada
| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Net Taker | -0.0625% | **-0.0321%** | **+0.0304%** |
| MFE/MAE | 1.31 | **1.40** | +0.09 |
| Win Rate | 53.2% | **54.9%** | +1.7% |
| failed_breakout | -0.0126% | **+0.0040%** | +0.0166% |

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

## Problema Resuelto: BEAR Market

La estrategia mean-reversion fallaba en tendencias bajistas. Solución implementada:
1. **Macro direction directo** para l2_ratio_min (no espera clasificación TREND_DOWN)
2. **Slow drift 60c** en circuit breaker (detecta drift gradual)
3. **Net direction ratio** en macro layer (reemplaza consecutive candles)
4. **Confidence escalation** para macro-alone TREND detection

**Resultado**: Net Taker mejoró de -0.0625% a -0.0321% (+0.0304%)

**Pendiente**: Mejorar síntesis del MarketRegimeSensor (futuras sesiones)
