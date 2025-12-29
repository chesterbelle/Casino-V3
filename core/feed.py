"""
Data Feed Layer for Casino-V3.
Manages Websocket streams via CCXTAdapter and dispatches events to the Engine.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Set

from core.events import EventType, OrderBookEvent, TickEvent
from core.observability.watchdog import watchdog
from exchanges.adapters import ExchangeAdapter
from utils.symbol_norm import normalize_symbol

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Manages Websocket streams and dispatches events to the Engine.
    """

    def __init__(self, adapter: ExchangeAdapter, engine):
        self.adapter = adapter
        self.engine = engine
        self.running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._subscribed_symbols: Set[str] = set()
        self._disabled_symbols: Set[str] = set()  # Symbols disabled due to stream failures
        self._last_price: Dict[str, float] = {}  # Last logged price per symbol
        self._max_disabled_before_reset = 3  # If this many symbols fail, trigger hard_reset

    async def connect(self):
        """Connect the adapter."""
        logger.info("🔌 Connecting Data Feed...")
        await self.adapter.connect()
        self.running = True

        # Start Health Check Loop
        self._tasks["health_check"] = asyncio.create_task(self._health_check_loop())

        # Start tasks for queued subscriptions
        for symbol in self._subscribed_symbols:
            if f"ticker_{symbol}" not in self._tasks:
                self._tasks[f"ticker_{symbol}"] = asyncio.create_task(self._watch_ticker_loop(symbol))
            if f"ob_{symbol}" not in self._tasks:
                self._tasks[f"ob_{symbol}"] = asyncio.create_task(self._watch_order_book_loop(symbol))
            if f"trades_{symbol}" not in self._tasks:
                self._tasks[f"trades_{symbol}"] = asyncio.create_task(self._watch_trades_loop(symbol))

    async def disconnect(self):
        """Disconnect and stop all streams."""
        logger.info("🔌 Disconnecting Data Feed...")
        self.running = False

        # Cancel all tasks first
        for task in self._tasks.values():
            task.cancel()

        # CRITICAL: Wait for all tasks to finish cancellation
        # Without this, tasks are still running when process tries to exit
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            self._tasks.clear()

        await self.adapter.disconnect()

    async def _health_check_loop(self):
        """Periodically check connection health."""
        logger.info("💓 Starting Health Check Loop")
        watchdog.register("feed_health_check", timeout=60.0)
        while self.running:
            try:
                watchdog.heartbeat("feed_health_check", "Checking WS health")
                await asyncio.sleep(10)
                if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "ensure_websocket"):
                    await self.adapter.connector.ensure_websocket()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Health check failed: {e}")

    async def subscribe_ticker(self, symbol: str):
        """Subscribe to ticker updates for a symbol."""
        norm_symbol = normalize_symbol(symbol)
        self._subscribed_symbols.add(norm_symbol)

        if self.running:
            if f"ticker_{norm_symbol}" in self._tasks:
                return
            logger.info(f"📡 Subscribing to ticker: {norm_symbol}")
            self._tasks[f"ticker_{norm_symbol}"] = asyncio.create_task(self._watch_ticker_loop(norm_symbol))
        else:
            logger.info(f"📝 Queued ticker subscription: {norm_symbol}")

    async def subscribe_order_book(self, symbol: str):
        """Subscribe to order book updates for a symbol."""
        norm_symbol = normalize_symbol(symbol)
        self._subscribed_symbols.add(norm_symbol)

        if self.running:
            if f"ob_{norm_symbol}" in self._tasks:
                return
            logger.info(f"📡 Subscribing to order book: {norm_symbol}")
            self._tasks[f"ob_{norm_symbol}"] = asyncio.create_task(self._watch_order_book_loop(norm_symbol))
        else:
            logger.info(f"📝 Queued order book subscription: {norm_symbol}")

    async def subscribe_trades(self, symbol: str):
        """Subscribe to trade updates for a symbol."""
        norm_symbol = normalize_symbol(symbol)
        self._subscribed_symbols.add(norm_symbol)

        if self.running:
            if f"trades_{norm_symbol}" in self._tasks:
                return
            logger.info(f"📡 Subscribing to trades: {norm_symbol}")
            self._tasks[f"trades_{norm_symbol}"] = asyncio.create_task(self._watch_trades_loop(norm_symbol))
        else:
            logger.info(f"📝 Queued trades subscription: {norm_symbol}")

    async def _watch_ticker_loop(self, symbol: str):
        """Continuous loop to watch ticker with error handling and auto-recovery."""
        logger.info(f"🔍 Starting ticker loop for {symbol}")

        try:
            from core.error_handling import RetryConfig, get_error_handler

            error_handler = get_error_handler()
            breaker_name = f"ticker_stream_{symbol}"
            # Register with watchdog for each symbol (long timeout due to potential inactivity)
            # Actually, let's use a unified 'feed_activity' or similar to avoid 48 tasks in monitor if preferred,
            # but for Task-Level, per-symbol is fine if timeout is large.
            watchdog.register(f"stream_{symbol}", timeout=120.0)

            consecutive_failures = 0
            max_consecutive_failures = 10
        except Exception as e:
            logger.critical(f"❌ Failed to initialize ticker loop: {e}", exc_info=True)
            return

        while self.running:
            try:
                # Use error handler with circuit breaker AND timeout
                # We wrap the execution in wait_for to prevent hanging if the queue is empty
                # and the websocket is dead but not closed.
                ticker = await asyncio.wait_for(
                    error_handler.execute_with_breaker(
                        breaker_name,
                        self.adapter.watch_ticker,
                        symbol,
                        retry_config=RetryConfig(
                            max_retries=3,
                            backoff_base=1.0,
                            backoff_max=30.0,
                        ),
                    ),
                    timeout=10.0,  # 10s timeout for ticker (should be frequent)
                )

                # Report heartbeat for this symbol
                watchdog.heartbeat(f"stream_{symbol}", "Tick received")
                await self.on_ticker(ticker)

                # Reset failure count on success
                consecutive_failures = 0

            except asyncio.TimeoutError:
                # Timeout is treated as a failure to trigger recovery if persistent
                consecutive_failures += 1
                logger.warning(
                    f"⚠️ Ticker stream for {symbol} timed out "
                    f"(consecutive failures: {consecutive_failures}/{max_consecutive_failures})"
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"⚠️ Ticker stream for {symbol} failed {max_consecutive_failures} times (Timeout). "
                        f"DISABLING this symbol to prevent affecting other streams."
                    )
                    # Reset circuit breaker for cleanup
                    error_handler.reset_circuit_breaker(breaker_name)

                    # Remove from subscribed symbols and add to disabled
                    self._subscribed_symbols.discard(symbol)
                    self._disabled_symbols.add(symbol)

                    # Check if too many symbols have failed (systemic issue)
                    if len(self._disabled_symbols) >= self._max_disabled_before_reset:
                        logger.critical(
                            f"🔥 {len(self._disabled_symbols)} symbols have failed! "
                            f"This indicates a systemic issue. Triggering hard_reset..."
                        )
                        try:
                            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "hard_reset"):
                                await self.adapter.connector.hard_reset()
                                # Clear disabled symbols after reset
                                self._disabled_symbols.clear()
                                logger.info("✅ hard_reset complete. Disabled symbols cleared.")
                        except Exception as reset_error:
                            logger.error(f"❌ hard_reset failed: {reset_error}")
                    else:
                        # Log and exit the loop for this symbol - bot continues with others
                        logger.error(
                            f"🚫 Symbol {symbol} has been disabled due to persistent timeout failures. "
                            f"The bot continues running with {len(self._subscribed_symbols)} remaining symbols. "
                            f"({len(self._disabled_symbols)}/{self._max_disabled_before_reset} disabled before hard_reset)"
                        )
                    return  # Exit this task gracefully

                # Short backoff on timeout
                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                logger.info(f"📡 Ticker stream for {symbol} cancelled")
                break
            except Exception as e:
                consecutive_failures += 1
                # ... existing error handling ...
                logger.error(
                    f"❌ Error in ticker stream for {symbol} "
                    f"(consecutive failures: {consecutive_failures}/{max_consecutive_failures}): {e}"
                )

                # If too many consecutive failures, DISABLE this symbol instead of hard_reset
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"⚠️ Ticker stream for {symbol} failed {max_consecutive_failures} times. "
                        f"DISABLING this symbol to prevent affecting other streams."
                    )
                    # Reset circuit breaker for cleanup
                    error_handler.reset_circuit_breaker(breaker_name)

                    # Remove from subscribed symbols and add to disabled
                    self._subscribed_symbols.discard(symbol)
                    self._disabled_symbols.add(symbol)

                    # Check if too many symbols have failed (systemic issue)
                    if len(self._disabled_symbols) >= self._max_disabled_before_reset:
                        logger.critical(
                            f"🔥 {len(self._disabled_symbols)} symbols have failed! "
                            f"This indicates a systemic issue. Triggering hard_reset..."
                        )
                        try:
                            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "hard_reset"):
                                await self.adapter.connector.hard_reset()
                                # Clear disabled symbols after reset
                                self._disabled_symbols.clear()
                                logger.info("✅ hard_reset complete. Disabled symbols cleared.")
                        except Exception as reset_error:
                            logger.error(f"❌ hard_reset failed: {reset_error}")
                    else:
                        # Log and exit the loop for this symbol - bot continues with others
                        logger.error(
                            f"🚫 Symbol {symbol} has been disabled due to persistent stream failures. "
                            f"The bot continues running with {len(self._subscribed_symbols)} remaining symbols. "
                            f"({len(self._disabled_symbols)}/{self._max_disabled_before_reset} disabled before hard_reset)"
                        )
                    return  # Exit this task gracefully

                # Exponential backoff
                backoff = min(2**consecutive_failures, 60)
                logger.info(f"⏳ Backing off for {backoff}s before retry")
                await asyncio.sleep(backoff)

    async def _watch_order_book_loop(self, symbol: str):
        """Continuous loop to watch order book with error handling and auto-recovery."""
        from core.error_handling import RetryConfig, get_error_handler

        error_handler = get_error_handler()
        breaker_name = f"orderbook_stream_{symbol}"
        consecutive_failures = 0
        max_consecutive_failures = 10
        recovery_pause = 60  # Pause before recovery attempt

        while self.running:
            try:
                # Use error handler with circuit breaker
                ob = await error_handler.execute_with_breaker(
                    breaker_name,
                    self.adapter.watch_order_book,
                    symbol,
                    retry_config=RetryConfig(
                        max_retries=3,
                        backoff_base=1.0,
                        backoff_max=30.0,
                    ),
                )

                # Create and dispatch event
                event = OrderBookEvent(
                    type=EventType.ORDER_BOOK,
                    timestamp=time.time(),
                    symbol=symbol,
                    bids=ob.get("bids", []),
                    asks=ob.get("asks", []),
                )
                await self.engine.dispatch(event)

                # Reset failure count on success
                consecutive_failures = 0

            except asyncio.CancelledError:
                logger.info(f"📡 Order book stream for {symbol} cancelled")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"❌ Error in order book stream for {symbol} "
                    f"(consecutive failures: {consecutive_failures}/{max_consecutive_failures}): {e}"
                )

                # If too many consecutive failures, enter recovery mode (don't stop!)
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"⚠️ Order book stream for {symbol} failed {max_consecutive_failures} times. "
                        f"Entering recovery mode - pausing {recovery_pause}s before retry..."
                    )
                    # Reset circuit breaker
                    error_handler.reset_circuit_breaker(breaker_name)
                    consecutive_failures = 0
                    await asyncio.sleep(recovery_pause)
                    logger.info(f"🔄 Order book stream for {symbol} attempting recovery...")
                    continue

                # Exponential backoff
                backoff = min(2**consecutive_failures, 60)
                logger.info(f"⏳ Backing off for {backoff}s before retry")
                await asyncio.sleep(backoff)

    async def _watch_trades_loop(self, symbol: str):
        """Continuous loop to watch trades with error handling and auto-recovery."""
        from core.error_handling import RetryConfig, get_error_handler

        error_handler = get_error_handler()
        breaker_name = f"trades_stream_{symbol}"
        consecutive_failures = 0
        max_consecutive_failures = 10

        while self.running:
            try:
                # Use error handler with circuit breaker AND timeout
                trade = await asyncio.wait_for(
                    error_handler.execute_with_breaker(
                        breaker_name,
                        self.adapter.watch_trades,
                        symbol,
                        retry_config=RetryConfig(
                            max_retries=3,
                            backoff_base=1.0,
                            backoff_max=30.0,
                        ),
                    ),
                    timeout=30.0,  # 30s timeout for trades (might be less frequent)
                )

                # Create and dispatch TickEvent with REAL side
                normalized_symbol = normalize_symbol(symbol)
                event = TickEvent(
                    type=EventType.TICK,
                    timestamp=trade["timestamp"] / 1000.0,
                    symbol=normalized_symbol,
                    price=trade["price"],
                    volume=trade["amount"],
                    side=trade["side"],  # REAL SIDE from Exchange
                )
                await self.engine.dispatch(event)

                consecutive_failures = 0

            except asyncio.TimeoutError:
                # Timeout is treated as a failure to trigger recovery if persistent
                # For trades, silence might be normal if low volume, but we expect heartbeats/pings usually.
                # If we rely on queue.get(), timeout means NO TRADES.
                # We should probably be lenient here or check connection status.
                # For now, let's just log and continue without incrementing failure count aggressively
                # UNLESS we know the connection is dead.
                # Actually, if we timeout, we should just loop again.
                # But if we loop 100 times with timeout, is it a failure?
                # Let's assume silence is okay for trades, but we want to check "running" flag.
                pass

            except asyncio.CancelledError:
                logger.info(f"📡 Trades stream for {symbol} cancelled")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"❌ Error in trades stream for {symbol} "
                    f"(consecutive failures: {consecutive_failures}/{max_consecutive_failures}): {e}"
                )

                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"⚠️ Trades stream for {symbol} failed {max_consecutive_failures} times. "
                        f"DISABLING this symbol to prevent affecting other streams."
                    )
                    error_handler.reset_circuit_breaker(breaker_name)

                    # Remove from subscribed symbols and add to disabled
                    self._subscribed_symbols.discard(symbol)
                    self._disabled_symbols.add(symbol)

                    # Check if too many symbols have failed (systemic issue)
                    if len(self._disabled_symbols) >= self._max_disabled_before_reset:
                        logger.critical(
                            f"🔥 {len(self._disabled_symbols)} symbols have failed! "
                            f"This indicates a systemic issue. Triggering hard_reset..."
                        )
                        try:
                            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "hard_reset"):
                                await self.adapter.connector.hard_reset()
                                self._disabled_symbols.clear()
                                logger.info("✅ hard_reset complete. Disabled symbols cleared.")
                        except Exception as reset_error:
                            logger.error(f"❌ hard_reset failed: {reset_error}")
                    else:
                        logger.error(
                            f"🚫 Symbol {symbol} has been disabled due to persistent stream failures. "
                            f"({len(self._disabled_symbols)}/{self._max_disabled_before_reset} disabled before hard_reset)"
                        )
                    return  # Exit this task gracefully

                backoff = min(2**consecutive_failures, 60)
                logger.info(f"⏳ Backing off for {backoff}s before retry")
                await asyncio.sleep(backoff)

    async def on_ticker(self, ticker: Dict[str, Any]):
        """Handle ticker update."""
        raw_symbol = ticker["symbol"]
        symbol = normalize_symbol(raw_symbol)
        price = float(ticker["last"])

        # Count ticks
        if not hasattr(self, "_tick_count"):
            self._tick_count = 0
        self._tick_count += 1

        # Log optimization: Only log if price changed or every 100th tick (heartbeat)
        last_price = self._last_price.get(symbol)
        # Round for comparison to avoid noise-triggered logs
        price_rounded = round(price, 8)
        price_changed = last_price is None or price_rounded != round(last_price, 8)

        if price_changed or self._tick_count % 100 == 0:
            logger.info(f"⚡ Tick: {symbol} {price}")
            self._last_price[symbol] = price

        # Ticker events are still useful for price updates, but we don't use them for Footprint anymore
        # because we have the real trades stream.
        event = TickEvent(
            type=EventType.TICK,
            timestamp=ticker["timestamp"] / 1000.0,
            symbol=symbol,
            price=float(ticker["last"]),
            volume=ticker.get("volume", 0.0),
            side="UNKNOWN",  # Side comes from trades stream now
        )
        await self.engine.dispatch(event)
