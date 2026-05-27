"""
Scenario ②: Failed Breakout — "Ruptura + Delta Divergente"

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
    def __init__(self) -> None:
        self.name = "FailedBreakout"
        # Track breakout events per symbol: {symbol: {side, level, break_ts, cvd_at_break, price_at_break}}
        self.pending_breaks: Dict[str, dict] = {}
        # Cooldown per symbol to prevent rapid re-fire
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 60.0  # 60s cooldown between signals (raised from 30s after Phase B audit)

        # Configuration
        self.max_break_age = 60.0  # Break must return within 60s
        self.min_break_distance_pct = 0.0003  # Price must cross level by at least 0.03%
        self.cvd_divergence_threshold = 0.3  # CVD move must be < 30% of what a confirming break would show

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_registry: Any, footprint_registry: Any
    ) -> Optional[Dict[str, Any]]:
        """Evaluate on each tick. Returns signal dict if pattern completes."""
        if not context_registry:
            return None

        poc, vah, val = context_registry.get_structural(symbol)
        if poc <= 0 or vah <= val:
            return None

        # Cooldown check
        if timestamp - self.last_fire_ts[symbol] < self.cooldown:
            return None

        footprint = footprint_registry.get_footprint(symbol)
        current_cvd = footprint.cvd if footprint else 0.0

        # === PHASE 1: Detect new breakouts ===
        pending = self.pending_breaks.get(symbol)

        if not pending:
            # Check if price is breaking VAH (potential SHORT setup)
            if price > vah * (1 + self.min_break_distance_pct):
                self.pending_breaks[symbol] = {
                    "direction": "ABOVE",  # Broke above VAH
                    "side": "SHORT",  # Trade direction if it fails
                    "level": vah,
                    "break_ts": timestamp,
                    "cvd_at_break": current_cvd,
                    "price_at_break": price,
                }
                return None

            # Check if price is breaking VAL (potential LONG setup)
            if price < val * (1 - self.min_break_distance_pct):
                self.pending_breaks[symbol] = {
                    "direction": "BELOW",  # Broke below VAL
                    "side": "LONG",  # Trade direction if it fails
                    "level": val,
                    "break_ts": timestamp,
                    "cvd_at_break": current_cvd,
                    "price_at_break": price,
                }
                return None

            return None

        # === PHASE 2: Monitor pending breakout for failure ===
        elapsed = timestamp - pending["break_ts"]

        # Expired — breakout held too long, it's probably real
        if elapsed > self.max_break_age:
            del self.pending_breaks[symbol]
            return None

        # Check for re-entry into VA (breakout failed)
        level = pending["level"]
        direction = pending["direction"]

        re_entered = False
        if direction == "ABOVE" and price < level:
            re_entered = True
        elif direction == "BELOW" and price > level:
            re_entered = True

        if not re_entered:
            return None

        # === PHASE 3: Confirm delta divergence & Exhaustion Gate ===
        cvd_change = current_cvd - pending["cvd_at_break"]

        # Step 1.2 Fix (AMT V10): Compare CVD change against expected change (slope * elapsed)
        baseline_slope = abs(footprint.get_cvd_slope(window_seconds=10)) if footprint else 0.0
        expected_change = baseline_slope * elapsed
        expected_change = max(expected_change, 5.0)  # Minimum expected change for significance

        # Exhaustion Gate (Phase B Audit Point 6):
        # If CVD change is TOO strong in the direction of the break, don't fade it.
        # This is the "Intensification" check.
        if direction == "ABOVE" and cvd_change > expected_change * 1.8:
            # Delta is intensifying - this is likely Trend Acceptance, not a failed break.
            del self.pending_breaks[symbol]
            return None
        if direction == "BELOW" and cvd_change < -expected_change * 1.8:
            del self.pending_breaks[symbol]
            return None

        if direction == "ABOVE":
            # Break above VAH: confirming = CVD positive & significant
            is_divergent = cvd_change <= 0 or abs(cvd_change) < expected_change * self.cvd_divergence_threshold
        else:
            # Break below VAL: confirming = CVD negative & significant
            is_divergent = cvd_change >= 0 or abs(cvd_change) < expected_change * self.cvd_divergence_threshold

        if not is_divergent:
            # Delta confirmed the break — it was real, don't fade it
            del self.pending_breaks[symbol]
            return None

        # === CONFIRMED: Failed Breakout ===
        side = pending["side"]
        self.last_fire_ts[symbol] = timestamp
        del self.pending_breaks[symbol]

        logger.info(
            f"🔄 [FAILED_BREAKOUT] {symbol} {side} | "
            f"Broke {direction} {level:.2f}, returned at {price:.2f} "
            f"(CVD divergent: Δ={cvd_change:.1f}, elapsed={elapsed:.1f}s)"
        )

        return {
            "symbol": symbol,
            "side": side,
            "price": price,
            "timestamp": timestamp,
            "scenario": "failed_breakout",
            "tactical_type": "FailedBreakout",
            "level": level,
            "direction": pending["direction"],
            "cvd_change": cvd_change,
            "elapsed_s": elapsed,
        }
