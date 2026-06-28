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

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.param_validation import validate_params
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "failed_breakout")
            params = validate_params(params or {}, "failed_breakout")
        except ImportError:
            params = {}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Error loading params for %s: %s", symbol, e)
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def cleanup(self, symbol: str, now_ts: float, max_age: float = 3600.0) -> None:
        """Remove stale state for a symbol if its entry hasn't been updated recently."""
        pending = self.pending_breaks.get(symbol)
        if pending is not None:
            if now_ts - pending["break_ts"] > max_age:
                del self.pending_breaks[symbol]
        # Also clean up last_fire_ts entry if it's too old
        if symbol in self.last_fire_ts:
            if now_ts - self.last_fire_ts[symbol] > max_age:
                del self.last_fire_ts[symbol]

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_or_levels, footprint=None
    ) -> Optional[Dict[str, Any]]:
        if price <= 0:
            return None

        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        max_break_age = params.get("max_break_age", self.max_break_age)
        min_break_distance_pct = params.get("min_break_distance_pct", self.min_break_distance_pct)

        if timestamp - self.last_fire_ts[symbol] < cooldown:
            return None

        if hasattr(context_or_levels, "get_pressure_state"):
            state = context_or_levels.get_pressure_state(symbol)
            poc, vah, val = context_or_levels.get_structural(symbol)
        else:
            state = self.pressure.get_state(symbol) if self.pressure else None
            vah = context_or_levels.get("vah", 0.0)
            val = context_or_levels.get("val", 0.0)

        # Validate that structural levels make sense
        if not state or vah <= 0 or val <= 0 or vah <= val:
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

        # === PHASE 3: Confirmation (z-score normalized) ===
        cvd_change = current_cvd - pending["cvd_at_break"]

        if elapsed > 0:
            avg_velocity = abs(cvd_change) / elapsed
            avg_velocity_z = self.pressure.zscore_velocity(symbol, avg_velocity)
        else:
            avg_velocity_z = 0.0

        # Exhaustion Gate: CVD too strong in breakout direction = Trend Acceptance
        exhaustion_z = params.get("exhaustion_z", 2.0)

        if (direction == "ABOVE" and cvd_change > 0 and avg_velocity_z > exhaustion_z) or (
            direction == "BELOW" and cvd_change < 0 and avg_velocity_z > exhaustion_z
        ):
            del self.pending_breaks[symbol]
            return None

        # Divergencia: CVD opposite or very weak relative to break direction
        divergence_z = params.get("divergence_z", 0.5)

        if direction == "ABOVE":
            is_divergent = cvd_change <= 0 or avg_velocity_z < divergence_z
        else:
            is_divergent = cvd_change >= 0 or avg_velocity_z < divergence_z

        if not is_divergent:
            del self.pending_breaks[symbol]
            return None

        # Confirmado
        side = pending["side"]
        self.last_fire_ts[symbol] = timestamp
        del self.pending_breaks[symbol]

        score = max(0.1, 1.0 - abs(avg_velocity_z) / max(exhaustion_z, 0.01))

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "timestamp": timestamp,
            "scenario": "failed_breakout",
            "level": level,
            "score": score,
        }
