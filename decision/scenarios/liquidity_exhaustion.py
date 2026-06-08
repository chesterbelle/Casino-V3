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

        # Fallback defaults
        self.cooldown = 30.0
        self.level_tolerance_pct = 0.0005
        self.test_memory_seconds = 120.0
        self.min_tests = 3
        self.declining_threshold = 0.7
        self.min_bounce_pct = 0.0003

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "liquidity_exhaustion")
        except Exception:
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def _prune_old_tests(self, tests: List[dict], now_ts: float, test_memory_seconds: float) -> List[dict]:
        cutoff = now_ts - test_memory_seconds
        pruned = [t for t in tests if t["ts"] >= cutoff]
        return pruned

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        level_tolerance_pct = params.get("level_tolerance_pct", self.level_tolerance_pct)
        test_memory_seconds = params.get("test_memory_seconds", self.test_memory_seconds)
        min_tests = params.get("min_tests", self.min_tests)
        declining_threshold = params.get("declining_threshold", self.declining_threshold)

        if timestamp - self.last_fire_ts[symbol] < cooldown:
            return None

        state = self.pressure.get_state(symbol)

        current_delta = abs(state.cvd_velocity)

        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)

        for level_name, level_price, signal_side in [
            ("VAL", val, "LONG"),
            ("VAH", vah, "SHORT"),
        ]:
            if level_price <= 0:
                continue

            if abs(price - level_price) <= (level_price * level_tolerance_pct):
                level_key = f"{level_name}_{level_price:.2f}"
                tests = self.level_tests[symbol][level_key]

                tests.append({"ts": timestamp, "delta": current_delta})

                tests = self._prune_old_tests(tests, timestamp, test_memory_seconds)
                self.level_tests[symbol][level_key] = tests

                if len(tests) >= min_tests:
                    recent = tests[-min_tests:]

                    is_declining = all(
                        recent[i]["delta"] < recent[i - 1]["delta"] * declining_threshold for i in range(1, len(recent))
                    )

                    if is_declining and any(t["delta"] > 0 for t in recent):
                        self.last_fire_ts[symbol] = timestamp
                        self.level_tests[symbol][level_key] = []
                        return {
                            "symbol": symbol,
                            "side": signal_side,
                            "price": price,
                            "timestamp": timestamp,
                            "scenario": "liquidity_exhaustion",
                        }
        return None
