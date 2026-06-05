# Sensor Parameter Analysis — Accuracy Improvement Plan

## Current State
- **Accuracy**: 41.3% (52/126 signals)
- **GT distribution**: TREND_UP 73.5%, BALANCE 14.9%, TREND_DOWN 11.6%
- **Sensor distribution**: TREND_UP 37.3%, BALANCE 20.6%, TREND_DOWN 42.1%

## Key Issues Identified

### 1. Persistence Override Problem
**Symptom**: 30 TREND_DOWN signals when Macro = NEUTRAL (score 0.0)
**Root Cause**: The persistence logic (lines 168-216 in core_detector.py) maintains regime for up to 5 candles without macro confirmation.
**Impact**: Sensor reports TREND_DOWN when the actual regime is TREND_UP.

### 2. Meso Veto Too Aggressive
**Symptom**: BALANCE signals when Macro = UP (score 0.881)
**Root Cause**: Meso veto threshold at 0.2 (line 299) blocks valid trends.
**Impact**: Good trend signals get downgraded to BALANCE.

### 3. Macro Threshold Asymmetry
**Symptom**: TREND_UP signals when Macro = DOWN
**Root Cause**: Markov prior lowers threshold to 0.10 for trends, making it too easy to declare trend direction.
**Impact**: Wrong direction classification.

### 4. Low BALANCE Detection
**Symptom**: Only 16.0% BALANCE accuracy
**Root Cause**: Macro threshold too low (0.10-0.15) allows noise to be classified as trend.
**Impact**: BALANCE gets misclassified as TREND.

## Parameter Map

### Layer 1 — Micro (Flow Momentum)
| Parameter | Current | Impact | Recommendation |
|-----------|---------|--------|----------------|
| MICRO_FLOW_WINDOW_SECONDS | 10.0 | Window for delta accumulation | Keep (tuned) |
| MICRO_SURGE_Z_THRESHOLD | 1.2 | Z-score for flow surge | Keep (tuned) |
| MICRO_ABSORPTION_Z_THRESHOLD | 1.8 | Z-score for absorption | Keep (tuned) |
| MICRO_SNAPSHOT_HZ | 4.0 | Snapshots per second | Keep |

### Layer 2 — Meso (VA Expansion)
| Parameter | Current | Impact | Recommendation |
|-----------|---------|--------|----------------|
| MESO_VA_EXPANSION_FAST_WINDOW | 3 | Candles for fast VA | Keep |
| MESO_VA_EXPANSION_SLOW_WINDOW | 10 | Candles for slow VA | Keep |
| MESO_EXPANSION_THRESHOLD | 0.05 | 5% faster expansion | Keep |
| MESO_IB_BREAK_WEIGHT | 0.4 | Extra weight for IB break | Keep |
| ib_break_decay | 120.0 | IB break signal decay | Keep |

### Layer 3 — Macro (POC Migration)
| Parameter | Current | Impact | Recommendation |
|-----------|---------|--------|----------------|
| MACRO_POC_HISTORY_WINDOW | 20 | Candles for POC velocity | **Increase to 30** |
| MACRO_POC_VELOCITY_THRESHOLD | 0.0001 | 0.01% per candle | **Decrease to 0.00008** |
| MACRO_CONSECUTIVE_MIGRATION | 3 | N consecutive candles | **Increase to 4** |
| vel_score ceiling | 0.7 | Max velocity score | Keep |
| has_direction threshold | 0.55 | >55% candles agree | **Increase to 0.60** |

### Synthesis Thresholds
| Parameter | Current | Impact | Recommendation |
|-----------|---------|--------|----------------|
| macro_threshold (default) | 0.15 | Base threshold for trend | **Increase to 0.18** |
| macro_threshold (Markov trend) | 0.10 | When Markov favors trend | **Increase to 0.12** |
| macro_threshold (Markov balance) | 0.20 | When Markov favors balance | **Keep at 0.20** |
| meso_veto_threshold | 0.2 | Meso score to veto | **Increase to 0.25** |
| persistence_decay_window | 5 | Candles before release | **Decrease to 3** |
| persistence_reset_threshold | 0.005 | 0.5% reversal to reset | **Decrease to 0.003** |

### Markov Integration
| Parameter | Current | Impact | Recommendation |
|-----------|---------|--------|----------------|
| markov_confidence_threshold (trend) | 0.45 | To lower threshold | **Increase to 0.50** |
| markov_confidence_threshold (balance) | 0.55 | To raise threshold | **Keep at 0.55** |

## Expected Impact

| Change | Accuracy Impact | Reason |
|--------|----------------|--------|
| Increase macro_threshold | +2-3% | Fewer false trends |
| Increase meso_veto_threshold | +1-2% | Fewer BALANCE misclassifications |
| Decrease persistence_decay_window | +2-3% | Faster regime transitions |
| Increase macro_window | +1% | Smoother POC velocity |
| Increase has_direction | +1% | More conviction required |

**Total expected improvement**: +7-10% (41.3% → 48-51%)

## Implementation Order

1. **Phase 1**: Adjust synthesis thresholds (macro_threshold, meso_veto)
2. **Phase 2**: Tune persistence parameters (decay_window, reset_threshold)
3. **Phase 3**: Adjust macro layer parameters (window, velocity_threshold)
4. **Phase 4**: Fine-tune Markov integration thresholds
5. **Phase 5**: Validate and iterate

## Validation Method

For each parameter change:
1. Run backtest: `python scripts/orchestrator.py --protocol single-coin --symbol DOGEUSDT --filter 2024-10-01`
2. Run validator: `python utils/regime_validator.py --db data/historian_2024-10-01_DOGEUSDT.db --coin DOGE/USDT:USDT`
3. Compare accuracy metrics
4. Keep changes that improve accuracy without degrading other metrics
