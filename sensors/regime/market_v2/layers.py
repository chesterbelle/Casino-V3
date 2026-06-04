"""
Regime Sensor V2 — Layer Implementations

Layer 1: Price Action (Lead Detector)
  - Detects trend via swing highs/lows
  - Measures momentum via price velocity

Layer 2: Volume Profile (Confirmation)
  - Confirms via POC migration
  - Measures value acceptance via VA position
"""

import logging
from collections import deque

logger = logging.getLogger("RegimeSensorV2.Layers")


class _PriceActionLayer:
    """
    Layer 1: Price Action Lead Detector.

    Detects market regime using only price (high, low, close).
    - Swing detection: Higher Highs / Higher Lows = UP
    - Lower Highs / Lower Lows = DOWN
    - Range compression = BALANCE

    Key insight: Price action is the primary truth. All other indicators
    (POC, VA, CVD) are derived from price. By measuring price structure
    directly, we get the fastest and most reliable regime signal.
    """

    def __init__(self, swing_window: int = 10, momentum_window: int = 5):
        self.swing_window = swing_window
        self.momentum_window = momentum_window

        # Rolling history of highs and lows
        self.highs: deque = deque(maxlen=swing_window + 5)
        self.lows: deque = deque(maxlen=swing_window + 5)
        self.closes: deque = deque(maxlen=swing_window + 5)

        # Swing points: list of (timestamp, price, type)
        self.swing_highs: deque = deque(maxlen=10)
        self.swing_lows: deque = deque(maxlen=10)

    def on_candle(self, high: float, low: float, close: float, ts: float):
        """Update with new candle data."""
        self.highs.append((ts, high))
        self.lows.append((ts, low))
        self.closes.append((ts, close))

        # Detect swing points
        self._detect_swings()

    def _detect_swings(self):
        """Detect swing highs and lows from price history."""
        if len(self.highs) < 5:
            return

        highs = list(self.highs)
        lows = list(self.lows)

        # Check for swing high at position -3 (need 2 bars on each side)
        idx = len(highs) - 3
        if idx >= 2:
            h = highs[idx][1]
            if (
                h > highs[idx - 1][1] and h > highs[idx - 2][1] and h > highs[idx + 1][1]
                if idx + 1 < len(highs)
                else True and h > highs[idx + 2][1] if idx + 2 < len(highs) else True
            ):
                # Avoid duplicates
                if not self.swing_highs or self.swing_highs[-1][1] != h:
                    self.swing_highs.append(highs[idx])

        # Check for swing low at position -3
        if idx >= 2:
            low_val = lows[idx][1]
            if (low_val < lows[idx - 1][1] and low_val < lows[idx - 2][1] and
                    low_val < lows[idx + 1][1] if idx + 1 < len(lows) else True and
                    low_val < lows[idx + 2][1] if idx + 2 < len(lows) else True):
                if not self.swing_lows or self.swing_lows[-1][1] != low_val:
                    self.swing_lows.append(lows[idx])

    def evaluate(self) -> dict:
        """
        Evaluate price action layer.

        Returns:
            {"vote": "UP/DOWN/NEUTRAL", "score": float, "reason": str, "momentum": float}
        """
        if len(self.closes) < self.momentum_window + 1:
            return {
                "vote": "NEUTRAL",
                "score": 0.0,
                "reason": "insufficient_data",
                "momentum": 0.0,
            }

        closes = list(self.closes)

        # 1. Determine trend from swing points
        trend_state = self._classify_trend()

        # 2. Calculate momentum
        momentum = self._calculate_momentum(closes)

        # 3. Calculate score
        has_trend = trend_state in ("UP", "DOWN")
        trend_score = 0.6 if has_trend else 0.0

        # Momentum score: normalized by ATR-like measure
        atr_pct = self._estimate_atr_pct(closes)
        momentum_score = min(0.4, abs(momentum) / (atr_pct * 0.01 + 0.0001) * 0.2) if atr_pct > 0 else 0.0

        total_score = trend_score + momentum_score

        # Determine vote
        if has_trend:
            vote = trend_state
            reason = "higher_highs_lows" if trend_state == "UP" else "lower_highs_lows"
        else:
            vote = "NEUTRAL"
            reason = "range_detected"

        return {
            "vote": vote,
            "score": round(min(1.0, total_score), 3),
            "reason": reason,
            "momentum": round(momentum, 6),
            "trend_state": trend_state,
        }

    def _classify_trend(self) -> str:
        """Classify trend from swing points."""
        if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
            return "BALANCE"

        # Compare last two swing highs and lows
        last_sh = self.swing_highs[-1][1]
        prev_sh = self.swing_highs[-2][1]
        last_sl = self.swing_lows[-1][1]
        prev_sl = self.swing_lows[-2][1]

        higher_high = last_sh > prev_sh
        higher_low = last_sl > prev_sl
        lower_high = last_sh < prev_sh
        lower_low = last_sl < prev_sl

        # Relaxed rules: trend if ANY condition is met (not requiring both)
        # This catches trends earlier, before both HH/HL or LH/LL are confirmed
        if higher_high or higher_low:
            return "UP"
        elif lower_high or lower_low:
            return "DOWN"
        else:
            return "BALANCE"

    def _calculate_momentum(self, closes: list) -> float:
        """Calculate price momentum over the momentum window."""
        if len(closes) < self.momentum_window + 1:
            return 0.0
        current = closes[-1][1]
        past = closes[-(self.momentum_window + 1)][1]
        if past <= 0:
            return 0.0
        return (current - past) / past

    def _estimate_atr_pct(self, closes: list) -> float:
        """Estimate ATR as percentage of price (simple range-based)."""
        if len(closes) < 5:
            return 0.01  # Default 1%
        highs = list(self.highs)[-5:]
        lows = list(self.lows)[-5:]
        ranges = []
        for i in range(len(highs)):
            h = highs[i][1]
            low_val = lows[i][1]
            mid = (h + low_val) / 2
            if mid > 0:
                ranges.append((h - low_val) / mid)
        return sum(ranges) / len(ranges) if ranges else 0.01


class _VolumeProfileLayer:
    """
    Layer 2: Volume Profile Confirmation.

    Confirms regime direction using:
    - POC migration velocity and direction
    - Price position within Value Area
    - VA expansion/contraction

    Key insight: Volume profile tells us where value is accepted.
    When POC migrates in the same direction as price, the trend is real.
    When price is inside VA, value is being accepted (trend continuation).
    """

    def __init__(self, poc_window: int = 10, va_window: int = 10):
        self.poc_window = poc_window
        self.va_window = va_window

        # POC history: (timestamp, poc_price)
        self.poc_history: deque = deque(maxlen=poc_window + 5)

        # VA width history: (timestamp, width_pct)
        self.va_width_history: deque = deque(maxlen=va_window + 5)

        # Latest VA levels
        self._latest_vah: float = 0.0
        self._latest_val: float = 0.0
        self._latest_poc: float = 0.0
        self._latest_close: float = 0.0

    def on_candle(
        self,
        poc: float,
        vah: float,
        val: float,
        close: float,
        volume: float,
        ts: float,
    ):
        """Update with new candle data."""
        if poc <= 0 or vah <= 0 or val <= 0:
            return

        self._latest_poc = poc
        self._latest_vah = vah
        self._latest_val = val
        self._latest_close = close

        # Track POC history
        self.poc_history.append((ts, poc))

        # Track VA width
        va_width_pct = (vah - val) / poc if poc > 0 else 0.0
        self.va_width_history.append((ts, va_width_pct))

    def evaluate(self) -> dict:
        """
        Evaluate volume profile layer.

        Returns:
            {
                "vote": "UP/DOWN/NEUTRAL",
                "score": float,
                "reason": str,
                "value_acceptance": "ACCEPTING/OUT_OF_VALUE/EXCESS",
                "poc_velocity": float,
                "va_expansion_rate": float,
                "absorption_detected": bool,
            }
        """
        if len(self.poc_history) < 3:
            return {
                "vote": "NEUTRAL",
                "score": 0.0,
                "reason": "insufficient_data",
                "value_acceptance": "NEUTRAL",
                "poc_velocity": 0.0,
                "va_expansion_rate": 0.0,
                "absorption_detected": False,
            }

        # 1. POC migration direction and velocity
        poc_vote, poc_velocity = self._evaluate_poc_migration()

        # 2. Value acceptance
        value_acceptance = self._evaluate_value_acceptance()

        # 3. VA expansion
        expansion_rate = self._evaluate_va_expansion()

        # 4. Absorption detection
        absorption = self._detect_absorption()

        # 5. Calculate score
        poc_score = min(0.5, abs(poc_velocity) / 0.001 * 0.3) if abs(poc_velocity) > 0 else 0.0
        position_score = 0.3 if value_acceptance == "IN_VALUE" else 0.15 if value_acceptance == "OUT_OF_VALUE" else 0.0
        expansion_score = 0.2 if expansion_rate > 0.05 else 0.0
        total_score = poc_score + position_score + expansion_score

        # Determine vote (POC is primary signal for this layer)
        vote = poc_vote
        if vote == "NEUTRAL" and expansion_rate > 0.1:
            # VA expanding but POC neutral → ambiguous, use close position
            if self._latest_close > self._latest_poc:
                vote = "UP"
            elif self._latest_close < self._latest_poc:
                vote = "DOWN"

        reason = (
            "poc_migration" if poc_vote != "NEUTRAL" else "va_expanding" if expansion_rate > 0.05 else "value_position"
        )

        return {
            "vote": vote,
            "score": round(min(1.0, total_score), 3),
            "reason": reason,
            "value_acceptance": value_acceptance,
            "poc_velocity": round(poc_velocity, 6),
            "va_expansion_rate": round(expansion_rate, 4),
            "absorption_detected": absorption,
        }

    def _evaluate_poc_migration(self):
        """Evaluate POC migration direction and velocity."""
        if len(self.poc_history) < self.poc_window:
            return "NEUTRAL", 0.0

        poc_list = list(self.poc_history)
        start_poc = poc_list[-self.poc_window][1]
        end_poc = poc_list[-1][1]

        if start_poc <= 0:
            return "NEUTRAL", 0.0

        velocity = (end_poc - start_poc) / start_poc / self.poc_window

        threshold = 0.0001  # 0.01% per candle
        if velocity > threshold:
            return "UP", velocity
        elif velocity < -threshold:
            return "DOWN", velocity
        else:
            return "NEUTRAL", velocity

    def _evaluate_value_acceptance(self) -> str:
        """Evaluate price position within Value Area."""
        if self._latest_vah <= self._latest_val or self._latest_poc <= 0:
            return "NEUTRAL"

        va_width = self._latest_vah - self._latest_val
        excess_threshold = va_width * 0.5  # 50% of VA width beyond VAH/VAL

        if self._latest_close <= self._latest_val:
            if self._latest_close < self._latest_val - excess_threshold:
                return "EXCESS"
            return "OUT_OF_VALUE"
        elif self._latest_close >= self._latest_vah:
            if self._latest_close > self._latest_vah + excess_threshold:
                return "EXCESS"
            return "OUT_OF_VALUE"
        else:
            return "IN_VALUE"

    def _evaluate_va_expansion(self) -> float:
        """Evaluate VA expansion rate (fast vs slow)."""
        if len(self.va_width_history) < 5:
            return 0.0

        widths = list(self.va_width_history)
        fast_avg = sum(w[1] for w in widths[-3:]) / 3
        slow_avg = sum(w[1] for w in widths) / len(widths)

        if slow_avg <= 0:
            return 0.0

        return (fast_avg - slow_avg) / slow_avg

    def _detect_absorption(self) -> bool:
        """Detect absorption (price not moving despite volume)."""
        # Simple heuristic: if VA is contracting but volume is high → absorption
        if len(self.va_width_history) < 5:
            return False

        expansion = self._evaluate_va_expansion()
        return expansion < -0.05  # VA contracting = potential absorption
