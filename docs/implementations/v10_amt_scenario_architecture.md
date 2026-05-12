# V10 Implementation Manifesto: AMT Scenario Architecture

**Branch**: `v8.0.0-absorption-amt`
**Base**: `v7.3.0-total-spectrum-absorption-v3`
**Componentes modificados**: 4 archivos core, 1 archivo nuevo

---

## 1. Visión Arquitectónica

La V10 evoluciona el pipeline de absorción de un **detector genérico + router post-hoc** a un sistema de **escenarios narrativos con confirmación de agotamiento**. El cambio fundamental es: la absorción deja de ser el gatillo final y pasa a ser un componente dentro de narrativas más ricas.

```
V9 (Anterior):
    AbsorptionDetector → ConfirmationSensors → RegimeGuardian → SetupEngine → Targets

V10 (AMT):
    ┌─ AbsorptionDetector → ConfirmationSensors → ExhaustionGate → SetupEngine → Targets
    │
    ├─ FailedBreakoutDetector ────────────────────→ SetupEngine → GuardianManager → Targets
    │
    ├─ LiquidityExhaustionDetector ──────────────→ SetupEngine → GuardianManager → Targets
    │
    └─ TrendAcceptanceDetector ──────────────────→ SetupEngine → GuardianManager → Targets
```

Los 4 paths convergen en el mismo pipeline de dispatch (`GuardianManager → _calculate_targets → AggregatedSignalEvent → Croupier`), pero cada uno tiene su propio detector y lógica de confirmación.

---

## 2. Componentes Modificados

### 2.1 `core/footprint_registry.py` — Exhaustion Metrics

**Cambio**: Nuevo método `FootprintData.get_exhaustion_metrics()` + accessor `FootprintRegistry.get_exhaustion()`.

**Mecánica**:
```python
def get_exhaustion_metrics(self, window_long=10.0, window_short=2.0) -> dict:
    # Recorre cvd_history (deque de (timestamp, cvd) por cada trade)
    # Calcula:
    #   delta_long = cvd_now - cvd_at_cutoff_long   (delta en 10s)
    #   delta_short = cvd_now - cvd_at_cutoff_short  (delta en 2s)
    #   delta_ratio = |delta_short| / |delta_long|   (< 0.5 = agotamiento)
    #   volume_ratio = n_short / (n_long × short/long)  (< 0.6 = vol cayendo)
    return {"delta_ratio", "volume_ratio", "delta_long", "delta_short", ...}
```

**Rendimiento**: O(n) sobre `cvd_history` (deque, maxlen=3600). En el peor caso son 3600 iteraciones — sub-milisegundo. Se calcula una vez por candidato, no por tick.

**Dependencias**: Ninguna nueva. Usa solo `self.cvd_history` que ya se alimenta en `add_trade()`.

### 2.2 `decision/absorption_reversal_guardian.py` — Exhaustion at Registration

**Cambio**: `register_candidate()` ahora calcula exhaustion metrics y las almacena en el `PendingCandidate`.

**Flujo**:
```
register_candidate(candidate, timestamp)
    │
    ├── footprint.get_exhaustion_metrics(10.0, 2.0)
    │       → candidate["exhaustion"] = {delta_ratio, volume_ratio, ...}
    │
    ├── Compute exhaustion_score (0-2):
    │       +1 if delta_ratio < 0.5
    │       +1 if volume_ratio < 0.6
    │
    └── pending.exhaustion = exh
        pending.exhaustion_score = score
```

La exhaustion se calcula al **registrar** el candidato (antes de la confirmación), porque mide el estado del flujo PRE-señal. Durante la confirmación (500ms window), las métricas de exhaustion se propagan al signal confirmado.

**`PendingCandidate` nuevo campo**:
```python
self.exhaustion = candidate.get("exhaustion", {})
self.exhaustion_score = 0  # 0-2
```

### 2.3 `decision/setup_engine.py` — Core Changes

#### 2.3.1 Imports & Init

```python
from decision.amt_scenarios import (
    FailedBreakoutDetector,
    LiquidityExhaustionDetector,
    TrendAcceptanceDetector,
)

# En __init__:
self.failed_breakout = FailedBreakoutDetector()
self.liquidity_exhaustion = LiquidityExhaustionDetector()
self.trend_acceptance = TrendAcceptanceDetector()
self._last_candle_boundary: Dict[str, float] = defaultdict(float)
```

#### 2.3.2 `on_tick()` — AMT Evaluation Pipeline

```python
async def on_tick(self, event):
    symbol, price, timestamp = event.symbol, event.price, event.timestamp

    # 1. Synthesize candle boundaries for TrendAcceptance (60s intervals)
    candle_boundary = timestamp - (timestamp % 60)
    if candle_boundary > self._last_candle_boundary.get(symbol, 0):
        self._last_candle_boundary[symbol] = candle_boundary
        self.trend_acceptance.on_candle(symbol, price, timestamp, ctx, fp)

    # 2. Evaluate AMT scenarios (first match wins)
    amt_signal = (
        self.failed_breakout.on_tick(symbol, price, timestamp, ctx, fp)
        or self.liquidity_exhaustion.on_tick(symbol, price, timestamp, ctx, fp)
        or self.trend_acceptance.on_tick(symbol, price, timestamp, ctx, fp)
    )

    if amt_signal:
        await self._dispatch_amt_signal(amt_signal)
        return  # One signal per tick — no double-firing

    # 3. Original absorption confirmation pipeline
    if symbol not in self.absorption_guardian.pending:
        return
    confirmed = self.absorption_guardian.on_tick(symbol, price, timestamp)
    ...
```

**Orden de evaluación**: `FailedBreakout → LiquidityExhaustion → TrendAcceptance → Absorption`. Si un escenario AMT dispara, el absorption confirmation no se evalúa en ese tick.

#### 2.3.3 Exhaustion Gate (post-guardian, pre-dispatch)

```python
# Solo para reversion + delta_ratio > 1.5:
delta_ratio = exhaustion.get("delta_ratio", 1.0)
if setup_type_name == "reversion" and delta_ratio > 1.5 and not self.fast_track:
    self._trace_decision(sym, "REJECTED", "EXHAUSTION_GATE", ...)
    return
```

**Rationale**: Phase A analysis demostró que reversion WINS tienen delta_ratio=0.52 y TIMEOUTS tienen 1.14. Solo bloqueamos cuando el ratio > 1.5 (agresor claramente intensificándose), porque el volumen_ratio del FootprintRegistry real difiere del análisis offline y un gate demasiado estricto destruye edge.

#### 2.3.4 `_dispatch_amt_signal()` — AMT Signal Pipeline

```python
async def _dispatch_amt_signal(self, signal: dict):
    # Cooldown check (shared cooldown con absorption)
    # In-trade check
    # System warmup check

    # Build reversal_signal for guardians
    reversal_signal = {
        "close": price, "price": price,
        "absorption_level": signal.get("level", 0.0),
        "direction": "SELL_EXHAUSTION" if side == "LONG" else "BUY_EXHAUSTION",
        "tactical_type": signal.get("tactical_type", scenario),
    }

    # Run through GuardianManager (regime + location + spread + liquidity)
    passed, multiplier, setup_mode, value_position = self.guardian_manager.evaluate_all(...)

    # Calculate structural targets (same _calculate_targets as absorption)
    tp_price, sl_price, setup_type_name, level_ref = self._calculate_targets(...)

    # Override setup_type with scenario name for audit tracking
    setup_type_name = scenario  # "failed_breakout", "liquidity_exhaustion", etc.

    # Build metadata with scenario_data
    trigger_meta = {
        "trigger": f"AMT_{scenario}",
        "scenario": scenario,
        "scenario_data": {k: v for k, v in signal.items() if k not in (...)}
    }

    # Dispatch AggregatedSignalEvent
    await self.engine.dispatch(out_evt)
```

### 2.4 `decision/amt_scenarios.py` — NEW: 3 Scenario Detectors

#### FailedBreakoutDetector

```
State: pending_breaks: {symbol: {direction, side, level, break_ts, cvd_at_break}}

on_tick():
    Phase 1: Detect breakout (price > VAH or price < VAL)
        → Store pending break with CVD snapshot

    Phase 2: Monitor for failure (price returns inside VA)
        → Timeout after 60s (breakout held = real)

    Phase 3: Confirm delta divergence
        → CVD change during break was weak/opposite
        → If CVD confirmed break → don't trade (real breakout)

    FIRE: Return signal dict with scenario="failed_breakout"
```

**Config**:
- `cooldown`: 60s (prevents rapid re-fire)
- `max_break_age`: 60s (break must fail within this window)
- `min_break_distance_pct`: 0.03% (filter noise)
- `cvd_divergence_threshold`: 0.3 (CVD < 30% of confirming move)

#### LiquidityExhaustionDetector

```
State: level_tests: {symbol: {level_key: [{ts, delta, cvd_slope, price}, ...]}}
       _at_level: {symbol: level_key or None}

on_tick():
    For each structural level (VAH, VAL):
        If at_level:
            Record test with current delta (min 5s between tests)

        If just_bounced_away AND tests >= 3:
            Check if delta is declining across tests
            If declining → FIRE

    Prune tests older than 120s
```

**Config**:
- `min_tests`: 3 (requires 3+ tests to confirm exhaustion pattern)
- `declining_threshold`: 0.7 (each test < 70% of previous)
- `test_memory_seconds`: 120s
- `min_bounce_pct`: 0.03% (must bounce, not consolidate)

#### TrendAcceptanceDetector

```
State: active_breakouts: {symbol: {side, level, break_ts, cvd_slope}}
       _candle_count_outside: {symbol: int}

on_candle() [called from on_tick via 60s boundary detection]:
    Track candles outside VA
    After 3+ candles outside + CVD confirming → register active_breakout

on_tick():
    If active_breakout exists:
        Check if price pulled back to broken level (± 0.1%)
        Check it hasn't re-entered VA too deep (> 0.1%)
        FIRE if at level
```

**Config**:
- `cooldown`: 60s
- `min_candles_outside`: 3
- `pullback_tolerance_pct`: 0.1%
- `cvd_confirmation_threshold`: 5.0 (slope magnitude)

---

## 3. Data Flow Diagram

```
                    ┌──────────────────────────┐
                    │   WebSocket / BacktestFeed │
                    │  (Trade Ticks + L2 Depth)  │
                    └────────────┬───────────────┘
                                 │
                    ┌────────────▼───────────────┐
                    │     FootprintRegistry       │
                    │  (CVD, Delta, Exhaustion)   │
                    └────────────┬───────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
┌───────▼────────┐    ┌──────────▼──────────┐    ┌───────▼────────┐
│  AbsorptionDet │    │  SessionValueArea   │    │  MarketRegime  │
│  (SensorWorker)│    │  (POC/VAH/VAL)      │    │  (3-layer V2)  │
└───────┬────────┘    └──────────┬──────────┘    └───────┬────────┘
        │                        │                        │
        │              ┌─────────▼──────────┐            │
        │              │  ContextRegistry    ◄────────────┘
        │              │  (Structural Levels │
        │              │   + Regime State)   │
        │              └─────────┬──────────┘
        │                        │
┌───────▼────────────────────────▼──────────────────────────────────┐
│                        SetupEngine.on_tick()                      │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
│  │ FailedBreakout   │  │ LiqExhaustion    │  │ TrendAcceptance │ │
│  │ Detector         │  │ Detector         │  │ Detector        │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬─────────┘ │
│           │                     │                     │           │
│           └─────────────────────┼─────────────────────┘           │
│                                 │ (first match)                   │
│                   ┌─────────────▼───────────────┐                 │
│                   │   _dispatch_amt_signal()     │                 │
│                   └─────────────┬───────────────┘                 │
│                                 │                                 │
│  ┌──────────────────────────────▼──────────────────────────────┐  │
│  │                   AbsorptionReversalGuardian                │  │
│  │  register_candidate() → exhaustion_metrics → on_tick()      │  │
│  │  → ConfirmationSensors (Delta/PriceBreak/CVD) → confirmed  │  │
│  └──────────────────────────────┬──────────────────────────────┘  │
│                                 │                                 │
│                   ┌─────────────▼───────────────┐                 │
│                   │     ExhaustionGate           │                 │
│                   │  (reversion + δ>1.5 → BLOCK) │                │
│                   └─────────────┬───────────────┘                 │
│                                 │                                 │
│                   ┌─────────────▼───────────────┐                 │
│                   │     GuardianManager          │                 │
│                   │  (Regime + Location + Spread │                 │
│                   │   + Liquidity + Inertia)     │                 │
│                   └─────────────┬───────────────┘                 │
│                                 │                                 │
│                   ┌─────────────▼───────────────┐                 │
│                   │    _calculate_targets()      │                 │
│                   │  (TP/SL by setup_mode)       │                 │
│                   └─────────────┬───────────────┘                 │
│                                 │                                 │
└─────────────────────────────────┼─────────────────────────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │   AggregatedSignalEvent      │
                    │   → Croupier → OrderManager  │
                    └─────────────────────────────┘
```

---

## 4. Telemetry & Audit Trail

### Decision Traces

Todas las decisiones se registran en `historian.db` vía `_trace_decision()`:

| Gate | Valores posibles |
|---|---|
| `EXHAUSTION_GATE` | `Reversion with intensifying aggression (δ_ratio=X, v_ratio=Y)` |
| `REGIME_ALIGNMENT_V3` | `BALANCE / IMBALANCE / BLOCKED + value_position + setup_mode` |
| `SPREAD_SANITY` | `Spread analyzed` |
| `LIQUIDITY_HEATMAP` | `Liquidity support analyzed` / `Low liquidity support` |

### Signal Metadata

Cada señal despachada incluye:
```json
{
    "trigger": "AMT_failed_breakout",
    "setup_type": "failed_breakout",
    "scenario": "failed_breakout",
    "scenario_data": {
        "level": 73.45,
        "direction": "ABOVE",
        "cvd_change": -15.3,
        "elapsed_s": 23.4
    },
    "exhaustion": {"delta_ratio": 0.45, "volume_ratio": 0.55},
    "exhaustion_score": 2
}
```

### Edge Auditor Compatibility

El `setup_edge_auditor.py` funciona sin cambios. Los nuevos `setup_type` values (`failed_breakout`, `liquidity_exhaustion`, `trend_acceptance`) aparecen automáticamente en el breakdown por setup.

---

## 5. Configuration Reference

### Exhaustion Gate (en SetupEngine.on_tick)
```python
EXHAUSTION_BLOCK_THRESHOLD = 1.5  # Block reversion when delta_ratio > this
```

### FailedBreakoutDetector
```python
cooldown = 60.0               # Seconds between signals per symbol
max_break_age = 60.0           # Break must fail within this window
min_break_distance_pct = 0.0003  # 0.03% minimum break distance
cvd_divergence_threshold = 0.3  # CVD < 30% of confirming move = divergent
```

### LiquidityExhaustionDetector
```python
cooldown = 30.0
level_tolerance_pct = 0.0005   # 0.05% tolerance for "same level"
test_memory_seconds = 120.0    # Tests older than 2min are forgotten
min_tests = 3                  # Minimum tests to confirm pattern
declining_threshold = 0.7      # Each test must have < 70% of previous delta
min_bounce_pct = 0.0003        # 0.03% bounce from level required
```

### TrendAcceptanceDetector
```python
cooldown = 60.0
min_candles_outside = 3        # Candles outside VA before breakout confirmed
pullback_tolerance_pct = 0.001  # 0.1% tolerance for pullback to level
max_pullback_penetration_pct = 0.001  # Can't re-enter VA by more than 0.1%
cvd_confirmation_threshold = 5.0  # CVD slope must exceed this
```

---

## 6. Edge Audit Results (Phase B)

### Raw MFE/MAE by Scenario
| Scenario | n | MFE% | MAE% | Ratio |
|---|---|---|---|---|
| reversion | 73 | 0.130% | 0.129% | 1.01 |
| rotation | 79 | 0.141% | 0.115% | 1.22 |
| failed_breakout | 29 | 0.221% | 0.230% | 0.96 |
| liquidity_exhaustion | 10 | 0.225% | 0.151% | 1.50 |
| trend_acceptance | 25 | 0.193% | 0.201% | 0.96 |

### Dynamic TP/SL Performance
| Scenario | n | WR% | Exp% | Status |
|---|---|---|---|---|
| reversion | 73 | 64.3% | +0.092% | WATCH |
| rotation | 79 | 66.7% | +0.189% | WATCH |
| failed_breakout | 29 | 35.7% | +0.084% | Needs target calibration |
| liquidity_exhaustion | 10 | 66.7% | +0.324% | Best edge |
| trend_acceptance | 25 | 42.9% | -0.064% | Needs trending market |

### Overall
| Metric | Value |
|---|---|
| Total Signals | 195 |
| Decided (W+L) | 49 |
| Overall WR | 57.1% |
| Gross Expectancy | +0.126% |
| Net (Taker) | +0.006% ✅ |
| Net (Maker) | +0.046% ✅ |

---

## 7. Known Issues & Future Work

1. **TrendAcceptance needs trending data**: Current audit uses 1-day RANGE data. Scenario ④ is designed for trends — test with BULL/BEAR datasets.

2. **FailedBreakout target calibration**: WR is low (36%) but Exp is positive because wins are large. Investigate TP cap at 0.4% to increase WR.

3. **Footprint volume_ratio differs from offline**: The CVD-based volume proxy in FootprintRegistry differs from the trade-count-based metric used in Phase A offline analysis. This is why the initial strict gate (score=0 blocked) destroyed edge.

4. **Candle boundary synthesis**: TrendAcceptance uses tick-based 60s boundary detection instead of actual candle events. This is accurate for backtesting but may drift slightly in live due to timing.

5. **Cooldown sharing**: AMT scenarios share the global `last_fire_ts` with absorption signals. This prevents AMT + Absorption double-firing on the same symbol within 15s. Consider per-scenario cooldowns if needed.
