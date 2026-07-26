# Decisiones Arquitectónicas

## ADR-1: Instant vs Confirmation Signals

### Contexto
Los 4 escenarios AMT tienen requisitos temporales fundamentalmente diferentes:

| Escenario | Tipo | Ventana de detección | Naturaleza |
|-----------|------|---------------------|------------|
| TacticalAbsorption | **Instant** | 1 tick | La absorción es un evento puntual. Si no se detecta en el tick exacto, ya pasó. |
| FailedBreakout | Confirmation | Múltiples ticks + 60s | Requiere breakout, divergencia CVD y re-entry al VA. |
| LiquidityExhaustion | Confirmation | Múltiples ticks + 120s | Requiere tests sucesivos con delta declinante. |
| TrendAcceptance | Confirmation | Múltiples ticks + candles | Requiere breakout VA, CVD confirmation y pullback. |

### Problema original
En la arquitectura anterior, `tactical_absorption` estaba clasificado como `REVERSION` junto con `failed_breakout` y `liquidity_exhaustion`. El análisis de MFE/MAE (0/927 señales revierten en <15 min) demostró que `tactical_absorption` es **flujo direccional**, no reversión. Esto llevó a la creación de `DIRECTIONAL_SCENARIOS` en `decision/engine/core.py:261`.

### Decisión
`tactical_absorption` bypasea `ScenarioManager` **intencionalmente** porque es una señal instantánea:

```python
# SetupEngine.on_signal (decision/engine/core.py ~210)
if event.sensor_id == "tactical_absorption":
    trace = black_box.create_trace(...)
    await self._process_signal(payload, trace=trace)
    return  # No pasa por ScenarioManager
```

Razones:
1. **Latencia**: TAV necesita disparar en el tick exacto. ScenarioManager introduce latencia de orquestación (priorización + fusión).
2. **Naturaleza**: TAV no compite con otros escenarios — detecta un fenómeno diferente (absorción de CVD, no patrón de precio).
3. **Historial**: 0/927 señales TAV compitieron con otro escenario en la misma dirección. El caso de conflicto es teórico, no práctico.
4. **Cooldown**: 180s previene doble disparo incluso si TAV se ejecuta en dos paths (SensorManager.on_tick + SetupEngine.on_signal).

### Consecuencias
- TAV no participa en conflict resolution ni signal fusion (trade-off aceptado)
- Si TAV y TrendAcceptance disparan simultáneamente en direcciones opuestas, no hay resolución automática (caso borde no observado en la práctica)
- El resto de escenarios (FailedBreakout, LiquidityExhaustion, TrendAcceptance) pasan por ScenarioManager con priorización y fusión completa

### Por qué NO unificar el ruteo
La recomendación del análisis externo de "mover TAV a ScenarioManager" no se implementa porque:
1. Rompería la capacidad de TAV de responder en tiempo real
2. No resolvería ningún problema real (no hay casos documentados de conflicto TAV vs otros escenarios)
3. Añadiría complejidad innecesaria a ScenarioManager

---

## ADR-2: PressureEngine Per-Coin

### Problema original
`PressureEngine` almacenaba `current_cvd`, `cvd_history` y `price_history` como atributos planos de instancia. Una sola instancia servía para TODAS las monedas, causando:

- **Contaminación cruzada**: Los ticks de DOGE sobrescribían el CVD de XRP (en modo multi-coin en vivo)
- **Parámetros globales**: `concentration_min=0.50` se aplicaba tanto a BTC como a DOGE, sin importar el perfil
- **Instancias duplicadas**: SensorManager usaba defaults hardcodeados; SetupEngine usaba parámetros de MID_LIQUID

### Síntomas
- El backtest funcionaba por accidente (un proceso por moneda aísla el estado)
- Las optimizaciones paramétricas de `concentration_min` y `noise_max` en `coin_profiles.py` no afectaban al `PressureEngine` de `SensorManager` (línea 63: `PressureEngine()` sin params)
- `AbsorptionDetector` compensaba leyendo `profile_manager.get_sensor_params()` directamente (línea 28 de `absorption_detector.py`), pero `PressureEngine.concentration_min` y `noise_max` seguían siendo globales

### Solución: PressureEngine Facade + CoinPressureEngine

```
PressureEngine (facade)
├── _engines: Dict[str, CoinPressureEngine]
│   ├── "BTC/USDT" → CoinPressureEngine(concentration_min=0.60, ...)
│   ├── "DOGE/USDT" → CoinPressureEngine(concentration_min=0.55, ...)
│   └── "XRP/USDT" → CoinPressureEngine(concentration_min=0.55, ...)
```

**CoinPressureEngine**: Estado aislado por símbolo. Cada instancia:
- Lee sus parámetros de `profile_manager.get_sensor_params(symbol, "absorption_detector")`
- Mantiene su propio `cvd_history`, `price_history`, `velocity_zscore`, etc.
- Calcula `absorption_score` con los `concentration_min`/`noise_max` de su perfil

**PressureEngine** (facade): Registry `Dict[symbol, CoinPressureEngine]`.
- `update(symbol, qty, ...)` → delega al engine de ese símbolo
- `get_state(symbol)` → delega
- No tiene parámetros propios — cada coin engine los obtiene de profile_manager

### Instancia compartida
SensorManager y SetupEngine comparten la **misma instancia** del facade:
- **SensorManager** escribe: `self.pressure_engine.update(event.symbol, ...)`
- **SetupEngine** solo lee: `self.pressure_engine.get_state(event.symbol)`

Beneficios:
- Cómputo único por tick (antes se duplicaba)
- `update_from_orderbook()` alimenta a todos los escenarios (antes solo a SensorManager)
- Una sola fuente de verdad

### Archivos modificados
- `core/pressure/engine.py`: Refactor completo (146→164 líneas)
- `core/sensor_manager.py`: 3 líneas — pasar symbol a update/get_state/update_from_orderbook
- `decision/engine/core.py`: 4 líneas — shared instance, eliminar update propio
- `decision/scenarios/failed_breakout.py`: 1 línea — get_state(symbol)
- `decision/scenarios/liquidity_exhaustion.py`: 1 línea — get_state(symbol)
- `decision/scenarios/trend_acceptance.py`: 1 línea — get_state(symbol)
- `sensors/absorption/absorption_detector.py`: 1 línea — get_state(symbol)
- `scripts/debug_pressure.py`, `scripts/analyze_pressure.py`, `scripts/calibrate_engine.py`: Pasar symbol
- `tests/test_reconstruction.py`: Actualizar API

### Riesgos
- **CoinPressureEngine se crea lazy** (al primer tick de cada símbolo). El warmup (200 ticks para CVD history) es por-símbolo.
- **Profile_manager debe estar inicializado** antes de que llegue el primer tick. Si no, `_load_params()` falla silenciosamente y usa defaults. Se agregó try/except para graceful fallback.

---

## Referencias
- `core/pressure/engine.py` — Implementación
- `docs/crystal_layer_analysis.md` — Análisis externo que identificó las inconsistencias
- `.agent/memory.md` — Roadmap y estado
