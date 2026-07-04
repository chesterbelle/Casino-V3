import logging
from typing import Dict

logger = logging.getLogger(__name__)


class SessionBoundaryManager:
    """
    Coordinated Daily State Reset (SBR).

    Detects 00:00 UTC day transitions per symbol and triggers
    cascading resets across all stateful components so that
    monthly backtests and live trading behave identically to
    isolated daily datasets.
    """

    def __init__(self):
        self._last_reset_day: Dict[str, int] = {}

    def is_new_day(self, symbol: str, timestamp: float) -> bool:
        current_day = int(timestamp) // 86400
        last_day = self._last_reset_day.get(symbol)
        if last_day is None:
            self._last_reset_day[symbol] = current_day
            return False
        if current_day > last_day:
            self._last_reset_day[symbol] = current_day
            return True
        return False

    def mark_day(self, symbol: str, timestamp: float) -> None:
        self._last_reset_day[symbol] = int(timestamp) // 86400
