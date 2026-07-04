"""
Scenario 3: Liquidity Exhaustion -- "Multiple Tests with Declining Delta"

AMT Narrative:
    A structural level is tested repeatedly. Each test has LESS aggressive
    flow than the previous one. The attacking side is running out of
    ammunition. The level will likely hold.

Entry conditions:
    1. >=min_tests touches of the same level (tolerance_pct) in test_memory_seconds
    2. Delta at each successive test is DECLINING (|delta_n| < |delta_n-1|)
    3. Price bounced from the level (not consolidating AT the level)

Signal: After min_tests+ test with declining delta
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AMTScenarios.LiquidityExhaustion")


class LiquidityExhaustionDetector:
    def __init__(self, pressure_engine, params=None) -> None:
        self.name = "LiquidityExhaustion"
        self.pressure = pressure_engine
        self.level_tests: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self._cluster_cache: Dict[str, dict] = {}
        self._max_bounce: Dict[str, float] = defaultdict(float)

        # Fallback defaults
        self.cooldown = 30.0
        self.level_tolerance_pct = 0.0005
        self.test_memory_seconds = 120.0
        self.min_tests = 3
        self.declining_threshold = 0.7
        self.min_bounce_pct = 0.0003

    def reset_for_symbol(self, symbol: str) -> None:
        """Clear per-symbol state at daily boundary."""
        self.level_tests.pop(symbol, None)
        self.last_fire_ts.pop(symbol, None)
        self._cluster_cache.pop(symbol, None)
        stale_bounce = [k for k in list(self._max_bounce) if k.startswith(f"{symbol}_")]
        for k in stale_bounce:
            del self._max_bounce[k]

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.param_validation import validate_params
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "liquidity_exhaustion")
            params = validate_params(params or {}, "liquidity_exhaustion")
        except ImportError:
            params = {}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Error loading params for %s: %s", symbol, e)
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def cleanup(self, symbol: str, now_ts: float, max_age: float = 3600.0) -> None:
        """Remove stale test data for a symbol."""
        if symbol in self.level_tests:
            # Remove test entries older than max_age
            stale_keys = []
            for level_key, tests in self.level_tests[symbol].items():
                tests = [t for t in tests if now_ts - t["ts"] <= max_age]
                if tests:
                    self.level_tests[symbol][level_key] = tests
                else:
                    stale_keys.append(level_key)
            for key in stale_keys:
                del self.level_tests[symbol][key]
            if not self.level_tests[symbol]:
                del self.level_tests[symbol]
        # Clean up old last_fire_ts entries
        if symbol in self.last_fire_ts:
            if now_ts - self.last_fire_ts[symbol] > max_age:
                del self.last_fire_ts[symbol]
        # Clean up stale bounce trackers for this symbol
        stale_bounce = [k for k in self._max_bounce if k.startswith(f"{symbol}_")]
        for k in stale_bounce:
            del self._max_bounce[k]

    def _prune_old_tests(self, tests: List[dict], now_ts: float, test_memory_seconds: float) -> List[dict]:
        cutoff = now_ts - test_memory_seconds
        pruned = [t for t in tests if t["ts"] >= cutoff]
        return pruned

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if price <= 0:
            return None

        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        level_tolerance_pct = params.get("level_tolerance_pct", self.level_tolerance_pct)
        test_memory_seconds = params.get("test_memory_seconds", self.test_memory_seconds)
        min_tests = params.get("min_tests", self.min_tests)
        declining_threshold = params.get("declining_threshold", self.declining_threshold)
        min_bounce_pct = params.get("min_bounce_pct", self.min_bounce_pct)

        if timestamp - self.last_fire_ts[symbol] < cooldown:
            return None

        state = self.pressure.get_state(symbol)
        if state is None:
            return None

        raw_cvd_velocity = getattr(state, "cvd_velocity", 0.0)
        # AMT Fix: Use raw flow magnitude for declining aggression test,
        # not z-score. Z-score can decline due to expanding std window,
        # not due to actual exhaustion of attacking flow.
        current_delta = abs(getattr(state, "cvd_delta", 0.0))

        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)

        for level_name, level_price, expected_attack_side in [
            ("VAL", val, "sell"),
            ("VAH", vah, "buy"),
        ]:
            if level_price <= 0:
                continue

            bounce_key = f"{symbol}_{level_name}"

            # Track max bounce distance from level (positive = away from level)
            if level_name == "VAL":
                bounce_distance = price - level_price
            else:
                bounce_distance = level_price - price
            if bounce_distance > self._max_bounce[bounce_key]:
                self._max_bounce[bounce_key] = bounce_distance

            if abs(price - level_price) <= (level_price * level_tolerance_pct):
                # AMT Fix: Accumulate tests per logical border (VAL/VAH),
                # not per exact decimal price. The VA border may shift
                # slightly between snapshots, but AMT treats it as the
                # same structural level being tested.
                level_key = f"{symbol}_{level_name}"
                tests = self.level_tests[symbol][level_key]

                # Fix 1: Bounce guard — skip test if prior tests had no bounce
                if tests and self._max_bounce.get(bounce_key, 0.0) < level_price * min_bounce_pct:
                    continue

                signal_side = "LONG" if level_name == "VAL" else "SHORT"

                tests.append({"ts": timestamp, "delta": current_delta})
                tests = self._prune_old_tests(tests, timestamp, test_memory_seconds)
                self.level_tests[symbol][level_key] = tests

                # Reset bounce tracker after recording a valid test
                self._max_bounce[bounce_key] = 0.0

                if len(tests) >= min_tests:
                    recent = tests[-min_tests:]

                    is_declining = all(
                        recent[i]["delta"] < recent[i - 1]["delta"] * declining_threshold for i in range(1, len(recent))
                    )

                    if is_declining and any(t["delta"] > 0 for t in recent):
                        # CVD confirmation: defense must be in control before entering
                        if level_name == "VAL" and raw_cvd_velocity <= 0:
                            continue  # Buyers not yet defending — sellers still in control
                        if level_name == "VAH" and raw_cvd_velocity >= 0:
                            continue  # Sellers not yet defending — buyers still in control
                        self.last_fire_ts[symbol] = timestamp
                        self.level_tests[symbol][level_key] = []
                        score = max(0.2, min(1.0, abs(raw_cvd_velocity) / 3.0))
                        return {
                            "symbol": symbol,
                            "side": signal_side,
                            "price": price,
                            "timestamp": timestamp,
                            "scenario": "liquidity_exhaustion",
                            "score": score,
                        }
        return None
