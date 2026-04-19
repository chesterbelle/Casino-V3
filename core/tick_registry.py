import logging
from typing import Dict

logger = logging.getLogger(__name__)


class TickSizeRegistry:
    """
    Centralized registry for exact exchange tick sizes (PRICE_FILTER).
    Provides symbol-agnostic exact tick_size lookups for Market Profiles.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TickSizeRegistry, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Pre-loaded exact Binance Futures tick sizes (PRICE_FILTER)
        # Guarantees perfect order book translation in Offline / Backtest nodes
        self._cache: Dict[str, float] = {
            "BTC/USDT:USDT": 0.1,
            "ETH/USDT:USDT": 0.01,
            "XRP/USDT:USDT": 0.0001,
            "LTC/USDT:USDT": 0.01,
            "LINK/USDT:USDT": 0.001,
            "ADA/USDT:USDT": 0.0001,
            "BNB/USDT:USDT": 0.01,
            "DOGE/USDT:USDT": 0.00001,
            "SOL/USDT:USDT": 0.01,
            "AVAX/USDT:USDT": 0.001,
            "SUI/USDT:USDT": 0.0001,
        }

    def get(self, symbol: str) -> float:
        """
        Get exact tick size for a symbol.
        Defaults to 0.01 if truly unknown, but will emit a warning.
        """
        if symbol in self._cache:
            return self._cache[symbol]

        # Fallback for unknown symbols
        logger.warning(f"⚠️ [TickRegistry] Unknown symbol '{symbol}'. Falling back to 0.01 tick_size.")
        self._cache[symbol] = 0.01
        return 0.01

    def update_from_exchange(self, symbol: str, tick_size: float):
        """Live nodes should call this to inject real precision from _markets."""
        if tick_size > 0 and self._cache.get(symbol) != tick_size:
            logger.info(f"📐 [TickRegistry] {symbol} tick_size updated to exact exchange spec: {tick_size}")
            self._cache[symbol] = tick_size


# Global Singleton Access
tick_registry = TickSizeRegistry()
