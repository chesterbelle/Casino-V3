"""
AMT Scenario Detectors — Phase B (Absorption AMT Branch).

Three additional scenario-based triggers that complement the AbsorptionDetector.
Each scenario is a complete AMT narrative with structural context, flow confirmation,
and specific entry conditions.

Architecture:
    These detectors run inside the SetupEngine (main process) and have full access
    to ContextRegistry + FootprintRegistry. They evaluate on each tick and fire
    signals directly through the SetupEngine dispatch pipeline.

Scenarios:
    ② FailedBreakoutDetector: VA break + delta divergence + re-entry
    ③ LiquidityExhaustionDetector: Multiple level tests with declining delta
    ④ TrendAcceptanceDetector: VA breakout + confirming delta + pullback

Integration:
    SetupEngine.on_tick() calls each detector's .on_tick() method.
    If a scenario fires, it returns a signal dict that SetupEngine processes
    through the normal target calculation and dispatch pipeline.
"""

import logging
from collections import defaultdict
from typing import Dict, Optional

logger = logging.getLogger("AMTScenarios")


class FailedBreakoutDetector:
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

    def __init__(self):
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
        self, symbol: str, price: float, timestamp: float, context_registry, footprint_registry
    ) -> Optional[dict]:
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

        # === PHASE 3: Confirm delta divergence ===
        cvd_change = current_cvd - pending["cvd_at_break"]

        # For break ABOVE VAH: confirming CVD would be positive (buyers aggressive)
        # Divergent = CVD flat or negative (no real buying conviction)
        if direction == "ABOVE":
            # Normalise: a confirming break would show CVD increase
            # Divergent = CVD didn't increase much, or went negative
            is_divergent = (
                cvd_change < 0 or abs(cvd_change) < abs(pending["cvd_at_break"]) * self.cvd_divergence_threshold
            )
        else:
            # For break BELOW VAL: confirming CVD would be negative (sellers aggressive)
            # Divergent = CVD didn't decrease much, or went positive
            is_divergent = (
                cvd_change > 0 or abs(cvd_change) < abs(pending["cvd_at_break"]) * self.cvd_divergence_threshold
            )

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


class LiquidityExhaustionDetector:
    """
    Scenario ③: Liquidity Exhaustion — "Multiple Tests with Declining Delta"

    AMT Narrative:
        A structural level is tested repeatedly. Each test has LESS aggressive
        flow than the previous one. The attacking side is running out of
        ammunition. The level will likely hold.

    Entry conditions:
        1. ≥2 touches of the same level (±0.05% tolerance) in last 120s
        2. Delta at each successive test is DECLINING (|delta_n| < |delta_n-1|)
        3. Price bounced from the level (not consolidating AT the level)

    Signal: After 2nd+ test with declining delta + bounce
    """

    def __init__(self):
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
        self, symbol: str, price: float, timestamp: float, context_registry, footprint_registry
    ) -> Optional[dict]:
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
                    # Get current delta at this level
                    current_delta = abs(footprint.get_delta_at_level(price))
                    cvd_slope = footprint.get_cvd_slope(window_seconds=2)

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
                        if tests[i]["delta"] > tests[i - 1]["delta"] * self.declining_threshold:
                            if tests[i]["delta"] > tests[i - 1]["delta"]:
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


class TrendAcceptanceDetector:
    """
    Scenario ④: Trend Acceptance — "VA Breakout + Confirming Delta + Pullback"

    AMT Narrative:
        Price leaves the VA with strong delta confirmation. The market is
        genuinely accepting new prices. The entry is on the pullback to
        the broken level (now acting as support/resistance).

    Entry conditions:
        1. Price was outside VA for ≥3 consecutive candles
        2. CVD during breakout CONFIRMED the direction
        3. Price pulled back toward the broken level (VAH or VAL)
           without fully re-entering the VA

    Signal: At the pullback to the broken level
    """

    def __init__(self):
        self.name = "TrendAcceptance"
        # Track confirmed breakouts: {symbol: {side, level, break_ts, candles_outside, cvd_at_break}}
        self.active_breakouts: Dict[str, dict] = {}
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 60.0  # Longer cooldown — trend trades are less frequent (Phase B: needs calibration)

        # Candle counter for "outside VA" tracking
        self._candle_count_outside: Dict[str, int] = defaultdict(int)
        self._last_candle_ts: Dict[str, float] = defaultdict(float)

        # Configuration
        self.min_candles_outside = 3  # Must stay outside VA for 3+ candles
        self.pullback_tolerance_pct = 0.001  # 0.1% — pullback must come within this of the level
        self.max_pullback_penetration_pct = 0.001  # Can't re-enter VA by more than 0.1%
        self.cvd_confirmation_threshold = 5.0  # CVD slope must be > this to confirm

    def on_candle(self, symbol: str, close: float, timestamp: float, context_registry, footprint_registry):
        """Called on each 1m candle close to track candles outside VA."""
        if not context_registry:
            return

        poc, vah, val = context_registry.get_structural(symbol)
        if poc <= 0 or vah <= val:
            return

        footprint = footprint_registry.get_footprint(symbol)
        cvd_slope = footprint.get_cvd_slope(window_seconds=5) if footprint else 0.0

        # Check if price is outside VA
        is_above = close > vah
        is_below = close < val
        is_outside = is_above or is_below

        if is_outside:
            self._candle_count_outside[symbol] = self._candle_count_outside.get(symbol, 0) + 1

            # After 3 candles outside, check for confirmed breakout
            if self._candle_count_outside[symbol] >= self.min_candles_outside:
                if symbol not in self.active_breakouts:
                    # Check CVD confirmation
                    if is_above and cvd_slope > self.cvd_confirmation_threshold:
                        self.active_breakouts[symbol] = {
                            "side": "LONG",  # Trend is UP, pullback entry is LONG
                            "level": vah,
                            "break_ts": timestamp,
                            "cvd_slope": cvd_slope,
                        }
                        logger.info(
                            f"📈 [TREND_ACCEPTANCE] {symbol} breakout ABOVE VAH={vah:.2f} confirmed "
                            f"({self._candle_count_outside[symbol]} candles, CVD slope={cvd_slope:.1f})"
                        )
                    elif is_below and cvd_slope < -self.cvd_confirmation_threshold:
                        self.active_breakouts[symbol] = {
                            "side": "SHORT",  # Trend is DOWN, pullback entry is SHORT
                            "level": val,
                            "break_ts": timestamp,
                            "cvd_slope": cvd_slope,
                        }
                        logger.info(
                            f"📉 [TREND_ACCEPTANCE] {symbol} breakout BELOW VAL={val:.2f} confirmed "
                            f"({self._candle_count_outside[symbol]} candles, CVD slope={cvd_slope:.1f})"
                        )
        else:
            # Price returned to VA — reset
            self._candle_count_outside[symbol] = 0
            if symbol in self.active_breakouts:
                logger.debug(f"[TREND_ACCEPTANCE] {symbol} breakout invalidated — price returned to VA")
                del self.active_breakouts[symbol]

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_registry, footprint_registry
    ) -> Optional[dict]:
        """Check for pullback to broken level on each tick."""
        if symbol not in self.active_breakouts:
            return None

        if timestamp - self.last_fire_ts[symbol] < self.cooldown:
            return None

        breakout = self.active_breakouts[symbol]
        level = breakout["level"]
        side = breakout["side"]

        # Check if price has pulled back to the broken level
        distance_pct = abs(price - level) / level

        if distance_pct <= self.pullback_tolerance_pct:
            # Price is at the broken level — check it hasn't re-entered VA
            poc, vah, val = context_registry.get_structural(symbol)
            if poc <= 0:
                return None

            # For LONG (broke above VAH): price should be at or slightly above VAH
            # For SHORT (broke below VAL): price should be at or slightly below VAL
            if side == "LONG" and price < vah - (vah * self.max_pullback_penetration_pct):
                # Price re-entered VA too deep — invalidate
                del self.active_breakouts[symbol]
                return None
            if side == "SHORT" and price > val + (val * self.max_pullback_penetration_pct):
                del self.active_breakouts[symbol]
                return None

            # CONFIRMED: Trend Acceptance pullback entry
            self.last_fire_ts[symbol] = timestamp
            elapsed = timestamp - breakout["break_ts"]
            del self.active_breakouts[symbol]

            logger.info(
                f"🎯 [TREND_ACCEPTANCE] {symbol} {side} pullback entry at {price:.2f} "
                f"(level={level:.2f}, elapsed={elapsed:.0f}s)"
            )

            return {
                "symbol": symbol,
                "side": side,
                "price": price,
                "timestamp": timestamp,
                "scenario": "trend_acceptance",
                "tactical_type": "TrendAcceptance",
                "level": level,
                "cvd_slope_at_break": breakout["cvd_slope"],
                "elapsed_since_break": elapsed,
            }

        return None
