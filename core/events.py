"""
Event definitions for Casino-V3 Event-Driven Architecture.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional


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
    ACCOUNT_UPDATE = auto()
    MICROSTRUCTURE = auto()
    MICROSTRUCTURE_BATCH = auto()
    TRADE_CLOSED = auto()
    DECISION_TRACE = auto()


@dataclass
class Event:
    type: EventType
    timestamp: float


@dataclass
class DecisionTraceEvent(Event):
    """Event for tracking setup engine accept/reject decisions."""

    symbol: str
    status: str  # 'PASS' or 'REJECT'
    gate: str
    reason: str
    metrics: Dict[str, Any]
    price: float
    side: str

    def __post_init__(self):
        self.type = EventType.DECISION_TRACE


@dataclass
class CandleEvent(Event):
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    atr: float = 0.0  # Average True Range (Volatility)

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
    side: str = "UNKNOWN"  # 'BUY' (Hits Ask) or 'SELL' (Hits Bid)

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
class MicrostructureEvent(Event):
    symbol: str
    cvd: float
    skewness: float
    bid_depth_5: float = 0.0  # Sum of Top 5 Bid Qty (Phase 1300)
    ask_depth_5: float = 0.0  # Sum of Top 5 Ask Qty (Phase 1300)
    spread: float = 0.0  # (Ask[0] - Bid[0]) (Phase 1300)
    z_score: float = 0.0
    price: float = 0.0

    def __post_init__(self):
        self.type = EventType.MICROSTRUCTURE


@dataclass
class MicrostructureBatchEvent(Event):
    events: List[MicrostructureEvent]

    def __post_init__(self):
        self.type = EventType.MICROSTRUCTURE_BATCH


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
    trace_id: Optional[str] = None
    fast_track: bool = False  # Phase 240: If true, bypasses Aggregator 500ms delay
    price: float = 0.0  # Phase 800: Required for level checks and auditor

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
    t0_timestamp: Optional[float] = None  # Phase 85: Latency Telemetry (Signal Time)
    t1_decision_ts: Optional[float] = None  # Phase 10: Decision Time
    trace_id: Optional[str] = None
    setup_type: Optional[str] = None
    price: float = 0.0  # Phase 800: Price at execution

    def __post_init__(self):
        self.type = EventType.AGGREGATED_SIGNAL


@dataclass
class AccountUpdateEvent(Event):
    """Real-time account/balance update event."""

    data: Dict[str, Any]

    def __post_init__(self):
        self.type = EventType.ACCOUNT_UPDATE


@dataclass
class TradeClosedEvent(Event):
    """Event emitted when a position is closed and finalized."""

    trade_id: str
    symbol: str
    side: str
    pnl: float
    won: bool
    exit_reason: str
    exit_price: float

    def __post_init__(self):
        self.type = EventType.TRADE_CLOSED
