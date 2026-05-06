# Statistical Absorption Scalping V3: Total Spectrum Dominance

## 1. Executive Summary
The **Absorption Scalping V3** represents a fundamental evolution from legacy mean-reversion models to a **Unified Order Flow Engine**. By synthesizing high-fidelity statistical location (VWAP Z-Bands) with multi-layer anticipatory regime detection, the V3 architecture captures liquidity bottlenecks across the entire market spectrum—dominating both **Extreme Reversion** in range and **Strategic Continuation** in trends.

---

## 2. Theoretical Foundation: The Dual-Core Edge
V3 operates on the principle that **Absorption is the ultimate lead indicator of price exhaustion and surge**. Unlike V2 which was limited to the edges (Z > 2.0), V3 categorizes opportunities into two distinct high-probability domains:

### A. Core 1: The "Rubber Band" (Extreme Reversion)
- **Domain:** Statistical extremes (|Z| > 2.0).
- **Thesis:** Price has overextended beyond 95% of its 120-minute distribution. The VWAP "Gravity" is at its maximum.
- **Trigger:** Heavy absorption against the overextension.
- **Edge:** High-win rate mean reversion to the VWAP.

### B. Core 2: The "Slipstream" (Trend-Aligned Absorption)
- **Domain:** The Mid-Spectrum (0.5 < |Z| < 1.5).
- **Thesis:** In a trending market, price consolidates near the mean. Absorption here indicates a "re-fueling" event where counter-trend orders are swallowed, paving the way for a momentum surge.
- **Trigger:** Absorption aligned with **MarketRegime V2** (Confidence > 0.3).
- **Edge:** High-expectancy trend continuation with minimal drawdown.

---

## 3. The Sensory Stack (Intelligence Layer)

### 3.1 MarketRegime V2 (The Anticipatory Traffic Light)
The system uses a 3-layer weighted confluence engine to determine the market state *before* traditional indicators lag:
- **Macro (POC Velocity):** Detects the "Value Migration". If the POC is moving > 0.01% per candle, a trend is active.
- **Meso (VA Expansion):** Measures the volatility width. An expansion rate > 5% indicates the market is leaving balance.
- **Micro (CVD Surge):** Analyzes the raw tick-level delta. Z-score > 1.2 indicates aggressive institutional participation.

### 3.2 Tactical Absorption V2.1 (The bottleneck Detector)
- **Z-Score Normalization:** Every tick is mapped to its statistical position relative to the 120m rolling VWAP.
- **Concentration Index:** Measures the "Density" of absorption. Higher concentration at a price level indicates a harder "floor" or "ceiling".
- **Dynamic Noise Filtering:** Filters out low-volume churn, ensuring the bot only reacts to meaningful liquidity barriers.

---

## 4. Execution Logic: The Context-Aware Sniper
V3 replaces hard thresholds with a **Context-Aware Decision Matrix**:

| Regime State | Logic Mode | Z-Threshold | Confirmation |
| :--- | :--- | :--- | :--- |
| **BALANCE (Range)** | Reversion | **2.0Z** | Mean-Reversal Focus |
| **TREND_UP** | LONG Sniper | **1.2Z** | Trend Alignment |
| **TREND_DOWN** | SHORT Sniper | **1.2Z** | Trend Alignment |
| **TRANSITION** | Defensive | **Blocked** | Avoid "Knife Catching" |

---

## 5. Risk & Trade Management: Asymmetric Gravity
V3 treats the VWAP as a magnetic force. Exit profiles are calculated dynamically based on the "Distance to Mean":
- **Reversion Exits:** Target is the 120m VWAP. Stop Loss is set at the recent structural high/low + ATR buffer.
- **Continuation Exits:** Target is an extension of the current value migration (ATR-based).
- **Shadow Protection:** A hidden trailing stop activates as soon as the trade reaches 0.15% PnL, securing the "Math Magnet" edge.

---

## 6. The "Math Magnet" Philosophy
V3 does not guess direction. It calculates **Liquidity Friction**. By trading the "Total Spectrum", the bot achieves:
1. **Zero-Alpha Starvation:** Constant participation in both calm and volatile markets.
2. **Structural Integrity:** Every entry is backed by a statistical anomaly (Z-score) and an Order Flow fact (Absorption).
3. **Adaptive Agility:** The system automatically tightens its filters when the market is indecisive and loosens them when a trend is confirmed.

---
**Status:** Architecture Validated | **Dataset:** LTC_Golden_24h | **Next Phase:** Total Profitability Audit.
