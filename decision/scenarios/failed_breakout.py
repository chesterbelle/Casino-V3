"""
Scenario 2: Failed Breakout — "Breakout + Divergent Delta"

AMT Narrative:
    Price breaks a structural level (VAH or VAL). Looks like a breakout.
    But delta (CVD) does NOT confirm — the break has weak conviction.
    Price returns inside the VA. Breakout traders are trapped.

Entry conditions (all must be true):
    1. Price crossed VAH (for SHORT) or VAL (for LONG) within the last 60s
    2. CVD during the break did NOT confirm direction (divergent)
    3. Price returned inside the VA (crossed back through the broken level)
    4. Return was fast (< 60s from break)

Signal: Entry at the moment of re-entry into VA
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("AMTScenarios.FailedBreakout")


class FailedBreakoutDetector:
    def __init__(self, pressure_engine=None, params=None) -> None:
        self.name = "FailedBreakout"
        self.pressure = pressure_engine
        self.pending_breaks = {}
        self.last_fire_ts = defaultdict(float)
        self._cluster_cache: Dict[str, dict] = {}

        # Fallback defaults
        self.cooldown = 60.0
        self.max_break_age = 60.0
        self.min_break_distance_pct = 0.0003
        self.cvd_divergence_threshold = 0.3

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "failed_breakout")
        except Exception:
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_or_levels, footprint=None
    ) -> Optional[Dict[str, Any]]:
        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        max_break_age = params.get("max_break_age", self.max_break_age)
        min_break_distance_pct = params.get("min_break_distance_pct", self.min_break_distance_pct)
        cvd_divergence_threshold = params.get("cvd_divergence_threshold", self.cvd_divergence_threshold)

        if timestamp - self.last_fire_ts[symbol] < cooldown:
            return None

        if hasattr(context_or_levels, "get_pressure_state"):
            state = context_or_levels.get_pressure_state(symbol)
            poc, vah, val = context_or_levels.get_structural(symbol)
        else:
            state = self.pressure.get_state(symbol) if self.pressure else None
            vah = context_or_levels.get("vah", 0.0)
            val = context_or_levels.get("val", 0.0)

        if not state or vah <= val:
            return None

        current_cvd = state.cvd_delta

        # === PHASE 1: Detect new breakouts ===
        pending = self.pending_breaks.get(symbol)
        if not pending:
            if price > vah * (1 + min_break_distance_pct):
                self.pending_breaks[symbol] = {
                    "direction": "ABOVE",
                    "side": "SHORT",
                    "level": vah,
                    "break_ts": timestamp,
                    "cvd_at_break": current_cvd,
                }
            elif price < val * (1 - min_break_distance_pct):
                self.pending_breaks[symbol] = {
                    "direction": "BELOW",
                    "side": "LONG",
                    "level": val,
                    "break_ts": timestamp,
                    "cvd_at_break": current_cvd,
                }
            return None

        # === PHASE 2: Monitor for failure ===
        elapsed = timestamp - pending["break_ts"]
        if elapsed > max_break_age:
            del self.pending_breaks[symbol]
            return None

        level = pending["level"]
        direction = pending["direction"]
        re_entered = (direction == "ABOVE" and price < level) or (direction == "BELOW" and price > level)

        if not re_entered:
            return None

        # === PHASE 3: Confirmation ===
        cvd_change = current_cvd - pending["cvd_at_break"]

        # Usamos la velocidad del motor para validar convicción
        expected_change = abs(state.cvd_velocity * elapsed)
        expected_change = max(expected_change, 5.0)

        # Exhaustion Gate: CVD demasiado fuerte = Trend Acceptance
        exhaustion_mult = params.get("exhaustion_mult", 1.8)

        if (direction == "ABOVE" and cvd_change > expected_change * exhaustion_mult) or (
            direction == "BELOW" and cvd_change < -expected_change * exhaustion_mult
        ):
            del self.pending_breaks[symbol]
            return None

        # Divergencia
        if direction == "ABOVE":
            is_divergent = cvd_change <= 0 or abs(cvd_change) < expected_change * cvd_divergence_threshold
        else:
            is_divergent = cvd_change >= 0 or abs(cvd_change) < expected_change * cvd_divergence_threshold

        if not is_divergent:
            del self.pending_breaks[symbol]
            return None

        # Confirmado
        side = pending["side"]
        self.last_fire_ts[symbol] = timestamp
        del self.pending_breaks[symbol]

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "timestamp": timestamp,
            "scenario": "failed_breakout",
            "level": level,
        }
