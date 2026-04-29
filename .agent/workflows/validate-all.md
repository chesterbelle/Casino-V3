---
description: Progressive validation pipeline for Absorption V1 architecture (6 layers, component-by-component → full integration)
---

# Validate-All: Progressive Integration Pipeline

// turbo-all

## Overview
Validation from isolated component math → pairwise integration → full pipeline → chaos stress.
Each layer must pass before proceeding to the next.

## Architecture Philosophy

**Layer 0.x** = Unit tests of isolated components (atomic math, no dependencies)
  - Input: Known synthetic data
  - Output: Assert exact values
  - No bot, no SensorManager, no database
  - **Purpose**: "Is the math correct?"

**Layer 1.x** = Pairwise integration (two components connected)
  - Input: Synthetic events flowing between components
  - Output: Verify data flows correctly at the boundary
  - **Purpose**: "Do these two components talk to each other correctly?"

**Layer 2.x** = Subsystem integration (full subsystem, e.g. signal pipeline)
  - Input: Real or realistic data through a complete subsystem
  - Output: Verify end-to-end subsystem behavior
  - **Purpose**: "Does the signal pipeline produce valid trades?"

**Layer 3.x** = Full pipeline integration (all subsystems connected)
  - Input: Real exchange or backtest data
  - Output: Verify complete bot lifecycle
  - **Purpose**: "Does the bot work as a whole?"

**Layer 4-5** = Stress & chaos (concurrent, adversarial)
  - Input: Concurrent chaos fuzzer, pressure benchmark
  - Output: Verify no data corruption under stress
  - **Purpose**: "Does it survive real-world conditions?"

**Debugging Principle**: When a bug occurs, the layer that fails tells you WHERE the bug is.
- Layer 0.B fails → bug is in AbsorptionDetector math
- Layer 0.B passes but Layer 1.2 fails → bug is in SensorManager↔Detector wiring
- Layer 1.2 passes but Layer 2.1 fails → bug is in SetupEngine signal→setup conversion
- All pass but production fails → bug is in deployment/config

---

## LAYER 0: ISOLATED COMPONENT MATH (No dependencies)

### Layer 0.A: FootprintRegistry Math
```bash
.venv/bin/python utils/validators/absorption_footprint_validator.py
```
**Must pass**: FootprintRegistry correctly accumulates trade data (ask/bid/delta/CVD).
- BUY trades → ask_volume +, delta +
- SELL trades → bid_volume +, delta -
- round_price() snaps to tick size
- get_volume_profile() returns correct range
- prune_old_levels() removes stale data without corrupting CVD

**Debug if fails**: Bug is in `core/footprint_registry.py` math logic.

### Layer 0.B: Absorption Quality Filters Math
```bash
.venv/bin/python utils/validators/absorption_guardian_validator.py
```
**Must pass**: The 3 quality filter methods compute correct metrics and pass/fail decisions.
- _calculate_z_score() with known history → correct z-score
- _calculate_concentration() with known timestamps → correct ratio
- _calculate_noise() with known ask/bid → correct opposite-volume ratio
- _validate_magnitude/velocity/noise() pass/fail at threshold boundaries

**Debug if fails**: Bug is in `sensors/absorption/absorption_detector.py` filter math.

### Layer 0.C: Candidate Detection Math
```bash
.venv/bin/python utils/validators/absorption_candidate_validator.py
```
**Must pass**: _find_extreme_deltas() correctly identifies absorption candidates.
- Returns top 5% by absolute delta (not by sign)
- Returns empty when < 10 levels with non-zero delta
- Top candidate has highest |delta|
- Correctly identifies SELL (negative delta) and BUY (positive delta) candidates

**Debug if fails**: Bug is in `sensors/absorption/absorption_detector.py` candidate ranking.

### Layer 0.D: Signal Generation (Isolated Detector)
```bash
.venv/bin/python utils/validators/absorption_signal_validator.py
```
**Must pass**: AbsorptionDetector.calculate() generates correct signals end-to-end.
- Obvious SELL absorption → SELL_EXHAUSTION signal with side=LONG
- Obvious BUY absorption → BUY_EXHAUSTION signal with side=SHORT
- No absorption (flat footprint) → None
- Insufficient footprint (< 10 levels) → None
- Signal has all required fields (direction, z_score, concentration, noise, level, side, volume_profile, price)

**Debug if fails**: Bug is in `sensors/absorption/absorption_detector.py` signal assembly.
**Debug if passes but Layer 1.2 fails**: Bug is in SensorManager wiring, not detector logic.

### Layer 0.E: ExitEngine Layer Math
```bash
.venv/bin/python utils/validators/exit_engine_validator.py
```
**Must pass**: Each ExitEngine layer computes correct exit decisions independently.
- Layer 5: Catastrophic triggers at >50% loss, never on profitable position
- Layer 4: Flow invalidation at Z>3.0 early / Z>5.5 emergency (correct direction)
- Layer 4: Counter-absorption: LONG+BUY_EXHAUSTION → exit, SHORT+SELL_EXHAUSTION → exit
- Layer 4: Stagnation ONLY triggers when unrealized PnL < 0 (profit-aware fix)
- Layer 3: Valentino triggers at 70% of TP distance, scale-out 50%
- Layer 2: Breakeven moves SL to entry when profit threshold reached
- Layer 1: Session drain activates only when croupier.is_drain_mode=True
- _pending_terminations prevents double-close from concurrent layers

**Debug if fails**: Bug is in `croupier/components/exit_engine.py` layer logic.
**NEW VALIDATOR** — Must be created.

### Layer 0.F: VirtualExchange Fee Accounting
```bash
.venv/bin/python utils/validators/virtual_exchange_fee_validator.py
```
**Must pass**: VirtualExchange correctly tracks and reports total fees (entry + exit).
- Market order: fee = notional × taker_rate (0.05%) + slippage
- Limit order (filled): fee = notional × maker_rate (0.02%), no slippage
- Position stores `entry_fee` on open
- Closing trade records `fee = entry_fee + exit_fee` (NOT just exit_fee)
- Limit BUY fills at min(limit, current) — never overpays
- Limit SELL fills at max(limit, current) — never undersells
- force_close_all_positions reports total_fee correctly

**Debug if fails**: Bug is in `exchanges/connectors/virtual_exchange.py` fee/price logic.
**NEW VALIDATOR** — Must be created. Critical for backtest accuracy.

### Layer 0.G: OCOManager Limit Order Logic
```bash
.venv/bin/python utils/validators/oco_limit_order_validator.py
```
**Must pass**: OCOManager correctly places limit orders when Limit Sniper enabled.
- LIMIT_SNIPER_ENABLED=True: _execute_main_order places LIMIT (not market)
- Limit price = level × (1+offset) for LONG, level × (1-offset) for SHORT
- LIMIT_SNIPER_ENABLED=False: _execute_main_order places MARKET (default)
- LIMIT_SNIPER_OFFSET_PCT correctly applied in both directions
- Limit order rejected if price would be negative or zero

**Debug if fails**: Bug is in `croupier/components/oco_manager.py` _execute_main_order.
**NEW VALIDATOR** — Must be created.

---

## LAYER 1: PAIRWISE INTEGRATION (Two components connected)

### Layer 1.1: FootprintRegistry + SensorManager (Tick Ingestion)
```bash
.venv/bin/python utils/validators/absorption_footprint_data_validator.py
```
**Must pass**: FootprintRegistry accumulates REAL trade data correctly during backtest.
- Registry receives trades (not empty after backtest)
- Multiple price levels exist (>= 10 non-zero delta levels)
- CVD is non-zero (trades are flowing)
- Volume distribution is realistic (both BUY and SELL trades)
- Levels have recent timestamps (data is fresh)

**Debug if fails**: Bug is in `core/sensor_manager.py` on_tick → FootprintRegistry.on_trade wiring.
**Debug if Layer 0.A fails too**: Bug is in FootprintRegistry math, not wiring.

### Layer 1.2: AbsorptionDetector + SensorManager (Signal Flow)
```bash
.venv/bin/python -m utils.validators.sensor_signal_validator
```
**Must pass**: Active sensors must generate signals with real backtest data.
- AbsorptionDetector generates >= 5 signals (filters not too strict)
- Signals have correct format (direction, z_score, concentration, noise, level)
- SensorManager tick_queues deliver ticks to AbsorptionDetector workers
- No "0 signals" problem (sensor is being called)

**Debug if fails**: Bug is in SensorManager→worker→sensor IPC or config/sensors.py registration.
**Debug if Layer 0.D passes**: Bug is in wiring, not detector logic.

### Layer 1.3: AbsorptionSetupEngine + SetupEngine (Setup Generation)
```bash
.venv/bin/python utils/validators/setup_data_validator.py
```
**Must pass**: Absorption V1 setup must produce valid `tp_price` and `sl_price`.
- No setup returns with missing or zero TP/SL values
- CVD flattening confirmation works (slope < 5.0)
- Price holding confirmation works (< 0.05% from level)
- TP distance in valid range (0.10% - 0.50%)
- SL placed at absorption level + buffer

**Debug if fails**: Bug is in `decision/absorption_setup_engine.py` confirmation/TP/SL logic.

### Layer 1.4: ExitEngine + Croupier (Exit Execution)
```bash
.venv/bin/python utils/validators/exit_engine_integration_validator.py
```
**Must pass**: ExitEngine correctly triggers Croupier close operations.
- Catastrophic exit → croupier.close_position() called with correct reason
- Valentino scale-out → croupier.scale_out_position() called (50% partial)
- Counter-absorption → immediate close, no grace period
- _pending_terminations prevents double-close
- Audit mode: ExitEngine logs but does NOT execute closes

**Debug if fails**: Bug is in ExitEngine→Croupier callback wiring.
**NEW VALIDATOR** — Must be created.

---

## LAYER 2: SUBSYSTEM INTEGRATION (Full subsystem)

### Layer 2.1: Signal Pipeline (Tick → Signal → Setup → Decision)
```bash
.venv/bin/python -m utils.validators.decision_pipeline_validator
```
**Must pass**: Complete signal pipeline produces valid DecisionEvents.
- 0 FATAL MATH INVERSION (TP/SL prices match strategy intent)
- 0 PIPELINE LEAK DETECTED (no signals lost between components)
- Context Mirror Integrity ✅ (ContextRegistry data consistent)
- DecisionEvent has valid tp_price, sl_price, bet_size, side
- Limit Sniper: limit_price extracted from trigger_level when enabled

**Debug if fails**: Trace the DecisionEvent through each component to find where data is lost/mutated.

### Layer 2.2: Execution Pipeline (Decision → Order → Position → Exit)
```bash
.venv/bin/python -m utils.validators.trading_flow_validator --exchange binance --symbol LTCUSDT --mode demo --size 0.05 --execute-orders
```
**Must pass**: 8/8 lifecycle tests.
- CONNECTION: Exchange connection established
- ORDER: Market/Limit order placed and filled
- OCO: Bracket (entry + TP + SL) created atomically
- TRACKING: Position appears in PositionTracker
- CLOSE: Position closed (TP or SL hit)
- ORPHAN: cleanup_symbol removes orphaned orders
- SHUTDOWN: Graceful shutdown with no hanging tasks
- ERROR: Error recovery works (circuit breaker → retry)

**Debug if fails**: Check logs for which specific test failed. Each test is independent.

---

## LAYER 3: FULL PIPELINE (All subsystems connected)

### Layer 3.1: Backtest End-to-End (VirtualExchange)
```bash
.venv/bin/python backtest.py --exchange binance --symbols LTCUSDT --start 2026-04-12 --end 2026-04-13
```
**Must pass**: Complete backtest produces trades with correct fee accounting.
- Trades recorded in Historian with total_fee (entry + exit)
- No "0 trades" when signals exist (check Layer 1.2 first)
- PnL = gross - total_fee (not gross - exit_fee only)
- Limit Sniper: maker fee on entry, taker fee on exit
- Valentino: partial close + SL move to breakeven tracked correctly
- ExitEngine counter-absorption exits recorded with correct reason

**Debug if fails**: Check `data/historian.db` for trade records. Compare fee field against expected.

### Layer 3.2: Multi-Symbol Concurrency
```bash
.venv/bin/python -m utils.validators.multi_symbol_validator --symbols LTCUSDT,DOGEUSDT,ETHUSDT --mode demo --size 500
```
**Must pass**: CONCURRENCY ✅ + INTEGRITY ✅
- Positions tracked independently per symbol
- No cross-symbol position contamination
- ExitEngine processes each symbol's positions independently (O(1) per symbol)

**Debug if fails**: Check PositionTracker for symbol normalization issues.

---

## LAYER 4: STRESS & CHAOS

### Layer 4.1: HFT Latency Benchmark
```bash
.venv/bin/python -m utils.validators.hft_latency_benchmark --symbols LTCUSDT,DOGEUSDT --mode demo --size 500 --iterations 3
```
**Must pass**: BRACKET_LATENCY ✅ (avg < 500ms), TP_SL_PARALLEL ✅, CACHE_HIT ✅

### Layer 4.2: Chaos Stress Test
```bash
.venv/bin/python -m utils.validators.multi_symbol_chaos_tester --symbols BTCUSDT,ETHUSDT,LTCUSDT --mode demo --duration 300 --max-ops 15
```
**Must pass**: 0 UNMATCHED events, 0 Task Stalls (Watchdog), Error Recovery = $0, Integrity ✅

### Layer 4.3: Reactor Pressure Benchmark
```bash
.venv/bin/python utils/validators/execution_pressure_benchmark.py --duration 30 --event-freq 2000
```
**Must pass**: Max Jitter < 100ms, 0 Systemic Stalls.

### Layer 4.4: Chaos Audit
// turbo
```bash
.venv/bin/python utils/audit_logs.py logs/chaos_test_$(ls -t logs/ | head -1)
```

---

## LAYER 5: EDGE VALIDATION (Strategy-specific)

### Layer 5.1: Edge Audit (Single Condition)
```bash
.venv/bin/python utils/setup_edge_auditor.py --dataset tests/validation/ltc_24h_audit.csv
```
**Must pass**: Gross Expectancy > 0.12% (viable with Limit Sniper).
- MFE/MAE Ratio > 1.2 (structural edge exists)
- Win Rate > 55% at optimal TP/SL
- Fee impact: Net (Maker) > Net (Taker)

**Debug if fails**: Strategy edge insufficient. Check Layer 0-3 first to rule out bugs.

### Layer 5.2: Long-Range Edge Audit (Multi-Condition)
```bash
.venv/bin/python utils/analysis/per_condition_audit.py --datasets tests/validation/ltc_24h_audit.csv,tests/validation/ltc_bear_normal_24h.csv,tests/validation/ltc_bull_24h_v2.csv
```
**Must pass**: Edge holds across RANGE + BEAR_NORMAL conditions.
- BULL and BEAR_CRASH may fail (expected — not target conditions)
- RANGE: Gross Expectancy > 0.12%
- BEAR_NORMAL: WR > 50%

---

## Success Criteria

### Layer 0: Isolated Component Math
- [ ] Layer 0.A: FootprintRegistry Math ✅
- [ ] Layer 0.B: Absorption Quality Filters Math ✅
- [ ] Layer 0.C: Candidate Detection Math ✅
- [ ] Layer 0.D: Signal Generation (Isolated) ✅
- [ ] Layer 0.E: ExitEngine Layer Math ✅ ← **NEW**
- [ ] Layer 0.F: VirtualExchange Fee Accounting ✅ ← **NEW**
- [ ] Layer 0.G: OCOManager Limit Order Logic ✅ ← **NEW**

### Layer 1: Pairwise Integration
- [ ] Layer 1.1: FootprintRegistry + SensorManager (Tick Ingestion) ✅
- [ ] Layer 1.2: AbsorptionDetector + SensorManager (Signal Flow) ✅
- [ ] Layer 1.3: AbsorptionSetupEngine + SetupEngine (Setup Generation) ✅
- [ ] Layer 1.4: ExitEngine + Croupier (Exit Execution) ✅ ← **NEW**

### Layer 2: Subsystem Integration
- [ ] Layer 2.1: Signal Pipeline (Tick → Decision) ✅
- [ ] Layer 2.2: Execution Pipeline (Decision → Exit) ✅

### Layer 3: Full Pipeline
- [ ] Layer 3.1: Backtest End-to-End ✅
- [ ] Layer 3.2: Multi-Symbol Concurrency ✅

### Layer 4: Stress & Chaos
- [ ] Layer 4.1: HFT Latency < 500ms ✅
- [ ] Layer 4.2: Chaos Stress (0 UNMATCHED, 0 Stalls) ✅
- [ ] Layer 4.3: Reactor Pressure < 100ms jitter ✅
- [ ] Layer 4.4: Chaos Audit PASS ✅

### Layer 5: Edge Validation
- [ ] Layer 5.1: Edge Audit (Gross Expectancy > 0.12%) ✅
- [ ] Layer 5.2: Long-Range Edge (RANGE + BEAR_NORMAL) ✅

---

## Obsolete Validators (DO NOT RUN)

The following validators reference LTA V4/V5/V6 or "Strategy 2.0" and are **obsolete**:
- `sensor_math_validator.py` — LTA regime/guardian math, replaced by Layer 0.E (ExitEngine)
- `zscore_math_validator.py` — Strategy 2.0 VolatilityRegime, not used in Absorption V1

These files remain in repo for historical reference but should NOT be part of validate-all.

---

## New Validators to Create

| Layer | Validator | Tests | Priority |
|-------|-----------|-------|----------|
| 0.E | `exit_engine_validator.py` | ExitEngine 5-layer math (catastrophic, flow, counter-absorption, valentino, drain) | HIGH |
| 0.F | `virtual_exchange_fee_validator.py` | Fee accounting (entry_fee + exit_fee), limit fill prices | HIGH |
| 0.G | `oco_limit_order_validator.py` | OCOManager limit order placement, offset calculation | MEDIUM |
| 1.4 | `exit_engine_integration_validator.py` | ExitEngine→Croupier close/scale_out callbacks | HIGH |
