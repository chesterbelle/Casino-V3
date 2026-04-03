# Casino-V3 Strategy Specification: Sniper Footprint Scalper

## 1. Overview
The **Sniper Footprint Scalper** is a high-frequency, order-flow-driven strategy strictly implementing **Trader Dale's** volume profiling and footprint methodologies.

After Phase 900/950, the strategy transitions from a reactive "flow scanner" built on generalized statistics (Z-scores) into a heavily gated **"Sniper Mode"**, which perfectly fuses Higher Timeframe (HTF) Location Context with Microstructure triggers.

---

## 2. The Core Edge (Why it works)
The statistical edge relies on the premise that Institutional Traders defend legacy volume clusters (HTF POC/VAH/VAL) and execute stop-runs at the edges of ranges.
- **The "Where"**: We only look for trades at heavily traded historical price levels.
- **The "When"**: We only pull the trigger when we see retail traders making a mistake (Trapped Traders) or institutional traders blocking the path (Absorption/Exhaustion) specifically AT those levels.

---

## 3. Location / Context Gating (The "Francotirador" Rule)
The bot **WILL NOT** execute any reversal setups unless the following strict conditions are met:

1. **HTF Structural Proximity Check (`_check_level_proximity`)**: The exact price where the micro-event occurred MUST be within **`0.20%`** of an active HTF Level.
   - Valid Levels: `POC`, `VAH`, `VAL`, `IBH` (Initial Balance High), `IBL`.
   - Data Source: `15m`, `1h`, or `Session Profile`.
   - *If the price is floating in "open space", the signal is immediately rejected, ignoring the micro shape.*
2. **Regime Alignment Check**: Reversals are ONLY allowed if the macro regime is `NEUTRAL`. Trading "Fade Extreme" or "Trapped Traders" directly into an `UP` or `DOWN` trend is strictly blocked by the `ContextRegistry`.
3. **Micro-Flow Confirmation (`_check_micro_gate`)**: We block the signal if the real-time order flow extremely opposes the trade direction (Z-score > 2.0 against the position).

---

## 4. Tactical Playbooks (The Triggers)

### Playbook #1: Trapped Traders (Top Priority)
**Trader Dale Theory**: Retail breakouts fail. Traders enter at the extreme of a move, high volume gets matched by a passive limit wall, and price snaps back.
- **Detector**: `FootprintTrappedTraders` sensor.
- **Condition**:
  - Price wicks at an extreme.
  - Significant volume (>20% of total candle volume) lands precisely inside the wick.
  - Price immediately closes in the opposite direction.
- **Action**: Fade the trap (trade against the wick).

### Playbook #2: Fade the Extreme / Absorption Reversal
**Trader Dale Theory**: Price hits a structural level and aggressive market orders are completely swallowed by a passive limit order wall, resulting in no progress.
- **Detector**: `FootprintAbsorptionV3` OR `FootprintPOCRejection`.
- **Condition**:
  - An Absorption or Rejection event occurs.
  - **Required Confluence**: Within 5 seconds, it MUST be confirmed by a `TacticalImbalance` or `TacticalExhaustion` in the *intended direction of the reversal*.
  - **L2 Order Book Wall**: The skewness of the top 5 levels must favor the reversal (e.g., > 51% Bid weight for a LONG).
- **Action**: Enter the reversal once the imbalance prints.

### Playbook #3: Trend Continuation (Secondary)
- **Detector**: `FootprintStackedImbalance`.
- **Condition**: 3+ consecutive price levels of aggressive market imbalance in the direction of the macro trend (`UP` or `DOWN` regimes).
- **Action**: Paused/In Development. Currently delegates to a "Pullback Watch" state to wait for a retrace to the imbalance POC instead of buying the breakout blindly.

---

## 5. Exit Management & Safety Nets
The `ExitManager` acts exclusively as a catastrophic safety net, allowing the geometric edge of the setups to play out.
- **Emergency Z-Burst Exit**: The bot will forcefully exit any active position via MARKET order if the fast real-time Z-score of the Cumulative Volume Delta (CVD) sharply exceeds `4.5` *against* the position direction. This protects the account from sudden toxic news/liquidation cascades.
