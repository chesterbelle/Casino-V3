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
│  ├─ Cascade       │  ← NEW: LiquidationCascadeDetector
│  └─ ...           │
└────────┬─────────┘
         │  SignalEvent (via IPC Queue)
         ▼
┌──────────────────┐
│   SetupEngineV4   │  decision/setup_engine.py
│   ├─ Signal Memory (5s sliding window)
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

## 2. Core Entry: `_evaluate_lta_structural()`

**File:** `decision/setup_engine.py` (line ~156)

### 2.1 Signal Source — Tactical Whitelist

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
    "TacticalLiquidationCascade",  # Phase C1
)
```

### 2.2 OHLC Backfill (Phase A1 Fix)

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

### 2.3 Location Gate

```python
LTA_PROXIMITY_THRESHOLD = 0.0025  # 0.25% from VAH/VAL
```

**Config:** `config/strategies.py:7`

---

## 3. The 6 Guardian Gates

### 3.1 Guardian 1: Regime Alignment (`_check_regime_alignment`)

**Purpose:** Prevents counter-trend reversions (e.g., shorting VAH during BULL_OTF).

**Logic:**
- NEUTRAL → PASS
- Trend-aligned → PASS (LONG during UP, SHORT during DOWN)
- Counter-trend → REJECT

**Data Source:** `ContextRegistry.get_regime(symbol)` + `ContextRegistry.otf[symbol]`

---

### 3.2 Guardian 2: POC Migration (`_check_poc_migration`)

**Purpose:** Rejects if POC is migrating aggressively against the intended direction (market in "discovery" phase).

**Threshold:** `LTA_POC_MIGRATION_THRESHOLD = 0.0050` (0.5%)

**Data Source:** `ContextRegistry.get_poc_migration(symbol, lookback_ticks=300)`

The `MarketProfile.poc_history` (deque of 300 entries) tracks POC position over time. Migration is calculated as `(current_poc - start_poc) / start_poc`.

---

### 3.3 Guardian 3: VA Integrity (`_check_va_integrity`)

**Purpose:** Ensures the Value Area is concentrated (bell-curve shaped) so the POC magnet effect is strong.

**Formula:**
```python
concentration = poc_vol / total_volume
magnetism = 1.0 / (va_range_pct * 100)
integrity = concentration * magnetism
```

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

### 3.4 Guardian 4: Failed Auction (`_check_failed_auction`)

**Purpose:** Confirms the candle shows a wick rejection at the VA edge (price probed beyond the edge but closed inside).

**Config:** `LTA_FAILED_AUCTION_BODY_MIN = 0.05` (wick must be 5% of body)

**Dependency on A1 Fix:** This gate requires valid `high`/`low` data. Before Phase A1, tick-based sensor signals provided `high=0.0` which caused the probe check to fail mathematically.

---

### 3.5 Guardian 5: Delta Divergence (`_check_delta_divergence`)

**Purpose:** Ensures order flow isn't aggressively opposing the trade direction.

**Data Source:** `ContextRegistry.micro_state[symbol]["cvd"]`

---

### 3.6 Guardian 6: Spread Sanity (`_check_spread_sanity`)

**Purpose:** Rejects entries when the bid/ask spread is abnormally wide (illiquid micro-moment) to protect against slippage.

**Threshold:** Current spread > 2× the 5-minute rolling average.

**Data Source:** `ContextRegistry.spread_state[symbol]` — updated every throttle cycle via `MicrostructureEvent.spread`.

---

## 4. Structural Source of Truth (Phase A2)

### The Problem (Pre-Fix)

The `ContextRegistry` accumulated all ticks into a single never-resetting `MarketProfile`. Over a 24-hour period, the POC/VAH/VAL became cumulative averages of the entire day, not clean per-window structures.

Meanwhile, the `SessionValueArea` sensor correctly reset its profile on each liquidity window transition (Asian → London → NY, etc.), producing fresh per-window levels.

**The guardians were checking stale cumulative levels while the sensor was producing fresh window levels.**

### The Fix

`ContextRegistry.get_structural()` now prioritizes session-aware levels stored in `_session_structural[symbol]`. These are updated by the `SetupEngine.on_signal()` handler when it receives `SessionValueArea` events:

```python
# In SetupEngine.on_signal():
if event.sensor_id == "SessionValueArea":
    self.context_registry.update_structural_from_session(
        event.symbol, poc, vah, val
    )
    self.context_registry.current_window[event.symbol] = window_name
```

When no session data is available (cold start), it falls back to the tick-accumulated profile.

---

## 5. Cascade Liquidation Detector (Phase C1)

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
3. Flow Invalidation (Z ±3.0) ← **NEW, always active**
4. Axia Thesis Invalidation (behind flag)
5. Tactical Airbag (behind flag)

### 6.3 Decision Trace Audit

All guardian decisions (PASS/REJECT) are offloaded to `historian.db` via `_trace_decision()` for post-mortem analysis.

---

## 7. Bet Sizing

**File:** `players/adaptive.py`

The `AdaptivePlayer` is a "Dumb Executor" — it trusts the SetupEngine's TP/SL blindly and only handles sizing:

1. **Base Size:** Kelly Criterion or fixed 1% of equity.
2. **Regime Multiplier:** 1.25× in trends, 0.75× in ranges.
3. **Delta-Velocity Multiplier:** From DeltaVelocity sensor.
4. **RR Scaling:** `max(0.5, min(2.0, rr_ratio / 1.5))`
5. **Validation:** RR < 1.0 → rejected. Distance > 10% → rejected.

---

## 8. File Reference Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Strategy Config | `config/strategies.py` | All thresholds, window map |
| Sensor Config | `config/sensors.py` | ACTIVE_SENSORS registry |
| Setup Engine | `decision/setup_engine.py` | `_evaluate_lta_structural`, 6 guardians |
| Context Registry | `core/context_registry.py` | Structural levels, micro-state, spread |
| Market Profile | `core/market_profile.py` | POC/VA calculation |
| Session Sensor | `sensors/footprint/session.py` | Window detection, IB, failed auctions |
| Cascade Sensor | `sensors/footprint/liquidation_cascade.py` | State machine detector |
| Absorption Sensor | `sensors/footprint/absorption.py` | Absorption + zone detection |
| Exhaustion Sensor | `sensors/footprint/exhaustion.py` | Volume exhaustion |
| Player | `players/adaptive.py` | Bet sizing, RR validation |
| Exit Manager | `croupier/components/hft_exit_manager.py` | Flow invalidation, thesis checks |
| Sensor Manager | `core/sensor_manager.py` | Worker processes, OHLC injection |
| Sensor Worker | `core/sensor_worker.py` | IPC, signal dispatch |
