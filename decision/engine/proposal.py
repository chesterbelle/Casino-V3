from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.events import EventType


@dataclass
class TradeProposal:
    symbol: str
    side: str  # LONG/SHORT
    entry_price: float
    tp_price: float
    sl_price: float
    grade: str  # "A" (Full Size) o "B" (Half Size)
    narrative: str
    trace_id: str
    timestamp: float
    type: EventType = EventType.TRADE_PROPOSAL
    setup_type: str = ""
    meta: Optional[Dict[str, Any]] = None
