# Perfil Changelog — VOLATIL_BAJO_FLOW

> Registro de iteraciones y hallazgos para evitar repetir trabajo en otros perfiles (SUI, AVAX).

## Parámetros Actuales (Código — `config/coin_profiles.py`)

> **Resincronizado**: 2026-06-01 — Refleja el estado actual del código, no iteraciones anteriores obsoletas.

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

## Historial de Iteraciones (Post-2026-06-01)

> **Sesión Profile Validation — Multi-Asset (LTC + AVAX + SUI)**

### Run Baseline (3,072 señales, 14 datasets)

**Config**: parámetros del código sin cambios (z=3.5, conc=0.40, l2_ratio_min=0.5, TAV per-regime, FB 2.0/2.5, LE 1.5/0.4, TA 0.9/0.9)

**Global**: 3,072 señales | 1,625 Decided | 1,447 TO (47% TO rate) | WR 72.6% | Gross +0.0134% | **Net Taker -0.1066%** | Net Maker -0.0666%

**Per Coin**:

| Coin | n | WR% | Gross Exp% | Net Taker% | Veredicto |
|------|:-:|:---:|:----------:|:----------:|:---------:|
| AVAX/USDT:USDT | 1,491 | 64.6% | -0.2315% | **-0.3515%** | ❌ ENTRY FAIL |
| LTC/USDT:USDT  | 1,140 | 79.5% | +0.2977% | **+0.1777%** | ✅ EDGE |
| SUI/USDT:USDT  |   441 | 82.6% | +0.5568% | **+0.4368%** | ✅ EDGE (mejor) |

**Per Setup × Coin**:

| Setup | LTC Net | AVAX Net | SUI Net |
|-------|:-------:|:--------:|:-------:|
| TAV | +0.2097% ✅ | **-0.4404%** ❌ | +0.6213% ✅ |
| FB | +0.4954% ✅ | +0.1992% ✅ | **-1.2137%** ❌ |
| LE | n/a (<25) | -0.0047% | n/a |
| TA | +0.1922% ✅ | +0.1192% ✅ | +0.3982% ✅ |

**L2 Depth (2,292 señales con L2 data)**:
| L2 Ratio (Wall) | Trades | MFE/MAE |
|-----------------|:------:|:-------:|
| High Wall (>2.0) | 893 | 1.15 |
| Balanced (1.0-2.0) | 191 | 1.03 |
| Thin Wall (<1.0) | 1,208 | 0.94 |

**Conclusiones Baseline**:
1. **AVAX TAV** es el drag principal (-0.44% con 1,247 señales — 41% del total)
2. **SUI FB** está roto (33 señales, WR 31%, -1.21%)
3. **Thin Wall** actual (l2_ratio_min=0.5) tiene MFE/MAE **peor** que High Wall — contradice análisis histórico LTC
4. **SUI TAV** es el mejor setup individual (+0.62%) — confirma edge de SUI/AVAX cluster
5. **Target failure** persiste: 47% TO rate es el drag secundario
6. **47% WR total** está OK pero el edge está mal distribuido (AVAX destruye valor)

| # | Cambio | Config antes → después | Net Taker Set A | Net Taker Set B | Conclusión |
|---|--------|------------------------|-----------------|-----------------|------------|
| 0 | Baseline | código actual | **-0.1066%** | — | AVAX TAV drag principal |
| 1 | l2_ratio_min 0.5→1.0 | guardia más estricta | **-0.1059%** | — | REVERTIDO: LTC mejor (+0.18→+0.32%) pero AVAX peor (-0.35→-0.43%). Neto neutral. Filter bloquea buenas señales AVAX. |
| 2 | concentration_min 0.40→0.50 | filtro absorción más estricto | **-0.0973%** | — | MEJORA +0.0093pp: LTC +0.18→+0.31 (+0.13pp), AVAX -0.35→-0.40 (-0.05pp), SUI +0.44→+0.45. Neto positivo. AVAX TAV sigue siendo el drag principal. |
| 3 | TAV SL tightening | TREND_UP 4→2.5%, TREND_DOWN 5→3%, BALANCE 4→2.5% | **+0.0455%** | — | 🎯 **GRAN MEJORA +0.143pp**: AVAX TAV -0.44→-0.19 (+0.25pp), LTC TAV +0.21→+0.38 (+0.17pp). PERO SUI TAV colapsa +0.62→+0.04 (-0.58pp, 92% perdido). SUI necesita SL más amplio. |
| 4 | TAV SL compromise | TREND_UP 2.5→3.0%, TREND_DOWN 3.0→3.5%, BALANCE 2.5→3.0% | **-0.0128%** | — | REVERTIDO: peor que iter 3 (-0.058pp). SUI recuperó +0.20pp pero AVAX perdió -0.12pp y LTC -0.03pp. El compromise no balancea bien. |
| 5 | FB targets tightening | 2.0/2.5% → 1.5/1.8% | **-0.0048%** | — | REVERTIDO: peor que iter 3 (-0.05pp). SUI FB destruida (WR cayó de 70% a 39.3%, -0.62pp). El MFE/MAE 0.55 indica que SUI FB ya no tenía edge. |
| 6 | l2_ratio_min_trend_down tightening | 2.0 → 2.5 | **+0.0128%** | — | REVERTIDO: peor que iter 3 (-0.033pp). Mejoró LTC marginalmente pero rompió SUI (-0.08pp) y AVAX (-0.015pp). Filtros estrictos en BEAR no ayudan con el desbalanceo de entrada. |

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

### 6. Configuración multi-asset confirmada
- Perfil VOLATIL_BAJO_FLOW agrupa LTC, AVAX, SUI correctamente
- Edge instrument-dependiente (3/10 coins con edge)
- SUI/AVAX/LTC validados como cluster

### 7. Liquidity Exhaustion y Trend Acceptance pendientes
- `liquidity_exhaustion` (47 señales) Net Taker -0.21% — necesita re-tuning
- `trend_acceptance` (98 señales) Net Taker -0.015% — borderline

---

## Recomendaciones para Futuras Iteraciones

1. **Empezar con l2_ratio_min**: 0.5 actual es bajo — probar 0.8-1.2 (riesgo bajo)
2. **concentration_min**: 0.40 puede ser muy permisivo — probar 0.45-0.55
3. **Per-regime targets**: Re-calibrar con datos de Set A multi-asset
4. **failed_breakout**: tp=2.0%/sl=2.5% ya validado, mantener
5. **No overfittear a 1 dataset** — siempre usar 14 datasets (6 LTC + 6 AVAX + 2 SUI)
6. **Métrica primary**: Net Taker global (no WR, no MFE/MAE)
7. **Validación cruzada**: Set B (LTC datos no usados) mide overfitting

---

## Pendiente Estructural (Fuera del Scope Paramétrico)

1. **TREND_DOWN LONG veto**: Prohibir LONGs en régimen DOWN (6% WR → tóxico)
2. **Reducir timeout rate**: ~60% de trades son timeouts (drag principal)
3. **Re-evaluar nombre**: TacticalAbsorptionV2 → InstitutionalFlowV2 (mediana 110 min, no es reversion micro)
4. **Síntesis MarketRegimeSensor**: Mejorar detección de TREND_DOWN estructural
