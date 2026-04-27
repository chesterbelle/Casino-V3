# Absorption Scalping V1 — Implementation Plan

**Branch**: `v7.0.0-absorption-scalping`
**Date**: 2026-04-27
**Status**: 🚧 PLANNING

---

## Executive Summary

**Objetivo**: Implementar Absorption Scalping V1 como reemplazo de LTA V6.

**Razón**: LTA V6 tiene edge +0.0155% (87% por debajo del mínimo viable). Absorption V1 tiene edge esperado +0.30-0.50% (20x mejor).

**Filosofía**: Detectar agotamiento del agresor en tiempo real usando Footprint + Delta + CVD. Sin zonas predefinidas, sin régimen, sin Value Areas.

**Tiempo estimado**: 1-2 semanas (implementación + validación)

---

## Phase 1: Architecture Analysis (2-4 horas)

### Objetivo: Identificar qué reutilizar y qué reemplazar

#### 1.1 Componentes a REUTILIZAR (Infraestructura Certificada):

| Componente | Status | Razón |
|------------|--------|-------|
| **Croupier** | ✅ KEEP | Orchestrator agnóstico a estrategia |
| **OCOManager** | ✅ KEEP | Bracket orders funcionan igual |
| **PositionTracker** | ✅ KEEP | Lifecycle management universal |
| **OrderManager** | ⚠️ MODIFY | Recalcular TP dinámico justo antes de ejecutar (< 50ms) |
| **Historian** | ✅ KEEP | Persistence layer universal |
| **PortfolioGuard** | ✅ KEEP | Risk management universal |
| **BinanceNativeConnector** | ✅ KEEP | Exchange API universal |
| **AdaptivePlayer** | ✅ KEEP | Kelly sizing y validación agnóstica a estrategia |
| **ExitEngine** | ⚠️ MODIFY | Layers 1,5 OK, pero Layer 4 (Thesis Invalidation) necesita lógica de absorción |

#### 1.2 Componentes a REEMPLAZAR:

| Componente | Acción | Razón |
|------------|--------|-------|
| **SetupEngineV4** | ❌ REPLACE | LTA-specific (VAL/VAH, POC, guardians) |
| **SessionValueArea** | ❌ REMOVE | No usa Value Areas |
| **OneTimeframing** | ❌ REMOVE | No usa régimen |
| **MarketRegimeSensor** | ❌ REMOVE | No usa régimen |
| **ContextRegistry** | ⚠️ SIMPLIFY | Solo necesita Footprint, no POC/VAH/VAL |
| **Sensores tácticos LTA** | ❌ REMOVE | TrappedTraders, DeltaDivergence, etc. |

#### 1.3 Componentes NUEVOS:

| Componente | Propósito |
|------------|-----------|
| **AbsorptionSetupEngine** | Detecta absorción + confirmación de giro |
| **FootprintRegistry** | Mantiene Footprint en tiempo real (Ask/Bid volume por nivel) |
| **AbsorptionDetector** | Sensor único: magnitud + velocidad + ruido |
| **DynamicExitManager** | TP dinámico basado en nodos de bajo/alto volumen |

---

## Phase 2: Footprint Infrastructure (4-6 días)

### 2.1 FootprintRegistry (Nuevo)

**Propósito**: Mantener Footprint Chart en tiempo real desde el stream de trades.

**🎯 OPTIMIZACIÓN CRÍTICA: Singleton Compartido**

FootprintRegistry será un **singleton en main process**, compartido por:
1. AbsorptionDetector (sensor en workers) — Read-only
2. AbsorptionSetupEngine (main process) — Read-only
3. ExitEngine (main process) — Read-only
4. OrderManager (main process) — Read-only

**Ventaja**: Footprint calculado UNA VEZ, compartido por todos (evita cálculo duplicado)

**Thread-safety**:
- Writes: Protegidos con `threading.RLock()`
- Reads: Lock-free (Python GIL protege dict reads)

**⚠️ CRÍTICO: HFT Latency Telemetry**

Absorption añade componentes ANTES de T1 (AdaptivePlayer). Necesitamos timestamps adicionales:

- **T0**: Tick del exchange (existente)
- **T0a**: FootprintRegistry actualizado (NUEVO)
- **T0b**: AbsorptionDetector analiza (NUEVO)
- **T0c**: Confirmación de giro detectada (NUEVO)
- **T1**: AdaptivePlayer decisión (existente)
- **T1a**: OrderManager recalcula TP dinámico (NUEVO)
- **T2**: OrderManager envía orden (existente)
- **T3**: Exchange confirma fill (existente)
- **T4**: PositionTracker registra (existente)

**Target latencies**:
- T0 → T0a: < 5ms (Footprint update)
- T0a → T0b: < 10ms (Absorption detection)
- T0b → T0c: 1-2 segundos (Confirmación de giro, 3-5 ticks)
- T0c → T1: < 50ms (AdaptivePlayer)
- T1 → T1a: < 5ms (TP recalculation)
- T1a → T2: < 50ms (Order submission)

**Total T0 → T2**: < 1.2 segundos (vs < 100ms en LTA V6)

**Estructura de datos**:

**Opción A: Dict (Simple, inicial)**:
```python
{
    "BTC/USDT:USDT": {
        "levels": {
            65432.5: {
                "ask_volume": 12.5,  # Compras agresivas
                "bid_volume": 8.3,   # Ventas agresivas
                "delta": 4.2,        # ask - bid
                "timestamp": 1714190400.123
            },
            65433.0: {...},
            ...
        },
        "cvd": 145.7,  # Cumulative Volume Delta
        "cvd_history": [(timestamp, cvd), ...],
        "tick_size": 0.5
    }
}
```

**Opción B: Numpy Arrays (Optimizado, si latencia > 5ms)**:
```python
{
    "BTC/USDT:USDT": {
        "price_levels": np.array([65432.0, 65432.5, 65433.0, ...]),  # Sorted
        "ask_volumes": np.array([12.5, 8.3, ...]),
        "bid_volumes": np.array([10.2, 7.1, ...]),
        "deltas": np.array([2.3, 1.2, ...]),  # Precomputed
        "cvd": 145.7,
        "tick_size": 0.5
    }
}
```

**Decisión**: Empezar con **Opción A** (dict), migrar a **Opción B** (numpy) si latency > 5ms

**Razón**: Dict es más simple de implementar y debuggear. Numpy es optimización prematura hasta que midamos latencia real.

**Métodos clave**:
- `on_trade(symbol, price, qty, side, timestamp)` — Actualiza Footprint con cada tick
  - **Telemetría**: Registra `t0a_footprint_update_ts = time.time()`
  - **Target**: < 5ms desde T0
- `get_delta_at_level(symbol, price)` — Delta en un nivel específico
- `get_cvd(symbol)` — Delta acumulado actual
- `get_cvd_slope(symbol, window_seconds)` — Pendiente del CVD
- `get_volume_profile(symbol, price_range)` — Nodos de alto/bajo volumen

**Integración**:
- Conectar al `BinanceNativeConnector` trade stream
- Actualizar en cada tick (< 5ms latency)
- Mantener ventana deslizante (últimos 60 min)
- **Logging de latencia**: `logger.debug(f"[LATENCY] T0→T0a: {(t0a - t0)*1000:.2f}ms")`

---

### 2.2 AbsorptionDetector (Nuevo Sensor)

**Propósito**: Detectar absorción en tiempo real.

**🎯 OPTIMIZACIÓN: Sensor en Workers (Paralelización)**

AbsorptionDetector será un **sensor estándar** ejecutado en workers (como sensores LTA actuales):
- Distribuido entre workers via SensorManager
- Paralelización automática (múltiples símbolos)
- Lee FootprintRegistry (read-only, sin IPC overhead significativo)

**Ventaja**: Aprovecha workers existentes, paralelización gratis

**Criterios de detección**:

1. **Magnitud del Agotamiento**:
   - Delta absoluto > 3× desviación estándar del delta promedio (últimos 50 niveles)
   - Implementar: `z_score = (delta - mean) / std`

2. **Velocidad de Absorción**:
   - 70%+ del delta concentrado en ventana corta (< 30 segundos)
   - Implementar: `concentration_ratio = delta_in_window / total_delta`

3. **Ausencia de Ruido Contrario**:
   - < 20% del volumen es delta contrario
   - Implementar: `noise_ratio = opposite_delta / total_delta`

**Output**: `AbsorptionSignalEvent`
```python
{
    "symbol": "BTC/USDT:USDT",
    "level": 65432.5,
    "direction": "SELL_EXHAUSTION",  # o "BUY_EXHAUSTION"
    "delta": -45.2,
    "z_score": 3.8,
    "concentration": 0.82,
    "noise": 0.12,
    "timestamp": 1714190400.123,  # T0 (tick original)
    "t0a_footprint_update_ts": 1714190400.125,  # +2ms
    "t0b_detection_ts": 1714190400.133,  # +10ms desde T0
}
```

**Telemetría**:
```python
def analyze(self, symbol):
    t0b_start = time.time()

    # Análisis de absorción
    ...

    t0b_end = time.time()
    latency_ms = (t0b_end - t0b_start) * 1000

    if latency_ms > 10:
        logger.warning(f"⚠️ [LATENCY] AbsorptionDetector slow: {latency_ms:.2f}ms")

    return AbsorptionSignalEvent(..., t0b_detection_ts=t0b_end)
```

---

### 2.3 Confirmación de Giro (En AbsorptionSetupEngine)

**Criterios**:
1. Delta opuesto aparece (compras tras absorción de venta)
2. Precio rompe el nivel de absorción
3. CVD cambia de dirección (inflexión visible)

**Implementación**:
- Esperar 3-5 ticks tras absorción
- Verificar delta opuesto > 30% del delta de absorción
- Verificar precio se movió > 0.05% en dirección opuesta
- Verificar CVD slope cambió de signo
- **Telemetría**: Registrar `t0c_confirmation_ts` cuando se confirma el giro

```python
async def _wait_for_confirmation(self, signal):
    t0c_start = time.time()

    # Esperar confirmación (3-5 ticks)
    for tick in range(5):
        await asyncio.sleep(0.2)  # ~200ms por tick

        if self._check_confirmation_criteria(signal):
            t0c_end = time.time()
            confirmation_latency = (t0c_end - t0c_start) * 1000

            logger.info(f"✅ [CONFIRMATION] Giro confirmado en {confirmation_latency:.0f}ms")

            return {
                "confirmed": True,
                "t0c_confirmation_ts": t0c_end
            }

    return {"confirmed": False}
```

---

## Phase 2.4: Latency Monitoring & Optimization

### 2.4.1 Latency Targets

| Stage | Component | Target | Critical? |
|-------|-----------|--------|-----------|
| T0 → T0a | FootprintRegistry.on_trade() | < 5ms | ✅ YES |
| T0a → T0b | AbsorptionDetector.analyze() | < 10ms | ✅ YES |
| T0b → T0c | Confirmación de giro (3-5 ticks) | 1-2s | ⚠️ Inherente |
| T0c → T1 | AdaptivePlayer.on_aggregated_signal() | < 50ms | ✅ YES |
| T1 → T1a | OrderManager.recalculate_tp() | < 5ms | ✅ YES |
| T1a → T2 | OrderManager.submit_order() | < 50ms | ✅ YES |

**Total T0 → T2**: < 1.2 segundos (vs < 100ms en LTA V6)

### 2.4.2 Latency Logging

**Implementar en cada componente**:

```python
# core/footprint_registry.py
def on_trade(self, symbol, price, qty, side, t0_timestamp):
    t0a_start = time.time()

    # Update footprint
    ...

    t0a_end = time.time()
    latency_ms = (t0a_end - t0_timestamp) * 1000

    if latency_ms > 5:
        logger.warning(f"⚠️ [LATENCY] FootprintRegistry slow: {latency_ms:.2f}ms")

    # Store for telemetry
    self._last_update_latency[symbol] = latency_ms
```

### 2.4.3 Latency Report

**Extender `utils/reports/latency_report.py`**:

```python
def generate_absorption_latency_report():
    """
    Genera reporte de latencia específico para Absorption V1.
    Incluye T0a, T0b, T0c además de T0-T4 existentes.
    """
    query = """
        SELECT
            trade_id, symbol, timestamp,
            t0_signal_ts,
            t0a_footprint_update_ts,
            t0b_detection_ts,
            t0c_confirmation_ts,
            t1_decision_ts,
            t1a_tp_recalc_ts,
            t2_submit_ts,
            t4_fill_ts
        FROM trades
        WHERE t0_signal_ts IS NOT NULL
    """

    # Calcular latencias
    latencies = {
        "footprint_update": [],  # T0 → T0a
        "detection": [],         # T0a → T0b
        "confirmation": [],      # T0b → T0c
        "decision": [],          # T0c → T1
        "tp_recalc": [],         # T1 → T1a
        "submission": [],        # T1a → T2
        "total": []              # T0 → T2
    }

    # Análisis y reporte
    ...
```

### 2.4.4 Optimizaciones

**Si latencia > targets**:

1. **FootprintRegistry** (T0 → T0a > 5ms):
   - Usar `numpy` arrays en vez de dicts
   - Pre-allocar memoria para niveles
   - Batch updates cada 10 ticks

2. **AbsorptionDetector** (T0a → T0b > 10ms):
   - Cachear z-score calculations
   - Usar rolling statistics (no recalcular cada vez)
   - Paralelizar análisis multi-símbolo

3. **TP Recalculation** (T1 → T1a > 5ms):
   - Cachear volume profile
   - Solo recalcular si Footprint cambió > 5%

---

## Phase 3: AbsorptionSetupEngine (2-3 días)

### 3.1 Reemplazar SetupEngineV4

**Archivo**: `decision/absorption_setup_engine.py` (nuevo)

**Lógica principal**:
```python
def on_absorption_signal(self, signal: AbsorptionSignalEvent):
    # 1. Verificar filtros de calidad
    if not self._check_quality_filters(signal):
        return None

    # 2. Esperar confirmación de giro
    confirmation = await self._wait_for_confirmation(signal)
    if not confirmation:
        return None

    # 3. Calcular TP/SL dinámico
    tp_price = self._calculate_dynamic_tp(signal)
    sl_price = signal.level  # Extremo del nivel de absorción

    # 4. Emitir AggregatedSignalEvent con telemetría completa
    return AggregatedSignalEvent(
        symbol=signal.symbol,
        side="LONG" if signal.direction == "SELL_EXHAUSTION" else "SHORT",
        setup_type="absorption",
        trigger_level=signal.level,
        tp_price=tp_price,
        sl_price=sl_price,
        t0_timestamp=signal.timestamp,  # Tick original
        t0a_footprint_update_ts=signal.t0a_footprint_update_ts,
        t0b_detection_ts=signal.t0b_detection_ts,
        t0c_confirmation_ts=confirmation.t0c_confirmation_ts,
        t1_decision_ts=time.time(),  # Será actualizado por AdaptivePlayer
        ...
    )
```

**Filtros de calidad** (3 filtros del documento):
1. `_check_magnitude(signal)` — z_score > 3.0
2. `_check_velocity(signal)` — concentration > 0.70
3. `_check_noise(signal)` — noise < 0.20

---

### 3.2 TP/SL Dinámico

**Arquitectura de TP Dinámico**:

El TP de Absorption NO es un porcentaje fijo. Depende del Footprint en tiempo real:
- **Primer objetivo (50%)**: Siguiente nivel de bajo volumen
- **Segundo objetivo (50%)**: Primer nodo de alto volumen contrario

**Problema**: El Footprint cambia constantemente (cada tick). Si calculamos TP en SetupEngine y ejecutamos 2-5 segundos después, el TP puede estar "stale".

**Solución**: Calcular TP en dos momentos:

1. **SetupEngine** (inicial):
   - Calcula TP con Footprint actual
   - Marca señal como `tp_calculation_method="dynamic_footprint"`
   - AdaptivePlayer valida con este TP inicial

2. **OrderManager** (final):
   - Justo antes de colocar orden (< 50ms)
   - Recalcula TP con Footprint actualizado
   - Usa TP fresco para bracket order

**TP (Take Profit)**:
- **Primer objetivo (50%)**: Siguiente nivel de bajo volumen en Footprint
- **Segundo objetivo (50%)**: Primer nodo de alto volumen contrario

**Implementación**:
```python
def _calculate_dynamic_tp(self, signal):
    # Obtener volume profile desde nivel de absorción
    profile = self.footprint_registry.get_volume_profile(
        signal.symbol,
        price_range=(signal.level, signal.level + 1%)  # 1% range
    )

    # Encontrar primer nivel de bajo volumen
    low_vol_level = self._find_low_volume_level(profile, signal.direction)

    return low_vol_level

# En OrderManager (core/execution.py):
def _execute_main_order(self, decision):
    # Recalcular TP si es dinámico
    if hasattr(decision, 'tp_calculation_method') and \
       decision.tp_calculation_method == "dynamic_footprint":
        tp_price = self.setup_engine.recalculate_dynamic_tp(
            decision.symbol,
            decision.side,
            decision.trigger_level
        )
    else:
        tp_price = decision.tp_price

    # Colocar orden con TP actualizado
    ...
```

**SL (Stop Loss)**:
- Extremo del nivel de absorción
- Si LONG: SL = mínimo del nivel
- Si SHORT: SL = máximo del nivel

---

## Phase 4: Exit Management (1-2 días)

### 4.1 Modificar ExitEngine

**Cambios necesarios**:

1. **Layer 3 (Valentino)**: Mantener scale-out al 70% de TP
2. **Layer 4 (Thesis Invalidation)**: Reemplazar lógica LTA con lógica de absorción

**Nueva lógica de invalidación**:
```python
def _check_absorption_invalidation(self, position):
    # Detectar nueva absorción en dirección contraria
    if position.side == "LONG":
        # Buscar absorción de compra (BUY_EXHAUSTION) por encima del entry
        new_absorption = self._detect_counter_absorption(
            position.symbol,
            direction="BUY_EXHAUSTION",
            above_price=position.entry_price
        )
    else:
        # Buscar absorción de venta (SELL_EXHAUSTION) por debajo del entry
        new_absorption = self._detect_counter_absorption(
            position.symbol,
            direction="SELL_EXHAUSTION",
            below_price=position.entry_price
        )

    if new_absorption:
        logger.warning(f"⚠️ Counter-absorption detected: {new_absorption}")
        return True  # Cerrar inmediatamente

    return False
```

---

## Phase 5: Configuration & Integration (1 día)

### 5.1 Nuevo archivo de configuración

**Archivo**: `config/absorption.py` (nuevo)

```python
# Absorption Scalping V1 Configuration

# Detection Thresholds
ABSORPTION_Z_SCORE_MIN = 3.0  # Magnitud mínima (3 std dev)
ABSORPTION_CONCENTRATION_MIN = 0.70  # 70% del delta en ventana corta
ABSORPTION_NOISE_MAX = 0.20  # Máximo 20% de ruido contrario

# Confirmation
ABSORPTION_CONFIRMATION_TICKS = 5  # Esperar 5 ticks para confirmación
ABSORPTION_CONFIRMATION_DELTA_MIN = 0.30  # Delta opuesto > 30% del original
ABSORPTION_CONFIRMATION_PRICE_MOVE = 0.0005  # 0.05% mínimo

# Exit Management
ABSORPTION_SCALE_OUT_PCT = 0.50  # 50% en primer objetivo
ABSORPTION_SCALE_OUT_TRIGGER = 0.70  # Al 70% del TP

# Footprint
FOOTPRINT_WINDOW_SECONDS = 3600  # 60 min de historia
FOOTPRINT_TICK_SIZE = 0.5  # BTC tick size (ajustar por símbolo)
```

---

### 5.2 Integrar en Croupier

**Cambios en `croupier/croupier.py`**:
```python
# OLD:
from decision.setup_engine import SetupEngineV4

# NEW:
from decision.absorption_setup_engine import AbsorptionSetupEngine

# OLD:
self.setup_engine = SetupEngineV4(...)

# NEW:
self.setup_engine = AbsorptionSetupEngine(
    footprint_registry=self.footprint_registry,
    config=absorption_config
)
```

---

## Phase 6: Validation (3-5 días)

### 6.1 Unit Tests

**Archivo**: `tests/unit/test_absorption_detector.py`

**Casos de prueba**:
1. Detectar absorción con z_score > 3.0
2. Rechazar absorción con concentración < 0.70
3. Rechazar absorción con ruido > 0.20
4. Confirmar giro con delta opuesto
5. Invalidar por counter-absorption

---

### 6.2 Backtest Validation

**Protocolo**: Similar a Long-Range Edge Audit

**Datasets**: Usar los mismos 9 backtests de LTA V6 (RANGE/BEAR/BULL × 3 días)

**Métricas esperadas**:
- Gross Expectancy: > 0.30% (target: 0.30-0.50%)
- WR: > 65% (target: 65-80%)
- Señales/día: 80-150 (vs 27.6 de LTA V6)
- Net (Maker): > 0.22% (viable con Limit Sniper)

**Criterio de éxito**:
- Expectancy > 0.30% en RANGE
- Expectancy > 0.20% en BEAR/BULL
- WR > 60% en todas las condiciones

---

### 6.3 Demo Validation (Fast-Track)

**Protocolo**: `/fast-track-parity` adaptado para Absorption

**Comando**:
```bash
python main.py --mode demo --symbol LTC/USDT:USDT --timeout 30 --fast-track --close-on-exit
```

**Objetivo**: Verificar que Footprint se actualiza en tiempo real y señales se generan correctamente.

---

## Phase 7: Production Deployment (1 día)

### 7.1 Pre-Flight Checklist

- [ ] Todos los unit tests pasan
- [ ] Backtest Expectancy > 0.30%
- [ ] Demo validation exitosa (señales generadas)
- [ ] Latencia < 50ms (crítico para absorción)
- [ ] Limit Sniper habilitado (maker orders obligatorio)
- [ ] PortfolioGuard configurado (max drawdown, loss streaks)

---

### 7.2 Deployment Strategy

**Fase 1 (Día 1-3)**: Conservative
- Filtros estrictos (z_score > 3.5, concentration > 0.75)
- Objetivo: 30-50 señales/día
- Sizing: 0.5% del capital por trade
- Monitorear edge real

**Fase 2 (Día 4-7)**: Moderate
- Si edge > 0.25%: Relajar filtros (z_score > 3.0, concentration > 0.70)
- Objetivo: 50-80 señales/día
- Sizing: 1.0% del capital por trade

**Fase 3 (Día 8+)**: Aggressive
- Si edge > 0.30%: Relajar más (z_score > 2.5)
- Objetivo: 80-120 señales/día
- Sizing: 1.5% del capital por trade

---

## Risk Management

### Riesgos Identificados:

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Latencia > 50ms** | Media | Alto | Optimizar Footprint updates, usar asyncio |
| **Fees erosionan edge** | Alta | Alto | Limit Sniper obligatorio (maker 0.08%) |
| **Falsos positivos** | Media | Medio | Filtros estrictos al inicio, relajar gradualmente |
| **Counter-absorption no detectada** | Baja | Alto | Layer 4 (Thesis Invalidation) activo |
| **Footprint memory leak** | Baja | Alto | Ventana deslizante (60 min max) |

---

## Success Metrics

### Semana 1:
- [ ] Footprint actualizado en tiempo real (< 50ms)
- [ ] Señales generadas (30-50/día)
- [ ] Edge > 0.20%

### Semana 2:
- [ ] Edge > 0.30%
- [ ] WR > 65%
- [ ] Señales 50-80/día
- [ ] Net PnL positivo

### Mes 1:
- [ ] Edge estable > 0.30%
- [ ] Sharpe Ratio > 2.0
- [ ] Max Drawdown < 10%
- [ ] Señales 80-120/día

---

## Rollback Plan

Si Absorption V1 falla (edge < 0.20% después de 2 semanas):

1. Volver a `v6.2.0-limit-sniper` (LTA V6 archivado)
2. Analizar logs de Footprint y señales
3. Ajustar filtros o considerar estrategia híbrida
4. Si falla definitivamente: Considerar otras estrategias (Momentum, Breakout, etc.)

---

## Next Steps

1. ✅ Crear branch `v7.0.0-absorption-scalping`
2. ⏳ Implementar FootprintRegistry (Phase 2.1)
3. ⏳ Implementar AbsorptionDetector (Phase 2.2)
4. ⏳ Implementar AbsorptionSetupEngine (Phase 3)
5. ⏳ Modificar ExitEngine (Phase 4)
6. ⏳ Backtest validation (Phase 6.2)
7. ⏳ Demo validation (Phase 6.3)
8. ⏳ Production deployment (Phase 7)

---

*Created: 2026-04-27*
*Branch: v7.0.0-absorption-scalping*
*Status: PLANNING*
