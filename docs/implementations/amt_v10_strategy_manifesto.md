# AMT V10 Strategy Manifesto — Casino-V3

> **Version**: V10.1 (Post-Cleanup)
> **Branch**: `v8.4-agent-friendly-refactor`
> **Status**: Certified (4-Coin Net Taker Positive)
> **Last Updated**: 2026-05-27

---

## 1. Central Thesis

Markets are continuous auctions. Price discovers value through the interaction of aggressive and passive participants. The system does not predict patterns — it detects **narratives**: market conditions where institutional order flow creates exploitable asymmetries.

**Three core principles:**

1. **Information Asymmetry**: L2 order book depth provides structural advantages unavailable to price-only systems. A "wall" (L2 Ratio >= 2.0) physically shields against adverse excursion, reducing average MAE to 0.358%.

2. **Mechanical Trapped-Trader Behavior**: When breakout traders are trapped (Failed Breakout) or when aggressive sellers exhaust against passive bids (Absorption), their forced exits create predictable directional pressure.

3. **Narrative Completeness**: A signal is not just an entry — it is a complete market story with regime context, structural geography, and microstructural confirmation. The Guardian chain validates the narrative before any capital is committed.

---

## 2. Architecture Overview

```
                          ┌─────────────────────────────────────┐
                          │           DATA LAYER                 │
                          │  ContextRegistry   FootprintRegistry │
                          │  (POC/VAH/VAL)     (CVD, Delta)     │
                          └────────┬───────────────┬────────────┘
                                   │               │
         ┌─────────────────────────┼───────────────┼─────────────────────────┐
         │                         │               │                         │
         ▼                         ▼               ▼                         ▼
  ┌─────────────┐         ┌──────────────┐  ┌──────────────┐         ┌──────────────┐
  │  TICK EVENT  │         │ SIGNAL EVENT │  │  CANDLES     │         │ MICROSTRUCTURE│
  └──────┬──────┘         └──────┬───────┘  └──────┬───────┘         └──────┬───────┘
         │                       │                  │                        │
         ▼                       │                  │                        │
  ═══════════════════════════════╪══════════════════╪════════════════════════╪═════
  ║        SetupEngineV4         │                  │                        ║
  ║                              │                  │                        ║
  ║  on_tick() ──────────────────┘                  │                        ║
  ║    │                                              │                        ║
  ║    ▼                                              │                        ║
  ║  ScenarioManager.on_tick()                        │                        ║
  ║    ├── LiquidityExhaustionDetector (P: 100)       │                        ║
  ║    ├── FailedBreakoutDetector      (P: 50)        │                        ║
  ║    └── TrendAcceptanceDetector     (P: 30)        │                        ║
  ║    │                                               │                        ║
  ║    ▼ (conviction arbitration)                      │                        ║
  ║                                                    │                        ║
  ║  on_signal() ◄─────────────────────────────────────┘                        ║
  ║    │                                                                        ║
  ║    ▼                                                                        ║
  ║  AbsorptionDetector ──► Fast-Lane ──► _process_signal()                     ║
  ║                                                                        ║
  ║  _process_signal() ◄─────────────────────────────────────────────────────╝
  ║    │
  ║    ├── GuardianManager.evaluate_all()
  ║    │     ├── RegimeGuardian      (7-case matrix)
  ║    │     ├── StructureGuardian   (micro-geography)
  ║    │     ├── SpreadSanityGuardian (spread quality)
  ║    │     └── LiquidityGuardian   (L2 wall)
  ║    │
  ║    ├── _calculate_targets()  (AMT Structural or ATR Fallback)
  ║    │
  ║    └── TradeProposal dispatch
  ║
  ════════════════════════════════════════════════════════════════════════════════
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │   TradeProposal      │
                            │   → AdaptivePlayer   │
                            │   → Croupier         │
                            │   → OrderManager     │
                            └──────────────────────┘
```

### Signal Priority & Arbitration

| Scenario | Priority | Edge | Frequency |
|----------|----------|------|-----------|
| LiquidityExhaustion | **100** | ~0.32% gross | Rare (n=10) |
| FailedBreakout | **50** | ~0.09% gross | Medium (n=29) |
| TrendAcceptance | **30** | -0.06% gross (range) | Medium (n=25) |
| Absorption (V2) | **80** (via Guardian) | ~0.09% gross | Frequent (n=73) |

**Conflict Resolution**: If LONG and SHORT fire simultaneously, conviction scores are summed per side. If |diff| < 30, both neutralize. If |diff| >= 30, the higher side wins. Multiple scenarios in the same direction are fused into a **composite signal** with enriched conviction.

**Global Cooldown**: 15 seconds per symbol between any signal dispatch.

---

## 3. Scenario Detectors

### 3.1 Liquidity Exhaustion — "Multiple Tests with Declining Delta"

> *A structural level is tested repeatedly. Each test has LESS aggressive flow. The attacking side is running out of ammunition. The level will likely hold.*

**AMT Narrative**: Institutional defense of a price level. Sellers (or buyers) repeatedly hit the level with decreasing conviction. Passive liquidity absorbs the flow. The attack fails.

**Entry Conditions** (ALL must be true):

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Touches of same level (±0.05%) | >= 3 in last 120s |
| 2 | Delta declining per test | Each test < 70% of previous |
| 3 | Price bounced from level | >= 0.03% away |

**Signal**: Fires after 2nd+ test with declining delta + bounce. Side = opposite to attacker (VAL tests → LONG, VAH tests → SHORT).

**Configuration**:
```python
level_tolerance_pct = 0.0005    # 0.05%
test_memory_seconds = 120.0
min_tests = 3
declining_threshold = 0.7       # < 70% of previous delta
min_bounce_pct = 0.0003         # 0.03%
cooldown = 30.0
```

**Observed Edge**: WR 66.7% | Gross +0.324% | MFE/MAE 1.50 | n=10

---

### 3.2 Failed Breakout — "Breakout + Divergent Delta"

> *Price breaks a structural level. Looks like a breakout. But delta does NOT confirm — the break has weak conviction. Price returns inside the VA. Breakout traders are trapped.*

**AMT Narrative**: Failed auction extension. Price temporarily leaves value but lacks institutional conviction (CVD divergence). The breakout is a trap. Trapped traders are forced to exit, creating reversal pressure.

**Entry Conditions** (ALL must be true):

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Price crossed VAH (SHORT) or VAL (LONG) | Within last 60s |
| 2 | CVD during break did NOT confirm | CVD change < 30% of expected |
| 3 | Price returned inside VA | Crossed back through broken level |
| 4 | Return was fast | < 60 seconds from break |

**Exhaustion Gate**: If CVD change > 1.8x expected confirming move → break is REAL → signal discarded (TrendAcceptance territory).

**Signal**: Entry at re-entry into VA. Direction = opposite to break.

**Configuration**:
```python
cooldown = 60.0
max_break_age = 60.0
min_break_distance_pct = 0.0003  # 0.03%
cvd_divergence_threshold = 0.3   # CVD < 30% of confirming move
```

**Observed Edge**: WR 35.7% | Gross +0.084% | MFE/MAE 0.96 | n=29

*Profile: Few large wins, many small losses. Asymmetric risk.*

---

### 3.3 Trend Acceptance — "VA Breakout + Confirming Delta + Pullback"

> *Price leaves the VA with strong delta confirmation. The market is genuinely accepting new prices. The entry is on the pullback to the broken level.*

**AMT Narrative**: Genuine trend initiation. Price breaks value with institutional conviction (CVD confirms). The breakout is real. Entry on the pullback to the broken level (now support/resistance).

**Entry Conditions** (ALL must be true):

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Price outside VA for consecutive candles | >= 3 candles (1m) |
| 2 | CVD confirmed breakout direction | Slope > 5.0 |
| 3 | Price pulled back toward broken level | Within 0.1% of level |
| 4 | Pullback did not re-enter VA | Max penetration 0.1% |

**Invalidation**: Breakout invalidated if price returns to VA for >= 2 consecutive candles.

**Signal**: Direction = trend direction (broke VAH → LONG, broke VAL → SHORT).

**Configuration**:
```python
cooldown = 60.0
min_candles_outside = 3
min_invalidation_candles = 2
pullback_tolerance_pct = 0.001     # 0.1%
max_pullback_penetration_pct = 0.001
cvd_confirmation_threshold = 5.0
```

**Observed Edge**: WR 42.9% | Gross -0.064% | MFE/MAE 0.96 | n=25

*Note: Negative edge in range data confirms correct regime classification. Needs BULL/BEAR validation.*

---

### 3.4 Absorption — "Institutional Exhaustion at Level"

> *Aggressive volume hits a level without price displacement. Sellers (or buyers) are exhausted. Price will reverse toward POC.*

**AMT Narrative**: Institutional absorption. A large passive order absorbs aggressive flow without letting price move. The aggressor exhausts their inventory. The level is a wall.

**Entry Conditions** (ALL must be true):

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Extreme delta (Z-score) | >= 3.0 (cross-sectional) |
| 2 | Concentration | >= 0.50 (50% one-directional) |
| 3 | Noise | <= 0.35 (max 35% counter-delta) |
| 4 | Price stagnation | Displacement < max(ATR×0.25, 0.10%) |

**Exhaustion Gate**: If `delta_ratio > 1.5` and setup is reversion → BLOCKED (aggressor intensifying, not exhausting).

**Signal**: SELL_EXHAUSTION (delta < 0) → LONG | BUY_EXHAUSTION (delta > 0) → SHORT

**Configuration**:
```python
ABSORPTION_MIN_Z_SCORE = 3.0
ABSORPTION_MIN_CONCENTRATION = 0.50
ABSORPTION_MAX_NOISE = 0.35
stagnation_floor_pct = 0.10
```

**Observed Edge**: WR 64.3% | Gross +0.092% | MFE/MAE 1.01 | n=73

---

## 4. Guardian Chain

The Guardian chain validates the **narrative** before any capital is committed. All guardians must pass. Any single failure → trade rejected.

### 4.1 Regime Guardian — "Is this trade aligned with the market?"

Determines **SetupMode** (REVERSION or CONTINUATION) and validates structural alignment.

**Value Position Calculation**:
```
IN_VALUE:      Price between VAL and VAH
OUT_OF_VALUE:  Price at/beyond VAH/VAL but within 50% of VA width
EXCESS:        Price beyond VAH/VAL + 50% of VA width
```

**Decision Matrix — TREND Regime**:

| Case | Alignment | Acceptance | Position | Result | Score | Mode |
|------|-----------|------------|----------|--------|-------|------|
| 1 | trend-aligned | ACCEPTING | any | PASS | 1.0 | CONTINUATION |
| 2 | trend-aligned | NEUTRAL | any | PASS | 0.7 | CONTINUATION |
| 3 | counter-trend | REJECTING | EXCESS | PASS | 0.8 | REVERSION |
| 4 | counter-trend | REJECTING | OUT_OF_VALUE | PASS | 0.5 | REVERSION |
| 5 | counter-trend | ACCEPTING | any | **BLOCK** | 0.0 | — |
| 6 | counter-trend | NEUTRAL | any | BLOCK if conf>0.3 | 0.0-0.9 | REVERSION |
| 7 | trend-aligned | REJECTING | any | PASS | 0.6 | CONTINUATION |

**BALANCE Regime**:
- OUT_OF_VALUE/EXCESS → PASS (score 1.0, REVERSION)
- IN_VALUE + pure reversion → PASS (score 0.7, REVERSION)
- IN_VALUE + continuation → PASS (score 0.7, CONTINUATION rotation)

**Toxic Flow Hard-Block**: Pure reversion setups (`TacticalAbsorptionV2`, `failed_breakout`) are **structurally banned** in OUT_OF_VALUE/EXCESS zones.

---

### 4.2 Structure Guardian — "Is the entry at the right geography?"

Validates micro-geography of entry price against Volume Profile nodes.

**Geography Tags**:
```
AT_VAH:        |price - VAH| <= tolerance (15% of VA width or 0.1%)
AT_VAL:        |price - VAL| <= tolerance
AT_POC:        |price - POC| <= tolerance
NO_MANS_LAND:  Not near any structural node
```

**REVERSION Mode**:

| Geography | Side=SHORT at VAH | Side=LONG at VAL | Other |
|-----------|-------------------|------------------|-------|
| AT_VAH | PASS (1.0) | **BLOCK** | — |
| AT_VAL | **BLOCK** | PASS (1.0) | — |
| AT_POC | **BLOCK** | **BLOCK** | — |
| NO_MANS_LAND | PASS (0.3) | PASS (0.3) | — |

**CONTINUATION Mode**:

| Geography | Result |
|-----------|--------|
| AT_POC | PASS (1.0) — strong pullback |
| AT_VAH | **BLOCK** — unsafe at VA edge |
| AT_VAL | **BLOCK** — unsafe at VA edge |
| NO_MANS_LAND | PASS (0.7) |

---

### 4.3 Spread Sanity Guardian — "Is execution quality acceptable?"

| Spread Ratio (current / 5m avg) | Result | Score |
|----------------------------------|--------|-------|
| > 2.0x | **BLOCK** | 0.0 |
| 1.0x - 2.0x | PASS (linear decay) | 0.3 - 1.0 |
| <= 1.0x | PASS | 1.0 |

---

### 4.4 Liquidity Guardian — "Is there a physical shield?"

Requires L2 order book depth ("wall") at the target price.

| L2 Ratio | Result | Score |
|----------|--------|-------|
| < 2.0 | **BLOCK** (thin wall) | 0.0 |
| >= 2.0 | PASS | varies |

**Impact**: High Wall (>2.0) reduces average MAE to 0.358% and achieves MFE/MAE ratio of 1.63.

---

## 5. Target Calculation

### Tier 1: AMT Structural (Primary)

When POC, VAH, and VAL are all available, TP/SL are derived from VA geometry:

| Scenario | TP Target | SL Buffer |
|----------|-----------|-----------|
| Absorption | OPPOSITE boundary (VAH for LONG, VAL for SHORT) | 0.3 × VA width |
| FailedBreakout | OPPOSITE boundary | 0.5 × VA width |
| LiquidityExhaustion | OPPOSITE boundary | 0.3 × VA width |
| TrendAcceptance | POC | ATR-based |

**Noise Floors**:
```python
noise_floor_tp = max(ATR × 1.5, 0.15%)   # Minimum TP distance
noise_floor_sl = max(ATR × 1.0, 0.10%)   # Minimum SL distance
```

### Tier 2: ATR Fallback (When VA unavailable)

| Scenario | TP Multiplier | SL Multiplier |
|----------|---------------|---------------|
| Absorption | 5.0× ATR | 3.33× ATR |
| TrendAcceptance | 4.5× ATR | 3.6× ATR |
| FailedBreakout | 2.5× ATR | 2.0× ATR |
| LiquidityExhaustion | 2.5× ATR | 2.0× ATR |

### Breakeven Guard

Before dispatch, a fee-friction guard checks:
```python
fee_friction = 0.09%  # 0.05% Taker + 0.02% Maker + 0.02% Slippage
if TP_distance < fee_friction → ABORT (TP too close to cover costs)
```

---

## 6. Configuration Reference

### Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `ABSORPTION_MAX_HOLDING_SEC` | 14,400 (4h) | Max holding for absorption scenarios |
| `fire_cooldown` | 15.0s | Global cooldown per symbol |
| `DEFAULT_TP_PCT` | 0.3% | Fallback TP (no VA data) |
| `DEFAULT_SL_PCT` | 0.2% | Fallback SL (no VA data) |
| `POSITION_SIZING_MODE` | FIXED_RISK | Risk-based sizing |
| `RISK_PER_TRADE` | 0.2% | Max risk per trade |
| `MAX_LEVERAGE` | 50x | Maximum leverage |

### Risk Management

| Mechanism | Threshold | Action |
|-----------|-----------|--------|
| Drawdown 2% | CAUTION | Block new entries |
| Drawdown 5% | CRITICAL | Drain mode |
| 12 consecutive losses | CRITICAL | Stop trading |

---

## 7. Data Flow

```
WebSocket/BacktestFeed (Trade Ticks + L2 Depth)
  │
  ▼
FootprintRegistry (CVD, Delta, Exhaustion metrics)
  │
  ├──► AbsorptionDetector (SensorWorker) ──► SignalEvent
  ├──► SessionValueArea (POC/VAH/VAL) ──► ContextRegistry
  └──► MarketRegimeSensor (3-layer V2) ──► ContextRegistry
  │
  ▼
SetupEngineV4.on_tick()
  │
  ▼
ScenarioManager.on_tick()
  ├── LiquidityExhaustionDetector  (Priority 100)
  ├── FailedBreakoutDetector       (Priority 50)
  └── TrendAcceptanceDetector      (Priority 30)
  │
  ▼ (conviction arbitration)
  │
_process_signal()
  │
  ▼
GuardianManager.evaluate_all()
  ├── RegimeGuardian      (7-case matrix)
  ├── StructureGuardian   (micro-geography)
  ├── SpreadSanityGuardian (spread quality)
  └── LiquidityGuardian   (L2 wall)
  │
  ▼ (all passed)
  │
_calculate_targets()
  ├── AMT Structural (VA geometry) or ATR Fallback
  ├── Noise floor enforcement
  └── Breakeven guard check
  │
  ▼
TradeProposal → AdaptivePlayer → Croupier → OrderManager
```

---

## 8. Edge Statistics

### Per-Scenario Performance (4h Window, Net Taker)

| Scenario | n | Win Rate | Gross Exp | Net Taker | Verdict |
|----------|---|----------|-----------|-----------|---------|
| LiquidityExhaustion | 10 | 66.7% | +0.324% | +0.204% | CERTIFIED |
| Absorption (V2) | 73 | 64.3% | +0.092% | -0.028% | WATCH |
| FailedBreakout | 29 | 35.7% | +0.084% | -0.036% | WATCH |
| TrendAcceptance | 25 | 42.9% | -0.064% | -0.184% | UNVALIDATED |

### Certification Status (4-Coin Net Taker Positive)

| Coin | Net Taker (1.2% target, 4h) | Status |
|------|----------------------------|--------|
| BNB | +0.107% | CERTIFIED |
| SOL | +0.280% | CERTIFIED |
| SUI | +0.080% | CERTIFIED |
| AVAX | +0.120% | CERTIFIED |
| ETH | Negative | EXCLUDED |

### Known Limitations

1. **Timeout Rate**: >70% of signals timeout in 1h window. The 4h window is required for narratives to develop.
2. **L2 Data Dependency**: Guardians require real L2 order book data. Backtests without L2 may overestimate edge.
3. **Trend Scenario Unvalidated**: TrendAcceptance shows negative edge in range data. Requires dedicated BULL/BEAR dataset validation.
4. **Sample Size**: LiquidityExhaustion has n=10. Statistical significance requires n>=50.
5. **ETH Problem**: ETH consistently fails to achieve Net Taker positive in any configuration. Under investigation.

---

## Appendix A: File Reference

| Component | File | Lines |
|-----------|------|-------|
| SetupEngineV4 | `decision/engine/core.py` | ~340 |
| ScenarioManager | `decision/scenario_manager.py` | ~150 |
| LiquidityExhaustionDetector | `decision/scenarios/liquidity_exhaustion.py` | ~146 |
| FailedBreakoutDetector | `decision/scenarios/failed_breakout.py` | ~161 |
| TrendAcceptanceDetector | `decision/scenarios/trend_acceptance.py` | ~161 |
| AbsorptionDetector | `sensors/absorption/absorption_detector.py` | ~249 |
| GuardianManager | `decision/guardians/guardian_manager.py` | ~80 |
| RegimeGuardian | `decision/guardians/regime_guardian.py` | ~167 |
| StructureGuardian | `decision/guardians/structure_guardian.py` | ~129 |
| TargetingMixin | `decision/engine/targets.py` | ~111 |
| TradeProposal | `decision/engine/proposal.py` | ~20 |
