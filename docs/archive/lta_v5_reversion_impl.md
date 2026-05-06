# LTA V5 — Implementation Manifest

> **Architecture Reference**: Casino-V3 `v6.1.0-edge-verified`
>
> This document supersedes `lta_v4_reversion_impl.md`. It maps every theoretical concept
> of the LTA V5 strategy to its exact code location, config value, and architectural decision.
>
> **Key changes from V4:**
> - Sensor consolidation (9 → 6 tactical sensors)
> - Guardian restructuring (6 → 5 guardians, Failed Auction removed)
> - Phase 2300: Price Circuit Breaker for extreme moves
> - Phase 2300: PortfolioGuard shadow mode in audit
> - Long-Range Edge Audit protocol with 4 market conditions

---

## 1. Signal Pipeline Architecture

```
Tick/Candle Events
        │
        ▼
┌──────────────────────────────────┐
│  SensorWorker(s)                  │  Parallel processes (Actor Model)
│  ├─ MarketRegime (Phase 2100+2300)│  3-Layer + Price Circuit Breaker
│  ├─ FootprintAbsorption           │  NÚCLEO: defensa del borde VA
│  ├─ FootprintDeltaDivergence      │  Confirmador: agotamiento momentum
│  ├─ FootprintTrappedTraders       │  Confirmador: participantes atrapados
│  ├─ FootprintVolumeExhaustion     │  Confirmador: volumen extremo
│  ├─ LiquidationCascade            │  Playbook Beta: fade dislocación
│  ├─ TacticalSinglePrintReversion  │  NEW: Market Profile single prints
│  └─ TacticalVolumeClimaxReversion │  NEW: Wyckoff volume climax
│
│  ELIMINATED in LTA V5:
│  ✗ FootprintPOCRejection (TacticalRejection) — redundante con Absorption
│  ✗ FootprintStackedImbalance — contradictorio (continuación vs reversión)
│  ✗ FootprintImbalance (TacticalImbalance) — menos específico que TrappedTraders
└────────┬─────────────────────────┘
         │  SignalEvent (via IPC Queue)
         ▼
┌──────────────────┐
│   SetupEngineV4   │  decision/setup_engine.py
│   ├─ Signal Memory (5s sliding window)
│   ├─ Structural Sync (POC/VAH/VAL + VA Integrity from session)
│   ├─ Strategy Evaluator (_evaluate_lta_structural)
│   └─ 5 Guardian Gates (Failed Auction REMOVED in Phase 2300)
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
│    └─ Shadow Mode │     │   Invalidation│
│      in Audit     │     └─────────────┘
└──────────────────┘
```

---

## 2. Sensor Consolidation (LTA V5)

### Tactical Whitelist

```python
TACTICAL_WHITELIST = (
    # Playbook Alpha: Reversión Estructural
    "TacticalAbsorption",           # Núcleo: defensa del borde VA
    "TacticalDivergence",           # Confirmador: agotamiento de momentum
    "TacticalTrappedTraders",       # Confirmador: participantes atrapados
    "TacticalExhaustion",           # Confirmador: volumen extremo sin follow-through
    "TacticalLiquidationCascade",   # Playbook Beta: fade de dislocación extrema
    # LTA V5: NEW SENSORS
    "TacticalSinglePrintReversion", # Market Profile: single print rejection
    "TacticalVolumeClimaxReversion",# Wyckoff: volume climax without extension
)
```

### Eliminated Sensors

| Sensor | Reason |
|--------|--------|
| `TacticalRejection` | Redundante con TacticalAbsorption (correlación >0.85) |
| `TacticalStackedImbalance` | Contradictorio — predice continuación en playbook de reversión |
| `TacticalImbalance` | Menos específico que TacticalTrappedTraders |

### New Sensors

**`TacticalSinglePrintReversion`** (`sensors/footprint/single_print_reversion.py`)
- Detecta zonas de single prints (volumen ultra-bajo) en bordes del VA
- Señala cuando el precio vuelve a testear la zona y rebota
- Basado en Market Profile / Auction Market Theory

**`TacticalVolumeClimaxReversion`** (`sensors/footprint/volume_climax_reversion.py`)
- Detecta volumen climax (>3x promedio) en bordes VA sin extensión de precio
- Delta se invierte en la misma vela del climax
- Basado en metodología Wyckoff

---

## 3. Guardian Architecture (LTA V5 — 5 Gates)

### Overview

| # | Guardian | Status | Phase |
|---|----------|--------|-------|
| 1 | Regime Alignment V2 | ✅ Active | 2100+2300 |
| 2 | POC Migration | ✅ Active | 1150 |
| 3 | VA Integrity | ✅ Active (soft gate) | 2200 |
| 4 | ~~Failed Auction~~ | ❌ **REMOVED** | 2300 |
| 5 | Delta Divergence | ✅ Active | 2200 |
| 6 | Spread Sanity | ✅ Active | 2000 |

### Why Failed Auction was removed (Phase 2300)

The Failed Auction concept in Axia Futures / Market Profile operates at **session timeframe** (hours), not 1-minute candles. The original implementation was:

1. **Wrong scale**: Checking 1m candle wicks for a concept that requires session-level IB breaks
2. **Duplicated**: `SessionValueArea` already calculates `failed_auctions` correctly at session level
3. **Inverted**: Empirically showed -29% discrimination (rejected MORE in RANGE than in trending conditions)
4. **Redundant**: Tactical sensors (Absorption, TrappedTraders) already confirm the rejection microstructure

**Evidence**: Guardian efficacy audit showed FAILED_AUCTION discrimination = -29.2% across 4 market conditions.

---

### 3.1 Guardian 1: Anticipatory Regime Alignment (`_check_regime_alignment`)

**Phase 2100 + 2300**

**Purpose**: Prevents reversions during market breakouts/trends.

**Implementation**: Two-layer detection:

**Layer A — Microstructure (3-layer voting)**:
1. **Micro (0-10s)**: Tick-level delta velocity (Z-score)
2. **Meso (1-5m)**: Value Area expansion and IB breaks
3. **Macro (15m+)**: POC migration velocity

**Layer B — Price Circuit Breaker (Phase 2300)**:
- Measures raw price displacement over 10 candles (no Z-score normalization)
- Triggers at >2% displacement (trend) or >4% (crash/rally)
- **Persistent**: Once triggered, stays active until price recovers >0.5% toward balance
- Prevents the Z-score adaptation problem where crashes appear "normal"

**Regime States**:
- `BALANCE` → PASS (reversion optimal)
- `TRANSITION` → REJECT (market leaving balance)
- `TREND_UP` → PASS if LONG only
- `TREND_DOWN` → PASS if SHORT only

**Config**:
```python
CIRCUIT_BREAKER_LOOKBACK = 10      # Candles
CIRCUIT_BREAKER_TREND_PCT = 0.02   # 2% = trend
CIRCUIT_BREAKER_CRASH_PCT = 0.04   # 4% = crash/rally override
```

---

### 3.2 Guardian 2: POC Migration (`_check_poc_migration`)

**Phase 1150** — Unchanged from V4.

**Purpose**: Rejects if POC is migrating aggressively against the intended direction.

**Threshold**: `LTA_POC_MIGRATION_THRESHOLD = 0.0050` (0.5%)

---

### 3.3 Guardian 3: VA Integrity (`_check_va_integrity`)

**Phase 2200** — Restructured from hard gate to soft gate.

**Change from V4**: Previously rejected ~80% of signals (1,594/1,986 in audit).
Now uses 50% of threshold as critical floor — only rejects critically low integrity.

```python
critical_threshold = threshold * 0.50  # Only reject at critically low integrity
```

**Rationale**: Regime Guardian (G1) already ensures we're in BALANCE. If we're in BALANCE, the VA doesn't need to be perfectly dense.

---

### 3.4 Guardian 5: Delta Divergence (`_check_delta_divergence`)

**Phase 2200** — Threshold relaxed.

**Change from V4**: Threshold relaxed from z < -1.5 to z < -2.5.

**Rationale**: In legitimate reversions, flow can be at -1.8 to -2.0 just before turning. Only truly extreme, sustained flow should block a LONG.

---

### 3.5 Guardian 6: Spread Sanity (`_check_spread_sanity`)

**Phase 2000** — Unchanged from V4.

**Purpose**: Rejects entries when spread > 2× 5-minute rolling average.

---

## 4. Phase 2300: PortfolioGuard Shadow Mode in Audit

**File**: `croupier/croupier.py` — `_on_guard_state_change()`

**Problem**: In `--audit` mode, PortfolioGuard could activate drain mode after consecutive losses, blocking new entries and violating the zero-interference principle.

**Fix**: In AUDIT_MODE, PortfolioGuard runs in shadow mode — logs state changes but does NOT activate drain mode or kill switch.

```python
if getattr(trading_config, "AUDIT_MODE", False):
    logger.warning(f"🔍 [AUDIT SHADOW] PortfolioGuard would transition {old} → {new}: {reason} (suppressed)")
    return
```

---

## 5. Edge Statistics (LTA V5)

### Standard Edge Audit (April 2025, LTC/SOL/ETH)

| Metric | LTA V4 | LTA V5 | Change |
|--------|--------|--------|--------|
| Signals | 44 | 80 | +82% |
| MFE/MAE Ratio | 1.37 | 1.62 | +18% |
| Win Rate 0.3% | 64.5% | 69.4% | +4.9% |
| Expectancy | +0.0871 | +0.1163 | +34% |

### Long-Range Edge Audit (4 Market Conditions, LTC)

| Condition | Date | n | WR% | Ratio | Verdict |
|-----------|------|---|-----|-------|---------|
| RANGE | 2026-04-12 | 13 | 75.0% | 2.19 | CERTIFIED |
| BEAR NORMAL | 2026-04-11 | 7 | 100.0% | 4.05 | LOW_N |
| BEAR CRASH | 2026-04-02 | 4 | 0.0% | 0.33 | FAILED |
| BULL | 2026-04-07 | 4 | 75.0% | 0.74 | LOW_N |

**Key insight**: Strategy has strong edge in BALANCE conditions. BEAR CRASH (-38% in 1 day) is an extreme tail event where no mean-reversion strategy should operate.

---

## 6. Guardian Efficacy Analysis

### Discrimination Score (how much MORE each guardian rejects in trending vs range)

| Guardian | Discrimination | Status |
|----------|---------------|--------|
| REGIME_ALIGNMENT_V2 | +0.5% | ⚠️ WEAK — needs improvement |
| POC_MIGRATION | -3.9% | ❌ INVERTED — pending analysis |
| VA_INTEGRITY | -3.1% | ❌ INVERTED — pending analysis |
| FAILED_AUCTION | REMOVED | — |
| DELTA_DIVERGENCE | +5.9% | ✅ GOOD |
| SPREAD_SANITY | N/A | — |

**Known issues for future work**:
- REGIME_ALIGNMENT_V2 discrimination is weak despite circuit breaker — Z-score adaptation still partially neutralizes crash detection
- POC_MIGRATION and VA_INTEGRITY show inverted discrimination — pending deeper analysis

---

## 7. Audit Datasets

**Location**: `tests/validation/`

| File | Date | Condition | Trades | Source |
|------|------|-----------|--------|--------|
| `ltc_24h_audit.csv` | 2026-04-12 | RANGE | 104K | parity_data_fetcher |
| `ltc_bear_normal_24h.csv` | 2026-04-11 | BEAR (-2.8%) | 113K | parity_data_fetcher |
| `ltc_bear_24h_v2.csv` | 2026-04-02 | BEAR CRASH (-38%) | 192K | parity_data_fetcher |
| `ltc_bull_24h_v2.csv` | 2026-04-07 | BULL (+11%) | 351K | parity_data_fetcher |

**Download tool**: `tests/validation/parity_data_fetcher.py` (Binance Futures aggTrades API, up to 1 year back)

**Analysis tools**:
- `utils/analysis/per_condition_audit.py` — Vectorized per-condition MFE/MAE
- `utils/analysis/guardian_efficacy_audit.py` — Guardian discrimination scores
- `utils/analysis/regime_guardian_debug.py` — Regime guardian trace analysis

---

## 8. File Reference Map

| Component | File | Notes |
|-----------|------|-------|
| Strategy Config | `config/strategies.py` | Thresholds, window map, lookback |
| Sensor Config | `config/sensors.py` | ACTIVE_SENSORS registry |
| Setup Engine | `decision/setup_engine.py` | `_evaluate_lta_structural`, 5 guardians |
| Context Registry | `core/context_registry.py` | Session structural levels, VA integrity |
| Market Profile | `core/market_profile.py` | POC/VA calculation |
| Regime Sensor | `sensors/regime/market_regime.py` | Phase 2100+2300: 3-Layer + Circuit Breaker |
| Session Sensor | `sensors/footprint/session.py` | Window detection, IB, VA integrity |
| Absorption Sensor | `sensors/footprint/absorption.py` | Core tactical sensor |
| Single Print | `sensors/footprint/single_print_reversion.py` | NEW: Market Profile |
| Volume Climax | `sensors/footprint/volume_climax_reversion.py` | NEW: Wyckoff |
| Cascade Sensor | `sensors/footprint/liquidation_cascade.py` | Playbook Beta |
| Player | `players/adaptive.py` | Bet sizing, RR validation |
| Exit Manager | `croupier/components/hft_exit_manager.py` | Flow invalidation |
| Croupier | `croupier/croupier.py` | Phase 2300: Audit shadow mode |
| Sensor Manager | `core/sensor_manager.py` | Worker processes, shutdown |
