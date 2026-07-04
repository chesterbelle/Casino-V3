# Propuesta Tecnica: Solucion Unificada Eradicacion de Contaminacion por Estado Acumulativo

> **Autor**: Analisis Profundo post-memory + analisis_contaminacion_indicadores.md
> **Fecha**: 2026-07-02
> **Branch Target**: `dev-8.9-datafeed-revamp`
> **Estado**: Propuesta Tecnica Pendiente de Aprobacion

---

## 1. Resumen Ejecutivo

### El Problema

Los datasets mensuales continuo generan resultados radicalmente distintos a los diarios aislados, **a pesar de contener la misma data subyacente**:

| Metrica | Daily (24h aislado) | Monthly (30 dias cont) | Delta |
|---------|---------------------|------------------------|-------|
| Net Taker (LTC) | **+0.1915%** | **-0.4754%** | -0.67% |
| Señales trend_acceptance | 36 | 119 | +230% |
| Win Rate trend_acceptance | **58.3%** | **15.1%** | -43.2 pp |
| Entry Quality (ta) | TARGETS OK | ENTRY FAILURE | Degradacion total |

**Hipotesis Validada**: Los indicadores de estado acumulativo (`MarketProfile` 8h, `CVD` sesionado, `VWAP` 120min, z-scores) arrastran informacion residual entre dias en flujo continuo. Esto crea un **Simulation Leak** que hace que los parametros optimizados en datasets diarios (aislados) se comporten de forma degradada en Live y en backtests mensuales.

### La Solucion

**SessionBoundaryReset (SBR)**: Un mecanismo determinista de reset de estado acumulativo que actua en funcion del timestamp de mercado, obligando a que el modo Live y el Monthly Backtest emulen con total fidelidad el comportamiento de los Daily Datasets donde se entreno el edge.

---

## 2. Diagnostico Tecnico Detallado

### 2.1 Componentes con Estado Acumulativo (Auditoria Completa)

| Componente | Archivo | Estado Acumulado | Ventana/Reset Actual | Impacto en Contaminacion |
|-----------|---------|-------------------|---------------------|-------------------------|
| `MarketProfile` | `core/market_profile.py` | `profile`, `total_volume`, `_tick_log` | Rolling 28,800s (8h), poda automatica en `add_trade()` | **ALTO**: El rolling de 8h permite que volumen del dia anterior influya hasta las 08:00 UTC del dia siguiente |
| `SensorManager.cvd_state` | `core/sensor_manager.py:81` | `cvd_state[symbol]`, `tick_history` | Poda manual 5 seg en `_dispatch_micro_state()` | **MEDIO**: El CVD acumulativo en `cvd_state` no tiene reset diario; la poda de 5s solo evita overflow, no limpia carga inercial |
| `CoinOrderFlowEngine` | `core/order_flow/engine.py` | `current_cvd`, `cvd_session`, `cvd_history`, `velocity/concentration/noise_zscore`, `price_history`, `price_returns` | Auto-reset CVD session cada 4h (`14400s`); z-scores no se resetean | **ALTO**: Los z-scores estadisticos (`RollingZScore`) arrastran distribuciones del dia anterior; el reset de 4h no coincide con UTC midnight |
| `ContextRegistry.vwap` | `core/context_registry.py:460-516` | `vwap_history`, `vwap_accumulators`, `_vwap_residuals` | Rolling 120 minutos, poda por cutoff | **MEDIO** : El VWAP en realidad solo mantiene 2h de data; el problema es que arranca con estado residual sin filtrado de outliers del dia anterior |
| `TrendAcceptanceDetector` | `decision/scenarios/confirmation/trend_acceptance.py` | `active_breakouts`, `last_fire_ts` | Cleanup manual > 3600s | **BAJO**: El estado de breakouts activos puede arrastrar interrupciones incompletas, aunque el impacto es menor que los anteriores |
| `RollingZScore` (micro) | `core/sensor_manager.py:101` | Historia de 120 muestras del CVD | Reinicializar explicitamente | **MEDIO**: Los z-scores estadisticos se calibran sobre 120 muestras; si cruzan la medianoche mantiene la distribucion del dia pasado |

### 2.2 Test de Aislamiento Definitivo (TEST Days)

Se extrajeron 4 dias del mensual de Mayo 2026 (dias 1, 10, 15, 20) como datasets aislados:

| Dia | TEST day aislado (trend_acceptance) | Misma fecha en monthly |
|-----|------------------------------------|------------------------|
| Mayo 1 | 0 señales | ~4 señales |
| Mayo 10 | 0 señales | ~4 señales |
| Mayo 15 | 0 señales | ~4 señales |
| Mayo 20 | 0 señales | ~4 señales |

**Conclusion**: En el monthly, `trend_acceptance` genera señales que NO existen cuando el mismo dia se ejecuta aislado. La diferencia radica en que los indicadores llevan dias acumulandose.

### 2.3 Root Cause Causal

```
Daily Dataset (aislado):
  00:00 UTC → MarketProfile.reset() → profile vacio, total_volume=0
  00:00 UTC → cvd_state=0, tick_history vacio
  00:00 UTC → VWAP arranca de cero, sin residuales
  → Resultado: Entorno CONTROLADO, edge validado (+0.19% Net)

Monthly / Live (continuo):
  Dia N: MarketProfile tiene 8h de acumulacion del dia anterior
  Dia N: cvd_state arrastra delta de las 23:59 del dia N-1
  Dia N: VWAP mantiene window de 120min (bueno), pero los residuales del dia N-1 se suman
  Dia N: z-scores estadisticos heredan distribucion del dia anterior
  → Resultado: Entorno CONTAMINADO, edge degrada (-0.47% Net)
```

---

## 3. Propuesta: SessionBoundaryReset (SBR)

### 3.1 Diseno Filosofico

> **Principio**: Los parametros fueron optimizados en un entorno donde cada dia comienza de cero (Daily Dataset). La solucion NO debe re-optimizar en Monthly, sino hacer que Monthly y Live se comporten EXACTAMENTE como una secuencia de Daily Datasets.

### 3.2 Trigger del Reset

| Modo | Trigger |
|------|---------|
| **Backtest (daily/monthly)** | `timestamp` del dataset cruza una frontera UTC: `timestamp // 86400` cambia de valor |
| **Live** | `time.time() // 86400` cambia de valor (00:00 UTC) |

**Deteccion**: Monitorear el dia calendario en el punto de entrada unificado de ticks (`SensorManager.on_tick()` en el origen del flujo de datos).

### 3.3 Componentes a Resetear (En Orden de Dependencia)

**Fase 1: Layer 5 — Estado Orquestador (SensorManager)**
- `SensorManager.cvd_state[symbol] = 0.0`
- `SensorManager.tick_history[symbol].clear()`
- `SensorManager.micro_zscores[symbol] = RollingZScore(window_size=120)` (reinstanciar)
- `SensorManager.ob_skewness[symbol] = 0.5` (neutral)
- `SensorManager.last_price[symbol] = 0.0`
- `SensorManager._last_z_update[symbol] = 0`
- `SensorManager._last_tick_dispatch[symbol] = 0`
- `SensorManager._last_ob_dispatch[symbol] = 0`

**Fase 2: Layer 4 — Estado Microestructura (OrderFlowEngine)**
- `CoinOrderFlowEngine.current_cvd = 0.0`
- `CoinOrderFlowEngine.cvd_session = 0.0`
- `CoinOrderFlowEngine.cvd_history.clear()`
- `CoinOrderFlowEngine._last_cvd_session_reset_ts = ts_actual` (prevenir double-reset)
- `CoinOrderFlowEngine.velocity_zscore = RollingZScore(window_size=200)` (reinstanciar)
- `CoinOrderFlowEngine.concentration_zscore = RollingZScore(window_size=500)` (reinstanciar)
- `CoinOrderFlowEngine.noise_zscore = RollingZScore(window_size=500)` (reinstanciar)
- `CoinOrderFlowEngine._trade_aggr_window.clear()`
- `CoinOrderFlowEngine._window_buy_vol = 0.0`
- `CoinOrderFlowEngine._window_sell_vol = 0.0`
- `CoinOrderFlowEngine.price_history.clear()`
- `CoinOrderFlowEngine.price_returns.clear()`
- `CoinOrderFlowEngine.last_price = 0.0`
- `CoinOrderFlowEngine.last_trade_price = 0.0`
- `CoinOrderFlowEngine.absorption_snapshots = 0`

**Fase 3: Layer 3 — Estado Estructural (ContextRegistry)**
- `ContextRegistry.reset_profile(symbol)` (ya existe, llama a `MarketProfile.reset()`)
- `ContextRegistry.vwap_history[symbol].clear()`
- `ContextRegistry.vwap_accumulators[symbol] = {"pv": 0.0, "v": 0.0}`
- `ContextRegistry._vwap_residuals[symbol] = {"history": deque(maxlen=500), "sum_sq": 0.0}`
- `ContextRegistry.liquidity_walls[symbol].clear()`
- `ContextRegistry._wall_age[symbol].clear()`
- `ContextRegistry.l2_imbalance[symbol] = 1.0` (neutral)
- `ContextRegistry.spread_state[symbol] = {"current": 0.0, "avg_5m": 0.0, "history": deque(maxlen=300)}`
- `ContextRegistry._spread_running_sum[symbol] = 0.0`
- `ContextRegistry.tick_stats[symbol] = {"speed": 0.0, "last_ts": now, "count": 0}`
- `ContextRegistry.micro_state[symbol] = reset neutral` (cvd=0, skewness=0.5, z_score=0)
- `ContextRegistry.ATR buffers`: limpiar `ranges_short`, `ranges_long`, actualizar `_range_short_running_sum` / `_range_long_running_sum`
- Mantener `_session_structural[symbol]` si existe (preserve session-scoped overrides)
- Mantener `active_trades`, `ib_levels`, `regimes`, `otf` (no son acumulativos)
- **MANTENER** `regime_v2` data (el regimen es una clasificacion, no acumulacion)

**Fase 4: Layer 2 — Estado de Escenarios (Detectors)**
- `TrendAcceptanceDetector.active_breakouts[symbol]`: clear
- `TrendAcceptanceDetector.last_fire_ts[symbol] = 0`
- Otros detectores confirmacion de escenarios limpiar cache interna de simbolo

### 3.4 Ubicacion del Trigger en el Flujo

```
SensorManager.on_tick(event)       <-- BACKTEST: BacktestFeed produce TickEvent
       ↓
   [CHECK day_boundary]
       ↓
   if is_new_day(symbol, event.timestamp):
       self._trigger_daily_reset(symbol, event.timestamp)
       # Propaga a las 3 capas abajo
       self.pressure_engine.reset_daily_state(symbol)
       ContextRegistry().reset_daily_state(symbol)
       for name, detector in self.scenarios.items():
           detector.reset_for_symbol(symbol)
```

### 3.5 Consideraciones Criticas

#### A. Blind Spot Diario (Trade-off Consciente)
- `MarketProfile.is_mature` requiere **15 minutos** de datos continuous (900s de span)
- Al resetear a las 00:00 UTC, el bot estara en estado "inmature" hasta ~00:15 UTC
- **Esto replica EXACTAMENTE el comportamiento de los Daily Datasets donde se valido el edge**
- Solucion: Aceptar el blind spot de ~15 minutos por preservacion del edge estadistico

#### B. Idempotencia del Reset
- El metodo `_trigger_daily_reset()` debe ser **idempotente** para el mismo dia calendario
- Almacenar `self._last_reset_day[symbol] = current_day` para evitar multiples resets en el mismo dia
- Manejar edge cases: replay del backtest sobre el mismo dataset, live sin perdida de conexion que cruce la medianoche

#### C. Per-Moneda (Multi-Asset Safety)
- El reset debe ser siempre **por simbolo**, nunca global
- Garantizar que el reset de LTC no afecte a BTC, SOL, etc.

---

## 4. Plan de Implementacion (Step-by-Step)

### Phase 0: Infraestructura Base (2-3h)

#### Paso 0.1: Crear modulo unificado `core/session_boundary.py`
- Archivo nuevo: `core/session_boundary.py`
- Responsabilidad: Centralizar la logica de deteccion de frontera y la lista de componentes a resetear
- Implementar `SessionBoundaryManager` con:
  - `register_resettable(component_name, reset_callback)`
  - `check_and_trigger(symbol, timestamp)`
  - `is_new_day(symbol, timestamp) -> bool`
  - `last_reset_day[symbol] -> int`

#### Paso 0.2: Metodos `reset_daily_state()` en cada componente
- `[MODIFY]` `core/order_flow/engine.py`:
  - En `CoinOrderFlowEngine`: `reset_daily_state(self) -> None`
  - En `OrderFlowEngine` (facade): `reset_daily_state(self, symbol: str) -> None`
- `[MODIFY]` `core/context_registry.py`:
  - `reset_daily_state(self, symbol: str) -> None`
- `[MODIFY]` `core/sensor_manager.py`:
  - `reset_daily_state(self, symbol: str) -> None`
- `[MODIFY]` `decision/scenarios/confirmation/trend_acceptance.py`:
  - `reset_for_symbol(self, symbol: str) -> None`

### Phase 1: Integracion en el Pipeline (2-3h)

#### Paso 1.1: Hook en `SensorManager.on_tick()`
- En `core/sensor_manager.py`: Detectar `day_changed = (timestamp // 86400) != self._last_reset_day.get(symbol)`
- Si cambio: llamar a `self._trigger_daily_reset(symbol, timestamp)`
- `_trigger_daily_reset()` ejecuta la cascada de resets en el orden correcto

#### Paso 1.2: Hook en `ContextRegistry.on_tick()` (Live)
- Para el modo Live, `ContextRegistry.on_tick()` tambien debe detectar el cambio de dia y disparar su propio reset
- Pero para evitar double-reset: el reset debe ser **coordinado** via `SessionBoundaryManager`

#### Paso 1.3: Hook en `BacktestFeed` (Backtest Only)
- En `core/backtest_feed.py`: Detectar cuando un evento del dataset cruza una frontera UTC
- Emitir un evento `SESSION_BOUNDARY` antes del primer tick del nuevo dia
- Este evento es capturado por `SensorManager` para disparar el reset

### Phase 2: Testing y Validacion (4-6h)

#### Paso 2.1: Unit Test `test_session_boundary_reset.py`
- Inyectar ticks que crucen la medianoche UTC (e.g., 23:59:59 -> 00:00:01)
- Asserts:
  - `MarketProfile.total_volume == 0`
  - `MarketProfile.profile == {}`
  - `MarketProfile.is_mature == False`
  - `cvd_state[symbol] == 0.0`
  - `tick_history[symbol] == empty`
  - `CoinOrderFlowEngine.cvd_session == 0.0`
  - `VWAP accumulators reseteados`

#### Paso 2.2: Backtest Monthly con Reset (Mayo 2026 LTC)
- Ejecutar: `python backtest.py --depth-db-path data/datasets/monthly_backtest_ready/LTC_2026-05.db --symbol LTCUSDT --run-type audit`
- **Criterio de Exito**:
  - Numero de señales de `trend_acceptance` debe caer de ~119 a ~36-40
  - Señales de `failed_breakout` debe caer de ~57 a ~10-12
  - Net Taker debe mejorar significativamente (objetivo: > +0.10%)
  - TEST days aislados deben generar los mismos resultados que dentro del mensual

#### Paso 2.3: No-Regression en Daily Datasets (84 datasets)
- Ejecutar orchestrator single-coin-audit para 6 datasets LTC 24h
- **Criterio de Exito**: Resultados identicos o mejorados; no debe haber degradacion

#### Paso 2.4: Validacion Live (Simulation)
- Correr en modo `demo` con `bet-size: 0` (solo captura de señales)
- Confirmar que no crashea al cruzar la medianoche UTC

### Phase 3: Cleanup y Documentacion (1-2h)

#### Paso 3.1: Actualizar `docs/ARCHITECTURE_MAP.md`
- Documentar `SessionBoundaryManager` y el flujo de reset
- Actualizar seccion de "Estado Acumulativo / Reset"

#### Paso 3.2: Actualizar `.agent/memory.md`
- Registrar la implementacion y resultados de validacion

#### Paso 3.3: Merge a `dev-8.9-datafeed-revamp`

---

## 5. Estrategia de Rollback

Si el SBR introduce regresiones no esperadas:

1. **Rollback Inmediato**: Flag de configuracion `ENABLE_SESSION_BOUNDARY_RESET = False` en `config/trading.py`
2. **Bypass Selectivo**: Reset por simbolo, no por moneda
3. **Reset Parcial**: Solo resetear los componentes de mayor impacto (MarketProfile + CVD) y dejar VWAP/z-scores sin tocar

---

## 6. Metricas de Exito

| Metrica | Baseline (Monthly sin reset) | Target (Monthly con reset) |
|---------|-------------------------------|---------------------------|
| Señales trend_acceptance | 119 | ~36-40 |
| Win Rate trend_acceptance | 15.1% | >45% |
| Net Taker Overall | -0.4754% | > +0.10% |
| TEST day consistency (Mayo 1) | 0 vs ~4 señales | ~0 vs ~0 señales |
| Daily dataset regression | N/A | < 2% delta vs baseline sin SBR |

---

## 7. Appendice: Diagrama de Secuencia del Reset

```
BacktestFeed (o Live Stream)
       |
       v
TickEvent(timestamp=1735689600.0)  <-- 00:00:01 UTC
       |
       v
SensorManager.on_tick(event)
       |
       +-- is_new_day(symbol, 1735689600.0)?
       |       Yes (1735689600 // 86400 > last_reset_day)
       |
       +-- _trigger_daily_reset(symbol, timestamp)
       |       |
       |       +-- self.reset_daily_state(symbol)
       |       |       cvd_state=0, tick_history.clear(), micro_zscores reiniciar
       |       |
       |       +-- self.pressure_engine.reset_daily_state(symbol)
       |       |       cvd_session=0, z-scores reiniciar, histories clear
       |       |
       |       +-- ContextRegistry().reset_daily_state(symbol)
       |       |       MarketProfile.reset(), VWAP clear, liquidity clear
       |       |
       |       +-- for detector in scenarios: detector.reset_for_symbol(symbol)
       |               active_breakouts.clear(), last_fire_ts=0
       |
       v
Procesamiento normal del tick con estado zero
```

---

## 8. Notas de Implementacion

### 8.1 Compatibilidad con Multi-Asset
- El `SessionBoundaryManager` mantiene un diccionario `_last_reset_day` indexado por `(symbol, date)`
- En modo multi-asset, cada simbolo tiene su propio ciclo de reset
- No hay cross-contamination entre simbolos

### 8.2 Compatibilidad con Daily Datasets
- En un dataset diario aislado, el primer tick tendra un timestamp del dia N
- Como no hay dia N-1, el reset se disparara en el primer tick
- Esto es **correcto** (asegura estado zero al inicio) y no afecta la validez estadistica del edge

### 8.3 Compatibilidad con Live
- En modo Live, `time.time()` es real
- El reset se diparara en el primer tick despues de 00:00:00 UTC
- Si no hay actividad a las 00:00:00, el reset se retrasa hasta el siguiente tick
- Esto es aceptable porque el MarketProfile necesita ticks para acumular, y sin ticks no hay señales de todos modos

### 8.4 Edge Cases
- **Dataset con gaps de tiempo > 86400s**: Si hay un gap y el dia cambio, el reset se dispara. Correcto.
- **Replay del mismo dataset**: Si `last_reset_day` persiste entre ejecuciones, reinicializar en el constructor del componente que reutiliza el manejador.
- **Live sin ticks a las 00:00**: El reset se retrasa hasta el siguiente tick. Aceptable.

---

*Fin del Documento*
