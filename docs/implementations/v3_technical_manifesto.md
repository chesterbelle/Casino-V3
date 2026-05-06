# V3 Implementation Manifesto: Order Flow Engineering Details

## 1. Architectural Overview
The Casino-V3 architecture has been evolved into a **Dual-Core Execution Engine**. The implementation focuses on three primary objectives: **Classification Accuracy**, **Structural Quality Enforcement**, and **Momentum Confluence**.

## 2. Dynamic Classification (SetupMode Enum)
The core of V3 is the intelligent classification of opportunities via the `GuardianManager`.
- **Implementation**: We introduced `SetupMode` (REVERSION vs. CONTINUATION).
- **Logic**: The `RegimeGuardian` and `StatisticalLocationGuardian` now propagate a classification based on macro-trend confidence and price distance from VWAP.
- **Result**: The system no longer treats every signal as a reversion play, allowing it to "ride" trends.

## 3. The Squeeze Guard (Structural Quality)
To combat high Maximum Adverse Excursion (MAE), we implemented a geometric filter in the `SetupEngineV4`.
- **Logic**: It evaluates the last 5 ticks of price action. If the price is "stabbing" (making erratic higher highs in a short setup) or if the volatility exceeds 2x ATR (Chaos Zone), the signal is aborted.
- **Code Ref**: `SetupEngineV4._evaluate_lta_structural()`

## 4. The Inertia Guard (V3.2 Momentum Validation)
This is the most critical update for Taker-viability.
- **Storage**: `self.micro_memory` stores a 5-second sliding window of `MicrostructureEvent` data (CVD, Skewness, Z-Score).
- **Calculation**: `_check_micro_inertia_guard()` computes the delta between the current CVD and the baseline CVD from 2000ms ago.
- **Enforcement**: For `CONTINUATION` trades, a same-direction delta is strictly required.
- **Impact**: This filter eliminates "passive-only" absorptions that lack aggressive follow-through.

## 5. Dynamic Exit Architecture (Phase 1200)
The `ExitEngine` uses a 5-layer stack to manage positions:
- **Layer 2 (Shadow Protection)**: Implements the "Winner Catcher" (Trailing Stop).
- **Trigger**: Once a profit threshold is reached, the TP is moved to a distant target (6:1 RR) and the Shadow SL trails the price using an ATR-based inertia multiplier.
- **Layer 4 (Thesis Invalidation)**: Monitors real-time toxic flow (Z > 5.5) to exit before a hard SL is hit.

## 6. Implementation Summary
The V3.2 codebase represents a shift from static pattern matching to dynamic liquidity observation. By decoupling the entry trigger from the execution dispatch (via Guards), we have achieved a system that is robust against slippage and profitable across multiple asset classes (LTC, SOL, BTC).
