"""
Bar Aggregator for Casino-V3.
Aggregates 1m candles into higher timeframes (5m, 15m, 1h, 4h).

Provides a unified context dict to all sensors containing
candles for multiple timeframes.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Timeframe definitions: name -> number of 1m candles
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}


class BarAggregator:
    """
    Aggregates 1-minute candles into higher timeframes.

    When a 1m candle arrives, this class:
    1. Stores it in the 1m buffer
    2. Aggregates into 5m, 15m, 1h, 4h as needed
    3. Returns a context dict with all timeframe candles

    Example:
        aggregator = BarAggregator()
        context = aggregator.on_candle(candle_1m)
        # context = {"1m": {...}, "5m": {...}, "15m": None, ...}
    """

    def __init__(self, timeframes: Optional[List[str]] = None):
        """
        Initialize the bar aggregator.

        Args:
            timeframes: List of timeframes to aggregate.
                        Default: ["1m", "5m", "15m", "1h", "4h"]
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h", "4h"]

        self.timeframes = timeframes

        # Buffers to accumulate 1m candles for each timeframe
        # Key: timeframe, Value: list of 1m candles to aggregate
        self.buffers: Dict[str, List[dict]] = {tf: [] for tf in timeframes if tf != "1m"}

        # Last completed candle for each timeframe
        self.completed: Dict[str, Optional[dict]] = {tf: None for tf in timeframes}

        # Historical buffer for each timeframe (for sensors that need lookback)
        # Stores last N completed candles per timeframe
        self.history: Dict[str, deque] = {tf: deque(maxlen=100) for tf in timeframes}

        # Counter for candles processed
        self.candle_count = 0

        logger.info(f"✅ BarAggregator initialized | Timeframes: {timeframes}")

    def on_candle(self, candle: dict) -> Dict[str, Optional[dict]]:
        """
        Process a 1-minute candle and aggregate into higher timeframes.

        Args:
            candle: 1-minute OHLCV candle dict with keys:
                    timestamp, open, high, low, close, volume

        Returns:
            Context dict with candles for each timeframe.
            Value is None if timeframe not yet complete.

        Example:
            >>> context = aggregator.on_candle({"open": 100, ...})
            >>> context["1m"]   # Always present
            >>> context["5m"]   # Present every 5 candles
            >>> context["15m"]  # Present every 15 candles
        """
        self.candle_count += 1

        # Build context dict
        context: Dict[str, Optional[dict]] = {"1m": candle}

        # Add 1m to history
        self.history["1m"].append(candle)

        # Process each higher timeframe
        for tf in self.timeframes:
            if tf == "1m":
                continue

            # Add candle to buffer
            self.buffers[tf].append(candle)

            # Check if buffer is complete
            required_candles = TIMEFRAME_MINUTES[tf]

            if len(self.buffers[tf]) >= required_candles:
                # Aggregate buffer into HTF candle
                htf_candle = self._aggregate_candles(self.buffers[tf], tf)
                self.completed[tf] = htf_candle
                self.history[tf].append(htf_candle)

                # Clear buffer
                self.buffers[tf] = []

                context[tf] = htf_candle

                logger.debug(
                    f"📊 {tf} candle complete | "
                    f"O:{htf_candle['open']:.2f} H:{htf_candle['high']:.2f} "
                    f"L:{htf_candle['low']:.2f} C:{htf_candle['close']:.2f}"
                )
            else:
                # Return the in-progress candle (partial aggregation)
                if self.buffers[tf]:
                    context[tf] = self._aggregate_candles(self.buffers[tf], tf, is_complete=False)
                else:
                    context[tf] = self.completed[tf]

        return context

    def _aggregate_candles(self, candles: List[dict], timeframe: str, is_complete: bool = True) -> dict:
        """
        Aggregate multiple 1m candles into a single HTF candle.
        Includes merging of Footprint profiles and recalculation of levels.
        """
        if not candles:
            return None

        # 1. Basic OHLCV Aggregation
        aggregated = {
            "timestamp": candles[0]["timestamp"],
            "open": candles[0]["open"],
            "high": max(c["high"] for c in candles),
            "low": min(c["low"] for c in candles),
            "close": candles[-1]["close"],
            "volume": sum(c.get("volume", 0) for c in candles),
            "delta": sum(c.get("delta", 0.0) for c in candles),
            "profile": {},
            "timeframe": timeframe,
            "is_complete": is_complete,
        }

        # 2. Merge Footprint Profiles
        profile = aggregated["profile"]
        for c in candles:
            p = c.get("profile", {})
            for price, data in p.items():
                if price not in profile:
                    profile[price] = {"bid": 0.0, "ask": 0.0}
                profile[price]["bid"] += data.get("bid", 0.0)
                profile[price]["ask"] += data.get("ask", 0.0)

        # 3. Recalculate Structural Levels (POC, VAH, VAL)
        poc, vah, val = self._calculate_footprint_stats(profile, aggregated["volume"])
        aggregated.update({"poc": poc, "vah": vah, "val": val})

        return aggregated

    def _calculate_footprint_stats(self, profile: dict, total_volume: float) -> tuple:
        """Lightweight POC/VA calculation for aggregation."""
        if not profile or total_volume == 0:
            return 0.0, 0.0, 0.0

        try:
            sorted_levels = sorted(profile.items(), key=lambda x: x[0])
            max_vol = -1
            poc_price = 0.0
            levels_vol = []
            for price, data in sorted_levels:
                vol = data["bid"] + data["ask"]
                levels_vol.append((price, vol))
                if vol > max_vol:
                    max_vol = vol
                    poc_price = float(price)  # Fix: Ensure float type

            target_vol = total_volume * 0.70
            current_vol = max_vol
            poc_idx = next((i for i, x in enumerate(levels_vol) if x[0] == poc_price), -1)

            up_idx = down_idx = poc_idx
            while current_vol < target_vol:
                vol_up = levels_vol[up_idx + 1][1] if up_idx + 1 < len(levels_vol) else 0
                vol_down = levels_vol[down_idx - 1][1] if down_idx - 1 >= 0 else 0
                if vol_up == 0 and vol_down == 0:
                    break
                if vol_up > vol_down:
                    current_vol += vol_up
                    up_idx += 1
                else:
                    current_vol += vol_down
                    down_idx -= 1

            return poc_price, levels_vol[up_idx][0], levels_vol[down_idx][0]
        except Exception:
            return 0.0, 0.0, 0.0

    def get_history(self, timeframe: str, lookback: int = 10) -> List[dict]:
        """
        Get historical candles for a timeframe.

        Args:
            timeframe: Timeframe to get history for
            lookback: Number of candles to return

        Returns:
            List of recent candles (most recent last)
        """
        if timeframe not in self.history:
            return []

        history = list(self.history[timeframe])
        return history[-lookback:] if len(history) >= lookback else history

    def reset(self):
        """Reset all buffers and history (for new trading session)."""
        for tf in self.buffers:
            self.buffers[tf] = []
        for tf in self.completed:
            self.completed[tf] = None
        for tf in self.history:
            self.history[tf].clear()
        self.candle_count = 0
        logger.info("🔄 BarAggregator reset")
