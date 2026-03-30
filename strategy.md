# Footprint Scalping Strategy - Casino-V3

**Version**: 1.0
**Last Updated**: 2026-03-03
**Status**: Development

---

## 1. Conceptual Foundation

### Primary Sources

| Book | Author | Focus | Concepts Used |
|------|--------|-------|---------------|
| Trading Order Flow: Looking Behind the Screen | Trader Dale | Micro-structure | Imbalance, Absorption, Delta, Footprint |
| Order Flow: Trading Setups | Trader Dale | Practical setups | Stacked Imbalance, Trapped Traders, Exhaustion |
| Markets in Profile | James Dalton | Auction theory | Value Area, POC, Market Profile |
| Mind Over Markets | James Dalton | Market structure | Day Type, Opening Range, Excess |

### Core Philosophy

**Footprint scalping** based on order flow micro-structure. The strategy exploits temporary imbalances between aggressive buyers and sellers at specific price levels, using auction theory to identify high-probability entry points.

**Edge hypothesis**: Order flow patterns (imbalance, absorption, delta divergence) are universal across all markets with public order books. Crypto exchanges expose this data via WebSocket, enabling real-time detection.

---

## 2. Concept Adaptations for Crypto 24/7

### Critical Adaptation: Sessions vs Liquidity Windows

Traditional markets have defined sessions (9:30 AM - 4:00 PM). Crypto operates 24/7. Dalton's concepts require adaptation:

| Original Concept | Source | Crypto Adaptation | Reason |
|------------------|--------|-------------------|--------|
| **Day Type** | Dalton | **Window Type** | No defined session in 24/7 markets |
| **Session** | Dalton | **Liquidity Window** | Asian/London/NY windows with fixed UTC |
| **Opening Range** | Dalton | **Window IB** | First N minutes of each liquidity window |
| **TPO Counting** | Dalton | Not implemented | Less relevant without session open/close |
| **Value Area** | Dalton | **Sliding Window VA** | Recalculated continuously via LiveFootprintMatrix |
| **Session POC** | Dalton | **Rolling POC** | 30-second sliding window in sensors |

### Liquidity Windows Definition

Fixed UTC boundaries aligned with traditional market activity:

| Window | UTC Hours | Characteristics | Volatility |
|--------|-----------|-----------------|------------|
| **Asian** | 00:00 - 08:00 | Lower volume, range-bound | Low |
| **London** | 08:00 - 16:00 | Higher volume, trend potential | Medium-High |
| **NY** | 13:00 - 21:00 | Highest volume during overlap | High |
| **London-NY Overlap** | 13:00 - 16:00 | Peak liquidity, best scalping | Very High |
| **Quiet** | 21:00 - 00:00 | Low liquidity, avoid trading | Very Low |

### Window Type Classification

Adapted from Dalton's Day Type:

| Window Type | Criteria | Trading Implication |
|-------------|----------|---------------------|
| **TREND_WINDOW** | Extension > 100% of IB range | Follow direction, no fading |
| **NORMAL_WINDOW** | Extension 20-100% of IB range | Mixed approach, most sensors work |
| **RANGE_WINDOW** | Extension < 20% of IB range | Fade extremes, reversal sensors |

**Note**: IB (Initial Balance) is calculated per window, not per day.

---

## 3. Sensor Inventory

### Order Flow Sensors (Dale)

| Sensor | File | Concept | Signal Type | Window Compatibility |
|--------|------|---------|-------------|---------------------|
| `FootprintImbalanceV3` | `sensors/footprint/imbalance.py` | Aggressive volume imbalance | Continuation | All |
| `FootprintAbsorptionV3` | `sensors/footprint/absorption.py` | High volume + price stall + DOM wall | Reversal | Range/Normal |
| `FootprintStackedImbalance` | `sensors/footprint/advanced.py` | 3+ consecutive imbalanced levels | Continuation | Trend/Normal |
| `FootprintTrappedTraders` | `sensors/footprint/advanced.py` | High volume in wick + reversal | Reversal | Range/Normal |
| `FootprintVolumeExhaustion` | `sensors/footprint/exhaustion.py` | Low volume at extreme | Reversal | Range |
| `CumulativeDeltaSensorV3` | `sensors/footprint/cumulative_delta.py` | Price vs Delta divergence | Reversal | All |
| `FootprintDeltaPoCShift` | `sensors/footprint/flow_shift.py` | POC migration + delta impulse | Continuation | Trend/Normal |
| `FootprintDeltaDivergence` | `sensors/footprint/advanced.py` | Inter-candle delta divergence | Reversal | All |

### Structural Sensors (Dalton)

| Sensor | File | Concept | Signal Type | Notes |
|--------|------|---------|-------------|-------|
| `SessionValueArea` | `sensors/footprint/session.py` | VA, IB, Window Type, Excess, Single Prints | Context (NEUTRAL) | Provides structural levels for filtering |
| `OneTimeframingSensor` | `sensors/regime/one_timeframing.py` | Regime filter | Context | Trend vs Range detection |
| `FootprintPOCRejection` | `sensors/footprint/advanced.py` | POC rejection | Reversal | Price rejects from POC |

### Sensor Metadata Contract

Each sensor must provide:

```python
{
    "side": "LONG" | "SHORT" | "TACTICAL",
    "metadata": {
        "tactical_type": "TacticalAbsorption" | "TacticalImbalance" | ...,
        "direction": "LONG" | "SHORT",
        "price": float,
        # ... pattern-specific fields
    }
}
```

---

 ## 4. Signal Aggregation: Sniper Playbooks (V4)

 **Location**: `decision/setup_engine.py`

 Replaces the old "Weighted Consensus". Instead of averaging scores, it uses a **5-second tactical memory** to match strict institutional playbooks.

 ### Playbook #1: Fade Extreme (Reversion)
 - **Conditions**: (TacticalAbsorption OR TacticalRejection) + TacticalImbalance in reverse direction.
 - **Context**: Only allowed in NEUTRAL/RANGE regimes.
 - **Structural Target**: VAH, VAL or POC.
 - **L2 Wall**: Requires Skewness confirmation (Bid wall for LONG, Ask wall for SHORT).

 ### Playbook #2: Trend Continuation
 - **Conditions**: TacticalStackedImbalance + Confirming TacticalImbalance/Divergence.
 - **Context**: Allowed in TREND regimes (UP/DOWN); requires CVD alignment.

 ### Playbook #3: Shark Follower (Incomplete Business)
 - **Conditions**: Price approaching `FAILED_HIGH` or `FAILED_LOW` + Flow alignment.
 - **Logic**: Market "owes" a visit to these levels to finish auction.

 ---

 ## 5. Execution & Safety Layers (Production Reality)

 ### Slippage Guard (R12 Calibration)
 - **Threshold**: 0.08% (8 bps).
 - **Logic**: Rejects signals if estimated market impact exceeds threshold.
 - **Reason**: Prevents math inversion (Slippage eating > 50% of RR).

 ### Shadow SL & Adaptive Breathing (Shark Breath)
 - **Implementation**: `AdaptivePlayer` + `ExitManager`.
 - **Dynamic Activation**:
     - **Reversion Setups**: 0.45% (Adaptive Breather). Allows structural setups to reach targets.
     - **Continuation Setups**: 0.25% (Tight Shadow). Momentum must not reverse.
 - **Observation**: This alignment prevents "Strategy Muteness" and ensures trades survive micro-noise.

 ### Cold Start Warmup
 - **Requirement**: 20 minutes (Reduced from 60m).
 - **Purpose**: Allows POC/VAH/VAL to calibrate without missing the session's first volatility wave.

 ### Data Flow


```
Binance WebSocket
    │
    ▼
BinanceWorker (multiprocessing.Process)
    │ Normalized packets: (type_code, ts, data)
    ▼
IngestionBridge (main process)
    │ Dispatch TickEvent / DepthEvent
    ▼
LiveFootprintMatrix (per sensor)
    │ Sliding window profile: {price: {bid_vol, ask_vol}}
    ▼
Sensors (on_tick / calculate)
    │ SignalEvent
    ▼
SignalAggregatorV3
    │ AggregatedSignalEvent
    ▼
OrderManager → Croupier → ExchangeAdapter → ResilientConnector
    │
    ▼
Exchange REST API
```

### Latency Targets

| Phase | Target | Current | Notes |
|-------|--------|---------|-------|
| t0→t1 (Signal→Decision) | < 20ms | 5-20ms | Fast-Track: 0ms |
| t1→t2 (Decision→Submit) | < 50ms | 5-50ms | Internal processing |
| t2→t3 (Submit→Ack) | < 300ms | 200-300ms | External REST latency |
| **Total** | < 400ms | 235-410ms | Competitive for scalping |

### Execution Components

| Component | File | Role |
|-----------|------|------|
| `OrderManager` | `core/execution.py` | Decision handling, sizing, OCO orchestration |
| `Croupier` | `croupier/` | Order execution coordinator |
| `ExchangeAdapter` | `exchanges/adapters/exchange_adapter.py` | Exchange-agnostic business logic |
| `ResilientConnector` | `exchanges/connectors/resilient_connector.py` | Retry, tracking, reconnection |
| `BinanceNativeConnector` | `exchanges/connectors/binance/binance_native_connector.py` | Pure asyncio implementation |

---

## 6. Risk Management

### Position Sizing

- Based on sensor historical win rate (tracked by `SensorTracker`)
- Kelly criterion applied to per-sensor expectancy
- Maximum position size: [TBD]

### Stop Loss / Take Profit

- Dynamic based on Value Area levels
- SL: Below VAL for LONG, above VAH for SHORT
- TP: Next structural level (POC, opposite VA boundary)

### Max Concurrent Positions

[TBD after backtesting]

---

## 7. Known Gaps / Future Work

| Gap | Status | Priority | Description |
|-----|--------|----------|-------------|
| **Failed Auction Detection** | ✅ **Implemented** | ~~High~~ | Break + immediate rejection (strong reversal) |
| **Initiating vs Responding Volume** | Not implemented | Medium | New volume vs reactive volume |

| **Liquidation Awareness** | Not implemented | High | Crypto-specific: stop cascades |
| **Tick Size per Symbol** | Hardcoded (0.1) | Medium | Should be dynamic from exchange info |
| **Delta per Price Level** | Not implemented | Medium | Iceberg detection |
| ~~Window Type Filter~~ | ✅ **Implemented** | ~~High~~ | ~~Filter sensors by window type~~ |
| ~~Liquidity Windows Integration~~ | ✅ **Implemented** | ~~High~~ | ~~Replace session concept~~ |
| ~~Profile Reset Logic~~ | ✅ **Implemented** | ~~Medium~~ | ~~SessionValueArea resets per window~~ |

---

## 8. Historical Decisions

### [2026-03-03] Liquidity Windows vs Day Type

**Problem**: Dalton's Day Type assumes defined sessions (9:30 AM open, 4:00 PM close). Crypto operates 24/7.

**Decision**: Implement Liquidity Windows with fixed UTC boundaries instead of Day Type.

**Rationale**:
- Crypto still has liquidity cycles aligned with traditional market hours
- Asian/London/NY windows have distinct volatility profiles
- Each window gets its own IB and Window Type classification

**Implementation**:
- `sensors/footprint/session.py`: `SessionValueArea` now tracks 5 liquidity windows
- `WindowState` class: Independent profile, IB, and window type per window
- Profile resets on window transition
- IB duration varies by window (15-60 min)

**Validation needed**: Does Window Type classification improve win rate vs no filter?

---

### [2026-03-03] Window Type Sensor Filter

**Problem**: Sensors have different optimal conditions. Trend-following sensors fail in range markets. Reversal sensors fail in trends.

**Decision**: Filter sensors by Window Type compatibility in aggregator.

**Rationale**:
- `FootprintVolumeExhaustion` only works in RANGE_WINDOW (volume dries at extremes)
- `FootprintDeltaPoCShift` only works in TREND_WINDOW (POC migration)
- Filtering reduces false signals

**Implementation**:
- `decision/aggregator.py`: `SENSOR_WINDOW_TYPE_COMPAT` mapping
- Signals rejected if sensor incompatible with current `window_type`
- Logged as `🚫 [WindowType] Rejecting...`

**Validation needed**: Compare win rates with/without filter.

---

### [2026-03-03] Sliding Window vs Session Profile

**Problem**: Dalton's Market Profile accumulates for an entire session. Crypto has no session boundaries.

**Decision**: Use `LiveFootprintMatrix` with 30-second sliding window for real-time footprint.

**Rationale**:
- Scalping requires immediate reaction to order flow changes
- 30-second window captures current micro-structure
- SessionValueArea provides longer-term structural context

**Trade-off**: Less "auction memory" than Dalton intended, but more responsive to rapid changes.

---

### [2026-03-03] Fast-Track for OrderFlow Sensors

**Problem**: 20ms timeout adds latency to high-conviction signals.

**Decision**: Bypass timeout for sensors with `fast_track=True` metadata.

**Rationale**:
- OrderFlow sensors (imbalance, absorption) have immediate edge
- Waiting 20ms for low-quality sensors dilutes the signal
- Context sensors also fast-tracked for zero-latency injection

**Validation**: Fast-tracked signals should have higher win rate than normal signals.

---

## 9. Performance Tracking

### Metrics per Sensor

| Sensor | Win Rate | Avg R | Sharpe | Trades | Notes |
|--------|----------|-------|--------|--------|-------|
| FootprintImbalanceV3 | TBD | TBD | TBD | TBD | |
| FootprintAbsorptionV3 | TBD | TBD | TBD | TBD | |
| CumulativeDeltaSensorV3 | TBD | TBD | TBD | TBD | |
| FootprintStackedImbalance | TBD | TBD | TBD | TBD | |
| FootprintTrappedTraders | TBD | TBD | TBD | TBD | |
| FootprintVolumeExhaustion | TBD | TBD | TBD | TBD | |
| FootprintDeltaPoCShift | TBD | TBD | TBD | TBD | |

### Metrics per Window Type

| Window Type | Trade Count | Win Rate | Avg R | Notes |
|-------------|-------------|----------|-------|-------|
| TREND_WINDOW | TBD | TBD | TBD | |
| RANGE_WINDOW | TBD | TBD | TBD | |
| NORMAL_WINDOW | TBD | TBD | TBD | |

### Metrics per Liquidity Window

| Window | Trade Count | Win Rate | Avg R | Notes |
|--------|-------------|----------|-------|-------|
| Asian | TBD | TBD | TBD | Lower volatility expected |
| London | TBD | TBD | TBD | |
| NY | TBD | TBD | TBD | |
| Overlap | TBD | TBD | TBD | Best conditions expected |
| Quiet | TBD | TBD | TBD | Should have minimal trades |

---

## 10. Backtesting Requirements

### Data Needed

- [ ] 6 months of tick-by-tick trades (aggTrade) for BTCUSDT
- [ ] 6 months of depth snapshots (depth5@100ms)
- [ ] Funding rate history
- [ ] Mark price history

### Validation Questions

1. **Sensor Win Rate**: Which sensors have > 55% win rate?
2. **Window Type Accuracy**: Does Window Type classification predict outcome?
3. **Level Proximity**: Does trading near levels improve win rate?
4. **MTF Alignment**: Does 30m alignment filter improve results?
5. **Fast-Track Quality**: Do fast-tracked signals outperform normal signals?
6. **Liquidity Window Performance**: Which windows are most profitable?

---

## 11. Competitive Analysis

### What Exists

| Tool | Footprint | Crypto | Automation | Limitation |
|------|-----------|--------|------------|------------|
| Bookmap | Excellent | Yes | No (visual only) | Manual trading |
| Quantower | Good | Yes | Limited | Not customizable |
| Hummingbot | No | Yes | Yes | Market making, no scalping |
| ATAS | Excellent | No | No | Traditional markets only |
| Commercial bots | No | Yes | Yes | No order flow |

### Our Differentiation

1. **Automated footprint scalping** for crypto perps
2. **Open-source, customizable** strategy logic
3. **Dalton + Dale hybrid** adapted for 24/7 markets
4. **Crypto-specific patterns** (liquidations, funding)
5. **Low internal latency** (5-100ms signal to submit)

---

## 12. Next Steps

1. [ ] Implement Liquidity Windows in `SessionValueArea`
2. [ ] Add Window Type filter in aggregator
3. [ ] Implement Failed Auction detection
4. [ ] Add Liquidation Awareness sensor
5. [ ] Backtest individual sensors
6. [ ] Optimize parameters (imbalance ratio, cooldown, window size)
7. [ ] Forward test on demo
8. [ ] Deploy to live with small size

---

*This document is a living reference. Update as strategy evolves.*
