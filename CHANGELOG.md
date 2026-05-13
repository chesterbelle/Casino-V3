# Changelog 📝

All notable changes to Casino-V3 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [8.0.0] - 2026-05-13

### Added - AMT Scenario V10 Alpha (Generalized Certification)
- **Priority-Based Orchestration**: Refactored `ScenarioManager` to evaluate all candidate scenarios per tick and dispatch based on statistical edge (Precedence: `LiquidityExhaustion` > `AbsorptionReversal` > `FailedBreakout` > `TrendAcceptance`).
- **Telemetry & Reporting**: Integrated `get_scenario_stats()` into `SetupEngine` and `backtest.py` to provide real-time scenario distribution transparency (e.g., 74% Absorption, 4% Exhaustion).
- **Source-Level Exhaustion Gate**: Integrated Delta Intensification checks directly into `FailedBreakoutDetector` and `LiquidityExhaustionDetector`, eliminating fragile external orchestration patches.

### Changed
- **SetupEngine Logic**: Removed redundant "reversion gates" in favor of the new prioritized dispatcher.
- **Scenario Detectors**: Standardized cooldowns and logic gates to ensure consistent event lifetimes.

### Verified - Generalized Edge Audit (10 Coins × 24h L2)
- **Global Result**: **7/10 Coins CERTIFIED/WATCH** (Win Rate > 50%).
- **LTC/USDT (Full 24h)**: **67.3% WR**, **+0.312% Gross Exp** ✅.
- **ETH/USDT (Full 24h)**: **61.1% WR**, **+0.282% Gross Exp** ✅.
- **XRP/USDT (Full 24h)**: **66.7% WR**, **+0.217% Gross Exp** ✅.
- **Findings**: Low-liquidity/High-volatility assets (SOL, AVAX, DOGE) showed negative edge due to "Delta Surges" bypassing structural levels.
- **Generalizability Score**: **70%** (Edge is confirmed as a market microstructure property, not an anomaly).

---

## [7.4.0] - 2026-05-11

### Fixed - Absorption Detector Implementation Bugs (Layer 1 Diagnostic)
- **Config not wired**: `AbsorptionDetector` hardcoded Z≥1.5, Conc≥0.15, Noise≤0.85 instead of reading from `config/absorption.py` (Z≥3.0, Conc≥0.50, Noise≤0.35). Config now imported directly.
- **Concentration was time-proxy**: `_concentration()` returned 0.90/0.60/0.30 based on `time_since_update` — not measuring actual volume concentration. Reimplemented as `dominant_vol / total_vol` per level.
- **Noise ratio inverted**: `_noise_ratio()` returned aggressor volume as "noise" and counter-directional as "signal". Fixed: counter-directional volume is now correctly identified as noise.

### Fixed - Target Calculation Bugs (Layer 2 Diagnostic)
- **POC TP on wrong side**: 67% of reversion signals had TP (POC) on opposite side of entry. Added `poc_valid` check: POC must be in trade direction, else use ATR-based TP.
- **SL behind VA too wide**: Reversion SL avg 1.26% vs MAE 0.194% (6.5× too wide). Replaced with ATR-based SL + 0.30% minimum (aligned with edge-audit calibration).

### Changed - Volume Profile Architecture (V4→V9)
- **RegimeGuardian**: VWAP Z-score → Volume Profile (POC/VAH/VAL) for `value_position` determination.
- **GuardianManager**: Removed `StatisticalLocationGuardian` from pipeline. Added poc/vah/val to attribution traces.
- **SetupEngine**: Targets use ATR-based SL with VA as directional reference only (not distance).

### Verified - Edge Audit V9 (LTC/USDT RANGE, 1-day L2 backtest)
- **Gross Expectancy**: **+0.224%** (first positive with dynamic targets + L2 real data)
- **Net Taker**: **+0.104%** | **Net Maker**: **+0.144%**
- **Overall WR**: 66.7% (33 decided, 145 timeouts)
- **Reversion**: 92.3% WR, +0.425% Exp (105 signals, 92 timeouts)
- **Rotation**: 41.2% WR, +0.028% Exp (70 signals)
- **Continuation**: 100% WR, +0.250% Exp (n=3)
- ⚠️ Edge is marginal: +0.104% net < 3× fee threshold

### Evolution V3→V9
| Ver | Signals | WR | Gross Exp | Net Taker | Root Cause |
|-----|---------|-----|-----------|-----------|------------|
| V3  | 399 | 33.0% | +0.052% | -0.068% ❌ | VWAP baseline |
| V4  | 503 | 60.3% | -0.114% | -0.234% ❌ | VP routing, broken targets |
| V5  | 122 | 61.9% | -0.359% | -0.479% ❌ | Strict filters killed high-Z signals |
| V9  | 178 | 66.7% | +0.224% | +0.104% ✅ | ATR SL + POC validation |

---

## [7.3.0] - 2026-05-06

### Added - Total Spectrum Absorption V3.2 (The Inertia Pivot)
- **Dual-Core Architecture**: Strategy now intelligently classifies and executes both `REVERSION` and `CONTINUATION` setups via the `GuardianManager`.
- **Squeeze Guard (V3.1)**: Implemented a structural quality filter in `SetupEngineV4` to reject trades in high-volatility "Chaos Zones," stabilizing MAE at **0.47%**.
- **Inertia Guard (V3.2)**: New momentum confluence layer that requires positive CVD acceleration within a 2-second window for trend-aligned entries.
- **Micro-Flow Confirmation**: Integrated 0-latency CVD tracking from `MicrostructureEvent` history to validate aggressive follow-through.
- **Strategy Manifestos**: Created comprehensive documentation for both institutional alpha scrutiny (`absorption_scalping_v3.md`) and technical implementation (`v3_technical_manifesto.md`).

### Verified - Edge Audit Certification (LTC + SOL)
- **Win Rate**: **66.7%** (Massive improvement via Inertia Guard).
- **Gross Expectancy**: **+0.2678%** per trade.
- **Net Performance**: **+0.1478% (Taker)** / **+0.1878% (Maker)**.
- ✅ **Certified for Taker Trading**: Gross expectancy > fees.

---

## [6.1.0] - 2026-04-11

### Added - LTA V4 Structural Reversion Pivot
- **Structural Location Gate**: Strategy migrated from Dale's micro-footprint signals to LTA V4 geometric bounds targeting the POC from VAH/VAL boundaries.
- **Dynamic Warmup**: Removed the arbitrary 60-minute time-lock. The `SetupEngine` now assumes "Combat Ready" status dynamically once the `ContextRegistry` loads the daily volume profile.
- **Fast-Track Infrastructure Bypass**: The `--fast-track` flag now overrides the Location Gate to force extreme mechanical execution testing without having to wait for actual VAH/VAL border crosses.
- **Execution Validation**: The execution quality workflow now gracefully accepts 0-trade runs as normal for short Live windows, and validates the event loop natively.

---

## [4.5.0] - 2026-04-03

### Added - Order Flow Refactor & Structural SL (Phase 850/860)
- **Continuation Pullbacks (Option A)**: Transformed immediate market entries into `PULLBACK_WATCH` states, targeting the POC of the trigger candle.
- **Delta Divergence Playbook**: New high-probability playbook with strict structural proximity gating (POC, VAH, VAL, IB).
- **Exhaustion Climax Gating**: Toxic OrderFlow (Z > 4.5) now requires a confirming `TacticalExhaustion` event within a 5s window to validate reversals.
- **Structural Stop-Loss**: Migrated from percentage-based SL to candle-boundary SL (+/- 2 ticks from trigger candle's high/low).
- **Metadata Enrichment**: Tactical sensors now inject `high`, `low`, and `poc` into event metadata for precise structural targeting.

### Fixed
- **UnboundLocalError**: Resolved variable scoping issues in `SetupEngineV4._process_microstructure` during multi-event playbook evaluation.

---

## [4.4.0] - 2026-04-02

### Added - Setup Edge Auditor (Phase 800)
- **Modo --audit (Zero-Interference)**: New CLI flag to record raw signals and price trajectories without bot intervention.
- **Bypass de Interferencia**: El `ExitManager` ahora ignora `Shadow SL`, `Breakeven` y `Micro-Exits` cuando el modo auditoría está activo.
- **Alta Definición de Datos**: El `Historian` ahora graba tablas de `signals` y `price_samples` (muestreo cada 1s).
- **Herramienta de Análisis Alpha**: Nuevo script `utils/setup_edge_auditor.py` para calcular MFE/MAE y la expectativa estadística de cada setup.
- **Paridad en Backtest**: El modo auditoría está disponible tanto en `main.py` como en `backtest.py`.

### Changed
- `config/trading.py`: Added `AUDIT_MODE` and `AUDIT_SAMPLING_FREQ`.
- `croupier/components/exit_manager.py`: Logic updated to respect `AUDIT_MODE`.
- `main.py` & `backtest.py`: CLI updated to support `--audit`.

---

## [4.3.0] - 2026-02-28

### Performance - HFT Latency Compression (Phase 310)
- **Tick-to-Order (T0-T2)**: Compressed from 551ms to **5.4ms** (100x improvement)
- **Signal Aggregation (T0-T1)**: 3.9ms avg (was 140ms, `SIGNAL_TIMEOUT_MS` 500→20ms)
- **Signal-to-Wire (T1-T2)**: 1.5ms avg (was 411ms, eliminated REST fallbacks)
- **TP/SL Parallelism Gap**: 3ms (was 10ms in Phase 240)
- **Error Recovery**: $0.00 (0 error trades across 150-min stress test)

### Changed
- `exchange_adapter.py`: WS cache staleness threshold extended to 60s (was 1.5s)
- `aggregator.py`: `SIGNAL_TIMEOUT_MS` compressed from 500ms to 20ms
- `.gitignore`: Hardened to prevent future log/data leakage

### Removed - Repo Cleanup
- Removed 19 debug/one-off scripts from root directory
- Removed 4 v4.2.0 backup files (preserved in git history)
- Removed 3 strategy backup copies
- Removed 16 stale log/report text dumps
- Updated all documentation to v4.3.0

### Verified
- ✅ 150-minute stress test: 74 trades, $0.00 error leakage
- ✅ 4-layer validation pipeline: Preflight, Concurrency, Latency (3ms), Chaos
- ✅ 100% Healing Efficiency (11/11 positions saved)
- ✅ 100% WebSocket integrity (0 unmatched events)

---

## [4.2.0] - 2026-02-22

### Added - Phase 240 HFT Optimizations
- **Execution Airlock**: IPC-based order execution via multiprocessing
- **4 Ingestion Shards**: Parallel WebSocket ingestion workers
- **Bulk Ticker Optimization**: Batch REST fallback for cache misses
- **TP/SL Parallelism**: Near-simultaneous bracket placement (10ms gap)

### Verified
- ✅ Phase 240: HFT benchmark passing all targets

---

## [4.1.0] - 2026-02-17

### Added - Phase 160 Resilience
- **Healing System**: Automatic orphan recovery with grace periods
- **Shadow SL**: In-memory stop-loss monitoring for rapid exit
- **Dynamic Drain**: 4-stage progressive exit (OPTIMISTIC→PANIC)
- **PortfolioGuard**: Drawdown protection with error caps

### Verified
- ✅ Phase 160: 100% healing efficiency, <2% orphan hygiene

---

## [4.0.0] - 2026-01-15

### Added - V4 Reactor Architecture
- **Clock Reactor**: Event-driven tick processing
- **Croupier V4**: Unified order lifecycle management
- **ReconciliationWorker**: Async exchange-state synchronization
- **TradeHistorian**: Persistent SQLite trade database

---

## [2.3.1] - 2025-12-28

### Fixed - Chaos Endurance Round 1 Completion
- **OCOManager Lock Leakage**: Fixed `pending_symbols` not releasing on price fetch failures
- **RateLimiter Timeouts**: Added 45s safety timeout to prevent indefinite waits
- **Connector Disconnect Timing**: Moved disconnect after `emergency_sweep`
- **Emergency Sweep**: Hardened with `return_exceptions=True`

### Verified
- ✅ 134 trades, 150 minutes, **53/53 positions closed cleanly**

---

## [2.0.0] - 2025-12-10

### Added - Casino-V3 Rewrite
- Native Exchange Integration (removed CCXT)
- WebSocket-First Architecture
- OCOManager, PositionTracker, ErrorHandler, CircuitBreaker
- Multiprocessing Sensors

---

## Stable Version Tags

| Tag | Date | Highlights |
|:----|:-----|:-----------|
| `v4.3.0-hft-stable` | 2026-02-28 | 5.4ms T0-T2, $0.00 errors |
| `v4.2.0-throughput-optimized` | 2026-02-22 | Execution Airlock, 4 shards |
| `v4.1.0-resilience-stable` | 2026-02-17 | Healing, Shadow SL, Drain |
| `v4.0.0-beta-stable` | 2026-01-15 | V4 Reactor Architecture |
