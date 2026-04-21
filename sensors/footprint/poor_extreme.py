"""
TacticalPoorExtreme Sensor - LTA V5
Detects session extremes formed with insufficient institutional participation.

Refinements over original proposal:
- Uses historical percentiles vs fixed averages
- Includes spread confirmation for lack of liquidity
- Adaptive time threshold by volatility regime
"""

import time
from collections import deque
from typing import Any, Dict, Optional

import numpy as np

from sensors.base import SensorV3


class TacticalPoorExtreme(SensorV3):
    """
    Detects Poor High/Low extremes - session extremes with abnormally low volume
    indicating lack of institutional acceptance at that level.

    When a VAH/VAL coincides with a Poor Extreme, it's double confirmation
    of structural weakness and high probability of reversion.

    Logic:
    1. Identify new session high/low
    2. Check if volume is in bottom 25th percentile of historical extremes
    3. Confirm with spread > 1.5x average (illiquidity signal)
    4. Verify rapid formation (< volatility-adjusted threshold)
    """

    def __init__(self):
        super().__init__()
        self.timeframe = "1m"

        # Historical tracking for percentile calculation
        self.extreme_history = deque(maxlen=100)  # Last 100 extremes
        self.spread_history = deque(maxlen=300)  # 5 hours of 1m candles

        # Session tracking
        self.session_high = 0.0
        self.session_low = float("inf")
        self.session_start_ts = 0.0
        self.last_extreme_ts = 0.0
        self.candles_since_extreme = 0

        # ATR for volatility adjustment
        self.atr_history = deque(maxlen=20)
        self.current_atr = 0.0
        self.historical_atr = 0.0

        # Cooldown to avoid duplicate signals
        self.last_signal_ts = 0.0
        self.signal_cooldown = 30.0  # Reduced from 60s to 30s

    @property
    def name(self) -> str:
        return "TacticalPoorExtreme"

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        """Main calculation on each 1m candle."""
        candle = context.get(self.timeframe)
        if not candle:
            return None

        # Extract candle data
        high = float(candle.get("high", 0))
        low = float(candle.get("low", 0))
        close = float(candle.get("close", 0))
        volume = float(candle.get("volume", 0))
        timestamp = float(candle.get("timestamp", time.time()))

        if high <= 0 or low <= 0 or volume <= 0:
            return None

        # Update ATR for volatility adjustment
        candle_range = high - low
        self.atr_history.append(candle_range)
        if len(self.atr_history) >= 14:
            self.current_atr = np.mean(list(self.atr_history)[-14:])
            if len(self.atr_history) == 20:
                self.historical_atr = np.mean(self.atr_history)

        # Update spread history (if available)
        spread = candle.get("spread", 0.0)
        if spread > 0:
            self.spread_history.append(spread)

        # Check cooldown
        if timestamp - self.last_signal_ts < self.signal_cooldown:
            return None

        # Reset session tracking if needed (simple: reset every 24h)
        if timestamp - self.session_start_ts > 86400:  # 24 hours
            self._reset_session(timestamp)

        # Track candles since last extreme
        self.candles_since_extreme += 1

        # Check for new session high
        if high > self.session_high:
            is_poor_high = self._evaluate_poor_extreme(
                price=high, volume=volume, spread=spread, timestamp=timestamp, direction="SHORT"
            )

            # Update session high
            self.session_high = high
            self.last_extreme_ts = timestamp
            self.candles_since_extreme = 0

            # Record extreme in history
            self.extreme_history.append(
                {"price": high, "volume": volume, "spread": spread, "timestamp": timestamp, "type": "high"}
            )

            if is_poor_high:
                self.last_signal_ts = timestamp
                return {
                    "side": "TACTICAL",
                    "metadata": {
                        "tactical_type": "TacticalPoorExtreme",
                        "direction": "SHORT",
                        "pattern": "Poor_High",
                        "price": close,
                        "extreme_price": high,
                        "volume": volume,
                        "volume_percentile": self._get_volume_percentile(volume),
                        "spread": spread,
                        "spread_ratio": self._get_spread_ratio(spread),
                        "candles_to_form": self.candles_since_extreme,
                        "high": high,
                        "low": low,
                        "close": close,
                    },
                }

        # Check for new session low
        if low < self.session_low:
            is_poor_low = self._evaluate_poor_extreme(
                price=low, volume=volume, spread=spread, timestamp=timestamp, direction="LONG"
            )

            # Update session low
            self.session_low = low
            self.last_extreme_ts = timestamp
            self.candles_since_extreme = 0

            # Record extreme in history
            self.extreme_history.append(
                {"price": low, "volume": volume, "spread": spread, "timestamp": timestamp, "type": "low"}
            )

            if is_poor_low:
                self.last_signal_ts = timestamp
                return {
                    "side": "TACTICAL",
                    "metadata": {
                        "tactical_type": "TacticalPoorExtreme",
                        "direction": "LONG",
                        "pattern": "Poor_Low",
                        "price": close,
                        "extreme_price": low,
                        "volume": volume,
                        "volume_percentile": self._get_volume_percentile(volume),
                        "spread": spread,
                        "spread_ratio": self._get_spread_ratio(spread),
                        "candles_to_form": self.candles_since_extreme,
                        "high": high,
                        "low": low,
                        "close": close,
                    },
                }

        return None

    def _evaluate_poor_extreme(
        self, price: float, volume: float, spread: float, timestamp: float, direction: str
    ) -> bool:
        """
        Evaluate if an extreme qualifies as "poor" (weak institutional participation).

        Criteria:
        1. Volume < 25th percentile of historical extremes
        2. Spread > 1.5x average (illiquidity confirmation) - OPTIONAL
        3. Rapid formation (< volatility-adjusted threshold)
        """
        # Need minimum history (reduced from 20 to 5 for faster activation)
        if len(self.extreme_history) < 5:
            return False

        # 1. Volume percentile check (relaxed to 30th percentile)
        volume_percentile = self._get_volume_percentile(volume)
        if volume_percentile > 30:  # Relaxed from 25 to 30
            return False

        # 2. Spread confirmation (OPTIONAL - don't block if no spread data)
        if len(self.spread_history) > 10:
            spread_ratio = self._get_spread_ratio(spread)
            if spread_ratio < 1.3:  # Relaxed from 1.5 to 1.3
                return False
        # If no spread data, continue anyway (don't block)

        # 3. Rapid formation check (volatility-adjusted) - RELAXED
        max_candles = self._get_volatility_adjusted_threshold()
        if self.candles_since_extreme > max_candles * 2:  # 2x more lenient
            return False  # Too gradual, not a "poor" extreme

        return True

    def _get_volume_percentile(self, volume: float) -> float:
        """Calculate what percentile this volume is in historical extremes."""
        if len(self.extreme_history) < 5:
            return 50.0  # Default to median if insufficient data

        volumes = [e["volume"] for e in self.extreme_history]
        percentile = (np.searchsorted(sorted(volumes), volume) / len(volumes)) * 100
        return percentile

    def _get_spread_ratio(self, spread: float) -> float:
        """Calculate current spread vs average spread."""
        if len(self.spread_history) < 10 or spread <= 0:
            return 1.0

        avg_spread = np.mean(self.spread_history)
        if avg_spread <= 0:
            return 1.0

        return spread / avg_spread

    def _get_volatility_adjusted_threshold(self) -> int:
        """
        Get max candles for "rapid formation" adjusted by volatility.
        Base: 2 minutes (2 candles)
        Adjusted by current ATR vs historical ATR
        """
        base_candles = 2

        if self.historical_atr <= 0 or self.current_atr <= 0:
            return base_candles

        # Higher volatility = allow more candles (market moves faster)
        vol_multiplier = self.current_atr / self.historical_atr
        adjusted = int(base_candles * vol_multiplier)

        # Cap between 1 and 5 candles
        return max(1, min(5, adjusted))

    def _reset_session(self, timestamp: float):
        """Reset session tracking."""
        self.session_high = 0.0
        self.session_low = float("inf")
        self.session_start_ts = timestamp
        self.last_extreme_ts = timestamp
        self.candles_since_extreme = 0
