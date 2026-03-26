"""
Multi-Asset Manager & Flytest Logic.
Responsible for validating symbols before the bot starts in MULTI mode.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Minimum order limits (approximate fallback if exchange fetch fails)
MIN_NOTIONAL = {"BTC": 100.0, "ETH": 20.0, "LTC": 10.0, "SOL": 10.0, "BNB": 10.0, "default": 10.0}

# Default precision fallback (3 decimals)
DEFAULT_STEP_SIZE = 0.001


class MultiAssetManager:
    """
    Manages multi-asset configuration and pre-flight validation (Flytest).

    Now also builds a PRECISION PROFILE during flytest for optimal order sizing.
    """

    def __init__(self, exchange_adapter):
        self.adapter = exchange_adapter
        self.precision_profile: Dict[str, Dict] = {}
        self._watchdog_task = None

    async def run_flytest(
        self,
        target_symbols: List[str],
        total_balance: float,
        bet_size: float,
        sizing_mode: str = "FIXED_NOTIONAL",
        stop_loss: float = 0.01,
        fast_track: bool = False,
    ) -> Tuple[List[str], Dict[str, Dict]]:
        """
        Run pre-flight checks on target symbols and build precision profile.

        Checks:
        1. Balance sufficiency (Actual Bet Size > Min Notional)
        2. Precision Profile (step_size from exchange)

        Args:
            target_symbols: List of symbols to check
            total_balance: Total account balance
            bet_size: Bet size as fraction of equity (e.g., 0.01 = 1%)
            sizing_mode: "FIXED_NOTIONAL" or "FIXED_RISK"
            stop_loss: Stop loss fraction (used for FIXED_RISK)
            fast_track: Bypass REST initialization logic for parity
        Returns:
            Tuple[List[str], Dict]: (valid symbols, precision_profile)
        """
        logger.info(f"✈️ Starting Flytest for {len(target_symbols)} symbols... (FastTrack: {fast_track})")
        logger.info(f"💰 Balance: {total_balance:.2f} | Bet Size: {bet_size:.2%}")

        valid_symbols = []
        precision_profile = {}
        rejections = {}  # reason -> count

        # Pre-fetch all tickers and book tickers for efficiency
        all_tickers = {}
        all_books = {}

        if not fast_track:
            logger.info("📊 Pre-fetching market data for validation...")
            try:
                # Get bulk 24h tickers (Volume)
                all_tickers = await self.adapter.fetch_tickers()
                # Get bulk book tickers (Spread)
                if hasattr(self.adapter, "fetch_book_tickers"):
                    all_books = await self.adapter.fetch_book_tickers()

                logger.info(
                    f"📊 Market data pre-fetched: {len(all_tickers)} 24h tickers, {len(all_books)} book tickers."
                )
            except Exception as e:
                logger.error(f"❌ Failed to pre-fetch market data: {e}")
                return [], {}
        else:
            logger.info("⏭️ Bypassing bulk market data fetch in FastTrack mode.")

        # Calculate actual bet amount based on sizing mode
        if sizing_mode == "FIXED_RISK":
            # In FIXED_RISK: Position Value = (Equity * BetSize) / SL
            # E.g. (1000 * 0.01) / 0.01 = 1000
            if stop_loss <= 0:
                logger.error("❌ Invalid Stop Loss for FIXED_RISK validation")
                stop_loss = 0.01  # Fallback

            alloc_per_pos = (total_balance * bet_size) / stop_loss
            logger.info(
                f"⚖️ Sizing Mode: FIXED_RISK | Risk Amount: {total_balance * bet_size:.2f} "
                f"({bet_size:.2%}) | SL: {stop_loss:.2%} | Target Notional: {alloc_per_pos:.2f} USDT"
            )
        else:
            # FIXED_NOTIONAL (Default)
            alloc_per_pos = total_balance * bet_size
            logger.info(f"💵 Sizing Mode: FIXED_NOTIONAL | Actual bet per position: {alloc_per_pos:.2f} USDT")

        # Check each symbol
        for target_symbol in target_symbols:
            try:
                # Normalize symbol to match connector output (e.g. SXP/USDT -> SXP/USDT:USDT)
                # This ensures we find it in the pre-fetched maps
                symbol = target_symbol
                if hasattr(self.adapter, "normalize_symbol"):
                    # First normalize to exchange format, then denormalize to unified
                    native = self.adapter.normalize_symbol(target_symbol)
                    symbol = self.adapter.denormalize_symbol(native)

                # A. Minimum Notional Check
                # Use dynamic min_notional from adapter if available
                min_req = MIN_NOTIONAL["default"]
                if hasattr(self.adapter, "get_min_notional"):
                    try:
                        # Check if it's a coroutine or sync function
                        # BinanceNative.get_min_notional is sync
                        res = self.adapter.get_min_notional(target_symbol)
                        if asyncio.iscoroutine(res):
                            sym_min = await res
                        else:
                            sym_min = res

                        if sym_min and sym_min > 0:
                            min_req = sym_min
                    except Exception as e:
                        logger.warning(f"⚠️ Could not fetch dynamic min_notional for {target_symbol}: {e}")

                if alloc_per_pos < min_req:
                    reason = "Min Notional"
                    logger.warning(
                        f"❌ Rejected {target_symbol}: {reason} ({alloc_per_pos:.2f}) < "
                        f"Exchange Min Notional ({min_req:.2f})"
                    )
                    rejections[reason] = rejections.get(reason, 0) + 1
                    continue

                # B. Load precision data from Exchange
                # Phase 102: Adaptive Throttling
                await self._check_rate_limit_throttle()
                step_size = await self._get_step_size(target_symbol)
                tick_size = await self._get_tick_size(target_symbol)

                # C. Liquidity Checks (Hardened)
                try:
                    # Use pre-fetched ticker data with normalized symbol
                    ticker = all_tickers.get(symbol, {})
                    book = all_books.get(symbol, {})

                    price = ticker.get("last", 0)
                    bid = book.get("bid", 0)
                    ask = book.get("ask", 0)
                    quote_vol = ticker.get("quote_volume", 0)

                    # Import thresholds inside loop for flexibility
                    from config import trading as trading_config

                    min_vol = getattr(trading_config, "FLYTEST_MIN_24H_VOLUME_USDT", 250000.0)
                    max_spread_pct = getattr(trading_config, "FLYTEST_MAX_SPREAD_PCT", 0.008)

                    # C1. Volume Check
                    if quote_vol < min_vol:
                        reason = "Low 24h Volume"
                        logger.warning(f"❌ Rejected {target_symbol}: {reason} (${quote_vol:,.0f} < ${min_vol:,.0f})")
                        rejections[reason] = rejections.get(reason, 0) + 1
                        continue

                    # C2. Spread Check
                    if bid > 0 and ask > 0:
                        spread_pct = (ask - bid) / ((ask + bid) / 2)
                        if spread_pct > max_spread_pct:
                            reason = "Wide Spread"
                            logger.warning(f"❌ Rejected {symbol}: {reason} ({spread_pct:.2%} > {max_spread_pct:.2%})")
                            rejections[reason] = rejections.get(reason, 0) + 1
                            continue

                        # Use midpoint as reference price if last is missing
                        if price == 0:
                            price = (bid + ask) / 2
                    else:
                        reason = "Invalid Order Book"
                        logger.warning(f"❌ Rejected {symbol}: {reason} (Empty Bid/Ask)")
                        rejections[reason] = rejections.get(reason, 0) + 1
                        continue

                    # C3. LOT_SIZE check
                    min_qty = step_size  # Minimum is 1 step
                    min_tradeable_value = min_qty * price

                    if alloc_per_pos < min_tradeable_value:
                        reason = "Below Min Tradeable"
                        logger.warning(
                            f"❌ Rejected {symbol}: {reason} Bet ({alloc_per_pos:.2f}) < Min Tradeable "
                            f"({min_tradeable_value:.2f} = {min_qty} × ${price:.2f})"
                        )
                        rejections[reason] = rejections.get(reason, 0) + 1
                        continue

                    # C4. PRICE_FILTER (tick_size) check
                    if price > 0 and tick_size >= price:
                        logger.warning(
                            f"❌ Rejected {symbol}: tick_size ({tick_size}) >= current price ({price})! Market is broken."
                        )
                        continue

                    # C5. Precision rounding check
                    min_tp_pct = 0.005  # 0.5% minimum sanity check
                    if (price * min_tp_pct) < tick_size:
                        logger.warning(
                            f"❌ Rejected {symbol}: Price granularity too low. "
                            f"0.5% TP ({price * min_tp_pct:.6f}) < tick_size ({tick_size})"
                        )
                        continue

                    # C6. Depth Check (Flytest 2.0 - The "Pool" Rule)
                    if hasattr(self.adapter, "fetch_order_book"):
                        # Fetch L2 Order Book (Limit 50 is sufficient for 1% depth usually)
                        order_book = await self.adapter.fetch_order_book(symbol, limit=50)

                        is_deep_enough = self._check_depth_sufficiency(symbol, alloc_per_pos, order_book, price)

                        if not is_deep_enough:
                            reason = "Shallow Liquidity"
                            rejections[reason] = rejections.get(reason, 0) + 1
                            continue  # Logged inside the method

                    # C7. Stream Liveness Check (Phase 37)
                    # Verify that the symbol actually streams WebSocket data
                    # Some testnet symbols exist in exchangeInfo but don't transmit
                    stream_liveness_timeout = getattr(trading_config, "FLYTEST_STREAM_LIVENESS_TIMEOUT", 10.0)
                    if not fast_track and stream_liveness_timeout > 0:
                        is_live = await self._check_stream_liveness(target_symbol, stream_liveness_timeout)
                        if not is_live:
                            reason = "Stream Liveness Failed"
                            logger.warning(
                                f"❌ Rejected {symbol}: {reason} " f"(no ticker received in {stream_liveness_timeout}s)"
                            )
                            rejections[reason] = rejections.get(reason, 0) + 1
                            # Phase 93: Cleanup subscription for failed liveness
                            if hasattr(self.adapter.connector, "unsubscribe_ticker"):
                                await self.adapter.connector.unsubscribe_ticker(target_symbol)
                            continue

                except Exception as e:
                    logger.warning(f"❌ Rejected {symbol}: Failed to validate market depth/liquidity ({e})")
                    # Phase 93: Cleanup subscription on exception
                    if hasattr(self.adapter.connector, "unsubscribe_ticker"):
                        await self.adapter.connector.unsubscribe_ticker(target_symbol)
                    continue  # STRICT: No fallback, skip this symbol

                # D. Store precision profile
                decimals_step = len(str(step_size).rstrip("0").split(".")[-1]) if "." in str(step_size) else 0
                decimals_tick = len(str(tick_size).rstrip("0").split(".")[-1]) if "." in str(tick_size) else 0

                precision_profile[symbol] = {
                    "step_size": step_size,
                    "tick_size": tick_size,
                    "decimals_step": decimals_step,
                    "decimals_tick": decimals_tick,
                }
                logger.info(f"📐 {symbol}: step_size={step_size}, tick_size={tick_size}")

                valid_symbols.append(symbol)
                logger.info(f"✅ {symbol} passed Flytest.")

            except Exception as e:
                logger.error(f"⚠️ Error checking {symbol}: {e}")

        # Store profile in adapter for use during order execution
        if hasattr(self.adapter, "set_precision_profile"):
            self.adapter.set_precision_profile(precision_profile)
        self.precision_profile = precision_profile

        logger.info(f"🏁 Flytest Complete: {len(valid_symbols)}/{len(target_symbols)} symbols qualified.")
        if rejections:
            logger.info("📊 Rejection Summary:")
            for reason, count in sorted(rejections.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"   • {reason}: {count}")
        return valid_symbols, precision_profile

    async def _get_step_size(self, symbol: str) -> float:
        """
        Get step_size for a symbol from the exchange.
        Falls back to DEFAULT_STEP_SIZE if not available.
        """
        try:
            # Try to get from connector's _markets cache
            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "_markets"):
                native_symbol = symbol.replace("/", "").replace(":USDT", "").upper()
                markets = self.adapter.connector._markets
                if native_symbol in markets:
                    step = markets[native_symbol].get("step_size", DEFAULT_STEP_SIZE)
                    return step if step and step > 0 else DEFAULT_STEP_SIZE

            # Fallback
            return DEFAULT_STEP_SIZE
        except Exception as e:
            logger.warning(f"⚠️ Could not get step_size for {symbol}: {e}. Using default.")
            return DEFAULT_STEP_SIZE

    async def _get_tick_size(self, symbol: str) -> float:
        """
        Get tick_size for a symbol from the exchange.
        """
        try:
            if hasattr(self.adapter, "connector") and hasattr(self.adapter.connector, "_markets"):
                native_symbol = symbol.replace("/", "").replace(":USDT", "").upper()
                markets = self.adapter.connector._markets
                if native_symbol in markets:
                    tick = markets[native_symbol].get("tick_size", 0.01)
                    return tick if tick and tick > 0 else 0.01
            return 0.01
        except Exception:
            return 0.01

    def get_multi_config(self) -> List[str]:
        """
        Get the list of target symbols for MULTI mode.
        Reads from config.trading.MULTI_ASSET_TARGETS.
        """
        try:
            from config.trading import MULTI_ASSET_TARGETS

            return MULTI_ASSET_TARGETS
        except ImportError:
            # Fallback if config version mismatch
            return ["LTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BTC/USDT:USDT"]

    def _check_depth_sufficiency(self, symbol: str, bet_size: str, book: Dict[str, Any], current_price: float) -> bool:
        """
        Flytest 2.0: Check if "Pool" is deep enough.
        Rule: Must have [FLYTEST_MIN_DEPTH_MULT]x bet size within [FLYTEST_DEPTH_CHECK_PCT]% range.

        Returns: True if passed, False if rejected.
        """
        try:
            from config import trading as trading_config

            min_depth_mult = getattr(trading_config, "FLYTEST_MIN_DEPTH_MULT", 3.0)
            check_pct = getattr(trading_config, "FLYTEST_DEPTH_CHECK_PCT", 0.01)

            required_liquidity = bet_size * min_depth_mult

            # 1. Check Bids (Support)
            # Sum value of bids >= (price * (1 - pct))
            bid_cutoff = current_price * (1 - check_pct)
            total_bids_value = 0.0
            for b_price, b_qty in book.get("bids", []):
                if b_price < bid_cutoff:
                    break  # Sorted descending
                total_bids_value += b_price * b_qty

            # 2. Check Asks (Resistance)
            # Sum value of asks <= (price * (1 + pct))
            ask_cutoff = current_price * (1 + check_pct)
            total_asks_value = 0.0
            for a_price, a_qty in book.get("asks", []):
                if a_price > ask_cutoff:
                    break  # Sorted ascending
                total_asks_value += a_price * a_qty

            # 3. Validate
            if total_bids_value < required_liquidity:
                logger.warning(
                    f"❌ Rejected {symbol}: Shallow Bids. Found ${total_bids_value:.0f} < Required ${required_liquidity:.0f} (3x Bet) "
                    f"within {check_pct:.1%}% range."
                )
                return False

            if total_asks_value < required_liquidity:
                logger.warning(
                    f"❌ Rejected {symbol}: Shallow Asks. Found ${total_asks_value:.0f} < Required ${required_liquidity:.0f} (3x Bet) "
                    f"within {check_pct:.1%}% range."
                )
                return False

            logger.info(
                f"💧 Depth OK {symbol}: Bids=${total_bids_value:.0f} Asks=${total_asks_value:.0f} "
                f"(> ${required_liquidity:.0f})"
            )
            return True

        except Exception as e:
            logger.warning(f"⚠️ Depth check error for {symbol}: {e}")
            return False

    async def _check_stream_liveness(self, symbol: str, timeout: float = 5.0) -> bool:
        """
        Phase 37: Stream Liveness Check.

        Verifies that Binance actually streams WebSocket data for this symbol.
        Some testnet symbols exist in exchangeInfo but don't transmit data.

        Args:
            symbol: Symbol to check
            timeout: Max seconds to wait for a ticker

        Returns:
            True if a ticker was received, False if timeout
        """
        import asyncio

        try:
            # Use the adapter's watch_ticker which subscribes and waits for data
            if not hasattr(self.adapter, "watch_ticker"):
                logger.debug(f"⚠️ Adapter doesn't support watch_ticker, skipping liveness check for {symbol}")
                return True  # Skip check if not supported

            # Try to get a ticker within the timeout
            ticker = await asyncio.wait_for(self.adapter.watch_ticker(symbol), timeout=timeout)

            if ticker and ticker.get("last", 0) > 0:
                logger.debug(f"✅ Stream liveness OK for {symbol}: price={ticker.get('last')}")
                return True
            else:
                logger.warning(f"⚠️ Stream liveness: empty ticker for {symbol}")
                return False

        except asyncio.TimeoutError:
            logger.debug(f"⚠️ Stream liveness timeout for {symbol} ({timeout}s)")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Stream liveness error for {symbol}: {e}")
            return False

    async def start_liquidity_watchdog(
        self,
        active_list: List[str],
        on_remove_callback,
        interval: int = 300,
        bet_size_pct: float = 0.01,
    ):
        """
        Start the continuous liquidity monitoring loop (Watchdog).
        Re-checks depth every [interval] seconds.
        """
        logger.info(f"🐶 Liquidity Watchdog started (Interval: {interval}s)")

        while True:
            try:
                await asyncio.sleep(interval)

                if not active_list:
                    logger.warning("🐶 Watchdog: No active symbols to monitor.")
                    continue

                logger.info("🐶 Watchdog: Checking liquidity for active symbols...")

                # 1. Fetch current balance to calculate required depth
                try:
                    bal_data = await self.adapter.fetch_balance()
                    total_balance = bal_data.get("total", {}).get("USDT", 0)
                except Exception as e:
                    logger.warning(f"🐶 Watchdog failed to fetch balance: {e}. Skipping cycle.")
                    continue

                alloc_per_pos = total_balance * bet_size_pct

                # 2. Check each symbol
                # Use a copy to iterate safely while modifying original list
                for symbol in list(active_list):
                    if not hasattr(self.adapter, "fetch_order_book"):
                        continue

                    # Phase 102: Adaptive Throttling
                    await self._check_rate_limit_throttle()
                    try:
                        # Fetch price first (needed for depth check)
                        ticker = await self.adapter.fetch_ticker(symbol)
                        price = float(ticker.get("last", 0))

                        if price <= 0:
                            continue

                        # Fetch book
                        book = await self.adapter.fetch_order_book(symbol, limit=50)

                        # Reuse the core logic
                        is_ok = self._check_depth_sufficiency(symbol, alloc_per_pos, book, price)

                        if not is_ok:
                            logger.warning(f"💀 Liquidity Watchdog: KILLING {symbol} (Insufficient Liquidity)")

                            # Execute removal action
                            if asyncio.iscoroutinefunction(on_remove_callback):
                                await on_remove_callback(symbol)
                            else:
                                on_remove_callback(symbol)

                            # Remove from list if not already removed by callback
                            if symbol in active_list:
                                active_list.remove(symbol)

                    except Exception as e:
                        logger.error(f"🐶 Watchdog error checking {symbol}: {e}")

            except asyncio.CancelledError:
                logger.info("🐶 Liquidity Watchdog stopped.")
                break
            except Exception as e:
                logger.error(f"🐶 Watchdog main loop error: {e}")
                await asyncio.sleep(60)  # Pause on error

    async def _check_rate_limit_throttle(self):
        """Phase 102: Industrial Resilience - Adaptive Throttling."""
        if not hasattr(self.adapter, "get_load_factor"):
            return

        load = self.adapter.get_load_factor()
        if load > 0.8:
            # 80-90% -> 1s delay
            # 90-100% -> 3s delay
            delay = 3.0 if load > 0.9 else 1.0
            logger.warning(f"⚠️ Exchange load high ({load:.2%}). Throttling Flytest for {delay}s...")
            await asyncio.sleep(delay)
