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
        Analyzes the potential impact of a market order.

        Args:
            symbol: Trading pair
            side: 'buy' (consuming asks) or 'sell' (consuming bids)
            amount: Quantity to execute
            limit: Order book depth to fetch

        Returns:
            Dict with:
                avg_price: Estimated average execution price
                slippage_pct: Estimated slippage relative to best bid/ask
                best_price: Current best bid/ask
                total_notional: Cost in quote currency
                is_safe: True if slippage < 1% (configurable)
        """
        try:
            book = await self.adapter.fetch_order_book(symbol, limit=limit)

            # side='buy' -> we consume ASKS (lowest price first)
            # side='sell' -> we consume BIDS (highest price first)
            levels = book.get("asks" if side == "buy" else "bids", [])

            if not levels:
                self.logger.warning(f"⚠️ Empty order book for {symbol}")
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
                self.logger.warning(
                    f"💀 Insufficient depth for {symbol}: {amount} requested, {amount - remaining_amount} available in top {limit} levels"
                )
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
            }

        except Exception as e:
            self.logger.error(f"❌ Depth analysis failed for {symbol}: {e}")
            return {"is_safe": True, "error": str(e)}  # Default to safe to not block if API fails

    def get_safe_chunk_size(self, symbol: str, side: str, max_slippage_pct: float = 0.002) -> float:
        """
        Suggests a chunk size that stays within a slippage target.
        (Requires cached order book or immediate fetch)
        """
        # Note: Implement if fragmented execution logic needs it
        return 0.0
