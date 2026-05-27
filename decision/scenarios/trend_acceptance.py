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

import logging
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("AMTScenarios.TrendAcceptance")


class TrendAcceptanceDetector:
    def __init__(self) -> None:
        self.name = "TrendAcceptance"
        # Track confirmed breakouts: {symbol: {side, level, break_ts, candles_outside, cvd_at_break}}
        self.active_breakouts: Dict[str, dict] = {}
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 60.0  # Longer cooldown

        # Candle counters for tracking
        self._candle_count_outside: Dict[str, int] = defaultdict(int)
        self._candle_count_inside: Dict[str, int] = defaultdict(int)  # For tolerant invalidation
        self._last_candle_ts: Dict[str, float] = defaultdict(float)

        # Configuration
        self.min_candles_outside = 3  # Must stay outside VA for 3+ candles
        self.min_invalidation_candles = 2  # Must be inside VA for 2+ candles to invalidate
        self.pullback_tolerance_pct = 0.001  # 0.1% — pullback must come within this of the level
        self.max_pullback_penetration_pct = 0.001  # Can't re-enter VA by more than 0.1%
        self.cvd_confirmation_threshold = 5.0  # CVD slope must be > this to confirm

    def on_candle(
        self, symbol: str, close: float, timestamp: float, context_registry: Any, footprint_registry: Any
    ) -> None:
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
            self._candle_count_inside[symbol] = 0
            self._candle_count_outside[symbol] = self._candle_count_outside.get(symbol, 0) + 1

            # After 3 candles outside, check for confirmed breakout
            if self._candle_count_outside[symbol] >= self.min_candles_outside:
                if symbol not in self.active_breakouts:
                    # Check CVD confirmation (must be positive for above, negative for below)
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
            # Price returned to VA
            self._candle_count_outside[symbol] = 0
            self._candle_count_inside[symbol] = self._candle_count_inside.get(symbol, 0) + 1

            # Only invalidate if it stays inside for 2+ consecutive candles
            if self._candle_count_inside[symbol] >= self.min_invalidation_candles:
                if symbol in self.active_breakouts:
                    logger.info(
                        f"🚫 [TREND_ACCEPTANCE] {symbol} breakout invalidated — "
                        f"price returned to VA for {self.min_invalidation_candles} candles"
                    )
                    del self.active_breakouts[symbol]

    def on_tick(
        self, symbol: str, price: float, timestamp: float, context_registry: Any, footprint_registry: Any
    ) -> Optional[Dict[str, Any]]:
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
