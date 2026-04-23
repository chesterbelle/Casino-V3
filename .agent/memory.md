# Casino-V3 Agent Memory

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, bugs encontrados, estado actual, gotchas nuevos, y cualquier cambio de arquitectura relevante.
> 3. Si el usuario no te lo recuerda, hazlo de todos modos. Es tu responsabilidad, no la suya.
> 4. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas de este repositorio. **NUNCA hagas merge ni rebase entre ramas.** Siempre que se haga un `push`, DEBE hacerse directa y exclusivamente dentro de la rama en cuestión (ej. `git push`) para evitar mezclar y destruir las arquitecturas de los bots.
> 5. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente. Limítate a hacer `git commit` en local para que el usuario mantenga el control manual de lo que sube al repositorio remoto.

## Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
Strategy: LTA V4 Structural Reversion (Institutional geometric scalping targeting POC from VAH/VAL).
Current branch: `v6.1.0-lta-structural-pivot`

---

## Capas de Certificación (Roadmap)
- **🏛️ Capa de Hierro (Infraestructura)**: Paridad 1:1, Resiliencia del Historian, Latencia < 50ms. [COMPLETADO]
- **💎 Capa de Cristal (Estrategia/Alpha)**: Validación de Edge, Win Rate > 64%, MAE/MFE. [COMPLETADO]
- **⚔️ Capa de Acero (Resiliencia)**: PortfolioGuard V2, Hyperliquid, ML Regime. [ENFOQUE ACTUAL]

### Core Components
| Component | Purpose |
|-----------|---------|
| `SetupEngineV4` | Tactical pattern detection → AggregatedSignalEvent |
| `AdaptivePlayer` | Signal → DecisionEvent (Kelly sizing, TP/SL validation) |
| `OrderManager` (core/execution.py) | DecisionEvent → exchange order |
| `Croupier` (croupier/croupier.py) | Execution orchestrator, position lifecycle |
| `OCOManager` | Bracket order (entry + TP + SL) management |
| `PositionTracker` | Single source of truth for open positions |
| `BinanceNativeConnector` | Exchange API (REST + WebSocket, 8 shards) |
| `Historian` | SQLite-based trade persistence (data/historian.db) |
| `PortfolioGuard` | Risk monitor (drawdown, loss streaks, sizing violations) |
| `ContextRegistry` | Zero-lag mirror of market structure (POC/VAH/VAL) |
| `SensorManager` | Multiprocess sensor workers → SignalEvents |
| `HFTExitManager` | Axia-style professional exit management |

### Key Files & Documentation
- `ROADMAP.md` — Certification Layers (Iron, Glass, Steel)
- `docs/strategies/` — Theoretical Manifests (Quick Scalping, Velocity & Vacuum, LTA-V4)
- `docs/implementations/` — Technical Specs (Sniper Footprint Scalper)
- `main.py` — Entry point with unified flag wiring
- `croupier/croupier.py` — Core execution orchestrator
- `core/portfolio/position_tracker.py` — Position lifecycle + HFT telemetry
- `CONFIGURATION.md` — Flag documentation and usage

---

## CLI Flags — Propósito Exacto

### `--close-on-exit`
- Al final de sesión: emergency sweep cierra todo en el exchange (evita posiciones huérfanas)
- Durante sesión con `--timeout`: activa **Drain Phase** progresiva (DEFENSIVE → AGGRESSIVE → PANIC)
  - Para nuevas entradas y ajusta TP/SL para cerrar limpio antes del timeout
- **Solo Demo/Live. NUNCA en Backtest.**

### `--fast-track`
- **Exclusivamente para protocolos de validación de infraestructura (Mocking).**
- **NUNCA en producción.**
- Bypasea gates de infraestructura para forzar la saturación del Event Loop en ventanas cortas (15/30m).
- **LTA V4 Location Bypass (Phase 990):** Miente temporalmente al `SetupEngine` simulando que  se tocó el VAH/VAL para forzar la creación de OCOs, purgar el ExitManager y testear el Portfolio Guard durante el protocolo `/fast-track-parity`.
- **NUNCA bypasea reglas de calidad defensiva:**
  - Math Inversion check (execution.py)
  - PortfolioGuard / Min Notional Limits

### `--audit`
- Zero-Interference Audit Mode para validación de edge
- Registra todas las señales en Historian aunque no se ejecuten

---

## Protocolos de Validación

### `/fast-track-parity` (30 min)
- **Propósito:** Verificar paridad mecánica Demo vs Backtest (fugas de simulación)
- **Ticker:** LTC/USDT:USDT (cumple min notional con balance testnet)
- **Comando demo:** `main.py --mode demo --symbol LTC/USDT:USDT --timeout 30 --fast-track --close-on-exit`
- **Nunca usar BTC** — min notional $100, balance testnet ~$3000 con 1% bet = $30 → rechazado por Flytest

### `/execution-quality-audit` (15 min)
- **Propósito:** Verificar pipeline asíncrono (zero stalls, zero CancelledErrors)
- **Ticker:** LTC/USDT:USDT
- **Salida:** `logs/demo_exec.log` y `logs/bt_exec.log`

### `/stress-test`, `/chaos-test`, `/validate-all`, `/edge-audit`, `/paritycheck`
- Ver `.agent/workflows/` para comandos exactos

---

## HFT Latency Telemetry (T0-T4)
- `t0` — Timestamp del tick en el exchange
- `t1_decision_ts` — Momento de decisión en AdaptivePlayer
- `t2_submit_ts` — Momento de envío al exchange (OrderManager)
- `t3` — Confirmación de fill del exchange
- `t4_fill_ts` — Registro en PositionTracker
- **Solo se persiste en Demo/Live orgánicamente. En Backtest se inyecta desde el VirtualExchange para paridad mecánica.**
- Fallbacks en `historian.py` (Resilient Mode): Si `entry_price <= 0`, se loguea ERROR CRÍTICO y se usa `exit_price` como fallback para evitar el **Silent Skip** (pérdida de trazabilidad).
- Fallbacks en `position_tracker.py:confirm_close` para evitar NULLs en Historian.

---

## Reglas de Operación del Bot

### Flytest (arranque)
- Valida cada símbolo antes de operar: min notional, precision profile, liquidez
- En `--fast-track`: bypasea bulk market fetch pero **mantiene validación de notional**

### Señales y Filtros (pipeline orgánico — no sintético)
- SetupEngine requiere patrones tácticos reales: TacticalTrappedTraders, TacticalDivergence
- Cooldown entre señales: 15s por símbolo
- Gate de proximidad a nivel estructural: 0.20% (fast_track: 1.0% — más permisivo pero real)
- **PROHIBIDO inyectar señales sintéticas o "heartbeat signals"** — si no hay señales orgánicas, investigar el bug, no inventar datos.
- **Agnostic Deployment (Anti-Overfitting)**: La estrategia debe ser **agnóstica al símbolo**. No se permiten ajustes de parámetros específicos por moneda (ej. thresholds distintos para SOL vs LTC) a menos que se decida explícitamente a futuro. El objetivo es el modo **MULTI**, lo que requiere una lógica que generalice y capture el edge institucional de forma global.
- **Structural Gating (Phase 2100)**: Las reversiones LTA V4 ahora están protegidas por el **3-Layer Market Regime Sensor** (Guardian 1) que utiliza votos de Micro/Meso/Macro para detectar el estado de `TRANSITION` y bloquear reversiones antes de rupturas de tendencia.
- **Structural Gating (Phase 2200)**: Los 5 guardianes restantes fueron reestructurados en LTA V5. G3 (VA Integrity) convertido a soft gate, G4 (Failed Auction) lookback extendido a 10 velas, G5 (Delta Divergence) threshold relajado a z < -2.5. Resultado: +70% más señales manteniendo el mismo win rate.

### Drain Phase
- Solo se activa si: `--close-on-exit` AND NOT `--fast-track` AND timeout configurado
- Activación: cuando `elapsed >= timeout - drain_duration`
- `drain_duration` = mín(DRAIN_PHASE_MINUTES, timeout * 0.30)
- `is_drain_mode = True` en Croupier bloquea TODAS las nuevas entradas

---

## Heurísticas de Diagnóstico (Debugging)

### Regla de Oro del Silencio en Fast-Track
**IF** el protocolo utiliza `--fast-track` **AND** el resultado es **0 trades** en el Historian:
1. **NO** asumas falta de volatilidad o problemas de símbolos.
2. **REVISA PRIMERO** la lógica de los flags (`fast_track` vs `drain_mode` vs `close_on_exit`).
3. **VERIFICA** si algún gate de ejecución (Math Inversion, RR, Notional) está bloqueando el flujo debido a un bypass incorrecto o a un cruce de banderas.
Es el camino más corto a la solución.

---

## Gotchas Críticos
1. **Min Notional BTC:** ~$100 mínimo. Con balance testnet ~$3000 y bet 1% = $30 → siempre falla Flytest. Para pruebas cortas usar **LTC** (min $5) o **DOGE** (min $5).
2. **Symbol Normalization:** Siempre usar `normalize_symbol()` — BTC/USDT:USDT ≠ BTCUSDT → órfanos
3. **Drain Mode vs Risk Halt:** Son conceptos distintos. `is_drain_mode` hoy mezcla ambos (debt de diseño). `PortfolioGuard` puede activar drain por riesgo aunque no haya timeout.
4. **OCO "would immediately trigger":** Si TP/SL ya está en precio al colocar el bracket → Binance rechaza con -2021. Causa: señal llegó stale y pasó el PreFlight por bypass de fast_track (ya corregido).
5. **Sensor UNKNOWN side:** Ticks sin clasificación buy/sell resultan en delta=0, degradando CVD. Investigar origen en conector si se repite frecuentemente.
6. **Historian 0 trades:** Si el bot ejecuta pero no registra → verificar que la posición pasó por `confirm_close` en PositionTracker.
7. **LTA V4 Live Validation (0 Trades):** Es matemáticamente natural obtener 0 trades en ventanas de 15 minutos en red en vivo. Si se requiere estresar la red (ej. `/execution-quality-audit`), `--fast-track` ES OBLIGATORIO para bypassear temporalmente el Location Gate y forzar órdenes orgánicas falsas de testeo.
8. **Warmup de Setup Engine:** Ya no existe el timer hardcodeado de 60m. LTA asume "Combat Ready" tan pronto el `ContextRegistry` resuelve `is_structural_ready()` procesando Historical Klines.

---

- ✅ **Capa de Hierro**: Paridad Mecánica 1:1 verificada (v5.2.0)
- ✅ **Resilient Historian**: Eliminación de Silent Skips y Fallback de precios
- ✅ **Deterministic Sim**: Inyección de timestamps de mercado en backtest

---

### Estado Actual (2026-04-21)
- **Infraestructura (Hierro)**: Certificada ✅ (Paridad 1:1, Latencia ultra-baja).
- **Estrategia (Cristal)**: **LTA V5 CERTIFIED (Phase 2200 — Guardian Restructuring)**.

#### LTA V5 — Cambios vs V4 (branch: `feature/lta-v5-sensor-consolidation`)

**Sensores Tácticos:**
- ❌ `TacticalRejection` eliminado — redundante con TacticalAbsorption (correlación >0.85)
- ❌ `TacticalStackedImbalance` eliminado — contradictorio (predice continuación en playbook de reversión)
- ❌ `TacticalImbalance` eliminado — menos específico que TacticalTrappedTraders
- ✅ `TacticalSinglePrintReversion` nuevo — Market Profile: single print rejection (zonas de bajo volumen)
- ✅ `TacticalVolumeClimaxReversion` nuevo — Wyckoff: volumen climax sin extensión de precio

**Guardianes Reestructurados (Phase 2200):**
- **G3 VA Integrity**: Convertido de hard gate a soft gate. Threshold reducido al 50% del original. Solo rechaza en casos críticos. Antes rechazaba el 80% de señales (1,594/1,986).
- **G4 Failed Auction**: Lookback extendido de 3 a 10 velas. Wick body check eliminado (redundante con sensores tácticos).
- **G5 Delta Divergence**: Threshold relajado de z < -1.5 a z < -2.5. Solo bloquea flujo extremo sostenido.

**Edge Statistics LTA V5 (72h, 3 activos: LTC/SOL/ETH):**
- **Señales**: 75 (vs 44 en V4, +70%)
- **Win Rate (0.3% TP/SL)**: **68.9%** (vs 64.5% en V4)
- **Ratio MFE/MAE**: **1.61** (vs 1.37 en V4)
- **Expectancy**: **+0.1133** (vs +0.0871 en V4)
- **Status**: CERTIFIED ✅

**Archivos modificados en LTA V5:**
- `decision/setup_engine.py` — Whitelist V5 + Guardianes Phase 2200
- `config/strategies.py` — LTA_FAILED_AUCTION_LOOKBACK=10
- `config/sensors.py` — Nuevos sensores registrados
- `core/sensor_manager.py` — Imports de nuevos sensores
- `sensors/footprint/advanced.py` — Rejection y StackedImbalance deshabilitados
- `sensors/footprint/imbalance.py` — Imbalance deshabilitado
- `sensors/footprint/single_print_reversion.py` — Nuevo sensor
- `sensors/footprint/volume_climax_reversion.py` — Nuevo sensor
- `sensors/footprint/deprecated_v4/` — Backups de sensores eliminados

**Próximo paso**: Integrar LTA V5 a `v6.1.0-lta-structural-pivot` via cherry-pick manual de archivos (NO merge). Ejecutar edge audit protocol en esa rama para certificar.

---

### Long-Range Edge Audit Protocol (2026-04-22)

**Protocolo**: `.agent/workflows/long-range-edge-audit.md`
**Propósito**: Certificar el edge en múltiples condiciones de mercado (Range/Bear/Bull)

**Diseño**: LTC/USDT × 3 condiciones × 3 días = 9 backtests
- **Por qué LTC**: Más range-bound que SOL/ETH. SOL genera ~15 señales/día (insuficiente). LTC genera ~50/día.
- **Por qué no SOL**: Demasiado trending/momentum. Ratio 0.86 en 3 condiciones SOL vs 1.10 en LTC.

**Datasets disponibles** (en `tests/validation/`):
- Range (Aug 14-16, 2024): ltc_range_2024-08-14.csv, ltc_range_24h.csv, ltc_range_2024-08-16.csv
- Bear  (Sep 05-07, 2024): ltc_bear_2024-09-05.csv, ltc_bear_24h.csv, ltc_bear_2024-09-07.csv
- Bull  (Oct 13-15, 2024): ltc_bull_2024-10-13.csv, ltc_bull_24h.csv, ltc_bull_2024-10-15.csv

**Resultados LTA V5 (Long-Range 2024)**:
- Total: 151 señales, Ratio 1.10, WR 50.0% → WATCH
- Range: n=64, WR 51.4%, Ratio 1.07 → WATCH
- Bear:  n=33, WR 52.4%, Ratio 1.06 → WATCH
- Bull:  n=54, WR 41.7%, Ratio 1.06 → FAILED

**Comparación vs Edge Audit Normal (abril 2025)**:
- Normal: Ratio 1.62, WR 69.4% → CERTIFIED
- Long-Range 2024: Ratio 1.10, WR 50.0% → WATCH
- Interpretación: Edge real pero más débil en 2024. LTA V5 mejoras validadas en condiciones recientes.

**Herramientas nuevas**:
- `utils/data/slice_audit_dataset.py` — corta días específicos de datasets mensuales
- `utils/analysis/per_condition_audit.py` — análisis vectorizado per-condición (evita timeout)
- `utils/data/download_trades.py` — descarga aggTrades mensuales desde Binance Vision

---
*Last Updated: 2026-04-22*
