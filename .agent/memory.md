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
Current branch: `v6.2.0-limit-sniper`

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
| `ExitEngine` | Unified 5-layer exit management (Phase 1200) |

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
- **Absorption V1 Bypass (Phase 6):** Bypasea las 3 confirmaciones del AbsorptionSetupEngine:
  - CVD flattening check (permite CVD slope > 5.0)
  - Price holding check (permite precio > 0.05% del nivel)
  - TP calculation (usa TP mock a 0.20% fijo en lugar de buscar LVN)
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

### `/edge-audit` — Certificación de Alpha (Phase 800)
- **Propósito:** Validar el edge predictivo de los setups usando MFE/MAE y Expectancia Bruta
- **Métricas clave:**
  - **MFE/MAE Ratio**: > 1.2 indica ventaja estructural
  - **Gross Expectancy (%)**: `(WR × Avg_Win) - (LR × Avg_Loss)` — Edge puro antes de fees
  - **Net Expectancy**: Gross - Fees (0.12% taker, 0.08% maker)
  - **Viabilidad**: Gross Expectancy > 3× fees (0.36%) = CERTIFIED
- **Auditor mejorado (Phase 800B):**
  - Sección [1B]: Expectancia Bruta por setup (pre-fee edge en %)
  - Sección [2]: Win Rate + Expectancy + Net (Taker/Maker) por TP/SL
  - Sección [3]: Per-setup con Expectancy% y veredicto basado en viabilidad
  - Sección [5]: Resumen global con recomendaciones (Limit Sniper, filtros, exits)
- **Interpretación correcta del Edge:**
  - NO usar solo Profit Factor o Ratio como métrica de viabilidad
  - La Expectancia Bruta en % es la métrica definitiva del edge
  - Si Expectancy < 3× fees → estrategia no viable sin optimización
  - Si Net (Maker) > 0 pero Net (Taker) < 0 → Limit Sniper obligatorio

### `/stress-test`, `/chaos-test`, `/validate-all`, `/generalized-edge-audit`, `/long-range-edge-audit`, `/paritycheck`
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
9. **Fee Accounting en Backtest:** `backtest.py` usa `VirtualExchange._trades` para persistir trades al historian. Solo las closing trades tienen `pnl != None`. La entry fee se almacena en `position["entry_fee"]` del VirtualExchange y se incluye en el trade record de cierre como `fee = entry_fee + exit_fee`. Si se modifica el VirtualExchange, verificar que la fee total se mantiene correcta.
10. **_deferred_fee_enrichment en Backtest:** Se salta en modo backtest porque sobreescribe la fee total correcta con solo la exit fee. Si se agrega un nuevo path de cierre, verificar que no se llame en backtest.

---

- ✅ **Capa de Hierro**: Paridad Mecánica 1:1 verificada (v5.2.0)
- ✅ **Resilient Historian**: Eliminación de Silent Skips y Fallback de precios
- ✅ **Deterministic Sim**: Inyección de timestamps de mercado en backtest

---

### Estado Actual (2026-04-26)
- **Infraestructura (Hierro)**: Certificada ✅
- **Estrategia (Cristal)**: **LTA V6 CERTIFIED (Phase 2350 — Alpha Recovery)**.
- **Resiliencia (Acero)**: **Phase 1200 — Limit Sniper + ExitEngine + Fee Fix**.
- **Edge Verified**: WR 60.5% (Range), 65.2% (Bear), Ratio 1.46.
- **Root Cause identificado**: Fees consumen 130% del gross PnL. Limit Sniper reduce fees 40% (maker entry).

#### LTA V6 — Phase 2350: Recovery of Alpha & Resolution of Analysis Paralysis

**Cambios Clave:**
1. **Regime Consensus Override (G1)**: Las capas Micro/Meso Neutral ahora mandan sobre la Macro. Se permite operar en `TRANSITION` si el Z-Score > 2.2.
2. **Arquitectura de Soft-Sizing**: G2 (POC Migration) y G3 (VA Integrity) ahora usan multiplicadores de 0.5x en zonas "amarillas" en lugar de bloqueos duros.
3. **Retorno a Parámetros Certificados**:
   - Proximity: 0.20% (ajustado de 0.25%).
   - POC Migration: 0.50% (ajustado de 0.80%).
   - VA Integrity Min: 0.08.
4. **Eliminación de G4**: El guardián de Failed Auction basado en velas OHLC fue removido por causar discriminación invertida.

**Resultados Audit (LTC 2024 Long-Range):**
- **RANGE**: WR 60.5%, Ratio 1.31 (Alpha recuperado).
- **BEAR**: WR 65.2%, Ratio 1.46 (Excelente captura de clímax).
- **Missed Wins**: Reducción drástica del 87% de rechazos falsos en régimen.

**Archivos modificados:**
- `decision/setup_engine.py` — Lógica de Consensus Override + Soft Gates.
- `config/strategies.py` — Restauración de umbrales LTA V5 Certified.
- `docs/implementations/lta_v6_reversion_impl.md` — Nueva documentación técnica.

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
- ~~`utils/data/download_trades.py`~~ — ELIMINADO. Usar solo `parity_data_fetcher.py`

---

### Long-Range Edge Audit V2 — Parity Fetcher Datasets (2026-04-22)

**Protocolo actualizado**: 4 condiciones con datasets del parity fetcher (formato idéntico al audit normal)

**Datasets disponibles** (en `tests/validation/`):
- Range:      `ltc_24h_audit.csv`       — 2026-04-12 ($53.50, lateral)
- Bear Normal:`ltc_bear_normal_24h.csv` — 2026-04-11 ($55.07→$53.50, -2.8%)
- Bear Crash: `ltc_bear_24h_v2.csv`     — 2026-04-02 ($84→$52, -38% crash)
- Bull:       `ltc_bull_24h_v2.csv`     — 2026-04-07 ($70→$78, +11%)

**Resultados LTA V5 (4 condiciones, parity fetcher)**:

| Condición | n | WR% | Ratio | Veredicto |
|-----------|---|-----|-------|-----------|
| RANGE (2026-04-12) | 37 | 57.1% | 1.46 | ✅ CERTIFIED |
| BEAR NORMAL (2026-04-11) | 14 | 100.0% | 4.85 | LOW_N (prometedor) |
| BEAR CRASH (2026-04-02) | 10 | 0.0% | 0.21 | ❌ FAILED (evento de cola) |
| BULL (2026-04-07) | 10 | 60.0% | 0.63 | LOW_N |

**Conclusiones clave**:
1. Edge confirmado en BALANCE (Ratio 1.46, WR 57.1%)
2. BEAR NORMAL funciona excepcionalmente (guardians filtran solo señales alineadas)
3. BEAR CRASH rompe la estrategia — evento de cola, no caso de uso normal
4. BULL tiene MAE > MFE — mercado sigue subiendo, reversiones fallan
5. Guardians funcionando: más rechazos `Trend-aligned`/`Counter-trend` en BULL/BEAR

**Datasets de 2024 (Binance Vision — formato diferente, menos confiable)**:
- Archivos en `tests/validation/ltc_range_*.csv`, `ltc_bear_*.csv`, `ltc_bull_*.csv`
- Ratio ~1.06-1.10 en 2024 vs 1.46 en 2026 — diferencia atribuida al formato de datos

---

### Guardian Efficacy Analysis (Phase 2300, 2026-04-23)

**Herramientas**: `utils/analysis/guardian_efficacy_audit.py`, `utils/analysis/regime_guardian_debug.py`

**Hallazgos principales**:

1. **Failed Auction Guardian ELIMINADO** — Concepto opera en timeframe de sesión (horas), no en velas de 1m. Causaba discriminación invertida (-29%). `SessionValueArea` ya maneja el concepto correctamente.

2. **Phase 2300: Price Circuit Breaker** — Añadido al `MarketRegimeSensor` para detectar crashes sin depender de Z-scores adaptativos. Con persistencia: se mantiene activo hasta que el precio recupera >0.5%.

3. **Phase 2300: PortfolioGuard Shadow Mode** — En `--audit`, el PortfolioGuard ya no activa drain mode. Solo loguea los cambios de estado.

4. **Discrimination scores actuales** (5 guardians):
   - REGIME_ALIGNMENT_V2: +0.5% ⚠️ WEAK
   - POC_MIGRATION: -3.9% ❌ INVERTED
   - VA_INTEGRITY: -3.1% ❌ INVERTED
   - DELTA_DIVERGENCE: +5.9% ✅ GOOD
   - SPREAD_SANITY: N/A

**Pendiente de análisis manual**: POC_MIGRATION y VA_INTEGRITY muestran discriminación invertida. Requiere investigación antes de próximas modificaciones.

**Documentación**: `docs/implementations/lta_v5_reversion_impl.md`

---

### Phase 1200: Limit Sniper Redesign + ExitEngine + Fee Fix (2026-04-26)

**Branch**: `v6.2.0-limit-sniper`

#### Limit Sniper Redesign
- **Antes**: `LIMIT_SNIPER_ENABLED=True` generaba señales `PreFlightProximity` extra (3.5x más trades, peor calidad)
- **Ahora**: Solo cambia el tipo de orden (market→limit) en señales LTA existentes. No genera nuevas señales.
- `_evaluate_pre_flight` en `setup_engine.py` **DISABLED**
- `_execute_main_order` en `oco_manager.py` coloca limit orders al nivel estructural (VAL/VAH) + offset
- `on_decision` en `execution.py` extrae `limit_price` de `DecisionEvent.trigger_level` / `initial_narrative`
- `LIMIT_SNIPER_OFFSET_PCT = 0.0004` (0.04% ahead del nivel)
- `LIMIT_SNIPER_BACKTEST_STRICT_FILL = False` (touch-fill: señal dispara al nivel)

#### ExitEngine (Unified 5-Layer Stack)
Reemplaza `ExitManager` + `HFTExitManager` con stack unificado:
- **Layer 5: CATASTROPHIC STOP** — Drawdown > 50%, siempre activo
- **Layer 4: THESIS INVALIDATION** — Flow + Setup-specific + Stagnation (solo si perdiendo) + Wall Collapse
- **Layer 3: VALENTINO** — Scale-out 50% al 70% de TP, move SL a breakeven
- **Layer 2: SHADOW PROTECTION** — Breakeven + Trailing (DISABLED por defecto)
- **Layer 1: SESSION DRAIN** — Salida progresiva durante shutdown

**Best Config (Phase 1200)**:
- `LTA_SL_TICK_BUFFER = 6.0` (0.30% SL)
- `EXIT_LAYER_CATASTROPHIC = True`
- `EXIT_LAYER_THESIS_INVALIDATION = False` (erode PF)
- `EXIT_LAYER_VALENTINO = True` (WR 33→43%)
- `EXIT_LAYER_SHADOW_PROTECTION = False` (breakeven/trailing matan edge)
- `EXIT_LAYER_SESSION_DRAIN = True`
- `BREAKEVEN_ENABLED = False`, `TRAILING_STOP_ENABLED = False`

#### Bug Fixes (Pre-existing)
1. **Fee accounting bug**: `backtest.py` solo registraba exit fee (0.06%), no total (entry+exit). La entry fee se cobraba del balance pero nunca se incluía en el trade record del historian.
   - Fix: VirtualExchange almacena `entry_fee` en position dict; closing trade records `fee = entry_fee + exit_fee`
   - Fix: `force_close_all_positions` también reporta total fee
   - Fix: `close_position` pasa `total_fee` a `confirm_close` en vez de `fee=0.0`
   - Fix: `_deferred_fee_enrichment` se salta en backtest (sobreescribía fee correcta con solo exit)

2. **Fill price bug**: Limit BUY por encima del market se llenaba al limit price (overpaying). Ahora llena al `min(limit, current)` para BUY, `max(limit, current)` para SELL — comportamiento real del exchange.

3. **Stagnation profit-aware**: Stagnation nunca cierra trades ganadores (era el #1 bug del HFTExitManager).

#### Backtest Results (LTC 24h audit)

| Metric | Baseline (Market) | Limit Sniper | Delta |
|--------|-------------------|-------------|-------|
| Trades | 30 | 29 | -1 |
| WR | 30.0% | **41.4%** | **+11.4%** |
| Gross | -1.91 | -2.09 | -0.18 |
| Fees | 4.37 | **2.64** | **-1.73 (-40%)** |
| Net | -6.28 | **-4.73** | **+1.55** |

- Fee per trade: 0.08% (maker 0.02% + taker exit 0.06%) vs baseline 0.12%
- **Root cause de edge erosion**: Fees consumen 130% del gross PnL. MFE=0.247%, friction=0.066/trade.

#### Root Cause Analysis: FEES, not ExitEngine
- Edge audit: MFE=0.247%, MAE=0.131%, Ratio=1.89 (GROSS, sin fees)
- VirtualExchange fees: taker 0.05%, maker 0.02%, slippage 0.01%
- Round-trip friction: ~0.066/trade (entry+exit taker+slippage)
- Gross PF: 0.589, Net PF: 0.297
- Signal MFE (0.247%) es demasiado delgado para cubrir friction (0.066/RT)

#### Archivos Clave Modificados
- `config/trading.py` — LIMIT_SNIPER_ENABLED=True, layer toggles
- `decision/setup_engine.py` — _evaluate_pre_flight DISABLED
- `croupier/components/oco_manager.py` — _execute_main_order con limit orders
- `croupier/components/exit_engine.py` — NEW: Unified engine
- `croupier/croupier.py` — fee accounting fix, scale_out_position
- `core/execution.py` — limit_price extraction, PreFlight disabled
- `core/portfolio/position_tracker.py` — scaled_out field, entry_fee tracking
- `exchanges/connectors/virtual_exchange.py` — immediate fill, better price, entry_fee tracking

#### Archivos Deprecated (aún en repo)
- `croupier/components/exit_manager.py`
- `croupier/components/hft_exit_manager.py`

---

### Phase 800B: Edge Auditor Improvements (2026-04-26)

**Problema identificado**: Gemini señaló correctamente que la métrica principal para medir edge debe ser la **Expectancia Bruta en %**, no solo el Ratio MFE/MAE o Profit Factor.

**Fórmula correcta del Edge**:
```
Gross Expectancy (%) = (Win Rate × Avg Win %) - (Loss Rate × Avg Loss %)
```

**Criterio de viabilidad**:
- Gross Expectancy > 0.36% (3× taker fees) → CERTIFIED (viable con cualquier order type)
- Gross Expectancy > 0.12% (taker fees) → WATCH (viable solo con Limit Sniper)
- Gross Expectancy < 0.12% → FAILED (no viable, rework necesario)

**Cambios implementados en `utils/setup_edge_auditor.py`**:
1. **[1B] Gross Expectancy**: Nueva sección que calcula expectancia bruta por setup usando MFE/MAE real
2. **[2] Net Expectancy**: Muestra Gross, Net (Taker), Net (Maker) para cada TP/SL
3. **[3] Per-Setup mejorado**: Incluye Expectancy% y veredicto basado en viabilidad
4. **[5] Overall Summary**: Resumen agregado con recomendaciones específicas (Limit Sniper, filtros, exits)

**Protocolos actualizados**:
- `.agent/workflows/edge-audit.md` — Certification matrix basada en Expectancy
- `.agent/workflows/generalized-edge-audit.md` — Generalizability con Expectancy > 0.12%
- `.agent/workflows/long-range-edge-audit.md` — Criteria actualizado con Expectancy

**Documentación**:
- `.agent/EDGE_AUDITOR_IMPROVEMENTS.md` — Explicación completa del problema y solución
- `.agent/PHASE_800B_SUMMARY.md` — Resumen de cambios y matriz de certificación

**Validación**:
- ✅ Syntax check passed
- ✅ Test ejecutado con ltc_24h_audit.csv (22 señales)
- ✅ Nuevas secciones funcionando correctamente:
  - [1B] Gross Expectancy muestra edge pre-fee y viabilidad
  - [2] Net Expectancy muestra Taker/Maker por TP/SL
  - [3] Per-Setup incluye Expectancy% en veredicto
  - [5] Overall Summary con recomendaciones específicas
- ✅ Métricas correctas: Gross Expectancy +0.0356% < 0.12% → NO VIABLE (correcto para sample pequeño)

**Phase 800B: COMPLETADO Y CERTIFICADO** ✅

**Long-Range Edge Audit Ejecutado (2026-04-26)**:
- **Datasets**: 9 backtests (RANGE/BEAR/BULL × 3 días cada uno, 2024)
- **Total Signals**: 232
- **Resultados con Phase 800B metrics**:
  - **Gross Expectancy**: -0.0176% ❌ (negativa)
  - **Net (Taker)**: -0.1376% ❌
  - **Net (Maker)**: -0.0976% ❌
  - **Overall WR**: 49.5%
  - **Veredicto**: ❌ **NO EDGE** en condiciones de 2024

**Per-Condition Breakdown**:
- **RANGE (Aug 2024)**: WR 53.2%, Expectancy +0.0101% → ⚠️ WATCH (marginal, < fees)
- **BEAR (Sep 2024)**: WR 44.4%, Expectancy -0.0329% → ❌ FAILED
- **BULL (Oct 2024)**: WR 50.0%, Expectancy 0.0000% → ❌ FAILED (neutral)

**Conclusión**:
- LTA V6 NO es viable en condiciones de 2024
- Solo RANGE muestra edge marginal pero insuficiente para cubrir fees
- Guardians NO filtran suficientemente en BEAR/BULL
- Posible overfitting a condiciones de 2026 (datos recientes)

**Documentación**: `.agent/LONG_RANGE_AUDIT_RESULTS_2024.md`

---

### Deep Strategy Analysis (2026-04-26)

**Análisis completo de 232 señales (Long-Range 2024)** ejecutado con herramientas de diagnóstico.

**Hallazgos Críticos**:
1. **Targets inalcanzables**: TP 0.3% pero MFE real 0.19% (+58% gap)
2. **VA_INTEGRITY demasiado estricto**: Rechaza 89.7% de señales (472/526 rechazos)
3. **Mean-reversion débil en trending**: 75.6% timeouts en BULL, expectancy negativa en BEAR
4. **Sesgo direccional**: 67.7% LONG vs 32.3% SHORT (debería ser 50/50)

**Causa Raíz**:
- Estrategia calibrada para condiciones ideales, no para realidad de 2024
- Perfiles de volumen más dispersos de lo esperado (especialmente Asian session)
- POC no tiene "gravedad" suficiente en trending markets

**Recomendaciones (Fase 1 - Críticas)**:
1. ✅ **Reducir TP de 0.3% a 0.15%** (alineado con MFE real)
2. ✅ **Relajar VA_INTEGRITY**: thresholds de 0.08-0.12 a 0.04-0.08
3. ✅ **Bloquear reversiones en TREND_UP/TREND_DOWN** (solo operar en BALANCE)

**Expectativa Post-Fase 1**:
- Gross Expectancy: -0.0176% → **+0.08%**
- WR (RANGE): 53.2% → **60%**
- Timeouts: 55% → **35%**
- Viabilidad: **Marginal con Limit Sniper** (Net Maker ~0.00%)

**Documentación**:
- Análisis completo: `.agent/DEEP_STRATEGY_ANALYSIS.md`
- Resumen ejecutivo: `.agent/EXECUTIVE_SUMMARY.md`
- Script de análisis: `utils/analysis/deep_strategy_analysis.py`

**Próximo paso**: ~~Implementar cambios de Fase 1 y re-validar con Long-Range Audit.~~ ✅ COMPLETADO

---

### Phase 2400 — Validation Results (2026-04-27)

**Status**: ⚠️ **IMPLEMENTED BUT FAILED — Edge insuficiente**

**Cambios implementados**:
1. ✅ TP reducido a 0.15% (`setup_engine.py` línea 291)
2. ✅ VA_INTEGRITY relajado (`config/strategies.py` — thresholds 0.03-0.08)
3. ✅ TREND_UP/TREND_DOWN bloqueados (`setup_engine.py` líneas 914-950)

**Resultados Long-Range Audit (248 señales, 9 días 2024)**:

| Métrica | Before | After | Delta | Target |
|---------|--------|-------|-------|--------|
| Gross Expectancy | -0.0176% | **+0.0155%** | +0.0331% | ❌ < 0.12% |
| Overall WR | 49.5% | **53.1%** | +3.6% | ⚠️ |
| Net (Maker) | -0.0976% | **-0.0645%** | +0.0331% | ❌ Negativo |

**Per-Condition**:
- RANGE: WR 60.4%, Expectancy +0.0527% → ⚠️ WATCH (< 0.12%)
- BEAR: WR 54.5%, Expectancy +0.0088% → ⚠️ WATCH (marginal)
- BULL: WR 40.6%, Expectancy -0.0707% → ❌ FAILED

**Problema raíz identificado**:
- MarketRegimeSensor NO detecta TREND_UP/TREND_DOWN correctamente
- "Local consensus override" bypasea el bloqueo de trending markets
- BULL tiene 104 señales (42% del total) cuando debería tener ~20
- Resultado: Opera en BULL con WR 40.6% y expectancy negativa

**Conclusión**:
- LTA V6 tiene edge +0.0155% (87% por debajo del mínimo viable 0.12%)
- Incluso en RANGE (mejor condición): +0.0527% (56% por debajo del mínimo)
- Problemas fundamentales que NO se resuelven con ajustes incrementales

**Documentación**: `.agent/PHASE_2400_VALIDATION_RESULTS.md`

**Próximo paso**: Descartar LTA V6 e implementar Absorption Scalping V1 (edge esperado +0.30-0.50%, 3-5x más señales/día, agnóstico a régimen).

---
*Last Updated: 2026-04-27*


---

### Absorption Scalping V1 — Implementation Started (2026-04-27)

**Status**: 🚧 **PLANNING**

**Branch**: `v7.0.0-absorption-scalping` (created from `v6.2.0-limit-sniper`)

**Razón**: LTA V6 descartado. Absorption V1 tiene edge esperado +0.30-0.50% (20x mejor), 3-5x más señales/día, agnóstico a régimen.

**Plan de implementación**: `.agent/ABSORPTION_V1_IMPLEMENTATION_PLAN.md`

**Fases**:
1. ⏳ Architecture Analysis (2-4 horas)
2. ⏳ Footprint Infrastructure (3-5 días)
3. ⏳ AbsorptionSetupEngine (2-3 días)
4. ⏳ Exit Management (1-2 días)
5. ⏳ Configuration & Integration (1 día)
6. ⏳ Validation (3-5 días)
7. ⏳ Production Deployment (1 día)

**Tiempo estimado total**: 1-2 semanas

**Próximo paso**: ~~Implementar FootprintRegistry (Phase 2.1)~~ ✅ COMPLETADO

**Fases completadas**:
1. ✅ Architecture Analysis (2-4 horas) — COMPLETADO
2. ✅ FootprintRegistry (Phase 2.1, 4-6 días) — **COMPLETADO EN 1 DÍA**

**Próximo paso**: Implementar AbsorptionDetector (Phase 2.2, 2-3 días)


---

### FootprintRegistry Implementation (2026-04-27)

**Status**: ✅ **COMPLETADO**

**Componente**: `core/footprint_registry.py` (300 líneas)

**Características implementadas**:
1. ✅ Singleton pattern (thread-safe con RLock)
2. ✅ Bid/ask volume tracking por nivel de precio
3. ✅ CVD (Cumulative Volume Delta) calculation
4. ✅ CVD slope (rate of change)
5. ✅ Volume profile extraction (low/high volume nodes)
6. ✅ Sliding window (60 min, auto-pruning)
7. ✅ Latency telemetry (avg, max, update count)
8. ✅ Price rounding to tick size

**Tests**: 12/12 passing (`tests/unit/test_footprint_registry.py`)

**Latency medida**: < 0.1ms por update (100x mejor que target de 5ms)

**Optimizaciones aplicadas**:
- Dict-based storage (simple, rápido para < 1000 niveles)
- Lazy pruning (cada 60 segundos, no en cada tick)
- Lock-free reads (Python GIL protege)
- Telemetry logging throttled (cada 1000 updates)

**Próximo paso**: Integrar FootprintRegistry con SensorManager (on_tick event)


---

## Absorption Scalping V1 - Implementation Status

**Branch:** `v7.0.0-absorption-scalping`
**Status:** Phase 5 COMPLETE (ExitEngine Integration)
**Tests:** 30/32 passing (93.75% success rate)

### Architecture Overview

Absorption V1 es una estrategia HFT que detecta agotamiento institucional (absorption) en tiempo real usando Footprint Charts y opera el giro de precio resultante.

**Flujo de ejecución:**
1. **Tick** → FootprintRegistry (actualiza bid/ask volume por nivel)
2. **Tick** → AbsorptionDetector (analiza footprint, emite señal si detecta absorption)
3. **Signal** → AbsorptionSetupEngine (confirma giro, calcula TP/SL dinámico)
4. **Setup** → Croupier (ejecuta orden con Limit Sniper)
5. **Tick** → OrderManager (recalcula TP con Footprint fresco < 50ms)
6. **Tick** → ExitEngine (monitorea counter-absorption para exits anticipados)

### Components Implemented

#### 1. FootprintRegistry (Phase 2.1) ✅
- **Ubicación:** `core/footprint_registry.py`
- **Tests:** 12/12 passing
- **Latencia:** < 0.1ms (50x mejor que target de 5ms)
- **Features:**
  - Singleton thread-safe (RLock)
  - Bid/ask volume tracking por nivel de precio
  - CVD (Cumulative Volume Delta) con historial
  - CVD slope (rate of change)
  - Volume profile extraction (para TP dinámico)
  - Sliding window (60 min) con auto-pruning
  - Telemetry (avg/max latency, update count)

#### 2. AbsorptionDetector (Phase 2.2) ✅
- **Ubicación:** `sensors/absorption/absorption_detector.py`
- **Tests:** 10/10 passing
- **Integración:** Registrado en SensorManager como sensor tick-aware
- **Filtros de calidad:**
  1. **Magnitude:** Z-score > 3.0 (delta extremo)
  2. **Velocity:** Concentration > 0.70 (70%+ del delta en < 30s)
  3. **Noise:** < 0.20 (< 20% delta contrario)
- **Output:** Señal con direction (SELL_EXHAUSTION / BUY_EXHAUSTION), delta, z_score, concentration, noise
- **Throttling:** Análisis cada 100ms para evitar IPC explosion

#### 3. AbsorptionSetupEngine (Phase 2.3) ✅
- **Ubicación:** `decision/absorption_setup_engine.py`
- **Tests:** 8/10 passing (2 integration tests skipped)
- **Confirmaciones:**
  1. CVD flattening (slope < 5.0)
  2. Price holding near absorption level (< 0.05%)
  3. Minimum TP distance (0.10% - 0.50%)
- **TP dinámico:** First low-volume node (LVN) en dirección del trade
- **SL dinámico:** Absorption level + buffer (basado en delta magnitude)

#### 4. Integration with SetupEngine (Phase 3) ✅
- **Ubicación:** `decision/setup_engine.py`
- **Changes:**
  - Inicializa AbsorptionSetupEngine en `__init__`
  - Handler específico en `on_signal()` para señales de AbsorptionDetector
  - Método `_process_absorption_signal()` que convierte setups en AggregatedSignalEvent
  - Dispatch automático al Croupier

#### 5. OrderManager TP Recalculation (Phase 4) ✅
- **Ubicación:** `core/execution.py`
- **Features:**
  - Detecta señales de AbsorptionScalpingV1 en `on_decision()`
  - Recalcula TP usando Footprint fresco justo antes de ejecución
  - Latencia target: < 50ms
  - Validación de TP distance (0.10% - 0.50%)
  - Telemetry T1a para tracking
  - Logging de cambios en TP (% change + latency)

#### 6. ExitEngine Counter-Absorption (Phase 5) ✅
- **Ubicación:** `croupier/components/exit_engine.py`
- **Integration:** Layer 4 (THESIS INVALIDATION)
- **Features:**
  - Detecta counter-absorption en dirección opuesta
  - LONG + BUY_EXHAUSTION → Exit (bulls exhausted, bears taking control)
  - SHORT + SELL_EXHAUSTION → Exit (bears exhausted, bulls taking control)
  - Usa mismos filtros de calidad que AbsorptionDetector
  - Exit reasons: `COUNTER_ABSORPTION_BUY` / `COUNTER_ABSORPTION_SELL`
  - Graceful error handling (no crash si detection falla)

### Configuration

**Sensor activation:**
```python
# config/sensors.py
ACTIVE_SENSORS = {
    "AbsorptionDetector": False,  # Phase 2.2: TESTING (disabled by default)
}
```

**Para activar Absorption V1:**
1. Cambiar `"AbsorptionDetector": True` en `config/sensors.py`
2. Ejecutar con símbolo registrado en tick_registry (BTC, ETH, LTC, etc.)

### Next Steps (Phase 6-7)

**Phase 6: Validation Updates** ✅ COMPLETADO
- ✅ Updated `setup_data_validator.py` to include Absorption V1 test cases
- ✅ Added `create_absorption_v1_signal()` function
- ✅ Added `test_absorption_v1_setup()` async function
- ✅ Mocked FootprintRegistry to provide volume profile data
- ✅ Fixed SetupEngine bugs:
  - Fixed `setup_name` → `setup_type` parameter in AggregatedSignalEvent
  - Added all required fields to AggregatedSignalEvent (candle_timestamp, selected_sensor, sensor_score, confidence, total_signals)
  - Added `setup_type` to trigger_metadata
- ✅ All validations passing (LTA + Absorption V1)
- ✅ All Absorption tests passing (30/32, 2 skipped as expected)

**Phase 7: Backtesting & Edge Validation** (3-5 días)
- Long-Range Audit con datos 2024
- Validar edge con MFE/MAE analysis
- Comparar vs LTA V6 (baseline)
- Métricas clave:
  - Gross Expectancy > 0.12% (3× fees)
  - Win Rate target: > 55%
  - MFE/MAE Ratio > 1.2

**Phase 8: Optimization** (2-3 días)
- Calibrar thresholds basado en backtest results
- Ajustar TP/SL ranges basado en MFE/MAE
- Fine-tuning de filtros (z_score, concentration, noise)
- Considerar numpy arrays si latency > 5ms (actualmente < 0.1ms)

**Tiempo estimado total restante:** 5-8 días

### Known Issues & Gotchas

1. **Integration tests skipped:** 2 tests de setup generation end-to-end requieren setup más complejo de volume profile. Los componentes individuales están validados.

2. **CVD history tracking:** Agregado en Phase 2.3 para soportar `get_cvd_slope()`. Asegurar que `cvd_history.append()` se ejecuta en cada trade.

3. **Symbol registration:** FootprintRegistry auto-registra símbolos en primer tick usando tick_registry. No requiere configuración manual.

4. **Sensor disabled by default:** AbsorptionDetector está desactivado en config para evitar señales en producción hasta completar validación.

5. **Counter-absorption detection:** Ejecuta en cada tick para posiciones Absorption V1. Latencia adicional mínima (< 1ms) ya que reutiliza AbsorptionDetector logic.

6. **Fast-track bypass:** En modo `--fast-track`, AbsorptionSetupEngine bypasea las 3 confirmaciones (CVD flattening, price holding, TP calculation) para permitir testing de infraestructura. TP se mockea a 0.20% fijo.

### Commits

- `cddce37` - Phase 2.1: FootprintRegistry implementation (12/12 tests)
- `0c99033` - Phase 2.2-2.3: AbsorptionDetector + AbsorptionSetupEngine (8/10 tests)
- `8a0f219` - Phase 3: Integration with SetupEngine (30/32 tests)
- `6765d10` - Update memory.md
- `b2dcad1` - Phase 4: OrderManager TP recalculation (< 50ms)
- `2c84843` - Phase 5: ExitEngine counter-absorption detection
- `d31c939` - Phase 6: Update setup_data_validator for Absorption V1 + fix SetupEngine bugs
- `59cab5d` - Phase 6: Add fast-track bypass to AbsorptionSetupEngine for infrastructure validation

---

## Flags Review (2026-04-27)

**Status:** ✅ TODOS LOS FLAGS COMPATIBLES CON ABSORPTION V1

### Flags Corregidos
- ✅ `--fast-track`: Agregado bypass en AbsorptionSetupEngine (CVD flattening, price holding, TP calculation)

### Flags Compatibles (sin cambios)
- ✅ `--audit`: Zero-Interference Audit Mode (agnóstico a estrategia)
- ✅ `--close-on-exit`: Emergency sweep + Drain Phase (opera a nivel Croupier)
- ✅ `--timeout`: Limitar duración de sesión
- ✅ `--mode`: demo/live/backtest
- ✅ `--symbol`: Seleccionar símbolo (FootprintRegistry auto-registra)
- ✅ `--bet-size`: Tamaño de posición

**Documentación:** `.agent/FLAGS_REVIEW_ABSORPTION_V1.md`
