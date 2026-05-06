# Guardians Optimization Log - Casino-V3 (Absorption V2.1)

## 1. STATISTICAL_LOCATION
- **Current State:** Hard threshold at 2.0Z.
- **Efficiency:** High protection (54% losers avoided), but high opportunity cost (30% winners killed).
- **Discovery:** Range 1.0-1.5Z has 44% winners but is net-negative due to fees and adjacent noise.
- **Proposal (Pending):** Implement **Dynamic Sniper Threshold**.
    - Base: 2.0Z.
    - Reduced (1.65Z): Only if `LIQUIDITY_SCORE > 0.8`.
    - Purpose: Capture border Alpha without increasing noise.

## 2. REGIME_ALIGNMENT_V2
- **Current State:** 100% Pass rate (592/592).
- **Verdict:** The sensor is "deaf". A 100% pass rate in 24h of crypto market is a failure of detection, not a success of the market.
- **Aggressive Proposal:**
    - Lower `BALANCE_MAX_CONFIDENCE` from **0.35 to 0.20**.
    - Purpose: Pre-emptive strike. Block reversions at the first sign of directional conviction.

## 3. LIQUIDITY_HEATMAP
- **Current State:** Soft Gate (always passes).
- **Proposal (Pending):** Convert to a **Hard Gate** (or semi-hard) to support the Dynamic Sniper Threshold of Guardian #1.

## 4. SPREAD_SANITY
- **Current State:** 100% Pass rate.
- **Verdict:** Threshold is too loose (2.0x). For a 0.3% TP, even a 1.3x spread spike is unacceptable.
- **Aggressive Proposal:**
    - Lower `ratio` threshold from **2.0 to 1.3**.
    - Purpose: Protect the thin margins of the "Math Magnet" strategy.
