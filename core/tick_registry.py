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

        # Pre-loaded exact spec (Canonical keys)
        self._cache: Dict[str, float] = {
            "BTCUSDT": 0.1,
            "ETHUSDT": 0.01,
            "XRPUSDT": 0.0001,
            "LTCUSDT": 0.01,
            "LINKUSDT": 0.001,
            "ADAUSDT": 0.0001,
            "BNBUSDT": 0.01,
            "DOGEUSDT": 0.00001,
            "SOLUSDT": 0.01,
            "AVAXUSDT": 0.001,
            "SUIUSDT": 0.0001,
        }

        # 'The Silicon Eye': Probabilistic Inference Buffers
        self._last_prices: Dict[str, float] = {}
        self._observed_min_diff: Dict[str, float] = {}
        self._observation_counts: Dict[str, int] = {}

    def _normalize(self, symbol: str) -> str:
        """Normalize symbol using CanonicalSymbolMapper."""
        from .symbol_manager import symbol_mapper

        return symbol_mapper.normalize(symbol)

    def observe_price(self, symbol: str, price: float):
        """
        'The Silicon Eye' Logic:
        Infers tick size by observing minimum price changes in real-time.
        """
        norm_sym = self._normalize(symbol)
        last_price = self._last_prices.get(norm_sym)

        if last_price and price != last_price:
            diff = round(abs(price - last_price), 8)
            if diff > 0:
                current_min = self._observed_min_diff.get(norm_sym, 999.0)
                if diff < current_min:
                    self._observed_min_diff[norm_sym] = diff
                    self._observation_counts[norm_sym] = self._observation_counts.get(norm_sym, 0) + 1

                    # High Confidence Update: More precise than cache
                    if self._observation_counts[norm_sym] >= 5:
                        cached = self._cache.get(norm_sym, 999.0)
                        if diff < cached:
                            logger.info(f"👁️ [Silicon Eye] Inferred higher precision for {norm_sym}: {cached} -> {diff}")
                            self._cache[norm_sym] = diff

        self._last_prices[norm_sym] = price

    def get(self, symbol: str) -> float:
        """Get exact tick size with inference priority."""
        norm_sym = self._normalize(symbol)
        return self._cache.get(norm_sym, 0.01)

    def update_from_exchange(self, symbol: str, tick_size: float):
        """External injection from Exchange spec."""
        norm_sym = self._normalize(symbol)
        if tick_size > 0:
            self._cache[norm_sym] = tick_size


# Global Singleton Access
tick_registry = TickSizeRegistry()
