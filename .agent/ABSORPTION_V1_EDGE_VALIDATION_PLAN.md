# Absorption V1 - Plan de Verificación de Edge

## Objetivo

Validar y optimizar Absorption Scalping V1 hasta lograr **Gross Expectancy > 0.12%** (viable con Limit Sniper) usando protocolos existentes con rondas iterativas de ajustes.

---

## Baseline Esperado vs LTA V6

### LTA V6 (Long-Range 2024)
- **Gross Expectancy:** +0.0155% ❌ (87% por debajo del mínimo viable)
- **Win Rate:** 53.1%
- **Señales:** 248 (9 días)
- **Problema:** Edge insuficiente, opera en trending markets

### Absorption V1 (Expectativa)
- **Gross Expectancy Target:** > 0.12% ✅ (mínimo viable con Limit Sniper)
- **Win Rate Target:** > 55%
- **Señales esperadas:** 150-300/día (3-5x más que LTA)
- **Ventaja:** Agnóstico a régimen, captura giros institucionales

---

## Fase 1: Baseline Validation (Día 1)

### Objetivo
Establecer baseline de Absorption V1 sin optimizaciones.

### Protocolo: Edge Audit (Single Day)

**Dataset:** `tests/validation/ltc_24h_audit.csv` (2026-04-12, RANGE)

**Comando:**
```bash
# 1. Activar Absorption V1 en config
# config/sensors.py: ACTIVE_SENSORS["AbsorptionDetector"] = True

# 2. Ejecutar backtest con audit mode
.venv/bin/python backtest.py \
  --dataset tests/validation/ltc_24h_audit.csv \
  --audit \
  --bet-size 0.01 \
  > .absorption_v1_baseline.txt 2>&1

# 3. Analizar edge
.venv/bin/python utils/setup_edge_auditor.py data/historian.db \
  > .absorption_v1_edge_baseline.txt 2>&1
```

**Métricas a capturar:**
- Gross Expectancy (%)
- Win Rate (%)
- MFE/MAE Ratio
- Número de señales
- Timeouts (%)
- Rejection reasons (CVD flattening, price holding, TP distance)

**Criterios de éxito:**
- ✅ Gross Expectancy > 0.00% (positivo)
- ✅ Señales > 20 (suficiente sample size)
- ✅ Win Rate > 45%

**Si falla:** Proceder a Fase 2 (Diagnóstico)

---

## Fase 2: Diagnóstico Profundo (Día 1-2)

### Objetivo
Identificar causas raíz de edge negativo o insuficiente.

### Protocolo: Deep Strategy Analysis

**Comando:**
```bash
# Análisis detallado de señales
.venv/bin/python utils/analysis/deep_strategy_analysis.py \
  --db data/historian.db \
  --strategy AbsorptionScalpingV1 \
  > .absorption_v1_deep_analysis.txt 2>&1
```

**Análisis a realizar:**

#### 1. Rejection Analysis
- ¿Cuántas señales rechazadas por CVD flattening?
- ¿Cuántas rechazadas por price holding?
- ¿Cuántas rechazadas por TP distance?
- **Acción:** Relajar thresholds si rejection rate > 70%

#### 2. TP/SL Analysis
- MFE promedio vs TP distance
- MAE promedio vs SL distance
- ¿TP demasiado ambicioso? (MFE < TP)
- ¿SL demasiado ajustado? (MAE > SL)
- **Acción:** Ajustar TP/SL ranges basado en MFE/MAE real

#### 3. Timeout Analysis
- ¿Qué % de trades timeout?
- ¿Timeouts ocurren cerca del TP? (MFE > 50% del TP)
- **Acción:** Reducir TP si timeouts > 40%

#### 4. Direction Bias
- ¿Sesgo LONG vs SHORT?
- ¿Win Rate diferente por dirección?
- **Acción:** Ajustar filtros si sesgo > 70/30

#### 5. Quality Filters
- Z-score promedio de señales ganadoras vs perdedoras
- Concentration promedio de ganadoras vs perdedoras
- Noise promedio de ganadoras vs perdedoras
- **Acción:** Ajustar thresholds de calidad

**Output esperado:**
- Lista priorizada de ajustes (Top 3)
- Expectativa de mejora por ajuste

---

## Fase 3: Ronda 1 de Ajustes (Día 2-3)

### Objetivo
Implementar Top 3 ajustes identificados en diagnóstico.

### Ajustes Candidatos (basado en experiencia LTA V6)

#### Ajuste 1A: Reducir TP Distance (si MFE < TP)
**Problema:** TP demasiado ambicioso, timeouts altos
**Cambio:** `config/absorption.py`
```python
# Antes
ABSORPTION_MIN_TP_DISTANCE_PCT = 0.10  # 0.10%
ABSORPTION_MAX_TP_DISTANCE_PCT = 0.50  # 0.50%

# Después
ABSORPTION_MIN_TP_DISTANCE_PCT = 0.08  # 0.08% (más conservador)
ABSORPTION_MAX_TP_DISTANCE_PCT = 0.25  # 0.25% (alineado con MFE real)
```

#### Ajuste 1B: Relajar CVD Flattening (si rejection > 50%)
**Problema:** CVD slope threshold demasiado estricto
**Cambio:** `decision/absorption_setup_engine.py`
```python
# Antes
self.cvd_slope_threshold = 5.0

# Después
self.cvd_slope_threshold = 10.0  # Más permisivo
```

#### Ajuste 1C: Relajar Price Holding (si rejection > 30%)
**Problema:** Precio se mueve demasiado rápido
**Cambio:** `decision/absorption_setup_engine.py`
```python
# Antes
distance_pct < 0.05  # 0.05%

# Después
distance_pct < 0.10  # 0.10% (más permisivo)
```

#### Ajuste 1D: Ajustar SL Buffer (si MAE > SL)
**Problema:** SL demasiado ajustado, stops prematuros
**Cambio:** `decision/absorption_setup_engine.py`
```python
# Antes
self.sl_buffer_multiplier = 1.5

# Después
self.sl_buffer_multiplier = 2.0  # Más espacio
```

#### Ajuste 1E: Aumentar Quality Filters (si noise alto en perdedoras)
**Problema:** Señales de baja calidad generan pérdidas
**Cambio:** `sensors/absorption/absorption_detector.py`
```python
# Antes
self.min_z_score = 3.0
self.min_concentration = 0.70
self.max_noise = 0.20

# Después
self.min_z_score = 3.5  # Más estricto
self.min_concentration = 0.75  # Más estricto
self.max_noise = 0.15  # Más estricto
```

### Protocolo de Testing

**Para cada ajuste:**
```bash
# 1. Implementar cambio
# 2. Ejecutar backtest
.venv/bin/python backtest.py \
  --dataset tests/validation/ltc_24h_audit.csv \
  --audit \
  > .absorption_v1_round1_adjustX.txt 2>&1

# 3. Analizar edge
.venv/bin/python utils/setup_edge_auditor.py data/historian.db \
  > .absorption_v1_edge_round1_adjustX.txt 2>&1

# 4. Comparar vs baseline
# - Gross Expectancy: ¿mejoró?
# - Win Rate: ¿mejoró?
# - Señales: ¿se mantiene sample size?
```

**Criterio de aceptación:**
- ✅ Gross Expectancy mejora > 0.02%
- ✅ Win Rate mejora > 2%
- ✅ Señales > 15 (mínimo sample size)

**Si mejora:** Mantener ajuste, proceder al siguiente
**Si empeora:** Revertir ajuste, probar alternativa

---

## Fase 4: Long-Range Validation (Día 3-4)

### Objetivo
Validar ajustes en múltiples condiciones de mercado.

### Protocolo: Long-Range Edge Audit

**Datasets:** 9 días (RANGE/BEAR/BULL × 3 días cada uno)

**Comando:**
```bash
# Ejecutar audit en 9 datasets
for dataset in \
  tests/validation/ltc_range_2024-08-14.csv \
  tests/validation/ltc_range_24h.csv \
  tests/validation/ltc_range_2024-08-16.csv \
  tests/validation/ltc_bear_2024-09-05.csv \
  tests/validation/ltc_bear_24h.csv \
  tests/validation/ltc_bear_2024-09-07.csv \
  tests/validation/ltc_bull_2024-10-13.csv \
  tests/validation/ltc_bull_24h.csv \
  tests/validation/ltc_bull_2024-10-15.csv
do
  echo "Testing $dataset..."
  .venv/bin/python backtest.py --dataset $dataset --audit
done

# Análisis agregado
.venv/bin/python utils/analysis/per_condition_audit.py \
  --db data/historian.db \
  --strategy AbsorptionScalpingV1 \
  > .absorption_v1_long_range_round1.txt 2>&1
```

**Métricas a capturar:**
- Gross Expectancy por condición (RANGE/BEAR/BULL)
- Win Rate por condición
- Señales por condición
- Overall Gross Expectancy

**Criterios de éxito:**
- ✅ Overall Gross Expectancy > 0.12% (viable)
- ✅ RANGE Gross Expectancy > 0.15% (mejor condición)
- ✅ BEAR/BULL Gross Expectancy > 0.00% (no negativo)
- ✅ Overall Win Rate > 55%

**Si falla:** Proceder a Fase 5 (Ronda 2 de Ajustes)

---

## Fase 5: Ronda 2 de Ajustes (Día 4-5)

### Objetivo
Ajustes específicos por condición de mercado (si necesario).

### Ajustes Candidatos (Avanzados)

#### Ajuste 2A: Regime-Aware Filters
**Problema:** Absorption V1 opera igual en RANGE/BEAR/BULL
**Cambio:** Agregar filtro de régimen en `AbsorptionDetector`
```python
# Rechazar señales en TREND_UP/TREND_DOWN (solo operar en BALANCE)
regime = context_registry.get_regime(symbol)
if regime in ["TREND_UP", "TREND_DOWN"]:
    return None  # Skip absorption signals in trending markets
```

#### Ajuste 2B: Dynamic TP Based on Volatility
**Problema:** TP fijo no se adapta a volatilidad
**Cambio:** Ajustar TP range basado en ATR o spread
```python
# Si volatilidad alta → TP más amplio
# Si volatilidad baja → TP más ajustado
volatility_multiplier = calculate_volatility_multiplier(symbol)
max_tp_distance = 0.25 * volatility_multiplier
```

#### Ajuste 2C: Confirmation Timeout
**Problema:** Señales stale (precio se movió después de absorption)
**Cambio:** Agregar timeout entre detección y confirmación
```python
# Rechazar señales si pasaron > 10 segundos desde absorption
time_since_absorption = timestamp - signal["timestamp"]
if time_since_absorption > 10.0:
    return None  # Signal too old
```

#### Ajuste 2D: Volume Threshold
**Problema:** Absorption en volumen bajo no es confiable
**Cambio:** Agregar filtro de volumen mínimo
```python
# Rechazar si volumen total < threshold
total_volume = sum(ask_vol + bid_vol for _, ask_vol, bid_vol in profile)
if total_volume < MIN_VOLUME_THRESHOLD:
    return None  # Insufficient volume
```

### Protocolo de Testing
Mismo que Ronda 1, pero con Long-Range Audit completo para cada ajuste.

---

## Fase 6: Optimization & Fine-Tuning (Día 5-6)

### Objetivo
Fine-tuning de parámetros para maximizar edge.

### Grid Search de Parámetros

**Parámetros a optimizar:**
1. `min_z_score`: [3.0, 3.5, 4.0]
2. `min_concentration`: [0.70, 0.75, 0.80]
3. `max_noise`: [0.15, 0.20, 0.25]
4. `cvd_slope_threshold`: [5.0, 10.0, 15.0]
5. `min_tp_distance_pct`: [0.08, 0.10, 0.12]
6. `max_tp_distance_pct`: [0.20, 0.25, 0.30]

**Comando:**
```bash
# Script de grid search (crear si no existe)
.venv/bin/python utils/optimization/absorption_grid_search.py \
  --datasets tests/validation/ltc_range_*.csv \
  --param min_z_score 3.0,3.5,4.0 \
  --param min_concentration 0.70,0.75,0.80 \
  --param max_noise 0.15,0.20,0.25 \
  --metric gross_expectancy \
  > .absorption_v1_grid_search.txt 2>&1
```

**Output esperado:**
- Mejor combinación de parámetros
- Gross Expectancy esperado con parámetros óptimos

---

## Fase 7: Final Validation (Día 6-7)

### Objetivo
Validación final con parámetros optimizados.

### Protocolo: Full Validation Suite

**1. Long-Range Edge Audit (9 días)**
```bash
# Ejecutar con parámetros optimizados
.venv/bin/python utils/analysis/per_condition_audit.py \
  --db data/historian.db \
  --strategy AbsorptionScalpingV1 \
  > .absorption_v1_final_validation.txt 2>&1
```

**2. Generalized Edge Audit (múltiples símbolos)**
```bash
# Validar en SOL, ETH, BTC (si hay datos)
for symbol in SOL ETH BTC; do
  .venv/bin/python backtest.py \
    --dataset tests/validation/${symbol,,}_24h_audit.csv \
    --audit
done
```

**3. Stress Test (chaos conditions)**
```bash
# Validar en crash/pump extremos
.venv/bin/python backtest.py \
  --dataset tests/validation/ltc_bear_24h_v2.csv \
  --audit
```

**Criterios de certificación:**
- ✅ Overall Gross Expectancy > 0.12% (CERTIFIED)
- ✅ RANGE Gross Expectancy > 0.15%
- ✅ BEAR/BULL Gross Expectancy > 0.00%
- ✅ Overall Win Rate > 55%
- ✅ MFE/MAE Ratio > 1.2
- ✅ Señales > 150 (9 días)

**Si pasa:** Proceder a Phase 8 (Production Deployment)
**Si falla:** Volver a Fase 5 (Ronda 3 de Ajustes)

---

## Fase 8: Production Readiness (Día 7)

### Objetivo
Preparar Absorption V1 para producción.

### Checklist

#### 1. Configuration
- [ ] Crear `config/absorption.py` con parámetros optimizados
- [ ] Actualizar `config/sensors.py` con `ACTIVE_SENSORS["AbsorptionDetector"] = False` (disabled by default)
- [ ] Documentar parámetros en `docs/strategies/absorption_scalping_v1.md`

#### 2. Documentation
- [ ] Actualizar `memory.md` con resultados finales
- [ ] Crear `ABSORPTION_V1_CERTIFICATION.md` con métricas
- [ ] Actualizar `ROADMAP.md` con Absorption V1 status

#### 3. Safety Checks
- [ ] Verificar que `--fast-track` bypasea correctamente
- [ ] Verificar que `--audit` registra señales
- [ ] Verificar que PortfolioGuard funciona con Absorption V1
- [ ] Verificar que ExitEngine counter-absorption funciona

#### 4. Demo Testing
- [ ] Ejecutar demo session (15 min) con Absorption V1 activado
- [ ] Verificar que genera señales orgánicas
- [ ] Verificar latencia < 50ms en TP recalculation
- [ ] Verificar que counter-absorption exits funcionan

---

## Matriz de Decisión por Ronda

### Baseline (Fase 1)

| Gross Expectancy | Win Rate | Acción |
|------------------|----------|--------|
| > 0.12% | > 55% | ✅ SKIP a Fase 4 (Long-Range) |
| 0.05% - 0.12% | > 50% | ⚠️ Fase 2 (Diagnóstico) → Fase 3 (Ajustes leves) |
| 0.00% - 0.05% | > 45% | ⚠️ Fase 2 → Fase 3 (Ajustes moderados) |
| < 0.00% | < 45% | ❌ Fase 2 → Fase 3 (Ajustes agresivos) |

### Ronda 1 (Fase 3)

| Mejora Expectancy | Mejora WR | Acción |
|-------------------|-----------|--------|
| > +0.05% | > +5% | ✅ Fase 4 (Long-Range) |
| +0.02% - +0.05% | +2% - +5% | ⚠️ Fase 4 (Long-Range con cautela) |
| < +0.02% | < +2% | ❌ Fase 5 (Ronda 2) |
| Negativa | Negativa | ❌ Revertir ajuste, probar alternativa |

### Long-Range (Fase 4)

| Overall Expectancy | RANGE Expectancy | Acción |
|--------------------|------------------|--------|
| > 0.12% | > 0.15% | ✅ Fase 6 (Optimization) |
| 0.08% - 0.12% | > 0.10% | ⚠️ Fase 5 (Ronda 2 - ajustes finos) |
| < 0.08% | < 0.10% | ❌ Fase 5 (Ronda 2 - ajustes agresivos) |

### Ronda 2 (Fase 5)

| Overall Expectancy | Acción |
|--------------------|--------|
| > 0.12% | ✅ Fase 6 (Optimization) |
| 0.08% - 0.12% | ⚠️ Fase 6 (Optimization conservador) |
| < 0.08% | ❌ Ronda 3 o ABORT |

### Final Validation (Fase 7)

| Criterios | Acción |
|-----------|--------|
| Todos ✅ | ✅ CERTIFIED → Fase 8 (Production) |
| 1-2 ❌ | ⚠️ Ronda 3 (ajustes específicos) |
| 3+ ❌ | ❌ ABORT - Revisar arquitectura |

---

## Criterios de ABORT

**Abortar Absorption V1 si:**
1. Después de Ronda 3, Overall Expectancy < 0.08%
2. Win Rate < 45% consistentemente
3. Señales < 10/día (insuficiente frecuencia)
4. MFE/MAE Ratio < 1.0 (no hay edge estructural)
5. Timeouts > 60% (TP inalcanzable)

**Acción si ABORT:**
- Revisar arquitectura fundamental (¿FootprintRegistry correcto?)
- Considerar estrategia alternativa (Imbalance Scalping, Stacked Imbalance)
- Volver a LTA V6 con optimizaciones

---

## Timeline Estimado

| Fase | Duración | Días Acumulados |
|------|----------|-----------------|
| Fase 1: Baseline | 4-6 horas | Día 1 |
| Fase 2: Diagnóstico | 4-6 horas | Día 1-2 |
| Fase 3: Ronda 1 | 8-12 horas | Día 2-3 |
| Fase 4: Long-Range | 6-8 horas | Día 3-4 |
| Fase 5: Ronda 2 | 8-12 horas | Día 4-5 |
| Fase 6: Optimization | 6-8 horas | Día 5-6 |
| Fase 7: Final Validation | 4-6 horas | Día 6-7 |
| Fase 8: Production | 2-4 horas | Día 7 |
| **TOTAL** | **42-62 horas** | **7 días** |

---

## Herramientas Necesarias

### Existentes ✅
- `backtest.py` - Backtesting engine
- `utils/setup_edge_auditor.py` - Edge analysis
- `utils/analysis/per_condition_audit.py` - Multi-condition analysis
- `.agent/workflows/edge-audit.md` - Edge audit protocol
- `.agent/workflows/long-range-edge-audit.md` - Long-range protocol

### A Crear 🔧
- `utils/analysis/deep_strategy_analysis.py` - Deep diagnostic tool (si no existe)
- `utils/optimization/absorption_grid_search.py` - Grid search optimizer
- `config/absorption.py` - Absorption V1 configuration file

---

## Métricas de Éxito Final

### Mínimo Viable (WATCH)
- Gross Expectancy: 0.08% - 0.12%
- Win Rate: 50% - 55%
- Net (Maker): -0.02% - +0.02%

### Certificado (CERTIFIED)
- Gross Expectancy: > 0.12%
- Win Rate: > 55%
- Net (Maker): > +0.02%
- MFE/MAE Ratio: > 1.2

### Excelente (EXCELLENT)
- Gross Expectancy: > 0.20%
- Win Rate: > 60%
- Net (Maker): > +0.10%
- MFE/MAE Ratio: > 1.5

---

**Fecha:** 2026-04-27
**Autor:** Kiro Agent
**Status:** PLAN APROBADO - LISTO PARA EJECUCIÓN
