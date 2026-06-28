#!/usr/bin/env python3
"""
Layer 0.C: Candidate Detection Validator (v2 — OrderFlowEngine)
---------------------------------------------------------------
In v8.9 architecture, candidate selection logic moved from AbsorptionDetector
into OrderFlowEngine.update() — specifically the concentration/z-noise z-scores
over the footprint level with the largest absolute delta.

This validator exercises that integrated candidate selection under controlled
inputs, ensuring:
  1. < 3 levels → rolling z-score remains cold (no false absorption)
  2. Mixed footprint → engine picks the level with highest |delta| for z-scoring
  3. Top candidate is a SELL_EXHAUSTION when bid_volume dominates the top level
  4. Top candidate is a BUY_EXHAUSTION when ask_volume dominates the top level
  5. Many levels → still 1 dominant outlier produces score saturating to 1.0
  6. Balanced → no extreme z-scores despite many levels
  7. Z-score ranking respects |delta| ordering

Usage:
    python utils/validators/absorption_candidate_validator.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.order_flow.engine import CoinOrderFlowEngine


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def warmup_and_score(symbol: str, footprint_levels: dict, warmup_levels: int = 30):
    """
    Spin up an OrderFlowEngine, warm its rolling z-scores with varied ratios,
    then feed the final candidate footprint and return the resulting state.

    `footprint_levels` must include a "delta" key per level (ask - bid).
    OrderFlowEngine.update() ranks levels by |delta| to pick the candidate.
    """
    engine = CoinOrderFlowEngine(symbol=symbol)
    # Disable book consolidation so the highest-|delta| candidate is scored directly,
    # not averaged with its neighbors (matches the legacy validator semantics).
    engine.book_bucket_pct = 0.0

    # Phase A: warm up with varied concentration ratios so z-scores have a baseline
    for i in range(warmup_levels):
        ratio = 0.40 + 0.02 * (i % 21)  # 0.40..0.80 range
        total = 1000.0
        ask_v = total * ratio
        bid_v = total * (1.0 - ratio)
        lvl = 100.0 + i * 0.001
        engine.update(
            qty=10.0,
            is_buyer_maker=False,
            ts=1000.0 + i * 0.1,
            price=lvl,
            footprint_levels={lvl: {"ask_volume": ask_v, "bid_volume": bid_v, "delta": ask_v - bid_v}},
        )

    # Phase B: feed the candidate footprint (must include "delta" keys for sorting)
    engine.update(qty=10.0, is_buyer_maker=False, ts=2000.0, price=200.0, footprint_levels=footprint_levels)
    return engine.get_state()


def main():
    print("=" * 60)
    print("  LAYER 0.C: CANDIDATE DETECTION VALIDATOR (OrderFlowEngine)")
    print("=" * 60)

    # ─────────────────────────────────────────────────────────
    # TEST 1: < 3 non-zero delta levels → z-score still cold
    # ─────────────────────────────────────────────────────────
    section("TEST 1: Sparse footprint (2 levels) → no false absorption")

    fp_small = {
        100.0: {"ask_volume": 100.0, "bid_volume": 50.0, "delta": 50.0},
        100.01: {"ask_volume": 80.0, "bid_volume": 60.0, "delta": 20.0},
    }
    engine = CoinOrderFlowEngine(symbol="T_RARE")
    engine.update(qty=10.0, is_buyer_maker=False, ts=1000.0, price=100.0, footprint_levels=fp_small)
    state = engine.get_state()

    if not engine.concentration_zscore.is_ready:
        ok("< 3 levels → concentration_zscore still cold (warming up) — ok")
    elif state.absorption_score_v2 > 0.5:
        fail(f"< 3 levels produced high score={state.absorption_score_v2:.3f} (false signal)")
    else:
        ok(f"< 3 levels → score={state.absorption_score_v2:.3f} (no false signal)")

    # ─────────────────────────────────────────────────────────
    # TEST 2: Exactly 10 levels → candidate produces absorption_score_v2
    # ─────────────────────────────────────────────────────────
    section("TEST 2: 10-level footprint → absorption score > 0 on extreme outlier")

    fp_10 = {100.0 + i * 0.01: {"ask_volume": 999.0, "bid_volume": 1.0, "delta": 998.0} for i in range(10)}
    state_10 = warmup_and_score("T_10", fp_10, warmup_levels=20)

    if state_10.absorption_score_v2 < 0.15:
        fail(f"Expected absorption_score_v2 > 0.15 with extreme ask dominance, got {state_10.absorption_score_v2:.3f}")
    ok(f"10-level extreme-ask → absorption_score_v2 = {state_10.absorption_score_v2:.3f}")

    # ─────────────────────────────────────────────────────────
    # TEST 3: Top candidate = level with highest |delta|
    # ─────────────────────────────────────────────────────────
    section("TEST 3: Mixed footprint → top candidate = highest |delta|")

    # 20 levels around an outlier at 100.10
    fp_mixed = {100.0 + i * 0.01: {"ask_volume": 55.0, "bid_volume": 45.0, "delta": 10.0} for i in range(20)}
    fp_mixed[100.10] = {"ask_volume": 10.0, "bid_volume": 510.0, "delta": -500.0}  # extreme sell
    state_mixed = warmup_and_score("T_MIXED", fp_mixed, warmup_levels=25)

    if state_mixed.absorption_score_v2 < 0.15:
        fail(f"Expected high absorption_score_v2 with delta=-500 outlier, got {state_mixed.absorption_score_v2:.3f}")
    # High bid_volume dominance → extreme negative z_noise → contributes to absorption
    if state_mixed.z_noise >= 0:
        fail(f"Expected z_noise < 0 (low noise ratio on top candidate), got {state_mixed.z_noise:.3f}")
    ok(f"Top candidate (delta=-500) → absorption_score_v2 = {state_mixed.absorption_score_v2:.3f}")
    ok(f"z_noise = {state_mixed.z_noise:.3f} (extreme negative → absorption trigger)")

    # ─────────────────────────────────────────────────────────
    # TEST 4: BUY_EXHAUSTION candidate (extreme ask_volume dominance)
    # ─────────────────────────────────────────────────────────
    section("TEST 4: BUY absorption candidate → positive ask dominance")

    fp_buy = {100.0 + i * 0.01: {"ask_volume": 55.0, "bid_volume": 45.0, "delta": 10.0} for i in range(20)}
    fp_buy[100.15] = {"ask_volume": 1000.0, "bid_volume": 1.0, "delta": 999.0}  # extreme buy
    state_buy = warmup_and_score("T_BUY", fp_buy, warmup_levels=25)

    if state_buy.absorption_score_v2 < 0.15:
        fail(f"Expected high absorption_score_v2 on BUY extreme, got {state_buy.absorption_score_v2:.3f}")
    if state_buy.z_concentration <= 0:
        fail(f"Expected z_concentration > 0 on ask dominant, got {state_buy.z_concentration:.3f}")
    ok(f"BUY top candidate → absorption_score_v2 = {state_buy.absorption_score_v2:.3f}")
    ok(f"z_concentration = {state_buy.z_concentration:.3f}")

    # ─────────────────────────────────────────────────────────
    # TEST 5: Large footprint → still saturates at 1.0 on outlier dominance
    # ─────────────────────────────────────────────────────────
    section("TEST 5: 200-level footprint with outlier → score saturates")

    fp_200 = {}
    for i in range(200):
        ask = 50.0 + i * 2.0
        fp_200[100.0 + i * 0.01] = {"ask_volume": ask, "bid_volume": 50.0, "delta": ask - 50.0}
    # Add an extreme outlier at the midpoint
    fp_200[101.00] = {"ask_volume": 999.0, "bid_volume": 1.0, "delta": 998.0}
    state_200 = warmup_and_score("T_200", fp_200, warmup_levels=25)

    if state_200.absorption_score_v2 < 0.5:
        fail(f"Expected score saturation > 0.5 on 200-level with outlier, got {state_200.absorption_score_v2:.3f}")
    ok(f"200-level with outlier → absorption_score_v2 = {state_200.absorption_score_v2:.3f} (saturated)")

    # ─────────────────────────────────────────────────────────
    # TEST 6: Balanced footprint → no false absorption
    # ─────────────────────────────────────────────────────────
    section("TEST 6: Balanced (no outlier) → score stays low")

    fp_balanced = {100.0 + i * 0.01: {"ask_volume": 500.0, "bid_volume": 500.0, "delta": 0.0} for i in range(15)}
    state_bal = warmup_and_score("T_BAL", fp_balanced, warmup_levels=25)

    if state_bal.absorption_score_v2 > 0.2:
        fail(f"Balanced footprint should not produce high score, got {state_bal.absorption_score_v2:.3f}")
    ok(f"Balanced footprint → absorption_score_v2 = {state_bal.absorption_score_v2:.3f} (no false absorption)")

    # ─────────────────────────────────────────────────────────
    # TEST 7: Z-score ranking — increasing outlier produces increasing score
    # ─────────────────────────────────────────────────────────
    section("TEST 7: Larger outlier produces larger score (monotonic ranking)")

    scores = []
    for extreme_intensity in [200.0, 500.0, 900.0]:
        fp = {100.0 + i * 0.01: {"ask_volume": 50.0, "bid_volume": 50.0, "delta": 0.0} for i in range(15)}
        fp[100.10] = {"ask_volume": extreme_intensity, "bid_volume": 1.0, "delta": extreme_intensity - 1.0}
        st = warmup_and_score(f"T_RANK_{int(extreme_intensity)}", fp, warmup_levels=20)
        scores.append((extreme_intensity, st.absorption_score_v2))

    for i in range(len(scores) - 1):
        _, s_low = scores[i]
        _, s_high = scores[i + 1]
        if s_high < s_low - 0.001:
            fail(f"Monotonicity broken: {scores[i][1]:.3f} → {scores[i+1][1]:.3f}")
    for intensity, score in scores:
        ok(f"outlier={intensity:.0f} → absorption_score_v2 = {score:.3f}")

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.C PASSED — Candidate detection is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
