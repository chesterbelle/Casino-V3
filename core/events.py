"""
Event definitions for Casino-V3 Event-Driven Architecture.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional


class EventType(Enum):
    TICK = auto()
    ORDER_BOOK = auto()
    ORDER_UPDATE = auto()
    CANDLE = auto()
    SIGNAL = auto()
    AGGREGATED_SIGNAL = auto()
    DECISION = auto()
    ERROR = auto()
    SYSTEM = auto()


@dataclass
class Event:
    type: EventType
    timestamp: float


@dataclass
class CandleEvent(Event):
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        self.type = EventType.CANDLE


@dataclass
class FootprintCandleEvent(CandleEvent):
    """
    Extended Candle Event with Order Flow data.
    profile: Dict[float, Dict['bid', 'ask']] -> Price Level -> Volume
    delta: float -> Net Buy Volume - Net Sell Volume
    """

    profile: Dict[float, Dict[str, float]] = None
    delta: float = 0.0
    poc: float = 0.0  # Point of Control (Price level with max volume)
    vah: float = 0.0  # Value Area High
    val: float = 0.0  # Value Area Low

    def __post_init__(self):
        self.type = EventType.CANDLE


@dataclass
class TickEvent(Event):
    symbol: str
    price: float
    volume: float = 0.0
    side: str = "UNKNOWN"  # 'BID' (Sell) or 'ASK' (Buy)

    def __post_init__(self):
        self.type = EventType.TICK


@dataclass
class OrderBookEvent(Event):
    symbol: str
    bids: list  # [[price, amount], ...]
    asks: list  # [[price, amount], ...]

    def __post_init__(self):
        self.type = EventType.ORDER_BOOK


@dataclass
class OrderUpdateEvent(Event):
    order_id: str
    symbol: str
    status: str  # 'open', 'closed', 'canceled', 'rejected'
    filled: float
    remaining: float
    price: float
    side: str
    client_order_id: Optional[str] = None

    def __post_init__(self):
        self.type = EventType.ORDER_UPDATE


@dataclass
class ErrorEvent(Event):
    source: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.type = EventType.ERROR


@dataclass
class SignalEvent(Event):
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    sensor_id: str  # Sensor that generated this signal
    score: float = 1.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.type = EventType.SIGNAL


@dataclass
class AggregatedSignalEvent(Event):
    """Aggregated signal from multiple sensors."""

    symbol: str
    candle_timestamp: float
    selected_sensor: str
    sensor_score: float
    side: str
    confidence: float
    total_signals: int
    metadata: Optional[Dict[str, Any]] = None
    strategy_name: Optional[str] = None

    def __post_init__(self):
        self.type = EventType.AGGREGATED_SIGNAL
