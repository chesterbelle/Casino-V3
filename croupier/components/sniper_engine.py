import asyncio
import logging
import time
from typing import Any, Dict

import config.trading
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger("SniperEngine")


class SniperEngine(TraceBulletMixin):
    """
    Dynamic Limit Sniper Engine.
    Handles the "Chase Logic" for Maker-entries:
    1. Places limit order at the edge of the book.
    2. Monitors the book and order status.
    3. If price moves away, it cancels and re-places at the new edge.
    4. Converts to Market if timeout reached.
    """

    def __init__(self, order_executor, exchange_adapter):
        super().__init__()
        self.executor = order_executor
        self.adapter = exchange_adapter
        self._active_snipers = {}  # trade_id -> task

        # Configuration from config/trading.py
        self.chase_enabled = getattr(config.trading, "LIMIT_SNIPER_CHASE_ENABLED", True)
        self.max_chase_attempts = getattr(config.trading, "LIMIT_SNIPER_MAX_CHASE_ATTEMPTS", 3)
        self.timeout_ms = getattr(config.trading, "LIMIT_SNIPER_TIMEOUT_MS", 5000)
        self.check_interval_ms = getattr(config.trading, "LIMIT_SNIPER_CHECK_INTERVAL_MS", 100)

    async def snipe_entry(
        self, symbol: str, side: str, amount: float, price: float, trace_id: str, params: Dict = None
    ) -> Dict[str, Any]:
        """
        Main entry point for sniper execution.
        Starts a background task and waits for the result (or timeout).
        """
        self.trace({"trace_id": trace_id, "symbol": symbol}, "SNIPER_START", {"price": price, "side": side})

        # Place initial order
        try:
            # Add trace_id to params if available
            order_params = params.copy() if params else {}
            order_params["trace_id"] = trace_id

            # Initial placement at requested price (or best bid/ask)
            # For now, we use the price passed from setup_engine
            result = await self.executor.execute_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                params={**order_params, "clientOrderId_prefix": "SNIPER"},
            )

            order_id = result.get("order_id")
            if not order_id:
                return result

            if result.get("status") == "filled":
                self.trace({**result, "trace_id": trace_id}, "SNIPER_FILLED_IMMEDIATE")
                return result

            # Start the Chase
            self.trace({**result, "trace_id": trace_id}, "SNIPER_CHASE_START")
            final_result = await self._chase_loop(symbol, side, amount, order_id, trace_id, price, order_params)

            return final_result

        except Exception as e:
            logger.error(f"💥 Sniper failed for {symbol}: {e}")
            self.trace({"trace_id": trace_id}, "SNIPER_ERROR", {"error": str(e)})
            raise

    async def _chase_loop(
        self, symbol: str, side: str, amount: float, order_id: str, trace_id: str, initial_price: float, params: Dict
    ) -> Dict[str, Any]:
        """
        Internal loop that monitors and re-prices the order.
        """
        start_time = time.time()
        attempts = 0
        current_order_id = order_id
        current_price = initial_price

        while (time.time() - start_time) < (self.timeout_ms / 1000):
            # 1. Check order status
            try:
                order = await self.adapter.fetch_order(current_order_id, symbol)
                if order.get("status") == "filled":
                    self.trace({**order, "trace_id": trace_id}, "SNIPER_FILLED")
                    return order
                if order.get("status") in ["canceled", "rejected"]:
                    self.trace({**order, "trace_id": trace_id}, "SNIPER_ABORTED_EXTERNALLY")
                    return order
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch order status for {current_order_id}: {e}")

            # 2. Check Order Book for better price (Maker Edge)
            try:
                book = self.adapter.get_cached_order_book(symbol)
                if book:
                    best_bid = float(book["bids"][0][0])
                    best_ask = float(book["asks"][0][0])

                    target_price = best_bid if side.upper() == "BUY" else best_ask

                    # If target price is better (or shifted) than our current price, re-price
                    if abs(target_price - current_price) > (current_price * 0.0001):  # 0.01% change threshold
                        if attempts < self.max_chase_attempts:
                            logger.info(
                                f"🏹 Sniper Re-pricing {symbol}: {current_price} -> {target_price} (Attempt {attempts+1})"
                            )

                            # Cancel current
                            await self.adapter.cancel_order(current_order_id, symbol)
                            self.trace({"trace_id": trace_id}, "SNIPER_REPRICE_CANCEL")

                            # Place new
                            current_price = target_price
                            new_order = await self.executor.execute_limit_order(
                                symbol=symbol,
                                side=side,
                                amount=amount,
                                price=current_price,
                                params={**params, "clientOrderId_prefix": f"SNIPER_CH{attempts+1}"},
                            )
                            current_order_id = new_order.get("order_id")
                            attempts += 1

                            if new_order.get("status") == "filled":
                                self.trace({**new_order, "trace_id": trace_id}, "SNIPER_FILLED_ON_REPRICE")
                                return new_order
                        else:
                            logger.warning(
                                f"⚠️ Sniper reached max chase attempts ({self.max_chase_attempts}) for {symbol}"
                            )
                            break
            except Exception as e:
                logger.warning(f"⚠️ Sniper re-pricing error: {e}")

            await asyncio.sleep(self.check_interval_ms / 1000)

        # 3. Timeout Fallback: Convert to Market
        logger.info(f"⏳ Sniper Timeout for {symbol}. Converting to Market...")
        self.trace({"trace_id": trace_id}, "SNIPER_TIMEOUT_FALLBACK")

        # Cancel current limit order if still open
        try:
            await self.adapter.cancel_order(current_order_id, symbol)
        except Exception:
            pass  # Might already be filled or canceled

        # Execute Market Entry
        return await self.executor.execute_market_order(
            {
                "symbol": symbol,
                "side": side.upper(),
                "amount": amount,
                "params": {**params, "exit_reason": "SNIPER_TIMEOUT"},
            }
        )
