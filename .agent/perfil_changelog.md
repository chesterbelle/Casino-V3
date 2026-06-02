# Perfil Changelog — ILLIQUID_SPEC

> Registro de iteraciones y hallazgos. Basado en datos de LTC.

## Parámetros Actuales (Código — `config/coin_profiles.py`)

> **Resincronizado**: 2026-06-01 — Refleja el estado actual del código.

### Sensores — `absorption_detector`
```python
"z_score_min": 3.5,           # Reducido de 2.5→3.5 (menos ruido, mejor WR)
"concentration_min": 0.40,    # Sin cambio desde baseline
"noise_max": 0.40,            # Sin cambio desde baseline
"stagnation_floor_pct": 0.08, # Sin cambio desde baseline
```

### Sensores — `failed_breakout`
```python
"min_break_distance_pct": 0.0008,    # 0.08% (subido desde default — filtra micro-breaks)
"max_break_age": 90.0,               # 90 segundos
"cvd_divergence_threshold": 0.25,
```

### Sensores — `liquidity_exhaustion`
```python
"min_tests": 3,
"declining_threshold": 0.75,
"min_bounce_pct": 0.0010,            # 0.10% (subido para evitar micro-noise)
"test_memory_seconds": 120.0,
```

### Sensores — `trend_acceptance`
```python
"min_candles_outside": 3,
"cvd_confirmation_threshold": 4.0,
"pullback_tolerance_pct": 0.001,
"max_pullback_penetration_pct": 0.001,
```

### Quality Scorer
```python
"weights": {
    "exhaustion": 0.40,   # Subido de 0.35→0.40
    "regime": 0.30,       # Subido de 0.25→0.30
    "structure": 0.15,    # Bajado de 0.20→0.15
    "liquidity": 0.10,    # Bajado de 0.15→0.10
    "spread": 0.05,       # Sin cambio
}
"grade_thresholds": {"A": 0.70, "B": 0.40}
```

### Targets — `TacticalAbsorptionV2` (Per-Regime + Fallback)
```python
# Per-regime (calibrado sobre 1975 señales V2)
"TREND_UP":   {"tp_pct": 0.012, "sl_pct": 0.040},  # 1.2% / 4.0%
"TREND_DOWN": {"tp_pct": 0.020, "sl_pct": 0.050},  # 2.0% / 5.0%
"BALANCE":    {"tp_pct": 0.008, "sl_pct": 0.040},  # 0.8% / 4.0%
# Fallback (si regime no detectado)
"tp_pct": 0.024, "sl_pct": 0.025,  # 2.4% / 2.5%
```

### Targets — Otros Setups
```python
"failed_breakout":     {"tp_pct": 0.020, "sl_pct": 0.025},  # 2.0% / 2.5% (grid optimal)
"liquidity_exhaustion":{"tp_pct": 0.015, "sl_pct": 0.004},  # 1.5% / 0.4% (grid optimal)
"trend_acceptance":    {"tp_pct": 0.009, "sl_pct": 0.009},  # 0.9% / 0.9% (default)
```

### Guardians
```python
"l2_ratio_min": 0.5,                    # Thin Wall para BALANCE/UP
"l2_ratio_min_trend_down": 2.0,         # High Wall para BEAR (asimetría régimen-aware)
"spread_max_ratio": 2.0,
```

---

## Historial de Iteraciones (Pre-2026-06-01)

> **Nota**: Esta tabla histórica refleja iteraciones ANTES de la resincronización. Los valores de "Config" mostrados son obsoletos — el código actual usa los parámetros de la sección "Parámetros Actuales" arriba.

| # | Cambio | Config | Net Taker (9 datasets LTC) | Conclusión |
|---|--------|--------|---------------------------|------------|
| 0 | Baseline original | z=2.5, A:0.65, 0.90% | -0.0625% | Punto de partida |
| 1 | +weights, +grades | z=2.5, A:0.70, 0.80% | -0.0464% | Mejor config histórica |
| 2 | +grade estricto | z=2.5, A:0.75, 0.80% | -0.0492% | Marginal |
| 3 | +sensor estricto | z=3.5, conc=0.60 | -0.0646% | PEOR — overfitting |
| 4 | +best uniform | 0.80/0.90/0.60/0.80 | -0.0626% | Auditor grid no siempre óptimo |
| 5 | z=3.5 + l2=0.5 + 0.90% | z=3.5, l2=0.5, 0.90% | -0.0479% | ≈ Iteración 1 |

**Mejor resultado histórico**: Iteración 1 (-0.0464%) — pero con configuración obsoleta.

---

## Hallazgos Clave (Acumulados)

### 1. Quality Scorer tiene impacto marginal
Los weights producen diferencia < 0.01% en Net Taker.
**Acción**: No gastar tiempo ajustando weights como primer paso.

### 2. Thin Wall vs High Wall es OPUESTO por régimen
| Condición | High Wall MFE/MAE | Thin Wall MFE/MAE | Ganador |
|-----------|-------------------|-------------------|---------|
| RANGE | 1.23 | 2.16 | Thin Wall |
| BULL | 0.59 | 1.61 | Thin Wall |
| BEAR | 1.49 | 0.48 | High Wall |

**Acción**: `l2_ratio_min` régimen-aware (`l2_ratio_min_trend_down: 2.0` ya implementado).

### 3. Mercado BEAR es el problema fundamental
- 388 LONGs tóxicos en BEAR con MFE/MAE 0.39
- La estrategia mean-reversion falla en tendencias bajistas
- TREND_DOWN LONGs tienen 6% WR (5 TP vs 79 SL) — tóxico

### 4. Per-regime targets asimétricos son superiores a fixed
- TAV per-regime: TREND_UP=1.2/4.0, TREND_DOWN=2.0/5.0, BALANCE=0.8/4.0
- Permite capturar movimiento institucional (mediana 110 min) sin sobreexponer en BEAR
- Fallback 2.4%/2.5% si regime no detectado

### 5. El dataset individual NO es representativo
LTC_RANGE_2024-02-01 mostró +0.2236%, pero el promedio de 9 datasets fue -0.0321%.
**Acción**: Siempre validar con 9+ datasets (3 RANGE + 3 BULL + 3 BEAR).

### 6. Liquidity Exhaustion y Trend Acceptance pendientes
- `liquidity_exhaustion` (47 señales) Net Taker -0.21% — necesita re-tuning
- `trend_acceptance` (98 señales) Net Taker -0.015% — borderline

---

## Recomendaciones para Futuras Iteraciones

1. **Empezar con l2_ratio_min**: 0.5 actual es bajo — probar 0.8-1.2 (riesgo bajo)
2. **concentration_min**: 0.40 puede ser muy permisivo — probar 0.45-0.55
3. **Per-regime targets**: Re-calibrar con datos multi-asset
4. **failed_breakout**: tp=2.0%/sl=2.5% ya validado, mantener
5. **No overfittear a 1 dataset** — siempre usar 9+ datasets (3 RANGE + 3 BULL + 3 BEAR)
6. **Métrica primary**: Net Taker global (no WR, no MFE/MAE)
7. **Validación cruzada**: Set B (datos no usados) mide overfitting

---

## Pendiente Estructural (Fuera del Scope Paramétrico)

1. **TREND_DOWN LONG veto**: Prohibir LONGs en régimen DOWN (6% WR → tóxico)
2. **Reducir timeout rate**: ~60% de trades son timeouts (drag principal)
3. **Re-evaluar nombre**: TacticalAbsorptionV2 → InstitutionalFlowV2 (mediana 110 min, no es reversion micro)
4. **Síntesis MarketRegimeSensor**: Mejorar detección de TREND_DOWN estructural
