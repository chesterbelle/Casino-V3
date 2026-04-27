"""
Absorption Detector Sensor for Absorption Scalping V1.

Detects absorption patterns (aggressive volume without price displacement)
using real-time Footprint data from FootprintRegistry.

Runs in SensorManager workers for parallelization.

Phase 2.2: Initial implementation with 3 quality filters.
"""

import logging
import time
from typing import Dict, Optional

from core.footprint_registry import footprint_registry

logger = logging.getLogger(__name__)


class AbsorptionDetector:
    """
    Detects absorption patterns in real-time.

    Absorption = Aggressive volume without price displacement.
    Indicates exhaustion of the aggressor (buyer or seller).

    Quality Filters:
    1. Magnitude: Delta z-score > 3.0 (extreme volume)
    2. Velocity: 70%+ of delta concentrated in short window (< 30s)
    3. Noise: < 20% opposite delta (clean absorption)
    """

    def __init__(self):
        self.name = "AbsorptionDetector"

        # Configuration (from config/absorption.py later)
        self.z_score_min = 3.0  # Minimum z-score for magnitude filter
        self.concentration_min = 0.70  # Minimum concentration for velocity filter
        self.noise_max = 0.20  # Maximum noise for noise filter

        # State tracking (per symbol)
        self.last_analysis: Dict[str, float] = {}  # symbol -> timestamp
        self.analysis_interval = 0.1  # Analyze every 100ms (throttled)

        # Statistics tracking (for z-score calculation)
        self.delta_history: Dict[str, list] = {}  # symbol -> [(timestamp, delta), ...]
        self.stats_window = 120  # 2 minutes of history for z-score

        logger.info(f"✅ {self.name} initialized")

    def calculate(self, candle_data: dict) -> Optional[dict]:
        """
        Sensor interface (called by SensorManager workers).

        Args:
            candle_data: Candle data from SensorManager (not used, we use ticks)

        Returns:
            Signal dict or None
        """
        # AbsorptionDetector works on tick data, not candles
        # This method is called by workers but we don't use it
        # Instead, we analyze on_tick events
        return None

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        """
        Analyze tick for absorption patterns.

        Called by SensorManager workers on each tick.

        Args:
            tick_data: {symbol, price, volume, side, timestamp}

        Returns:
            AbsorptionSignal dict or None
        """
        symbol = tick_data["symbol"]
        timestamp = tick_data["timestamp"]

        # Throttle analysis (every 100ms)
        last_analysis = self.last_analysis.get(symbol, 0)
        if timestamp - last_analysis < self.analysis_interval:
            return None

        self.last_analysis[symbol] = timestamp

        # Analyze for absorption
        t0b_start = time.time()
        signal = self._analyze_absorption(symbol, timestamp)
        t0b_end = time.time()

        # Telemetry
        latency_ms = (t0b_end - t0b_start) * 1000
        if latency_ms > 10:
            logger.warning(f"⚠️ [LATENCY] AbsorptionDetector slow: {latency_ms:.2f}ms (symbol={symbol})")

        if signal:
            signal["t0b_detection_ts"] = t0b_end
            logger.info(
                f"🔍 [ABSORPTION] Detected: {symbol} {signal['direction']} "
                f"(z={signal['z_score']:.2f}, conc={signal['concentration']:.2f}, "
                f"noise={signal['noise']:.2f})"
            )

        return signal

    def _analyze_absorption(self, symbol: str, timestamp: float) -> Optional[dict]:
        """
        Analyze footprint for absorption pattern.

        Returns:
            Signal dict or None
        """
        # Get footprint data
        footprint = footprint_registry.get_footprint(symbol)
        if not footprint or len(footprint.levels) < 10:
            return None  # Insufficient data

        # Find levels with extreme delta (potential absorption)
        candidates = self._find_extreme_deltas(footprint, timestamp)

        if not candidates:
            return None

        # Check each candidate against quality filters
        for level, delta, ask_vol, bid_vol in candidates:
            # Filter 1: Magnitude (z-score)
            z_score = self._calculate_z_score(symbol, delta, timestamp)
            if abs(z_score) < self.z_score_min:
                continue

            # Filter 2: Velocity (concentration)
            concentration = self._calculate_concentration(footprint, level, timestamp)
            if concentration < self.concentration_min:
                continue

            # Filter 3: Noise (opposite delta)
            noise = self._calculate_noise(ask_vol, bid_vol, delta)
            if noise > self.noise_max:
                continue

            # All filters passed → Absorption detected
            direction = "SELL_EXHAUSTION" if delta < 0 else "BUY_EXHAUSTION"

            return {
                "symbol": symbol,
                "level": level,
                "direction": direction,
                "delta": delta,
                "z_score": z_score,
                "concentration": concentration,
                "noise": noise,
                "timestamp": timestamp,
                "ask_volume": ask_vol,
                "bid_volume": bid_vol,
            }

        return None

    def _find_extreme_deltas(self, footprint, timestamp: float) -> list:
        """
        Find price levels with extreme delta (top 5%).

        Returns:
            List of (level, delta, ask_vol, bid_vol) tuples
        """
        # Get all deltas
        deltas = []
        for level, data in footprint.levels.items():
            delta = data["delta"]
            if abs(delta) > 0:  # Ignore zero deltas
                deltas.append((level, delta, data["ask_volume"], data["bid_volume"]))

        if len(deltas) < 10:
            return []

        # Sort by absolute delta (descending)
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)

        # Return top 5% (at least 1, max 10)
        top_n = max(1, min(10, len(deltas) // 20))
        return deltas[:top_n]

    def _calculate_z_score(self, symbol: str, delta: float, timestamp: float) -> float:
        """
        Calculate z-score of delta relative to recent history.

        Z-score = (delta - mean) / std_dev

        Returns:
            Z-score (positive or negative)
        """
        # Initialize history if needed
        if symbol not in self.delta_history:
            self.delta_history[symbol] = []

        history = self.delta_history[symbol]

        # Add current delta to history
        history.append((timestamp, delta))

        # Prune old data (keep last 2 minutes)
        cutoff = timestamp - self.stats_window
        self.delta_history[symbol] = [(ts, d) for ts, d in history if ts >= cutoff]

        # Calculate statistics
        if len(self.delta_history[symbol]) < 10:
            return 0.0  # Insufficient data

        deltas = [d for _, d in self.delta_history[symbol]]
        mean = sum(deltas) / len(deltas)
        variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
        std_dev = variance**0.5

        if std_dev == 0:
            return 0.0

        z_score = (delta - mean) / std_dev
        return z_score

    def _calculate_concentration(self, footprint, level: float, timestamp: float) -> float:
        """
        Calculate concentration ratio (velocity filter).

        Concentration = Volume in last 30s / Total volume at level

        Returns:
            Ratio (0.0 to 1.0)
        """
        data = footprint.levels.get(level)
        if not data:
            return 0.0

        # For now, assume all volume is recent (simplified)
        # TODO: Track volume timestamps per level for accurate calculation
        # This is acceptable for Phase 2.2, can optimize later

        # Heuristic: If level was updated recently, concentration is high
        time_since_update = timestamp - data["last_update"]
        if time_since_update < 30:
            return 0.9  # High concentration (recent activity)
        elif time_since_update < 60:
            return 0.6  # Medium concentration
        else:
            return 0.3  # Low concentration (old data)

    def _calculate_noise(self, ask_vol: float, bid_vol: float, delta: float) -> float:
        """
        Calculate noise ratio (opposite delta filter).

        Noise = Opposite volume / Total volume

        For SELL_EXHAUSTION (delta < 0): Noise = ask_vol / total_vol
        For BUY_EXHAUSTION (delta > 0): Noise = bid_vol / total_vol

        Returns:
            Ratio (0.0 to 1.0)
        """
        total_vol = ask_vol + bid_vol
        if total_vol == 0:
            return 1.0  # Max noise (invalid)

        if delta < 0:
            # SELL_EXHAUSTION: Check for opposite (buy) volume
            noise = ask_vol / total_vol
        else:
            # BUY_EXHAUSTION: Check for opposite (sell) volume
            noise = bid_vol / total_vol

        return noise


# Sensor registration (for SensorManager)
def get_sensor_class():
    """Return sensor class for SensorManager."""
    return AbsorptionDetector
