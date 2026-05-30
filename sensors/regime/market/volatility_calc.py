import logging
from collections import deque

logger = logging.getLogger("MarketRegimeSensor.Volatility")

# Configuration
CIRCUIT_BREAKER_LOOKBACK = 10  # Candles to measure price displacement
CIRCUIT_BREAKER_TREND_PCT = 0.02  # 2% move in 10 candles = TREND (no Z-score needed)
CIRCUIT_BREAKER_CRASH_PCT = 0.04  # 4% move in 10 candles = TREND_DOWN (crash override)
CIRCUIT_BREAKER_SLOW_LOOKBACK = 60  # 60 candles (1 hour) for slow drift detection
CIRCUIT_BREAKER_DRIFT_PCT = 0.008  # 0.8% drift in 60 candles = slow TREND


class _PriceCircuitBreaker:
    """
    Phase 2300: Absolute Price Movement Detector with Persistence.

    Problem with Z-score based regime detection:
    - Z-scores normalize against recent history
    - In a crash, the crash itself becomes the "normal" baseline
    - Result: sensor declares BALANCE during a 38% crash

    Solution: Measure raw price displacement over N candles.
    No normalization. No Z-scores. Pure price action.

    Persistence: Once triggered, stays active until price returns
    to within RESET_PCT of the reference price. This prevents the
    sensor from oscillating between TREND and BALANCE every candle.

    If price moved >2% in 10 candles → TREND (direction from sign)
    If price moved >4% in 10 candles → TREND with high confidence (crash/rally)
    """

    def __init__(self):
        self.price_history: deque = deque(maxlen=CIRCUIT_BREAKER_LOOKBACK + 2)
        self.price_history_slow: deque = deque(maxlen=CIRCUIT_BREAKER_SLOW_LOOKBACK + 2)
        # Persistence state
        self._active: bool = False
        self._active_direction: str = "NEUTRAL"
        self._active_confidence: float = 0.0
        self._active_reason: str = ""
        self._reference_price: float = 0.0  # Price when CB was triggered
        self._reset_threshold: float = 0.005  # 0.5% return toward balance to reset

    def on_candle(self, close: float, ts: float):
        if close > 0:
            self.price_history.append((ts, close))
            self.price_history_slow.append((ts, close))

    def evaluate(self) -> dict:
        """
        Returns circuit breaker verdict with persistence.

        Once triggered, stays active until price returns within
        reset_threshold of the reference price.
        """
        if len(self.price_history) < CIRCUIT_BREAKER_LOOKBACK:
            return {
                "triggered": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "displacement_pct": 0.0,
                "reason": "insufficient_data",
            }

        oldest_price = self.price_history[0][1]
        current_price = self.price_history[-1][1]

        if oldest_price <= 0:
            return {
                "triggered": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "displacement_pct": 0.0,
                "reason": "invalid_price",
            }

        displacement = (current_price - oldest_price) / oldest_price  # signed
        abs_displacement = abs(displacement)
        direction = "UP" if displacement > 0 else "DOWN"

        # --- Check if we should RESET an active circuit breaker ---
        if self._active and self._reference_price > 0:
            if self._active_direction == "DOWN":
                # For DOWN trend: reset if price recovered >reset_threshold
                recovery = (current_price - self._reference_price) / self._reference_price
                if recovery > self._reset_threshold:
                    self._active = False
                    self._active_direction = "NEUTRAL"
            elif self._active_direction == "UP":
                # For UP trend: reset if price pulled back >reset_threshold
                pullback = (self._reference_price - current_price) / self._reference_price
                if pullback > self._reset_threshold:
                    self._active = False
                    self._active_direction = "NEUTRAL"

        # --- Check if we should TRIGGER ---
        # Crash/rally override: >4% in 10 candles
        if abs_displacement >= CIRCUIT_BREAKER_CRASH_PCT:
            confidence = min(1.0, abs_displacement / (CIRCUIT_BREAKER_CRASH_PCT * 2))
            self._active = True
            self._active_direction = direction
            self._active_confidence = confidence
            self._active_reason = "crash_rally_override"
            self._reference_price = current_price
            return {
                "triggered": True,
                "direction": direction,
                "confidence": round(confidence, 3),
                "displacement_pct": round(displacement * 100, 3),
                "reason": "crash_rally_override",
            }

        # Normal trend: >2% in 10 candles
        if abs_displacement >= CIRCUIT_BREAKER_TREND_PCT:
            confidence = min(0.8, abs_displacement / (CIRCUIT_BREAKER_TREND_PCT * 3))
            self._active = True
            self._active_direction = direction
            self._active_confidence = confidence
            self._active_reason = "trend_override"
            self._reference_price = current_price
            return {
                "triggered": True,
                "direction": direction,
                "confidence": round(confidence, 3),
                "displacement_pct": round(displacement * 100, 3),
                "reason": "trend_override",
            }

        # Slow drift detection: 0.8% in 60 candles (1 hour)
        if len(self.price_history_slow) >= CIRCUIT_BREAKER_SLOW_LOOKBACK:
            oldest_slow = self.price_history_slow[0][1]
            displacement_slow = (current_price - oldest_slow) / oldest_slow
            abs_displacement_slow = abs(displacement_slow)
            direction_slow = "UP" if displacement_slow > 0 else "DOWN"

            if abs_displacement_slow >= CIRCUIT_BREAKER_DRIFT_PCT:
                confidence = min(0.7, abs_displacement_slow / (CIRCUIT_BREAKER_DRIFT_PCT * 3))
                self._active = True
                self._active_direction = direction_slow
                self._active_confidence = confidence
                self._active_reason = "slow_drift_override"
                self._reference_price = current_price
                return {
                    "triggered": True,
                    "direction": direction_slow,
                    "confidence": round(confidence, 3),
                    "displacement_pct": round(displacement_slow * 100, 3),
                    "reason": "slow_drift_override",
                }

        # --- Persistence: if still active, maintain the signal ---
        if self._active:
            return {
                "triggered": True,
                "direction": self._active_direction,
                "confidence": round(self._active_confidence * 0.9, 3),  # Decay slightly
                "displacement_pct": round(displacement * 100, 3),
                "reason": f"{self._active_reason}_persistent",
            }

        return {
            "triggered": False,
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "displacement_pct": round(displacement * 100, 3),
            "reason": "within_balance_range",
        }
