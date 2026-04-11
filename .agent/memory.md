# Casino-V3 Agent Memory

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, bugs encontrados, estado actual, gotchas nuevos, y cualquier cambio de arquitectura relevante.
> 3. Si el usuario no te lo recuerda, hazlo de todos modos. Es tu responsabilidad, no la suya.

## Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
Strategy: Institutional scalping via Footprint/Order Flow analysis (Dale methodology).
Current branch: `v5.2.0-certified-reactor-sniper`

---

## Capas de Certificación (Roadmap)
- **🏛️ Capa de Hierro (Infraestructura)**: Paridad 1:1, Resiliencia del Historian, Latencia < 50ms. [COMPLETADO]
- **💎 Capa de Cristal (Estrategia/Alpha)**: Validación de Edge, Win Rate > 55%, MAE/MFE. [ENFOQUE ACTUAL]
- **⚔️ Capa de Acero (Resiliencia)**: PortfolioGuard V2, Hyperliquid, ML Regime. [PRÓXIMO PASO]

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
- **Solo bypasea gates de tiempo/calentamiento:**
  - Warmup timer de 60min del SetupEngine → 0
  - Micro-gate, wick gate, regime gate (dependen de historia de datos)
  - Drain Phase (sesión demasiado corta para que tenga sentido)
- **NUNCA bypasea reglas de calidad:**
  - Math Inversion check (execution.py) — soberano siempre
  - Inverted TP/SL, Max Distance, RR ≥ 1.0 (adaptive.py) — reglas de estrategia
  - PortfolioGuard — riesgo siempre soberano
  - Min Notional — límites del exchange siempre aplican
- **Exclusivamente para protocolos de validación de infraestructura.**
- **NUNCA en producción.**

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
- **PROHIBIDO inyectar señales sintéticas o "heartbeat signals"** — si no hay señales orgánicas, investigar el bug, no inventar datos

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
6. **Historian 0 trades:** Si el bot ejecuta pero no registra → verificar que la posición pasó por `confirm_close` en PositionTracker completo (no force-closed por OCO failure antes de que se registrara el trade).

---

- ✅ **Capa de Hierro**: Paridad Mecánica 1:1 verificada (v5.2.0)
- ✅ **Resilient Historian**: Eliminación de Silent Skips y Fallback de precios
- ✅ **Deterministic Sim**: Inyección de timestamps de mercado en backtest

---

### Estado Actual (2026-04-09)
- **Infraestructura (Hierro)**: Certificada v5.2.0 ✅
- **Estrategia (Cristal)**: Iniciando Auditoría de Edge para `quick_scalping_strategy.md` 🛡️
- **Meta Actual**: Encontrar rentabilidad orgánica con paridad confirmada.

---
*Last Updated: 2026-04-09*
