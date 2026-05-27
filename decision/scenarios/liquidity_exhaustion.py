"""
Scenario ③: Liquidity Exhaustion — "Multiple Tests with Declining Delta"

AMT Narrative:
    A structural level is tested repeatedly. Each test has LESS aggressive
    flow than the previous one. The attacking side is running out of
    ammunition. The level will likely hold.

Entry conditions:
    1. >=3 touches of the same level (±0.05% tolerance) in last 120s
    2. Delta at each successive test is DECLINING (|delta_n| < |delta_n-1|)
    3. Price bounced from the level (not consolidating AT the level)

Signal: After 2nd+ test with declining delta + bounce
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("AMTScenarios.LiquidityExhaustion")


class LiquidityExhaustionDetector:
    def __init__(self) -> None:
        self.name = "LiquidityExhaustion"
        # Track level tests: {symbol: {level_key: [test1, test2, ...]}}
        # Each test: {ts, delta, price, cvd}
        self.level_tests: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 30.0

        # Configuration
        self.level_tolerance_pct = 0.0005  # 0.05% tolerance for "same level"
        self.test_memory_seconds = 120.0  # How long to remember tests
        self.min_tests = 3  # Minimum tests to trigger (raised from 2 after Phase B audit)
        self.declining_threshold = 0.7  # Each test must have < 70% of previous delta
        self.min_bounce_pct = 0.0003  # 0.03% bounce from level to confirm rejection

        # Track if we're currently at a level vs bounced away
        self._at_level: Dict[str, Optional[str]] = {}  # symbol -> level_key or None
        self._last_test_ts: Dict[str, float] = defaultdict(float)

    def _level_key(self, price: float) -> str:
        """Quantize price to create a level key (0.05% buckets)."""
        bucket = round(price / (price * self.level_tolerance_pct))
        return str(bucket)

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_registry: Any, footprint_registry: Any
    ) -> Optional[Dict[str, Any]]:
        """Evaluate on each tick."""
        if not context_registry:
            return None

        poc, vah, val = context_registry.get_structural(symbol)
        if poc <= 0:
            return None

        if timestamp - self.last_fire_ts[symbol] < self.cooldown:
            return None

        footprint = footprint_registry.get_footprint(symbol)
        if not footprint:
            return None

        # Check structural levels for tests: POC, VAH, VAL
        structural_levels = []
        if val > 0:
            structural_levels.append(("VAL", val, "LONG"))  # Tests of VAL → LONG signal
        if vah > 0:
            structural_levels.append(("VAH", vah, "SHORT"))  # Tests of VAH → SHORT signal

        for level_name, level_price, signal_side in structural_levels:
            tolerance = level_price * self.level_tolerance_pct
            at_level = abs(price - level_price) <= tolerance

            level_key = f"{level_name}_{int(level_price * 100)}"
            tests = self.level_tests[symbol][level_key]

            # Prune old tests
            cutoff = timestamp - self.test_memory_seconds
            self.level_tests[symbol][level_key] = [t for t in tests if t["ts"] > cutoff]
            tests = self.level_tests[symbol][level_key]

            if at_level:
                # We're at the level — record test if enough time since last
                if timestamp - self._last_test_ts.get(f"{symbol}_{level_key}", 0) > 5.0:
                    # Step 1.1 Fix (AMT V10): Use CVD slope as proxy for instant delta (non-accumulated)
                    # get_delta_at_level(price) was returning cumulative session delta.
                    cvd_slope = footprint.get_cvd_slope(window_seconds=3)
                    current_delta = abs(cvd_slope)

                    tests.append(
                        {
                            "ts": timestamp,
                            "delta": current_delta,
                            "cvd_slope": cvd_slope,
                            "price": price,
                        }
                    )
                    self._last_test_ts[f"{symbol}_{level_key}"] = timestamp
                    self._at_level[symbol] = level_key

            elif self._at_level.get(symbol) == level_key:
                # We just bounced away from the level
                bounce_pct = abs(price - level_price) / level_price
                if bounce_pct >= self.min_bounce_pct and len(tests) >= self.min_tests:
                    # Check if delta is declining across tests
                    is_declining = True
                    for i in range(1, len(tests)):
                        # Step 1.1 Fix: Stricter declining check using the non-accumulated delta
                        if tests[i]["delta"] >= tests[i - 1]["delta"] * self.declining_threshold:
                            is_declining = False
                            break

                    if is_declining:
                        # CONFIRMED: Liquidity Exhaustion
                        self.last_fire_ts[symbol] = timestamp
                        self._at_level[symbol] = None
                        # Clear tests for this level
                        self.level_tests[symbol][level_key] = []

                        deltas_str = [f"{t['delta']:.0f}" for t in tests]
                        logger.info(
                            f"⚡ [LIQUIDITY_EXHAUSTION] {symbol} {signal_side} | "
                            f"{len(tests)} tests at {level_name}={level_price:.2f}, "
                            f"delta declining: {deltas_str}"
                        )

                        return {
                            "symbol": symbol,
                            "side": signal_side,
                            "price": price,
                            "timestamp": timestamp,
                            "scenario": "liquidity_exhaustion",
                            "tactical_type": "LiquidityExhaustion",
                            "level": level_price,
                            "level_name": level_name,
                            "n_tests": len(tests),
                            "deltas": [t["delta"] for t in tests],
                        }

                self._at_level[symbol] = None

        return None
