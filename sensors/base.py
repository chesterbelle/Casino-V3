"""
Base Class for V3 Sensors.

Sensors receive a multi-timeframe context dict containing candles
for all available timeframes (1m, 5m, 15m, 1h, 4h).

Each sensor can monitor multiple timeframes and emit independent signals.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union


class SensorV3(ABC):
    """
    Abstract Base Class for V3 Sensors.

    Sensors receive a context dict with candles for multiple timeframes.
    Each sensor can monitor multiple TFs and emit signals for each.

    Example context:
        {
            "1m": {"open": 100, "high": 101, "low": 99, "close": 100.5, ...},
            "5m": {"open": 99, "high": 102, ...},  # Complete every 5 candles
            "15m": None,  # Not complete yet
        }

    Attributes:
        timeframes: List of TFs this sensor monitors (set by SensorManager)
    """

    # List of timeframes this sensor monitors (set by SensorManager from config)
    timeframes: List[str] = ["1m"]

    @property
    @abstractmethod
    def name(self) -> str:
        """Sensor Name."""
        pass

    @abstractmethod
    def calculate(self, context: Dict[str, Optional[dict]]) -> Union[Optional[dict], List[dict]]:
        """
        Calculate signal(s) based on multi-timeframe context.

        Args:
            context: Dict with candles for each timeframe.
                     Access 1m candle: context["1m"]
                     Access 15m candle: context.get("15m")

        Returns:
            Single signal dict, list of signals, or None.
            Signal dict should have: 'side', 'score', 'metadata', 'timeframe' (optional)
        """
        pass

    async def emit_signal(self, side: str, score: float = 1.0, metadata: Optional[dict] = None):
        """Emit a trading signal."""
        from core.events import SignalEvent

        signal = SignalEvent(
            timestamp=self.last_candle["timestamp"],
            symbol=self.symbol,
            side=side,
            sensor_id=self.__class__.__name__,  # Use class name as sensor ID
            score=score,
            metadata=metadata,
        )
        await self.engine.dispatch(signal)
