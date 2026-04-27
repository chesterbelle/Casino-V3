# Absorption V1 — Architecture Analysis (Phase 1)

**Date**: 2026-04-27
**Branch**: `v7.0.0-absorption-scalping`
**Status**: 🔍 ANALYSIS

---

## Executive Summary

**Objetivo**: Analizar arquitectura actual para identificar:
1. Qué componentes reutilizar (infraestructura certificada)
2. Qué componentes modificar (adaptaciones menores)
3. Qué componentes reemplazar (LTA-specific)
4. Optimizaciones críticas (compartir Footprint, workers, latencia)

**Hallazgos clave**:
- ✅ **80% de infraestructura es reutilizable** (Croupier, OCO, Historian, etc.)
- ⚠️ **MarketProfile NO es Footprint** — Necesitamos nuevo componente
- ✅ **Workers ya existen** — Podemos paralelizar AbsorptionDetector
- ⚠️ **Footprint debe ser compartido** — Evitar cálculo duplicado
- ✅ **Telemetría T0-T4 ya existe** — Solo añadir T0a-T0c, T1a

---

## 1. Análisis de Componentes Existentes

### 1.1 Infraestructura Core (REUTILIZAR ✅)

| Componente | Archivo | Propósito | Absorption Compatible? |
|------------|---------|-----------|------------------------|
| **Croupier** | `croupier/croupier.py` | Orchestrator principal | ✅ YES — Agnóstico a estrategia |
| **OCOManager** | `croupier/components/oco_manager.py` | Bracket orders | ✅ YES — Funciona igual |
| **PositionTracker** | `core/portfolio/position_tracker.py` | Lifecycle management | ✅ YES — Universal |
| **OrderManager** | `core/execution.py` | Order submission | ⚠️ MODIFY — Añadir TP recalc |
| **Historian** | `core/historian.py` | Trade persistence | ✅ YES — Universal |
| **PortfolioGuard** | `core/portfolio/portfolio_guard.py` | Risk management | ✅ YES — Universal |
| **BinanceNativeConnector** | `exchanges/connectors/binance_native.py` | Exchange API | ✅ YES — Universal |
| **AdaptivePlayer** | `players/adaptive.py` | Kelly sizing + validation | ✅ YES — Agnóstico |
| **SensorManager** | `core/sensor_manager.py` | Worker orchestration | ✅ YES — Reutilizar workers |

**Conclusión**: Toda la infraestructura de ejecución es reutilizable. Solo necesitamos cambiar la lógica de detección de señales.

---

### 1.2 ContextRegistry (MODIFICAR ⚠️)

**Archivo**: `core/context_registry.py`

**Estado actual**:
- Mantiene POC/VAH/VAL (LTA-specific)
- Mantiene CVD y skewness (✅ útil para Absorption)
- Mantiene MarketProfile (solo volumen total, NO bid/ask separado)

**Cambios necesarios**:

#### Opción A: Extender ContextRegistry con Footprint
```python
class ContextRegistry:
    def __init__(self):
        # Existente
        self.profiles: Dict[str, MarketProfile] = {}
        self.micro_state: Dict[str, dict] = {}  # CVD, skewness

        # NUEVO: Footprint data
        self.footprint: Dict[str, FootprintData] = {}
```

**Ventaja**: Centralizado, fácil acceso
**Desventaja**: ContextRegistry se vuelve muy grande

#### Opción B: Crear FootprintRegistry separado (RECOMENDADO)
```python
# core/footprint_registry.py (NUEVO)
class FootprintRegistry:
    def __init__(self):
        self.footprints: Dict[str, FootprintData] = {}

    def on_trade(self, symbol, price, qty, side, timestamp):
        # Actualizar bid/ask volume por nivel
        ...
```

**Ventaja**: Separación de responsabilidades, más limpio
**Desventaja**: Un componente más

**Decisión**: **Opción B** — FootprintRegistry separado

**Razón**:
1. ContextRegistry ya es complejo (POC, VAH, VAL, CVD, skewness, ATR, etc.)
2. Footprint es específico de Absorption (no todas las estrategias lo necesitan)
3. Más fácil de testear y mantener

---

### 1.3 MarketProfile vs Footprint

**MarketProfile actual** (`core/market_profile.py`):
```python
self.profile: Dict[float, float] = {}  # price_level -> TOTAL volume
```

**Footprint necesario**:
```python
self.levels: Dict[float, dict] = {}  # price_level -> {ask_vol, bid_vol, delta}
```

**Diferencia crítica**:
- MarketProfile: Solo volumen total (no sabe si fue compra o venta)
- Footprint: Separa ask_volume (compras agresivas) y bid_volume (ventas agresivas)

**Conclusión**: **NO podemos reutilizar MarketProfile**. Necesitamos FootprintRegistry nuevo.

---

### 1.4 SensorManager & Workers (REUTILIZAR ✅)

**Archivo**: `core/sensor_manager.py`

**Arquitectura actual**:
- **Workers**: ProcessPoolExecutor con `SENSOR_WORKERS = max(2, cpu_count // 2)`
- **Distribución**: Round-robin de sensores entre workers
- **IPC**: Input queues (per worker) + Output queue (shared)
- **Capabilities**: Tick-aware workers, OB-aware workers

**Optimización identificada**:

#### Problema: Footprint calculado múltiples veces

Si AbsorptionDetector está en Worker 1 y ExitEngine necesita Footprint:
1. Worker 1 calcula Footprint → detecta absorción
2. ExitEngine (main process) necesita Footprint → ¿recalcula?

**Solución**: **FootprintRegistry en main process, compartido**

```
Main Process:
  ├─ FootprintRegistry (actualizado en cada tick)
  ├─ SensorManager
  │   ├─ Worker 1: AbsorptionDetector (lee FootprintRegistry)
  │   ├─ Worker 2: ...
  │   └─ Worker N: ...
  ├─ ExitEngine (lee FootprintRegistry)
  └─ AbsorptionSetupEngine (lee FootprintRegistry)
```

**Ventaja**: Footprint calculado UNA VEZ, compartido por todos
**Desventaja**: FootprintRegistry debe ser thread-safe

---

## 2. Optimizaciones Críticas

### 2.1 Compartir Footprint entre Componentes

**Componentes que necesitan Footprint**:
1. **AbsorptionDetector** (sensor) — Detecta absorción
2. **AbsorptionSetupEngine** — Calcula TP dinámico
3. **ExitEngine** — Invalidación por counter-absorption
4. **OrderManager** — Recalcula TP antes de ejecutar

**Problema**: Si cada uno calcula su propio Footprint → 4x latencia

**Solución**: **FootprintRegistry singleton en main process**

```python
# core/footprint_registry.py
class FootprintRegistry:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def on_trade(self, symbol, price, qty, side, timestamp):
        # Actualizar footprint (< 5ms target)
        ...
```

**Acceso desde workers**:
- Workers NO calculan Footprint
- Workers leen FootprintRegistry (read-only)
- Solo main process actualiza (write)

**Thread-safety**:
- Usar `threading.RLock()` para proteger writes
- Reads pueden ser lock-free (Python GIL protege dict reads)

---

### 2.2 Paralelización de AbsorptionDetector

**Opción A**: AbsorptionDetector como sensor en workers (actual)
```python
# sensors/absorption/absorption_detector.py
class AbsorptionDetector(BaseSensor):
    def calculate(self, candle_data):
        # Lee FootprintRegistry
        footprint = FootprintRegistry().get_footprint(symbol)
        # Analiza absorción
        ...
```

**Ventaja**: Usa workers existentes, paralelizado automáticamente
**Desventaja**: Workers necesitan acceso a FootprintRegistry (IPC overhead)

**Opción B**: AbsorptionDetector en main process (sin workers)
```python
# decision/absorption_setup_engine.py
class AbsorptionSetupEngine:
    def __init__(self):
        self.detector = AbsorptionDetector()

    async def on_tick(self, tick_event):
        # Detecta absorción en main process
        signal = self.detector.analyze(tick_event.symbol)
```

**Ventaja**: Acceso directo a FootprintRegistry (sin IPC)
**Desventaja**: No paralelizado, puede añadir latencia al main loop

**Decisión**: **Opción A** — AbsorptionDetector como sensor en workers

**Razón**:
1. Aprovecha workers existentes (ya certificados)
2. Paralelización gratis (múltiples símbolos)
3. IPC overhead es mínimo (FootprintRegistry es read-only para workers)

**Implementación**:
```python
# Worker lee FootprintRegistry via shared memory o pickle
# Main process actualiza FootprintRegistry en cada tick
```

---

### 2.3 Latencia de Footprint Update

**Target**: < 5ms por tick

**Optimizaciones**:

#### 1. Usar numpy arrays en vez de dicts
```python
# ANTES (dict):
self.levels[price] = {"ask_vol": 10.5, "bid_vol": 8.3}

# DESPUÉS (numpy):
self.price_levels = np.array([...])  # Sorted prices
self.ask_volumes = np.array([...])
self.bid_volumes = np.array([...])
```

**Ventaja**: 5-10x más rápido para lookups y cálculos
**Desventaja**: Más complejo de mantener

#### 2. Pre-allocar memoria
```python
# Pre-allocar 1000 niveles (±0.5% desde precio actual)
self.max_levels = 1000
self.price_levels = np.zeros(self.max_levels)
self.ask_volumes = np.zeros(self.max_levels)
self.bid_volumes = np.zeros(self.max_levels)
```

**Ventaja**: Sin allocations dinámicas (más rápido)
**Desventaja**: Memoria fija (pero solo ~24KB por símbolo)

#### 3. Batch updates cada N ticks
```python
# En vez de actualizar en cada tick:
self.pending_updates = []

def on_trade(self, ...):
    self.pending_updates.append((price, qty, side))

    if len(self.pending_updates) >= 10:
        self._flush_updates()  # Batch update
```

**Ventaja**: Reduce overhead de locking
**Desventaja**: Footprint ligeramente stale (10 ticks = ~100ms)

**Decisión**: **Usar numpy + pre-allocación** (sin batching)

**Razón**: Absorption necesita Footprint actualizado en tiempo real. Batching añade latencia inaceptable.

---

## 3. Modos de Operación (Backtest/Demo/Live)

### 3.1 Backtest Mode

**Diferencias vs Demo/Live**:
1. **Ticks**: Reproducidos desde CSV (no real-time)
2. **Timestamps**: Simulados (market time, no wall time)
3. **Footprint**: Debe ser determinístico (mismo input → mismo output)

**Implicaciones para FootprintRegistry**:

```python
class FootprintRegistry:
    def __init__(self, mode="live"):
        self.mode = mode
        self.use_wall_time = (mode == "live")

    def on_trade(self, symbol, price, qty, side, timestamp):
        # En backtest: usar timestamp del tick (market time)
        # En live: usar time.time() (wall time)
        ts = timestamp if not self.use_wall_time else time.time()

        # Actualizar footprint
        ...
```

**Ventana deslizante**:
- **Live**: Mantener últimos 60 min (wall time)
- **Backtest**: Mantener últimos 60 min (market time)

**Pruning**:
```python
def _prune_old_data(self, symbol, current_time):
    cutoff = current_time - 3600  # 60 min

    # Remover niveles antiguos
    for level in list(self.footprints[symbol].levels.keys()):
        if self.footprints[symbol].levels[level]["last_update"] < cutoff:
            del self.footprints[symbol].levels[level]
```

---

### 3.2 Demo vs Live

**Diferencias**:
- Demo: Testnet (balance virtual, órdenes simuladas)
- Live: Mainnet (dinero real)

**Footprint**: Idéntico en ambos (mismo stream de ticks)

**Telemetría**: Idéntica (T0-T4 + T0a-T0c + T1a)

---

## 4. Componentes a Reemplazar

### 4.1 SetupEngineV4 → AbsorptionSetupEngine

**Archivo actual**: `decision/setup_engine.py` (1,200 líneas)

**LTA-specific logic**:
- `_evaluate_lta_structural()` — Detecta touch de VAL/VAH
- `_check_poc_migration()` — Guardian 2
- `_check_va_integrity()` — Guardian 3
- `_check_failed_auction()` — Guardian 4 (deprecated)
- `_check_delta_divergence()` — Guardian 5
- `_check_regime_alignment()` — Guardian 1

**Absorption logic** (nuevo):
- `on_absorption_signal()` — Recibe señal de AbsorptionDetector
- `_check_quality_filters()` — 3 filtros (magnitud, velocidad, ruido)
- `_wait_for_confirmation()` — Espera giro (3-5 ticks)
- `_calculate_dynamic_tp()` — TP basado en Footprint

**Decisión**: **Crear AbsorptionSetupEngine nuevo** (no modificar SetupEngineV4)

**Razón**:
1. SetupEngineV4 tiene 1,200 líneas de lógica LTA
2. Más limpio crear nuevo que refactorizar
3. Mantiene LTA V6 intacto en `v6.2.0-limit-sniper` (rollback fácil)

---

### 4.2 Sensores Tácticos LTA → AbsorptionDetector

**Sensores actuales** (LTA-specific):
- `FootprintTrappedTraders` — Detecta trapped traders en VAL/VAH
- `FootprintDeltaDivergence` — Divergencia de delta vs precio
- `FootprintStackedImbalance` — Imbalances apilados
- `FootprintPOCRejection` — Rechazo del POC
- `FootprintVolumeExhaustion` — Exhaustion en extremos
- `TacticalSinglePrintReversion` — Single prints
- `TacticalVolumeClimaxReversion` — Volume climax

**Total**: 7 sensores tácticos

**Absorption**: **1 sensor único** — `AbsorptionDetector`

**Razón**: Absorption detecta UN patrón (agotamiento del agresor), no múltiples patrones.

**Decisión**: **Crear AbsorptionDetector nuevo, deshabilitar sensores LTA**

---

### 4.3 SessionValueArea → ¿Mantener o Eliminar?

**Archivo**: `sensors/footprint/session.py`

**Propósito**: Calcula POC/VAH/VAL por sesión (Asian, London, NY)

**¿Absorption lo necesita?**: ❌ NO

**Razón**: Absorption no usa zonas predefinidas (opera en cualquier nivel)

**Decisión**: **Deshabilitar en config** (no eliminar código)

```python
# config/sensors.py
ACTIVE_SENSORS = {
    "SessionValueArea": False,  # Disabled for Absorption
    "AbsorptionDetector": True,  # NEW
    ...
}
```

---

### 4.4 MarketRegimeSensor → ¿Mantener o Eliminar?

**Archivo**: `sensors/regime/market_regime_sensor.py`

**Propósito**: Detecta TREND_UP/TREND_DOWN/BALANCE/TRANSITION

**¿Absorption lo necesita?**: ❌ NO

**Razón**: Absorption es agnóstico al régimen

**Decisión**: **Deshabilitar en config** (no eliminar código)

**Ventaja**: Si Absorption falla, podemos volver a LTA sin reescribir código

---

## 5. Arquitectura Propuesta

### 5.1 Diagrama de Flujo

```
Exchange (Binance)
  ↓ Tick Stream
BinanceNativeConnector
  ↓ TickEvent
FootprintRegistry (Main Process)
  ├─ on_trade() → Actualiza bid/ask volume por nivel (< 5ms)
  ├─ get_footprint() → Read-only access
  └─ get_volume_profile() → Nodos de alto/bajo volumen
  ↓
SensorManager
  ├─ Worker 1: AbsorptionDetector
  │   ├─ Lee FootprintRegistry
  │   ├─ Detecta absorción (z-score, concentration, noise)
  │   └─ Emite AbsorptionSignalEvent
  ├─ Worker 2: ...
  └─ Worker N: ...
  ↓
AbsorptionSetupEngine (Main Process)
  ├─ on_absorption_signal()
  ├─ _check_quality_filters() → 3 filtros
  ├─ _wait_for_confirmation() → 3-5 ticks
  ├─ _calculate_dynamic_tp() → Lee FootprintRegistry
  └─ Emite AggregatedSignalEvent
  ↓
AdaptivePlayer
  ├─ Valida señal (RR, notional)
  ├─ Calcula sizing (Kelly)
  └─ Emite DecisionEvent
  ↓
OrderManager
  ├─ recalculate_tp() → Lee FootprintRegistry (< 5ms)
  └─ Envía orden al exchange
  ↓
OCOManager → PositionTracker → Historian
```

---

### 5.2 Componentes Nuevos

| Componente | Archivo | Propósito | Latency Target |
|------------|---------|-----------|----------------|
| **FootprintRegistry** | `core/footprint_registry.py` | Mantiene bid/ask volume por nivel | < 5ms/tick |
| **AbsorptionDetector** | `sensors/absorption/absorption_detector.py` | Detecta absorción | < 10ms |
| **AbsorptionSetupEngine** | `decision/absorption_setup_engine.py` | Confirmación + TP dinámico | < 50ms |

---

### 5.3 Componentes Modificados

| Componente | Archivo | Cambio | Razón |
|------------|---------|--------|-------|
| **OrderManager** | `core/execution.py` | Añadir `recalculate_tp()` | TP dinámico antes de ejecutar |
| **ExitEngine** | `croupier/components/exit_engine.py` | Layer 4: Counter-absorption | Invalidación por nueva absorción |
| **SensorManager** | `core/sensor_manager.py` | Registrar AbsorptionDetector | Nuevo sensor |

---

## 6. Estimación de Esfuerzo Revisada

### Fase Original vs Realidad

| Fase | Estimación Original | Estimación Revisada | Razón |
|------|---------------------|---------------------|-------|
| **Phase 2: Footprint Infrastructure** | 3-5 días | **4-6 días** | Numpy optimization + thread-safety |
| **Phase 3: AbsorptionSetupEngine** | 2-3 días | **3-4 días** | Confirmación asíncrona compleja |
| **Phase 4: Exit Management** | 1-2 días | **2-3 días** | Counter-absorption detection |
| **Phase 5: Configuration** | 1 día | **1 día** | Sin cambios |
| **Phase 6: Validation** | 3-5 días | **4-6 días** | Más tests de latencia |
| **Phase 7: Deployment** | 1 día | **1-2 días** | Monitoreo de latencia |
| **TOTAL** | **11-17 días** | **15-22 días** | **~3 semanas** |

---

## 7. Riesgos Identificados

### 7.1 Latencia de FootprintRegistry

**Riesgo**: Actualizar Footprint en cada tick puede añadir > 5ms latencia

**Mitigación**:
1. Usar numpy arrays (5-10x más rápido)
2. Pre-allocar memoria (sin allocations dinámicas)
3. Profiling con `cProfile` antes de deployment
4. Si latencia > 5ms → considerar batching (10 ticks)

**Probabilidad**: Media
**Impacto**: Alto (Absorption necesita Footprint fresco)

---

### 7.2 IPC Overhead (Workers ↔ FootprintRegistry)

**Riesgo**: Workers necesitan leer FootprintRegistry → IPC overhead

**Mitigación**:
1. FootprintRegistry como singleton (shared memory)
2. Workers leen sin locking (Python GIL protege)
3. Si overhead > 10ms → mover AbsorptionDetector a main process

**Probabilidad**: Baja
**Impacto**: Medio

---

### 7.3 Confirmación de Giro (1-2 segundos)

**Riesgo**: Esperar 3-5 ticks añade 1-2 segundos de latencia

**Mitigación**:
1. Usar `asyncio.sleep()` (no bloquea main loop)
2. Timeout de 2 segundos (si no confirma → descartar señal)
3. Monitorear % de señales confirmadas vs descartadas

**Probabilidad**: Alta (inherente al diseño)
**Impacto**: Bajo (es parte de la estrategia)

---

## 8. Próximos Pasos

### 8.1 Decisiones Pendientes

1. ✅ **FootprintRegistry**: Singleton en main process (decidido)
2. ✅ **AbsorptionDetector**: Sensor en workers (decidido)
3. ✅ **SetupEngine**: Crear nuevo AbsorptionSetupEngine (decidido)
4. ⏳ **Numpy vs Dict**: ¿Usar numpy arrays o dicts para Footprint?
5. ⏳ **Batching**: ¿Batch updates cada 10 ticks o update en cada tick?

### 8.2 Implementación Recomendada

**Orden sugerido**:
1. **FootprintRegistry** (4-6 días)
   - Implementar con dicts primero (más simple)
   - Profiling de latencia
   - Si latencia > 5ms → migrar a numpy
2. **AbsorptionDetector** (2-3 días)
   - Como sensor en workers
   - Unit tests con Footprint mock
3. **AbsorptionSetupEngine** (3-4 días)
   - Confirmación asíncrona
   - TP dinámico
4. **ExitEngine** (2-3 días)
   - Counter-absorption detection
5. **Validation** (4-6 días)
   - Backtest con 9 datasets
   - Latency profiling
6. **Deployment** (1-2 días)
   - Demo validation
   - Production rollout

**Total**: 16-24 días (~3-4 semanas)

---

## 9. Conclusiones

### 9.1 Viabilidad

✅ **SÍ, es viable implementar Absorption V1**

**Razones**:
1. 80% de infraestructura es reutilizable
2. Workers ya existen (paralelización gratis)
3. Telemetría T0-T4 ya existe (solo añadir T0a-T0c, T1a)
4. Footprint es el único componente crítico nuevo

### 9.2 Optimizaciones Críticas

1. ✅ **FootprintRegistry singleton** — Compartido entre componentes
2. ✅ **AbsorptionDetector en workers** — Paralelización
3. ✅ **Numpy arrays** — 5-10x más rápido que dicts
4. ✅ **Pre-allocación** — Sin allocations dinámicas

### 9.3 Tiempo Estimado

**Conservador**: 3-4 semanas (16-24 días)
**Optimista**: 2-3 semanas (11-17 días)

**Recomendación**: Planificar para **3 semanas** (buffer para imprevistos)

---

*Analysis Date: 2026-04-27*
*Branch: v7.0.0-absorption-scalping*
*Status: ANALYSIS COMPLETE*
