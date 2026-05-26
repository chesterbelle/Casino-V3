# Plan de Optimización — Capa de Hierro (v8.3)

> Auditoría de Baja Latencia y HPC sobre el código de ejecución crítica.
> Ramas objetivo: `v8.3-optimized`

---

## Fase 0: Quick Wins (Sin riesgo, alto impacto)

### 0.1 — Cache de `normalize_symbol()` en todas las capas

**Archivos**: `core/context_registry.py`, `core/feed.py`, `croupier/components/slim_exit_engine.py`

**Problema**: `normalize_symbol()` se llama 3-4 veces por tick en cada símbolo. Con 48 símbolos y ~100 ticks/segundo, son ~14,400 normalizaciones/segundo. Cada una hace split/replace de strings.

**Solución**: Cache LRU global con `functools.lru_cache(maxsize=200)` o dict manual.

```python
# utils/symbol_norm.py o un decorador global
from functools import lru_cache

@lru_cache(maxsize=256)
def normalize_symbol(symbol: str) -> str:
    # ... lógica existente ...
```

**Impacto**: Elimina ~99.9% de las llamadas redundantes. Costo: 0 (puro beneficio).

---

### 0.2 — Acumulador O(1) para Spread Average en `context_registry.py`

**Archivo**: `core/context_registry.py`, método `update_spread()`

**Problema**: `sum(state["history"])` en cada tick es O(n) con n=300. Se ejecuta por cada símbolo en cada order book update.

**Solución**: Mantener `_running_sum: float` por símbolo.

```python
# Estado actual (O(n) por tick):
avg = sum(state["history"]) / len(state["history"])

# Estado optimizado (O(1) por tick):
self._spread_running_sum[symbol] += new_spread
if len(history) > maxlen:
    removed = history.popleft()
    self._spread_running_sum[symbol] -= removed
avg = self._spread_running_sum[symbol] / len(history)
```

**Impacto**: Elimina O(48*symbols*300) sumas de float por segundo → O(48). **Top priority.**

---

### 0.3 — Acumulador O(1) para ATR en `context_registry.py`

**Archivo**: `core/context_registry.py`, método `on_candle()`

**Problema**: `sum(self.ranges_short[symbol])` en cada candle. O(n) con n=10.

**Solución**: Mismo patrón de running sum.

```python
self._atr_running_sum[symbol] += new_range
if len(self.ranges_short[symbol]) > maxlen:
    removed = self.ranges_short[symbol].popleft()
    self._atr_running_sum[symbol] -= removed
atr = self._atr_running_sum[symbol] / len(self.ranges_short[symbol])
```

**Impacto**: Elimina O(48*10) sumas de float por minuto → O(48).

---

### 0.4 — Welford Online Algorithm para VWAP Std Dev

**Archivo**: `core/context_registry.py`, método `update_vwap()`

**Problema**: Cada 100 ticks crea `sample_prices = [history[i][1] for i in range(0, len(history), step)]` (lista de ~500 elementos) y luego itera para calcular varianza.

**Solución**: Welford's online algorithm — actualiza media y varianza en O(1) por tick.

```python
class WelfordRunningStats:
    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self.M2 = 0.0

    def update(self, value: float):
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.M2 += delta * delta2

    def std(self) -> float:
        if self.count < 2:
            return 0.0
        return (self.M2 / (self.count - 1)) ** 0.5
```

**Impacto**: Elimina creación de lista temporal de 500 elementos y su iteración. Reduce presión de GC.

---

### 0.5 — Cache de `symbol → profile` en SlimExitEngine

**Archivo**: `croupier/components/slim_exit_engine.py`, método `_get_profile()`

**Problema**: Cada tick itera sobre `self.profiles.items()` (todos los perfiles, todos los assets) para cada posición abierta.

**Solución**: Cache en `__init__` o lazy cache.

```python
# En __init__ o primer llamado:
self._profile_cache: Dict[str, Dict] = {}

def _get_profile(self, symbol: str) -> Dict[str, Any]:
    symbol_norm = normalize_symbol(symbol)
    if symbol_norm in self._profile_cache:
        return self._profile_cache[symbol_norm]

    for name, profile in self.profiles.items():
        if name == "DEFAULT":
            continue
        if symbol_norm in profile.get("normalized_assets", []):
            self._profile_cache[symbol_norm] = profile
            return profile

    default = self.profiles.get("DEFAULT", {})
    self._profile_cache[symbol_norm] = default
    return default
```

**Impacto**: O(n*tick) → O(1) lookup después del primer tick.

---

## Fase 1: Control de Concurrencia (Riesgo bajo, impacto medio)

### 1.1 — Semáforo en `execution_process.py` pipe handler

**Archivo**: `core/execution_process.py`, línea ~119

**Problema**: `create_task()` sin límite. 1000 órdenes en ráfaga = 1000 tasks saturando el event loop.

**Solución**: `asyncio.Semaphore(N)` con N=10-20.

```python
class ExecutionProcess:
    def __init__(self):
        self._exec_semaphore = asyncio.Semaphore(10)

    async def _execute_request(self, request: ...):
        async with self._exec_semaphore:
            # ... lógica existente ...
```

**Impacto**: Previene saturación de memoria y starvation del event loop.

---

### 1.2 — Task Tracking con límite en `croupier.py`

**Archivo**: `croupier/croupier.py`

**Problema**: `create_task()` descontrolado en `_on_position_closed_cleanup`, `trigger_reconciliation_task`, y `_run_periodic_task`.

**Solución**: Set global de tareas + semáforo o flag de exclusión.

```python
# Patrón para tasks periódicos:
async def _run_periodic_task(self):
    if self._periodic_task_running:
        return
    self._periodic_task_running = True
    try:
        # ...
    finally:
        self._periodic_task_running = False
```

**Impacto**: Elimina acumulación de tasks no monitoreados.

---

### 1.3 — Flag anti-duplicado en SlimExitEngine reversal

**Archivo**: `croupier/components/slim_exit_engine.py`, línea ~112

**Problema**: Múltiples reversiones por tick lanzan múltiples `_execute_limit_close` para la misma posición.

**Solución**: Flag `_closing` en la posición (ya existe `_pending_terminations`, verificar cobertura).

**Impacto**: Previene cierres duplicados y tasks zombies.

---

## Fase 2: Reducción de Context Switches (Riesgo medio)

### 2.1 — Eliminar `await asyncio.sleep(0.1)` en `execution_process.py`

**Archivo**: `core/execution_process.py`, línea ~130

**Problema**: Context switch forzado cada 100ms sin razón. El pipe reader es event-driven.

**Solución**: Reemplazar con `await asyncio.Event().wait()` señalizado por el pipe reader.

```python
class ExecutionProcess:
    def __init__(self):
        self._work_event = asyncio.Event()

    async def _main_loop(self):
        while self._running:
            await self._work_event.wait()
            self._work_event.clear()
            # procesar cola de trabajo

    # Pipe reader señaliza:
    self._work_event.set()
```

**Impacto**: Elimina 10 context switches/segundo innecesarios.

---

### 2.2 — Hacer síncrono `_check_micro_z_reversal()` en `slim_exit_engine.py`

**Archivo**: `croupier/components/slim_exit_engine.py`, línea ~86

**Problema**: `await` en cada tick para cada posición activa (1000 awaits/segundo potenciales).

**Solución**: Separar el check (síncrono) del close (async).

```python
async def on_tick(self, event: TickEvent):
    # ... setup ...
    if profile["micro_z_reversal"]["enabled"]:
        if self._check_micro_z_reversal(position, profile):  # síncrono ahora
            continue

def _check_micro_z_reversal(self, position, profile) -> bool:  # sync
    # ... lógica existente sin await ...
```

**Impacto**: Elimina cientos de awaits/segundo en el hot path.

---

### 2.3 — Reducir timeout de lock de cierre a 100ms

**Archivo**: `core/portfolio/position_tracker.py`, línea ~506

**Problema**: `asyncio.timeout(2.0)` en lock de cierre. En HFT, 2s es una eternidad.

**Solución**: Reducir a 100ms para hot path y reintentar.

```python
async def lock_for_closure(self, trade_id: str) -> bool:
    try:
        async with asyncio.timeout(0.1):  # 100ms
            await self._closure_locks[trade_id].acquire()
            return True
    except asyncio.TimeoutError:
        self.logger.warning(f"Closure lock timeout for {trade_id}")
        return False
```

**Impacto**: Reduce bloqueo del event loop en contención de cierres de 2s a 100ms.

---

## Fase 3: Optimización de Memoria y GC (Riesgo alto, verificar)

### 3.1 — Template de dict de orden en `execution.py`

**Archivo**: `core/execution.py`, método `on_decision()`

**Problema**: Dict grande (~20 keys) + sub-dict `params` creado en cada decisión.

**Solución**: Template cacheado + `dict.update()` con solo campos variables.

```python
class OrderBuilder:
    _template: ClassVar[Dict] = {
        "symbol": None,
        "side": None,
        "type": "LIMIT",
        "quantity": None,
        "price": None,
        "timeInForce": "GTC",
        "params": {
            "positionSide": "BOTH",
            "reduceOnly": False,
            # ... resto de campos fijos ...
        }
    }

    @classmethod
    def build(cls, symbol, side, quantity, price, **overrides) -> Dict:
        payload = cls._template.copy()  # shallow copy ~ 20 punteros
        payload["symbol"] = symbol
        payload["side"] = side
        payload["quantity"] = quantity
        payload["price"] = price
        payload.update(overrides)
        return payload
```

**Impacto**: Reduce presión de GC. Shallow copy de dict pre-asignado vs creación completa desde cero.

---

### 3.2 — `__slots__` en `OpenPosition` dataclass

**Archivo**: `core/portfolio/position_tracker.py`

**Problema**: `OpenPosition` con 40+ campos. Cada instancia tiene overhead de `__dict__` (~40% más memoria).

**Solución**: Agregar `__slots__` para reducir footprint de memoria.

```python
@dataclass
class OpenPosition:
    __slots__ = (
        "trade_id", "symbol", "side", "entry_price",
        "entry_atr", "quantity", "timestamp", ...
    )
    # ... campos ...
```

**Impacto**: Reduce ~40% el uso de memoria por posición. Crítico si hay cientos de posiciones históricas en memoria.

---

### 3.3 — Sin lista temporal en HMAC signing

**Archivo**: `core/execution_process.py`, línea ~336

**Problema**: `sorted([(k, v) for k, v in payload.items()])` en cada orden.

**Solución**: Pre-definir orden canónico de parámetros.

```python
CANONICAL_PARAM_ORDER = [
    "symbol", "side", "type", "timeInForce",
    "quantity", "price", "positionSide",
    "reduceOnly", "newClientOrderId",
]

def _build_query_string(payload: Dict) -> str:
    return "&".join(
        f"{k}={payload[k]}" for k in CANONICAL_PARAM_ORDER if k in payload
    )
```

**Impacto**: Elimina creación de lista temporal y sorting O(n log n).

---

## Fase 4: I/O No Bloqueante

### 4.1 — Reemplazar `sqlite3` por `aiosqlite` en backtest_feed

**Archivo**: `core/backtest_feed.py`

**Problema**: `sqlite3.connect()` y `pd.read_sql_query()` sincrónicos dentro de `async def`.

**Solución**: `aiosqlite` para queries asincrónicas.

```python
import aiosqlite

async def load_data(self):
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute("SELECT * FROM signals")
        rows = await cursor.fetchall()
```

**Impacto**: No bloquea el event loop durante lecturas de BD. Esencial para backtests multi-símbolo.

---

### 4.2 — Logging asincrónico en `sensor_worker.py`

**Archivo**: `core/sensor_worker.py`

**Problema**: `FileHandler` sincrónico en worker de sensores (hot path).

**Solución**: `QueueHandler` + `QueueListener`.

```python
import logging.handlers

log_queue = queue.Queue()
queue_handler = logging.handlers.QueueHandler(log_queue)
listener = logging.handlers.QueueListener(
    queue_handler, logging.FileHandler("logs/sensors.log")
)
listener.start()
```

**Impacto**: Logging no bloqueante. El worker escribe a cola en memoria en O(1).

---

### 4.3 — Eliminar `print()` en hot paths

**Archivos**: `core/sensor_worker.py`, `core/execution_process.py`

**Problema**: `print()` sincrónico a stdout en hot path del worker.

**Solución**: Reemplazar con `logger.debug()` (o eliminar si es debug solo).

---

## Fase 5: Portfolio Guard — Ventana Deslizante O(1)

### 5.1 — Peak tracking incremental en `portfolio_guard.py`

**Archivo**: `core/portfolio/portfolio_guard.py`, método `_check_drawdown_velocity()`

**Problema**: Itera sobre TODO el deque de 720 items en cada balance update.

**Solución**: Mantener pico actualizado incrementalmente.

```python
def _update_balance(self, timestamp, balance):
    self._balance_history.append((timestamp, balance))

    # Actualizar peak incremental
    if balance > self._peak_in_window:
        self._peak_in_window = balance

    # Si el peak está expirando, recalcular (solo cuando expira)
    while (timestamp - self._balance_history[0][0]) > WINDOW_SECONDS:
        old_ts, old_balance = self._balance_history.popleft()
        if old_balance == self._peak_in_window:
            self._peak_in_window = max(b for _, b in self._balance_history)
```

**Impacto**: O(1) en el 99.9% de los casos, O(n) solo cuando expira el peak.

---

## Orden de Implementación Recomendado

```
Fase 0   → Inmediato (sin riesgo)
0.1, 0.2, 0.3, 0.4, 0.5

Fase 1   → Siguiente (bajo riesgo)
1.1, 1.2, 1.3

Fase 2   → Próximo (riesgo medio, requiere testing)
2.1, 2.2, 2.3

Fase 3   → Después (riesgo alto, verificar regresiones)
3.1, 3.2, 3.3

Fase 4   → Posterior (requiere dependencias externas)
4.1, 4.2, 4.3

Fase 5   → Final (aislado, sin dependencias)
5.1
```

---

## Métricas de Éxito

| Métrica | Antes | Después (estimado) |
|---------|-------|--------------------|
| Latencia promedio por tick (48 símbolos) | ~2-5ms | <1ms |
| Context switches/segundo | ~1500 | <200 |
| Presión de GC (obj creados/segundo) | ~5000 | <1000 |
| I/O bloqueante en hot path | 5 ubicaciones | 0 |
| Tasks no monitoreados | 10+ ubicaciones | 0 |
| Uso de memoria por posición | ~5-10KB | ~3-6KB |
