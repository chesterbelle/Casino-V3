import asyncio
import logging
from typing import Any, Dict


class DepthProfiler:
    """
    Analyzes Order Book depth to predict slippage and market impact.

    This component helps the Croupier decide if an order should be:
    1. Executed normally (Low Impact)
    2. Fragmented (Medium Impact)
    3. Rejected (Extreme Impact)
    """

    def __init__(self, exchange_adapter):
        self.adapter = exchange_adapter
        self.logger = logging.getLogger("DepthProfiler")

    async def analyze_execution(self, symbol: str, side: str, amount: float, limit: int = 20) -> Dict[str, Any]:
        """
        Analyzes the potential impact of a market order (Hybrid: Cache -> REST).
        Prioritizes Zero-Latency Cache check.
        """
        # 1. Try Cache First (Golden Execution Path)
        cached = self.analyze_cached_execution(symbol, side, amount, limit)
        if not cached.get("error"):
            # Cache Hit & Valid
            return cached

        # 2. Fallback to REST (Safety Net)
        try:
            # Phase 234: Critical Timeout Fix
            # Prevent indefinite hang during congestion
            book = await asyncio.wait_for(self.adapter.fetch_order_book(symbol, limit=limit), timeout=2.0)
            return self._analyze_book(book, side, amount, limit)
        except asyncio.TimeoutError:
            self.logger.warning(f"⚠️ Depth analysis timed out for {symbol} (Fail Open)")
            return {"is_safe": True, "error": "timeout"}
        except Exception as e:
            self.logger.error(f"❌ Depth analysis failed for {symbol}: {e}")
            return {"is_safe": True, "error": str(e)}

    def analyze_cached_execution(self, symbol: str, side: str, amount: float, limit: int = 5) -> Dict[str, Any]:
        """
        Analyzes the potential impact using cached data (Phase 230).
        Zero Network I/O.
        """
        book = self.adapter.get_cached_order_book(symbol)
        if not book:
            return {"is_safe": False, "error": "cache_miss"}

        # Check staleness
        if self.adapter.is_cache_stale(symbol):
            return {"is_safe": False, "error": "cache_stale"}

        return self._analyze_book(book, side, amount, limit)

    def _analyze_book(self, book: Dict[str, Any], side: str, amount: float, limit: int) -> Dict[str, Any]:
        """Internal helper for slippage calculation."""
        # side='buy' -> we consume ASKS (lowest price first)
        # side='sell' -> we consume BIDS (highest price first)
        levels = book.get("asks" if side == "buy" else "bids", [])

        if not levels:
            return {"is_safe": False, "error": "empty_book"}

        best_price = float(levels[0][0])
        remaining_amount = amount
        total_cost = 0.0

        for price, qty in levels:
            price = float(price)
            qty = float(qty)

            fill = min(remaining_amount, qty)
            total_cost += fill * price
            remaining_amount -= fill

            if remaining_amount <= 0:
                break

        if remaining_amount > 0:
            # Estimate remaining at 5% worse price for safety metric
            total_cost += remaining_amount * (best_price * (1.05 if side == "buy" else 0.95))

        avg_price = total_cost / amount
        slippage = abs(avg_price - best_price) / best_price

        return {
            "avg_price": avg_price,
            "best_price": best_price,
            "slippage_pct": slippage,
            "total_notional": total_cost,
            "is_safe": slippage < 0.01,  # Default 1% threshold
            "depth_consumed": amount - max(0, remaining_amount),
            "source": "cache" if "timestamp" in book else "rest",
        }

    def get_safe_chunk_size(self, symbol: str, side: str, max_slippage_pct: float = 0.002) -> float:
        """
        Suggests a chunk size that stays within a slippage target.
        (Requires cached order book or immediate fetch)
        """
        # Note: Implement if fragmented execution logic needs it
        return 0.0
