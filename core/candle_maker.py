"""
Candle Maker Component.
Aggregates ticks into candles and emits CandleEvents.
Multi-Symbol Safe: Each symbol has its own candle state.
"""

import asyncio
import logging
import time
from typing import Dict

from .events import EventType, FootprintCandleEvent, TickEvent

logger = logging.getLogger(__name__)


class CandleMaker:
    """
    Subscribes to TICK events and emits CANDLE events.
    Multi-Symbol Safe: Maintains separate candle state per symbol.
    """

    def __init__(self, engine, timeframe_seconds=60):
        self.engine = engine
        self.timeframe = timeframe_seconds
        # Multi-symbol safe: Dict[symbol, candle_data]
        self.current_candles: Dict[str, dict] = {}
        self.last_candle_times: Dict[str, int] = {}

        # Subscribe to Ticks
        self.engine.subscribe(EventType.TICK, self.on_tick)

    async def on_tick(self, tick: TickEvent):
        """Process incoming tick (multi-symbol safe)."""
        symbol = tick.symbol

        # Calculate candle start time (floor to minute)
        tick_time = int(tick.timestamp)
        candle_start_time = tick_time - (tick_time % self.timeframe)

        # Get current candle for THIS symbol
        current_candle = self.current_candles.get(symbol)
        last_candle_time = self.last_candle_times.get(symbol, 0)

        # If we have a current candle for this symbol and we moved to a new minute
        if current_candle and candle_start_time > last_candle_time:
            # Emit the closed candle
            await self._emit_candle(current_candle)
            # Reset for new candle
            current_candle = None
            self.current_candles[symbol] = None

        # Initialize new candle if needed
        if not current_candle:
            current_candle = {
                "timestamp": candle_start_time,
                "symbol": symbol,
                "open": tick.price,
                "high": tick.price,
                "low": tick.price,
                "close": tick.price,
                "volume": tick.volume,
                "profile": {},  # Price -> {bid: 0, ask: 0}
                "delta": 0.0,
            }
            self.current_candles[symbol] = current_candle
            self.last_candle_times[symbol] = candle_start_time
        else:
            # Update current candle
            current_candle["high"] = max(current_candle["high"], tick.price)
            current_candle["low"] = min(current_candle["low"], tick.price)
            current_candle["close"] = tick.price
            current_candle["volume"] += tick.volume

        # Update Footprint Profile
        price_level = tick.price  # In real impl, round to tick size
        if price_level not in current_candle["profile"]:
            current_candle["profile"][price_level] = {"bid": 0.0, "ask": 0.0}

        if tick.side == "BID":
            current_candle["profile"][price_level]["bid"] += tick.volume
            current_candle["delta"] -= tick.volume
        elif tick.side == "ASK":
            current_candle["profile"][price_level]["ask"] += tick.volume
            current_candle["delta"] += tick.volume

    def _calculate_footprint_stats(self, profile: dict, total_volume: float):
        """
        Calculate POC, VAH, VAL from profile.
        """
        if not profile or total_volume == 0:
            return 0.0, 0.0, 0.0

        # 1. Find POC (Price with max volume)
        sorted_levels = sorted(profile.items(), key=lambda x: x[0])  # Sort by price
        max_vol = -1
        poc_price = 0.0

        # Convert to list of (price, total_vol)
        levels_vol = []
        for price, data in sorted_levels:
            vol = data["bid"] + data["ask"]
            levels_vol.append((price, vol))
            if vol > max_vol:
                max_vol = vol
                poc_price = price

        # 2. Calculate Value Area (70% of volume around POC)
        target_vol = total_volume * 0.70
        current_vol = max_vol

        # Find index of POC
        poc_idx = -1
        for i, (p, v) in enumerate(levels_vol):
            if p == poc_price:
                poc_idx = i
                break

        # Expand up/down
        up_idx = poc_idx
        down_idx = poc_idx

        while current_vol < target_vol:
            # Check volumes above and below
            vol_up = 0
            vol_down = 0

            if up_idx + 1 < len(levels_vol):
                vol_up = levels_vol[up_idx + 1][1]

            if down_idx - 1 >= 0:
                vol_down = levels_vol[down_idx - 1][1]

            # If no more levels, break
            if vol_up == 0 and vol_down == 0:
                break

            # Expand to side with more volume (dual auction theory)
            # Or expand both if equal (rare)
            if vol_up > vol_down:
                current_vol += vol_up
                up_idx += 1
            else:
                current_vol += vol_down
                down_idx -= 1

        val = levels_vol[down_idx][0]
        vah = levels_vol[up_idx][0]

        return poc_price, vah, val

    async def _emit_candle(self, candle_data: dict):
        """Emit a closed candle event."""

        # Calculate advanced stats
        poc, vah, val = self._calculate_footprint_stats(candle_data["profile"], candle_data["volume"])

        event = FootprintCandleEvent(
            type=EventType.CANDLE,
            timestamp=time.time(),  # Event timestamp
            symbol=candle_data["symbol"],
            timeframe="1m",  # Hardcoded for now
            open=candle_data["open"],
            high=candle_data["high"],
            low=candle_data["low"],
            close=candle_data["close"],
            volume=candle_data["volume"],
            profile=candle_data["profile"],
            delta=candle_data["delta"],
            poc=poc,
            vah=vah,
            val=val,
        )
        logger.info(
            f"🕯️ Candle Closed: {candle_data['symbol']} {event.close} | Vol: {event.volume} | Delta: {event.delta:.2f} | POC: {poc}"
        )
        # Use create_task to prevent blocking the tick processing loop
        # This is CRITICAL for multi-symbol performance to allow parallel OCO creation
        asyncio.create_task(self.engine.dispatch(event))
