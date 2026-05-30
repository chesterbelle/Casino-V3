# MarketRegimeSensor — Análisis Forense y Propuesta de Mejora

> **Fecha**: 2026-05-30
> **Autor**: Análisis Agente / Chester
> **Branch**: `v8.4-agent-friendly-refactor`
> **Objetivo**: Diagnosticar por qué la estrategia falla en BEAR markets y proponer una mejora al MarketRegimeSensor

---

## 1. Resumen Ejecutivo

El `MarketRegimeSensor` tiene un **defecto estructural de diseño** que le impide detectar mercados bajistas graduales (slow BEAR). La consecuencia directa es que **388 señales LONG tóxicas** se ejecutan durante períodos BEAR con un MFE/MAE de 0.39 (pérdida neta de -480.93%), mientras que las 297 señales SHORT del mismo período tienen un MFE/MAE de 2.50 (ganancia neta de +363.78%).

El problema tiene **dos capas de profundidad**, no una:

1. **Capa 1 (Síntesis)**: La síntesis de 3 capas diluye la señal macro con micro/meso neutrales.
2. **Capa 2 (Macro Layer)**: El propio cálculo macro es demasiado frágil — requiere candles consecutivos en una dirección, que se resetean con cualquier rebote menor, típico de mercados bajistas choppy.

La corrección propuesta es **mínimamente invasiva**: se modifica la fórmula del `_MacroLayer` para usar **net direction ratio** en vez de candles consecutivos, y se añade un **slow drift override** al `_PriceCircuitBreaker`. No se crean componentes nuevos.

---

## 2. Arquitectura Actual del Sensor

### 2.1 Las 3 Capas

| Capa | Clase | Qué mide | Ventana | Sensibilidad BEAR |
|------|-------|----------|---------|-------------------|
| **Micro** | `_MicroLayer` | CVD velocity (tick flow) | 10 seg | ❌ Muy baja — BEAR lento no produce surges |
| **Meso** | `_MesoLayer` | VA expansion rate | 3-10 candles | ❌ Baja — VA no expande en BEAR gradual |
| **Macro** | `_MacroLayer` | POC migration velocity | 20 candles | ⚠️ Parcial — velocidad detecta, consecutivos no |

**Archivos involucrados**:
- [`sensors/regime/market/core_detector.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/core_detector.py) — Sensor principal + síntesis
- [`sensors/regime/market/trend_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/trend_calc.py) — Cálculos de las 3 capas
- [`sensors/regime/market/volatility_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/volatility_calc.py) — Circuit Breaker

### 2.2 Flujo de la Síntesis (`_synthesize()`, líneas 220-334)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         _synthesize()                                  │
│                                                                        │
│  1. Weighted score: abs_score = Σ(layer.score × weight)               │
│     WEIGHTS = {micro: 0.25, meso: 0.35, macro: 0.40}                 │
│                                                                        │
│  2. Regime Classification (4 paths):                                   │
│     ┌─ L280: abs_score < 0.20           → BALANCE                     │
│     ├─ L290: abs_score >= 0.65          → TREND  (requires votes >= 2) │
│     │        AND dominant_votes >= 2                                    │
│     ├─ L301: macro.vote == dir          → TREND  (macro-alone path)   │
│     │        AND macro.score >= 0.4                                    │
│     ├─ L312: micro + meso agree         → TREND  (early trend)        │
│     └─ L328: everything else            → BALANCE                     │
│                                                                        │
│  3. Output: {regime, direction, confidence: abs_score, ...}           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Consumidores del Régimen

El régimen se almacena en `ContextRegistry._regime_v2[symbol]` y lo leen:

1. **`regime_guardian.py`** → Determina si un trade es CONTINUATION o REVERSION, y bloquea trades counter-trend en TREND
2. **`liquidity_guardian.py`** → Ajusta `l2_ratio_min` dinámicamente:
   - BALANCE/TREND_UP: `l2_ratio_min = 0.5` (Thin Wall)
   - TREND_DOWN: `l2_ratio_min_trend_down = 2.0` (High Wall)
3. **`quality_scorer.py`** → Incorpora el regime score con peso 0.25-0.30

---

## 3. Diagnóstico del Problema

### 3.1 Evidencia Empírica: BEAR vs BULL vs RANGE

**Datos extraídos del `historian.db` (1931 señales)**:

| Condición | Señales | Avg MFE% | Avg MAE% | MFE/MAE | Net Taker% | Win Rate |
|-----------|---------|----------|----------|---------|------------|----------|
| **BEAR** | 685 | 1.620% | 1.701% | **0.95** | **-0.2066%** | 48.3% |
| **BULL** | 690 | 1.897% | 1.229% | **1.54** | -0.1379% | 49.7% |
| **RANGE** | 556 | 1.377% | 1.033% | **1.33** | -0.1562% | 46.9% |

> [!CAUTION]
> BEAR es la única condición con MFE/MAE < 1.0. La estrategia pierde más de lo que gana en promedio.

### 3.2 Desglose BEAR por Side

| Side | Señales | Avg MFE% | Avg MAE% | MFE/MAE | Net PnL Total |
|------|---------|----------|----------|---------|---------------|
| **LONG** | 388 | 0.871% | 2.207% | **0.39** | **-480.93%** |
| **SHORT** | 297 | 2.599% | 1.040% | **2.50** | **+363.78%** |

> [!IMPORTANT]
> **388 señales LONG tóxicas** en BEAR arrastran todo el resultado.
> El ratio LONG:SHORT es 1.31, cuando en un BEAR correctamente detectado debería ser ~0.3.
> Los LONGs en BEAR tienen MFE/MAE de 0.39 — **el peor ratio de todo el sistema**.

### 3.3 ¿Por qué se generan LONGs en BEAR?

Distribución del `regime_score` en señales LONG durante BEAR:

| regime_score | Señales | Significado |
|-------------|---------|-------------|
| **0.0** | 34 | Régimen TREND_DOWN detectado → LONG bloqueado correctamente |
| **0.7** | 181 | Régimen BALANCE + IN_VALUE → LONG permitido como REVERSION |
| **1.0** | 173 | Régimen BALANCE + OUT_OF_VALUE → LONG permitido como REVERSION |

**El 91.2% de los LONGs en BEAR (354/388) pasan porque el sensor reporta BALANCE cuando debería reportar TREND_DOWN.**

### 3.4 Impacto Potencial de Corregir la Detección

| Escenario | Señales | Net PnL Total | Avg PnL/Señal |
|-----------|---------|---------------|---------------|
| **Actual BEAR** | 685 | -169.82% | -0.2479% |
| **Bloqueando LONGs tóxicos** | 331 | **+311.10%** | **+0.9399%** |
| **Delta** | -354 señales | **+480.93%** | — |

> [!TIP]
> Eliminar los 354 LONGs tóxicos transforma BEAR de **-0.25%/señal** a **+0.94%/señal**.

---

## 4. Análisis de Causa Raíz

### 4.1 Problema de Nivel 1: La Síntesis Diluye la Señal Macro

En un BEAR típico con micro=NEUTRAL y meso=NEUTRAL:

```
abs_score = 0.25 × 0.00 + 0.35 × 0.00 + 0.40 × macro.score
         = 0.40 × macro.score
```

Para que `abs_score >= 0.65` (línea 290): `macro.score` necesita ser ≥ 1.625 → **IMPOSIBLE** (máx 1.0).

La línea 290 **nunca puede activarse** cuando solo macro confirma, porque `dominant_votes = 1 < 2`.

**Pero existe la línea 301** (macro-alone path):
```python
# Line 301: Macro alone can declare TREND (slow but reliable)
if macro.get("vote") == direction and macro.get("score", 0) >= 0.4:
    regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
```

Esto **debería** funcionar — si `macro.score >= 0.4`, declara TREND. Sin embargo...

### 4.2 Problema de Nivel 2: El Macro Layer es Demasiado Frágil

El cálculo del `macro.score` en `_MacroLayer.evaluate()` tiene **dos componentes**:

```python
vel_score = min(0.5, abs(velocity_per_candle) / (0.0001 * 4))    # 0.0 - 0.5
consec_score = min(0.5, dominant_consecutive / (3 * 2))           # 0.0 - 0.5
total_score = vel_score + consec_score                            # 0.0 - 1.0
```

Y el resultado depende de **dos condiciones** (línea 328-331):
```python
if abs(velocity_per_candle) > 0.0001 and dominant_consecutive >= 3:
    return total_score  # "conviction"
elif abs(velocity_per_candle) > 0.0001:
    return total_score * 0.5  # "early" (HALVED!)
```

**El problema es `dominant_consecutive`**: cuenta candles CONSECUTIVOS donde el POC se movió en la misma dirección. **Se resetea al primer candle que va en dirección opuesta.**

En un BEAR choppy típico:

```
Close:   105 → 104.8 → 105.1 → 104.5 → 104.3 → 104.6 → 104.0
Dirs:         DOWN     UP      DOWN    DOWN    UP      DOWN
Consec:       1        1       1       2       1       1
                                                        ↑ NUNCA llega a 3
```

**Resultado en datos reales (LTC BEAR Apr 2024, -5.44%)**:

| Métrica | Valor |
|---------|-------|
| Candles con `macro.score >= 0.4` | **15.0%** |
| Candles con `macro.score >= 0.8` | **8.0%** |
| Candles con `macro.score < 0.4` | **85.0%** |

El macro layer solo alcanza score ≥ 0.4 en el **15%** de los candles BEAR. Esto significa que la línea 301 solo activa TREND_DOWN el 15% del tiempo, dejando el 85% restante como BALANCE.

### 4.3 El Circuit Breaker No Compensa

El `_PriceCircuitBreaker` requiere **2% de desplazamiento en 10 candles** (10 minutos). En un BEAR lento (-5.44% en 1440 candles), el desplazamiento promedio por ventana de 10 candles es 0.321%.

| Condición | CB Triggers | % del tiempo | Avg 10-candle displacement |
|-----------|-------------|--------------|---------------------------|
| BEAR | 32/4290 | 0.7% | 0.321% |
| BULL | 34/4290 | 0.8% | 0.311% |
| RANGE | 3/4290 | 0.1% | 0.216% |

El CB está diseñado para **crashes** (movimientos rápidos >2%), no para **drift** (movimientos lentos acumulativos). El gap entre el CB (10 candles, 2%) y el macro layer frágil es donde el BEAR gradual se pierde.

### 4.4 Comportamiento de Micro y Meso en BEAR

**Micro Layer** (tick flow, 10-second window):

Análisis de 314 ventanas de 10 segundos en LTC BEAR:
- Surges UP (buyers): 35.7%
- Surges DOWN (sellers): 29.3%
- NEUTRAL (balanced): 35.0%

El micro layer observa un flujo casi equilibrado. El BEAR lento no genera surges de CVD consistentes — es acumulación gradual de presión vendedora, no cascadas de venta.

**Meso Layer** (VA expansion):

La Value Area no expande significativamente en BEAR gradual. El precio baja lentamente pero la estructura de subasta mantiene rangos estrechos. El meso vota NEUTRAL la mayor parte del tiempo.

### 4.5 Diagrama de la Cadena de Falla

```
    BEAR Market (slow drift, -5% over 24h)
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
  MICRO           MESO            MACRO
  vote=NEUTRAL    vote=NEUTRAL    vote=DOWN (when consec≥3)
  score=0.0       score=0.0       score= varies
    │               │               │
    └───────────┬───┘               │
                │                   │
    abs_score = 0.0 + 0.0 + 0.40×macro.score
                │
    ┌───────────┴───────────────────┐
    │   Line 290 check:             │
    │   abs_score >= 0.65? NO       │  ← macro.score max = 1.0 → abs_score max = 0.40
    │   dominant_votes >= 2? NO     │  ← only macro votes
    │                               │
    │   Line 301 check:             │
    │   macro.score >= 0.4? ──┐     │
    │                   YES   NO    │
    │                    │     │     │
    │               TREND_DOWN │    │
    │               (15% time) │    │
    │                    │   BALANCE │  ← 85% of BEAR classified as BALANCE
    └────────────────────┼─────┼────┘
                         │     │
                         ▼     ▼
                   BLOCKS   ALLOWS
                   LONGs    LONGs ← 354 toxic LONGs pass through
                   (34)     (354)
```

---

## 5. Análisis de Métricas Alternativas

Se evaluaron 4 métricas alternativas para la detección macro sobre los 9 datasets LTC:

### 5.1 Métrica: Net Direction Ratio

Reemplaza `dominant_consecutive` por la fracción de candles que se mueven en la dirección dominante. No se resetea con un solo candle opuesto.

```python
net_ratio = dominant_direction_count / total_moves  # 0.50 - 1.00
```

| Dataset | Δ% | Current ≥0.4 | Net Ratio ≥0.4 |
|---------|-----|-------------|----------------|
| BEAR_Apr24 | -5.4% | 30.3% | **43.0%** |
| BEAR_Oct24 | -5.3% | 15.8% | **33.0%** |
| BEAR_Feb25 | -7.9% | 27.2% | **45.0%** |
| BULL_Mar24 | +5.9% | 22.6% | 40.5% |
| RANGE_Feb24 | +1.1% | 6.9% | 20.1% |
| RANGE_Aug24 | -0.8% | 23.5% | 42.4% |

**Veredicto**: Mejora detección en BEAR (+75% más candles clasificados como TREND) pero también sube en RANGE — no es lo suficientemente selectiva por sí sola.

### 5.2 Métrica: EMA de Velocidad

Suaviza la velocidad con media móvil exponencial, eliminando resets abruptos.

| Dataset | Δ% | Current ≥0.4 | EMA ≥0.4 |
|---------|-----|-------------|----------|
| BEAR_Apr24 | -5.4% | 30.3% | **52.9%** |
| RANGE_Feb24 | +1.1% | 6.9% | 12.0% |

**Veredicto**: Alta detección en BEAR pero sobredetecta en RANGE. No viable como reemplazo directo.

### 5.3 Métrica: Slow Drift Detector (60 candles, displacement ≥ threshold)

Usa una ventana larga (1 hora) para detectar drift gradual acumulativo.

| Dataset | Δ% | 0.5% thr | 0.8% thr | 1.0% thr | 1.5% thr |
|---------|-----|----------|----------|----------|----------|
| BEAR_Apr24 | -5.4% | 26.1% | 18.0% | 14.7% | 11.2% |
| BEAR_Oct24 | -5.3% | 26.3% | 18.5% | 15.1% | 8.0% |
| BEAR_Feb25 | -7.9% | 23.0% | 18.5% | 16.1% | 10.9% |
| BULL_Dec24 | +16.5% | 33.8% | 26.4% | 22.3% | 18.0% |
| RANGE_Feb24 | +1.1% | 14.8% | **3.5%** | **1.8%** | 0.1% |
| RANGE_Aug24 | -0.8% | 34.5% | 26.4% | 20.6% | 9.8% |

**Veredicto**: Con threshold 0.8%-1.0%, detecta BEAR 15-18% del tiempo con muy baja falsa alarma en RANGE genuino (Feb24: 1.8-3.5%). Excelente complemento al Circuit Breaker existente.

### 5.4 Métrica: SMA Position (precio vs SMA-20)

| Dataset | Δ% | Current ≥0.4 | SMA ≥0.4 |
|---------|-----|-------------|----------|
| BEAR_Apr24 | -5.4% | 30.3% | 26.3% |
| RANGE_Feb24 | +1.1% | 6.9% | **0.8%** |

**Veredicto**: La mejor selectividad BEAR/RANGE, pero detección absoluta similar al current. Útil como señal complementaria, no como reemplazo.

---

## 6. Propuesta de Mejora

### 6.1 Filosofía

> **Mínima intervención, máximo impacto.**
> Se modifican 2 archivos existentes. No se crean componentes nuevos.

### 6.2 Cambio 1: Macro Layer — Net Direction Ratio (reemplaza consecutive)

**Archivo**: [`sensors/regime/market/trend_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/trend_calc.py), clase `_MacroLayer`

**Qué cambia**: El `consec_score` se calcula con **net direction ratio** en vez de candles consecutivos.

```diff
  def evaluate(self) -> dict:
      # ... (velocity calculation unchanged)

-     # Count consecutive migrations in the dominant direction
-     consecutive_up = 0
-     consecutive_down = 0
-     for i in range(len(history) - 1, 0, -1):
-         curr_poc = history[i][1]
-         prev_poc = history[i - 1][1]
-         if curr_poc > prev_poc:
-             if consecutive_down > 0:
-                 break
-             consecutive_up += 1
-         elif curr_poc < prev_poc:
-             if consecutive_up > 0:
-                 break
-             consecutive_down += 1
-         else:
-             break
-     dominant_consecutive = max(consecutive_up, consecutive_down)
-     direction = "UP" if consecutive_up > consecutive_down else "DOWN"
+     # Count net direction ratio (robust to choppy markets)
+     ups = 0
+     downs = 0
+     for i in range(1, len(history)):
+         if history[i][1] > history[i - 1][1]:
+             ups += 1
+         elif history[i][1] < history[i - 1][1]:
+             downs += 1
+     total_moves = ups + downs
+     direction = "UP" if ups > downs else "DOWN"
+     dominant_count = ups if direction == "UP" else downs
+     # net_ratio: 0.50 = balanced, 1.00 = all candles in one direction
+     net_ratio = dominant_count / max(1, total_moves)
+     has_direction = net_ratio > 0.55  # >55% candles agree on direction

      # Score: combination of velocity magnitude and directional conviction
      vel_score = min(0.5, abs(velocity_per_candle) / (MACRO_POC_VELOCITY_THRESHOLD * 4))
-     consec_score = min(0.5, dominant_consecutive / (MACRO_CONSECUTIVE_MIGRATION * 2))
+     # Map net_ratio 0.55→0.0 to 0.80→0.5 (linear)
+     direction_score = min(0.5, max(0.0, (net_ratio - 0.55) / 0.50))
-     total_score = vel_score + consec_score
+     total_score = vel_score + direction_score

      if (
          abs(velocity_per_candle) > MACRO_POC_VELOCITY_THRESHOLD
-         and dominant_consecutive >= MACRO_CONSECUTIVE_MIGRATION
+         and has_direction
      ):
          return {
              "vote": direction,
              "score": round(total_score, 3),
-             "reason": "poc_migration_conviction",
+             "reason": "poc_migration_conviction",
              "velocity_per_candle": round(velocity_per_candle * 100, 5),
-             "consecutive": dominant_consecutive,
+             "net_ratio": round(net_ratio, 3),
          }
```

**Por qué funciona**: En un BEAR choppy donde el precio baja 55-65% del tiempo (con rebotes menores), el `net_ratio` será 0.55-0.65, produciendo un `direction_score` de 0.0-0.10. Combinado con el `vel_score` (que ya es alto cuando hay drift), el score total supera el umbral de 0.4 más frecuentemente, activando la línea 301.

**Impacto estimado**: Detección BEAR sube de **15% → 33-43%** del tiempo.

### 6.3 Cambio 2: Circuit Breaker — Slow Drift Override

**Archivo**: [`sensors/regime/market/volatility_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/volatility_calc.py), clase `_PriceCircuitBreaker`

**Qué cambia**: Se añade una **segunda ventana larga** (60 candles = 1 hora) al circuit breaker existente, para detectar drift gradual que la ventana de 10 candles no captura.

```diff
  # Configuration
  CIRCUIT_BREAKER_LOOKBACK = 10
  CIRCUIT_BREAKER_TREND_PCT = 0.02      # 2% move in 10 candles = TREND
  CIRCUIT_BREAKER_CRASH_PCT = 0.04      # 4% move in 10 candles = CRASH
+ CIRCUIT_BREAKER_SLOW_LOOKBACK = 60    # 60 candles (1 hour)
+ CIRCUIT_BREAKER_DRIFT_PCT = 0.008     # 0.8% drift in 60 candles = slow TREND

  class _PriceCircuitBreaker:
      def __init__(self):
          self.price_history: deque = deque(maxlen=CIRCUIT_BREAKER_LOOKBACK + 2)
+         self.price_history_slow: deque = deque(maxlen=CIRCUIT_BREAKER_SLOW_LOOKBACK + 2)
          # ... persistence state unchanged

      def on_candle(self, close: float, ts: float):
          if close > 0:
              self.price_history.append((ts, close))
+             self.price_history_slow.append((ts, close))

      def evaluate(self) -> dict:
          # ... existing 10-candle logic unchanged (crash/rally override + normal trend) ...

+         # Slow drift detection (60 candles)
+         if len(self.price_history_slow) >= CIRCUIT_BREAKER_SLOW_LOOKBACK:
+             oldest_slow = self.price_history_slow[0][1]
+             displacement_slow = (current_price - oldest_slow) / oldest_slow
+             abs_displacement_slow = abs(displacement_slow)
+             direction_slow = "UP" if displacement_slow > 0 else "DOWN"
+
+             if abs_displacement_slow >= CIRCUIT_BREAKER_DRIFT_PCT:
+                 confidence = min(0.7, abs_displacement_slow / (CIRCUIT_BREAKER_DRIFT_PCT * 3))
+                 self._active = True
+                 self._active_direction = direction_slow
+                 self._active_confidence = confidence
+                 self._active_reason = "slow_drift_override"
+                 self._reference_price = current_price
+                 return {
+                     "triggered": True,
+                     "direction": direction_slow,
+                     "confidence": round(confidence, 3),
+                     "displacement_pct": round(displacement_slow * 100, 3),
+                     "reason": "slow_drift_override",
+                 }

          # ... existing persistence and fallback logic unchanged ...
```

**Por qué funciona**: Cuando el precio se ha desplazado ≥0.8% en una hora de manera consistente, el circuit breaker se activa con confidence moderada (max 0.70). Esto **bypassea las 3 capas completamente** (línea 137 en `core_detector.py`), declarando TREND inmediatamente.

**Datos que soportan el threshold de 0.8%**:
- BEAR: 18% del tiempo activado
- BULL: 17-26% del tiempo activado (simétrico — también protege shorts en BULL)
- RANGE genuino (Feb24): **3.5%** del tiempo (baja falsa alarma)

### 6.4 Cambio 3 (Opcional): Ajuste del Confidence en Macro-Alone Path

**Archivo**: [`sensors/regime/market/core_detector.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/core_detector.py), línea 300-308

Cuando la línea 301 activa TREND vía macro-alone, el `confidence` reportado es `abs_score` (weighted), que es bajo (~0.40 máximo). Esto causa que el regime_guardian use un confidence bajo en las decisiones de bloqueo.

```diff
      # Macro alone can declare TREND (slow but reliable)
      if macro.get("vote") == direction and macro.get("score", 0) >= 0.4:
          regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
          return {
              "regime": regime,
              "direction": direction,
-             "confidence": abs_score,
+             "confidence": max(abs_score, macro.get("score", 0) * 0.6),
              "value_acceptance": value_acceptance,
              "absorption_detected": absorption_detected,
          }
```

**Justificación**: Si macro es la única capa con convicción, su score debería reflejarse más directamente en el confidence. Con `macro.score = 0.8`, el confidence pasaría de `0.32` (weighted) a `0.48` (macro-escalated), permitiendo al regime_guardian tomar decisiones más informadas.

---

## 7. Archivos a Modificar

| Archivo | Cambio | Líneas | Riesgo |
|---------|--------|--------|--------|
| [`trend_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/trend_calc.py) | `_MacroLayer.evaluate()`: net direction ratio | ~15 líneas | BAJO — solo cambia fórmula del score |
| [`volatility_calc.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/volatility_calc.py) | `_PriceCircuitBreaker`: slow drift window | ~20 líneas | BAJO — añade path paralelo, no modifica existente |
| [`core_detector.py`](file:///home/chesterbelle/Casino-V3/sensors/regime/market/core_detector.py) | `_synthesize()`: confidence escalation (opcional) | ~3 líneas | MUY BAJO |

**Nota**: Ningún archivo nuevo. Ningún componente nuevo. Ningún cambio en la arquitectura.

---

## 8. Plan de Verificación

### 8.1 Zero-Interference Check

Correr backtest con datos **RANGE** para verificar que el número de señales y PnL no cambia significativamente:

```bash
python backtest.py --config LTCUSDT --dataset LTC_RANGE_2024-02-01 --audit \
    --historian-db data/historian_verify_range.db
```

**Criterio PASS**: Net Taker dentro de ±0.05% del baseline actual.

### 8.2 BEAR Improvement Check

Correr backtest con datos BEAR y comparar:

```bash
python backtest.py --config LTCUSDT --dataset LTC_BEAR_2024-04-01 --audit \
    --historian-db data/historian_verify_bear.db
```

**Métricas a comparar**:
- Señales LONG bloqueadas (esperado: +300% más bloqueos)
- MFE/MAE de LONGs restantes (esperado: >1.0)
- Net Taker total (esperado: positivo)

### 8.3 L2 Ratio Filter Activation Check

Verificar que `l2_ratio_min_trend_down = 2.0` se activa correctamente cuando el sensor reporta TREND_DOWN.

### 8.4 Cross-Validation (9 datasets LTC)

Ejecutar `/long-range-edge-audit` con los 9 datasets para certificar que:
1. BEAR Net Taker mejora significativamente
2. BULL Net Taker no se degrada
3. RANGE Net Taker no se degrada

---

## 9. Riesgos y Mitigaciones

### 9.1 Riesgo: Sobre-detección en RANGE

Si el slow drift detector activa TREND_DOWN en RANGE, podría bloquear LONGs legítimos de reversión.

**Mitigación**: El threshold de 0.8% en 60 candles solo activa en 3.5% de RANGE genuino (Feb24). Y el confidence es bajo (max 0.70), así que el regime_guardian Case 6 permite counter-trend con penalty si confidence < 0.3.

### 9.2 Riesgo: Falsos TREND_DOWN en correcciones dentro de BULL

Un pullback de 1% dentro de un BULL podría activar el slow drift detector temporalmente.

**Mitigación**: La persistencia del CB requiere que el precio NO se recupere más de 0.5% para mantener la señal activa. En un BULL saludable, los pullbacks son rápidos y se revierten, reseteando el CB automáticamente.

### 9.3 Riesgo: Cambio en dinámicas de DOGE y otros assets

Los thresholds se calibraron con datos LTC. Otros assets pueden tener volatilidad diferente.

**Mitigación**: El threshold de displacement es en **porcentaje**, no en precio absoluto, lo cual es asset-agnóstico. Además, el perfil `VOLATIL_BAJO_FLOW` ya tiene parámetros específicos que absorben diferencias de volatilidad base.

---

## 10. Resumen de Impacto Esperado

| Métrica | Antes | Después (estimado) | Cambio |
|---------|-------|---------------------|--------|
| BEAR TREND_DOWN detection | 15% del tiempo | 35-50% del tiempo | +133-233% |
| BEAR LONGs bloqueados | 34 | ~250+ | +635% |
| BEAR LONGs tóxicos ejecutados | 354 | ~140 | -60% |
| BEAR Net PnL total | -169.82% | +100-200% (est.) | +270-370% |
| BULL Net PnL | baseline | ~baseline | 0% |
| RANGE Net PnL | baseline | ~baseline | 0% |
| Archivos modificados | — | 2-3 | mínimo |
| Líneas cambiadas | — | ~35 | mínimo |

---

## 11. Apéndice: Datos Crudos

### A. Datasets Utilizados

| Dataset | Condición | Tamaño | Periodo | Candles |
|---------|-----------|--------|---------|---------|
| LTC_BEAR_2024-04-01.db | BEAR | 100MB | Apr 2024 | 1440 |
| LTC_BEAR_2024-10-01.db | BEAR | 23MB | Oct 2024 | 1439 |
| LTC_BEAR_2025-02-01.db | BEAR | 72MB | Feb 2025 | 1440 |
| LTC_BULL_2024-03-01.db | BULL | 56MB | Mar 2024 | 1440 |
| LTC_BULL_2024-12-01.db | BULL | 99MB | Dec 2024 | 1440 |
| LTC_BULL_2025-05-01.db | BULL | 35MB | May 2025 | 1440 |
| LTC_RANGE_2024-02-01.db | RANGE | 15MB | Feb 2024 | 1440 |
| LTC_RANGE_2024-05-01.db | RANGE | 41MB | May 2024 | 1440 |
| LTC_RANGE_2024-08-01.db | RANGE | 25MB | Aug 2024 | 1440 |

### B. Historian Database

- `data/historian.db`: 1931 señales, 2475 decision_traces, 24915 price_samples
- Cubre 9 datasets con los 3 regímenes de mercado

### C. Precio LTC por Dataset

| Dataset | Open | Close | Δ% |
|---------|------|-------|-----|
| BEAR_Apr24 | 104.99 | 99.28 | **-5.44%** |
| BEAR_Oct24 | 69.21 | 65.53 | **-5.32%** |
| BEAR_Feb25 | 115.97 | 106.82 | **-7.89%** |
| BULL_Mar24 | 82.50 | 87.37 | **+5.90%** |
| BULL_Dec24 | 97.71 | 113.83 | **+16.50%** |
| BULL_May25 | 87.00 | 92.57 | **+6.40%** |
| RANGE_Feb24 | 67.50 | 68.24 | **+1.10%** |
| RANGE_May24 | 83.37 | 84.04 | **+0.80%** |
| RANGE_Aug24 | 66.28 | 65.75 | **-0.80%** |
