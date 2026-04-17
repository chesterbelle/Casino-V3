# LTA V4 — Implementation Manifest

> **Architecture Reference**: Casino-V3 `v6.0.0-lta-structural-pivot`
>
> This document maps every theoretical concept of the LTA V4 strategy to its exact code location, config value, and architectural decision. It supersedes all previous implementation documents.

---

## 1. Signal Pipeline Architecture

```
Tick/Candle Events
        │
        ▼
┌──────────────────┐
│  SensorWorker(s)  │  Parallel processes (Actor Model)
│  ├─ Absorption    │
│  ├─ Exhaustion    │
│  ├─ Cascade       │  LiquidationCascadeDetector
│  └─ ...           │
└────────┬─────────┘
         │  SignalEvent (via IPC Queue)
         ▼
┌──────────────────┐
│   SetupEngineV4   │  decision/setup_engine.py
│   ├─ Signal Memory (5s sliding window)
│   ├─ Structural Sync (POC/VAH/VAL + VA Integrity from session)
│   ├─ Strategy Evaluator (_evaluate_lta_structural)
│   ├─ 6 Guardian Gates
│   └─ TP/SL Calculator (structural anchors)
└────────┬─────────┘
         │  AggregatedSignalEvent
         ▼
┌──────────────────┐
│  AdaptivePlayer   │  players/adaptive.py
│  └─ Dumb Executor (trusts SetupEngine TP/SL)
└────────┬─────────┘
         │  DecisionEvent
         ▼
┌──────────────────┐     ┌─────────────┐
│    Croupier       │────▶│ HFTExitMgr  │
│    └─ OCO Orders  │     │ └─ Flow     │
│                   │     │   Invalidation│
└──────────────────┘     └─────────────┘
```

---

## 2. Source of Truth: Session-Scoped Profiles (Phase 2000)

### The Problem (Pre-Fix)

The `ContextRegistry` maintained two independent data paths:

1. **`_session_structural[symbol]`** — POC/VAH/VAL from `SessionValueArea` sensor (fresh, per-window).
2. **`profiles[symbol]`** — A global `MarketProfile` that accumulates all ticks forever (stale).

Phase A2 fixed `get_structural()` to prefer (1) over (2). But `get_va_integrity()` still used the global profile (2). This caused:

- **0% PASS rate** on London, NY, Overlap, and Quiet windows.
- Only Asian passed because it was the first window and the global profile hadn't inflated yet.
- The integrity formula (`concentration × magnetism`) collapsed as total volume grew unbounded.

### The Fix (3 files)

**Step 1: Sensor emits session VA integrity.**

```python
# sensors/footprint/session.py (line ~460)
"va_integrity": window_state.market_profile.calculate_va_integrity()
```

The `SessionValueArea` sensor already had a per-window `MarketProfile` that resets on window transitions. We just needed it to calculate and emit `va_integrity` from that profile.

**Step 2: SetupEngine passes it through.**

```python
# decision/setup_engine.py (line ~328)
s_va_integrity = event.metadata.get("va_integrity", 0.0)
self.context_registry.update_structural_from_session(
    event.symbol, s_poc, s_vah, s_val, va_integrity=s_va_integrity
)
```

**Step 3: ContextRegistry prefers session integrity.**

```python
# core/context_registry.py
def get_va_integrity(self, symbol: str) -> float:
    session = self._session_structural.get(symbol)
    if session and session.get("va_integrity", 0) > 0:
        return session["va_integrity"]  # Fresh, per-window
    # Fallback: global profile (cold start only)
    profile = self.profiles.get(symbol)
    return profile.calculate_va_integrity() if profile else 0.0
```

### Impact

| Metric | Before | After |
|--------|--------|-------|
| VA_INTEGRITY PASS | 317 (9.2%) | **2,199 (79.5%)** |
| Signals through all 6 gates | 2 | **112** |
| Verdict | INSUFFICIENT | **CERTIFIED** |

---

## 3. Core Entry: `_evaluate_lta_structural()`

**File:** `decision/setup_engine.py` (line ~156)

### 3.1 Signal Source — Tactical Whitelist

```python
TACTICAL_WHITELIST = (
    "TacticalAbsorption",
    "TacticalRejection",
    "TacticalDivergence",
    "TacticalTrappedTraders",
    "TacticalExhaustion",
    "TacticalPoCShift",
    "TacticalImbalance",
    "TacticalStackedImbalance",
    "TacticalLiquidationCascade",
)
```

### 3.2 OHLC Backfill (Phase A1 Fix)

Tick-based sensors (e.g., `FootprintAbsorption`) only emit `price` in metadata, not candle OHLC. The Failed Auction gate requires `high`/`low` for wick rejection validation.

**Fix:** After finding the reversal signal, the engine scans backwards through the 5-second memory for the most recent candle-based signal that carries OHLC data, and merges missing values into the reversal signal dict.

```python
for ohlc_key in ("high", "low", "open", "close"):
    if not reversal_signal.get(ohlc_key):
        for _, _, mem_event in reversed(self.memory[symbol]):
            mem_md = mem_event.metadata or {}
            if mem_md.get(ohlc_key) and mem_md[ohlc_key] > 0:
                reversal_signal[ohlc_key] = mem_md[ohlc_key]
                break
```

### 3.3 Location Gate

```python
LTA_PROXIMITY_THRESHOLD = 0.0025  # 0.25% from VAH/VAL
```

**Config:** `config/strategies.py:7`

---

## 4. The 6 Guardian Gates

### 4.1 Guardian 1: Regime Alignment (`_check_regime_alignment`)

**Purpose:** Prevents counter-trend reversions (e.g., shorting VAH during BULL_OTF).

**Logic:**
- NEUTRAL → PASS
- Trend-aligned → PASS (LONG during UP, SHORT during DOWN)
- Counter-trend → REJECT

**Data Source:** `ContextRegistry.get_regime(symbol)` + `ContextRegistry.otf[symbol]`

---

### 4.2 Guardian 2: POC Migration (`_check_poc_migration`)

**Purpose:** Rejects if POC is migrating aggressively against the intended direction (market in "discovery" phase).

**Threshold:** `LTA_POC_MIGRATION_THRESHOLD = 0.0050` (0.5%)

**Data Source:** `ContextRegistry.get_poc_migration(symbol, lookback_ticks=300)`

The `MarketProfile.poc_history` (deque of 300 entries) tracks POC position over time. Migration is calculated as `(current_poc - start_poc) / start_poc`.

---

### 4.3 Guardian 3: VA Integrity (`_check_va_integrity`)

**Purpose:** Ensures the Value Area is concentrated (bell-curve shaped) so the POC magnet effect is strong.

**Formula:**
```python
concentration = poc_vol / total_volume
magnetism = 1.0 / (va_range_pct * 100)
integrity = concentration * magnetism
```

**Source of truth:** Session-scoped. The integrity is calculated from the `SessionValueArea` sensor's per-window `MarketProfile` — NOT the global cumulative profile. See Section 2.

**Dynamic Threshold (Phase B1):**

```python
LTA_VA_INTEGRITY_BY_WINDOW = {
    "asian": 0.06,
    "london": 0.10,
    "overlap": 0.12,
    "ny": 0.10,
    "quiet": 0.05,
}
LTA_VA_INTEGRITY_MIN = 0.08  # Global fallback
```

**Config:** `config/strategies.py:19-26`

The current liquidity window is tracked per symbol in `ContextRegistry.current_window[symbol]`, updated by the `SetupEngine.on_signal()` handler when it receives `SessionValueArea` events.

---

### 4.4 Guardian 4: Failed Auction (`_check_failed_auction`)

**Purpose:** Confirms the candle shows a wick rejection at the VA edge (price probed beyond the edge but closed inside).

**Config:** `LTA_FAILED_AUCTION_BODY_MIN = 0.05` (wick must be 5% of body)

**Dependency on A1 Fix:** This gate requires valid `high`/`low` data. Before Phase A1, tick-based sensor signals provided `high=0.0` which caused the probe check to fail mathematically.

---

### 4.5 Guardian 5: Delta Divergence (`_check_delta_divergence`)

**Purpose:** Ensures order flow isn't aggressively opposing the trade direction.

**Data Source:** `ContextRegistry.micro_state[symbol]["cvd"]`

---

### 4.6 Guardian 6: Spread Sanity (`_check_spread_sanity`)

**Purpose:** Rejects entries when the bid/ask spread is abnormally wide (illiquid micro-moment) to protect against slippage.

**Threshold:** Current spread > 2× the 5-minute rolling average.

**Data Source:** `ContextRegistry.spread_state[symbol]` — updated every throttle cycle via `MicrostructureEvent.spread`.

---

## 5. Cascade Liquidation Detector

**File:** `sensors/footprint/liquidation_cascade.py`

### State Machine

```
IDLE → INITIATION → TRACKING → EXHAUSTION → SIGNAL
 ↑                    ↓ (timeout)
 └────────────────────┘
```

### Detection Criteria

| Phase | Condition | Value |
|-------|-----------|-------|
| Initiation | Volume > N× avg | 5× |
| Initiation | Delta Z-score > threshold | ±4.0 |
| Exhaustion | Volume decay | < 50% of peak |
| Exhaustion | Delta reversal | Sign flip |
| Exhaustion | Price displacement | > 2× ATR |
| Timeout | Max cascade bars | 5 |

### Signal Output

```python
{
    "side": "TACTICAL",
    "metadata": {
        "tactical_type": "TacticalLiquidationCascade",
        "direction": "LONG" | "SHORT",  # Opposite of cascade
        "cascade_direction": "UP" | "DOWN",
        "cascade_bars": int,
        "displacement_atr": float,
        # Includes full OHLC for Failed Auction gate
    }
}
```

**Config Registration:**
- `config/sensors.py`: `ACTIVE_SENSORS["LiquidationCascade"] = True`
- `config/strategies.py`: `ACTIVE_STRATEGIES = ["LTA_STRUCTURAL", "LTA_CASCADE"]`
- `core/sensor_manager.py`: `LiquidationCascadeDetector` in class loader

---

## 6. Exit Architecture

### 6.1 Primary Exit: OCO Orders (TP/SL)

Placed at order time with absolute prices from SetupEngine.

### 6.2 Flow Invalidation (Phase B2)

**File:** `croupier/components/hft_exit_manager.py`

Always active. Monitors Z-score while position is open:
- LONG + Z < -3.0 → `FLOW_INVALIDATION` exit
- SHORT + Z > +3.0 → `FLOW_INVALIDATION` exit

This is stricter than the existing `THESIS_TOXIC_FLOW` (Z=5.5) — it fires earlier as the "institutional panic button."

**Execution order in HFTExitManager.on_tick:**
1. Catastrophic Stop (>50% loss)
2. Patience Lock (3s grace period)
3. Flow Invalidation (Z ±3.0) ← always active
4. Axia Thesis Invalidation (behind flag)
5. Tactical Airbag (behind flag)

### 6.3 Decision Trace Audit

All guardian decisions (PASS/REJECT) are offloaded to `historian.db` via `_trace_decision()` for post-mortem analysis.

---

## 7. Shutdown Architecture (Phase 2000)

### The Problem

The backtest runner hung indefinitely on exit due to:
1. `_listen_for_signals` async task was orphaned (no stored reference, never cancelled).
2. `multiprocessing.Queue` feeder threads deadlocked when workers were terminated with unread data in the pipe.

### The Fix (2 files)

**`core/sensor_manager.py` — `stop()` method:**
1. Set `_stopped = True` flag (checked by both async loops).
2. Cancel `_batch_flush_task` and `_signal_listener_task`.
3. Send "STOP" to all worker input queues.
4. Drain the output queue to prevent feeder thread deadlock.
5. Join/terminate workers.
6. Close all queues and join feeder threads.

**`backtest.py` — Nuclear fallback:**
```python
finally:
    os._exit(0)  # Kill zombie multiprocessing feeder threads
```

---

## 8. Bet Sizing

**File:** `players/adaptive.py`

The `AdaptivePlayer` is a "Dumb Executor" — it trusts the SetupEngine's TP/SL blindly and only handles sizing:

1. **Base Size:** Kelly Criterion or fixed 1% of equity.
2. **Regime Multiplier:** 1.25× in trends, 0.75× in ranges.
3. **Delta-Velocity Multiplier:** From DeltaVelocity sensor.
4. **RR Scaling:** `max(0.5, min(2.0, rr_ratio / 1.5))`
5. **Validation:** RR < 1.0 → rejected. Distance > 10% → rejected.

---

## 9. File Reference Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Strategy Config | `config/strategies.py` | All thresholds, window map |
| Sensor Config | `config/sensors.py` | ACTIVE_SENSORS registry |
| Setup Engine | `decision/setup_engine.py` | `_evaluate_lta_structural`, 6 guardians, structural sync |
| Context Registry | `core/context_registry.py` | Session structural levels, VA integrity, micro-state, spread |
| Market Profile | `core/market_profile.py` | POC/VA calculation, `calculate_va_integrity()` |
| Session Sensor | `sensors/footprint/session.py` | Window detection, IB, failed auctions, VA integrity emission |
| Cascade Sensor | `sensors/footprint/liquidation_cascade.py` | State machine detector |
| Absorption Sensor | `sensors/footprint/absorption.py` | Absorption + zone detection |
| Exhaustion Sensor | `sensors/footprint/exhaustion.py` | Volume exhaustion |
| Player | `players/adaptive.py` | Bet sizing, RR validation |
| Exit Manager | `croupier/components/hft_exit_manager.py` | Flow invalidation, thesis checks |
| Sensor Manager | `core/sensor_manager.py` | Worker processes, shutdown, OHLC injection |
| Sensor Worker | `core/sensor_worker.py` | IPC, signal dispatch |
