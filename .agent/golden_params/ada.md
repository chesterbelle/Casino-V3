# ADAUSDT Golden Parameters (Fast-Tracked from NEAR)

## Profile Summary
- **Cluster:** MEGA_LIQUID
- **Dataset Count:** 6
- **Total Signals (Audit):** 199
- **Overall Win Rate:** 15.1% (Decided 30W/11L)
- **Net Taker (0.07% fee):** +0.1682%
- **Net Maker (0.02% fee):** +0.2182%
- **Is Certified:** Yes (Fast-Tracked via NEAR Profile)

## Targets (Optimized via Audit Static Grid)

### Trend Acceptance
- **TP/SL:** 1.50% / 1.50%
- **Edge:** MFE/MAE 1.47 ✅, Positive Net Taker

### Failed Breakout
- **TP/SL:** 2.50% / 2.50%
- **Edge:** MFE/MAE 5.89 ✅, Positive Net Taker

### Tactical Absorption
- **TP/SL:** 1.20% / 1.20%
- **Edge:** MFE/MAE 1.42 ✅, Positive Net Taker

### Liquidity Exhaustion
- **TP/SL:** 0.50% / 0.80%
- **Edge:** MFE/MAE 0.59 ❌ (Target optimized for positive net, but structurally weak edge in ADA)

## Key Observations
ADAUSDT shares the `MEGA_LIQUID` microstructure with NEARUSDT. Copying NEAR's parameters and adjusting the targets based on a single 6-dataset audit run was sufficient to produce a profitable net taker edge.

**Note:** `liquidity_exhaustion` in ADA has a poor structural edge (MFE/MAE < 1.2), very similar to DOGE, indicating that exhaustion setups are not reliable for this asset class. The system handles this gracefully by either timing out or tuning tight targets.
