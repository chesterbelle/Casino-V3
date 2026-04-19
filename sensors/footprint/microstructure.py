from typing import Any, Dict, Optional

from core.events import Event, EventType, FootprintCandleEvent, TickEvent
from core.tick_registry import tick_registry
from sensors.base_sensor import BaseSensor


class MicroStructureContext(BaseSensor):
    """
    Evaluates the short-term microstructure bias by continuously comparing
    the current market price against the current session/candle's Point of Control (POC).

    Logic (O(1) complexity):
    - Price > POC = BULLISH (Buyers defending the high volume node)
    - Price < POC = BEARISH (Sellers defending the high volume node)
    - Price == POC = NEUTRAL
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.symbol = config.get("symbol", "LTC/USDT:USDT")
        self.current_poc: Optional[float] = None
        self.current_price: Optional[float] = None
        self.micro_bias = "NEUTRAL"

    def handles(self) -> list[EventType]:
        return [EventType.CANDLE, EventType.TICK]

    def process(self, event: Event) -> None:
        if isinstance(event, FootprintCandleEvent) and event.symbol == self.symbol:
            # Update the reference POC when a footprint candle arrives/closes
            if hasattr(event, "poc") and event.poc > 0:
                self.current_poc = event.poc
                self._update_bias()

        elif isinstance(event, TickEvent) and event.symbol == self.symbol:
            # Continuously update the current price to check against POC
            self.current_price = event.price
            self._update_bias()

    def _update_bias(self) -> None:
        """Evaluate Price vs POC to determine microstructure context."""
        poc = self.current_poc
        price = self.current_price

        if poc is None or price is None:
            return

        old_bias = self.micro_bias

        # We add a tiny buffer (1 tick) to avoid flip-flopping exactly ON the POC
        sym_tick_size = tick_registry.get(self.symbol)

        if price >= (poc + sym_tick_size):
            self.micro_bias = "BULLISH"
        elif price <= (poc - sym_tick_size):
            self.micro_bias = "BEARISH"
        else:
            self.micro_bias = "NEUTRAL"

        if self.micro_bias != old_bias:
            self.logger.debug(
                f"🔍 [MicroStructure] Bias Shifted -> {self.micro_bias} " f"(Price: {price:.2f} vs POC: {poc:.2f})"
            )

    def get_state(self) -> Dict[str, Any]:
        return {"poc": self.current_poc, "price": self.current_price, "bias": self.micro_bias}
