# Alpha Specifications (AMT V3)

## 1. Liquidity Exhaustion
**Objective:** Detect structural level tests with declining aggressive flow.

### Critical Thresholds & Parameters
- **`level_tolerance_pct`**: 0.05% (default).
- **`test_memory_seconds`**: 120s (max age of a test).
- **`min_tests`**: 3 (must have 3+ touches).
- **`declining_threshold`**: 0.7 (each test must have < 70% of previous delta).
- **`min_bounce_pct`**: 0.03% (required bounce from level to confirm rejection).
- **`cooldown`**: 30s.

### Logic
- If `price` within `level_tolerance_pct` of POC/VAH/VAL:
    - Record new test if transitioned from outside.
    - Measure delta as `abs(cvd_slope)` over 3 seconds.
- If price bounces `> min_bounce_pct` from level:
    - If `len(tests) >= min_tests` AND all `tests[i].delta < tests[i-1].delta * 0.7`:
        - **SIGNAL FIRE.**

---

## 2. Failed Breakout
**Objective:** Identify breakout trap where delta diverges.

### Critical Thresholds & Parameters
- **`max_break_age`**: 60s.
- **`min_break_distance_pct`**: 0.03%.
- **`cvd_divergence_threshold`**: 0.3 (30% of confirming break volume).
- **`cooldown`**: 60s.

### Logic
- **Detection:** Break VAH by `> min_break_distance_pct` (Short setup) or VAL (Long setup).
- **Confirmation:**
    - `elapsed` since break must be `< max_break_age`.
    - Price must return *inside* the VA.
    - **Exhaustion Gate:** If `cvd_change` is `> 1.8 * expected_change`, block signal (Trend Acceptance).
    - **Divergence:** `abs(cvd_change) < expected_change * 0.3`.
- **SIGNAL FIRE** on re-entry if divergent.

---

## 3. Absorption Detector
**Objective:** Detect volume without price movement (Stagnation).

### Critical Thresholds & Parameters
- **`z_score_min`**: 3.0 (from `config.absorption`).
- **`concentration_min`**: 0.50 (from `config.absorption`).
- **`noise_max`**: 0.35 (from `config.absorption`).
- **`stagnation_floor_pct`**: 0.10.

### Logic
1. **Magnitude:** `abs(z_score) >= 3.0`.
2. **Velocity:** `concentration >= 0.50`.
3. **Noise:** `noise (counter-directional vol) <= 0.35`.
4. **Stagnation:** `displacement_pct < max(atr_pct * 0.25, 0.10)`.
5. **Exhaustion Gate:** If `delta_ratio > 1.5`, reject (intensifying).

---

## 4. Market Trend Calculation (Layers)

### Micro Layer (Tick-level Momentum)
- **`MICRO_SURGE_Z_THRESHOLD`**: 1.2 (Surge).
- **`MICRO_ABSORPTION_Z_THRESHOLD`**: 1.8 (Absorption).
- **Logic:** Aligned if `dv_z > 1.2` and `pv_z > 1.0`. Absorption if `dv_z > 1.8` and `pv_z < 1.0` (requires 2+ snapshots).

### Meso Layer (VA Expansion)
- **`MESO_EXPANSION_THRESHOLD`**: 0.05 (5% faster expansion).
- **Logic:** If `fast_va_avg > slow_va_avg * 1.05`, market is leaving balance. Direction defined by price position relative to VA center (>75% or <25%).

### Macro Layer (POC Migration)
- **`MACRO_POC_VELOCITY_THRESHOLD`**: 0.0001 (0.01% per candle).
- **Logic:** `net_ratio (direction agreement) > 0.55` and `velocity > 0.01%`.
