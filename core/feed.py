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
        self._reset_lock = asyncio.Lock()  # Prevent multiple simultaneous hard resets

    async def connect(self):
        """Connect the adapter."""
        logger.info("🔌 Connecting Data Feed...")
        await self.adapter.connect()
        self.running = True

        # Phase 37/410: Register push-based event callbacks (eliminates per-symbol loops)
        if hasattr(self.adapter, "connector"):
            if hasattr(self.adapter.connector, "set_tick_callback"):
                self.adapter.connector.set_tick_callback(self._on_push_tick)
                logger.info("✅ Push-based tick dispatch enabled")
                self._push_mode = True

            # Phase 410: Register Depth callback
            if hasattr(self.adapter.connector, "set_depth_callback"):
                self.adapter.connector.set_depth_callback(self._on_push_depth)
                logger.info("✅ Push-based depth dispatch enabled")
        else:
            logger.warning("⚠️ Connector doesn't support push mode, using legacy loops")
            self._push_mode = False

        # Start Health Check Loop
        self._tasks["health_check"] = asyncio.create_task(self._health_check_loop())

        # Start tasks for queued subscriptions
        for symbol in self._subscribed_symbols:
            # Subscribe to ticker stream (connector will push events)
            self._tasks[f"sub_{symbol}"] = asyncio.create_task(self._subscribe_and_watch(symbol))
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

    async def _on_push_depth(self, depth_data: Dict[str, Any]):
        """Phase 410: Handle depth event pushed directly from connector."""
        try:
            symbol = depth_data.get("symbol", "")

            # Filter: only process subscribed symbols
            norm_symbol = normalize_symbol(symbol)
            if norm_symbol not in self._subscribed_symbols:
                return

            event = OrderBookEvent(
                type=EventType.ORDER_BOOK,
                timestamp=depth_data.get("timestamp", time.time() * 1000) / 1000.0,
                symbol=norm_symbol,
                bids=depth_data.get("bids", []),
                asks=depth_data.get("asks", []),
            )
            await self.engine.dispatch(event)

        except Exception as e:
            logger.debug(f"⚠️ Push depth error: {e}")

    async def _on_push_tick(self, ticker_data: Dict[str, Any]):
        """Phase 37: Handle tick event pushed directly from connector.

        This is the push-based event handler - no loops, no timeouts, no queues.
        Events flow directly from WebSocket -> Connector -> here -> Engine.
        """
        try:
            symbol = ticker_data.get("symbol", "")

            # Filter: only process subscribed symbols
            norm_symbol = normalize_symbol(symbol)
            if norm_symbol not in self._subscribed_symbols:
                return

            # Track last tick time for health monitoring
            if not hasattr(self, "_last_tick_time"):
                self._last_tick_time = {}
            self._last_tick_time[norm_symbol] = time.time()

            # Dispatch to engine (same as legacy on_ticker)
            await self.on_ticker(ticker_data)

        except Exception as e:
            logger.debug(f"⚠️ Push tick error: {e}")

    async def _subscribe_and_watch(self, symbol: str):
        """Phase 37: Subscribe to ticker stream and optionally start legacy loop.

        In push mode, this just subscribes. In legacy mode, falls back to polling.
        """
        norm_symbol = normalize_symbol(symbol)

        try:
            # Subscribe to the ticker stream
            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "subscribe_ticker"):
                await self.adapter.connector.subscribe_ticker(symbol)
                logger.debug(f"📡 Subscribed to ticker: {norm_symbol}")

            # In push mode, we're done - connector will push events
            if getattr(self, "_push_mode", False):
                # Just keep this task alive for cleanup tracking
                while self.running:
                    await asyncio.sleep(60)
            else:
                # Legacy mode: fall back to polling loop
                await self._watch_ticker_loop(symbol)

        except asyncio.CancelledError:
            logger.debug(f"📡 Subscription cancelled for {norm_symbol}")
        except Exception as e:
            logger.error(f"❌ Subscription error for {norm_symbol}: {e}")

    async def subscribe_ticker(self, symbol: str):
        """Subscribe to ticker updates for a symbol."""
        norm_symbol = normalize_symbol(symbol)
        self._subscribed_symbols.add(norm_symbol)

        # Phase 37/410: Lazy push callback registration (once, on first subscription)
        if not hasattr(self, "_push_mode"):
            if hasattr(self.adapter, "connector"):
                if hasattr(self.adapter.connector, "set_tick_callback"):
                    self.adapter.connector.set_tick_callback(self._on_push_tick)
                    logger.info("✅ Push-based tick dispatch enabled")
                    self._push_mode = True
                    # Auto-enable running when push mode is activated (connect() wasn't called)
                    if not self.running:
                        self.running = True
                        logger.info("✅ StreamManager auto-started in push mode")

                if hasattr(self.adapter.connector, "set_depth_callback"):
                    self.adapter.connector.set_depth_callback(self._on_push_depth)
                    logger.info("✅ Push-based depth dispatch enabled")
            else:
                logger.warning("⚠️ Connector doesn't support push mode, using legacy loops")
                self._push_mode = False

        if self.running:
            task_key = f"sub_{norm_symbol}"
            if task_key in self._tasks:
                return
            logger.info(f"📡 Subscribing to ticker: {norm_symbol}")
            self._tasks[task_key] = asyncio.create_task(self._subscribe_and_watch(norm_symbol))
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

    async def subscribe_depth(self, symbol: str, levels: int = 5):
        """
        Specialized subscription for Fast-Track Execution depth cache (Phase 230).
        This does NOT start a loop; it tells the connector to start caching depth.
        """
        norm_symbol = normalize_symbol(symbol)
        if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "subscribe_depth"):
            await self.adapter.connector.subscribe_depth(symbol, levels)
            logger.info(f"📡 Depth Caching Enabled for {norm_symbol} (levels={levels})")

    async def unsubscribe_all(self, symbol: str):
        """
        Unsubscribe from all streams for a symbol.
        Used by Liquidity Watchdog to quarantine symbols.
        """
        norm_symbol = normalize_symbol(symbol)
        logger.info(f"🛑 Unsubscribing from all streams for {norm_symbol}...")

        # Remove from set
        self._subscribed_symbols.discard(norm_symbol)
        self._disabled_symbols.add(norm_symbol)  # Mark as disabled/quarantined

        # Cancel tasks
        for prefix in ["ticker", "ob", "trades"]:
            task_key = f"{prefix}_{norm_symbol}"
            if task_key in self._tasks:
                task = self._tasks.pop(task_key)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info(f"✅ Cancelled {task_key}")

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
            # LINK: Register recovery callback to trigger hard_reset on stall
            watchdog.register(f"stream_{symbol}", timeout=120.0, recovery_callback=self._trigger_adapter_reset)

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

                # Create and dispatch TickEvent with REAL side (BUY/SELL)
                normalized_symbol = normalize_symbol(symbol)
                event = TickEvent(
                    type=EventType.TICK,
                    timestamp=trade["timestamp"] / 1000.0,
                    symbol=normalized_symbol,
                    price=trade["price"],
                    volume=trade["amount"],
                    side=trade["side"].upper(),  # Ensure uppercase BUY/SELL
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
        # Phase 410 Fix: Support both 'last' (TICK) and 'price' (TRADE)
        price = float(ticker.get("last") or ticker.get("price") or 0.0)

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
            # logger.debug(f"⚡ Tick: {symbol} {price}") # DISABLED to prevent log explosion in MULTI mode
            self._last_price[symbol] = price

        # Periodic throughput log (every 1000 total ticks across all symbols)
        if self._tick_count % 1000 == 0:
            logger.info(f"📊 Market Feed: Processed {self._tick_count} total ticks")

        # Ticker events are still useful for price updates, but we now accurately capture
        # side and volume from real trades when available (Phase 410 Fix)
        # Ticker events should use standardized BUY/SELL
        raw_side = ticker.get("side", "UNKNOWN").upper()
        if raw_side in ["BUY", "ASK"]:
            side = "BUY"
        elif raw_side in ["SELL", "BID"]:
            side = "SELL"
        else:
            side = "UNKNOWN"

        event = TickEvent(
            type=EventType.TICK,
            timestamp=ticker["timestamp"] / 1000.0,
            symbol=symbol,
            price=price,
            volume=float(ticker.get("volume") or ticker.get("amount") or 0.0),
            side=side,
        )
        await self.engine.dispatch(event)

    async def _trigger_adapter_reset(self):
        """
        Trigger a hard reset of the adapter's connector.
        Protected by a lock to prevent concurrent reset storms.
        """
        if self._reset_lock.locked():
            logger.warning("🔄 Hard reset already in progress, skipping redundant trigger.")
            return

        async with self._reset_lock:
            logger.critical("🚨 StreamManager: Systemic stall detected! Triggering Hard Reset...")
            try:
                if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "hard_reset"):
                    success = await self.adapter.connector.hard_reset()
                    if success:
                        logger.info("✅ Hard Reset successful. Monitoring for recovery...")
                        # Clear disabled symbols as they might recover now
                        self._disabled_symbols.clear()
                    else:
                        logger.error("❌ Hard Reset returned failure status.")
                else:
                    logger.error("❌ Adapter/Connector does not support hard_reset().")
            except Exception as e:
                logger.error(f"❌ Error during hard reset: {e}", exc_info=True)
