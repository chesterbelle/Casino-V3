"""
Multi-Asset Manager & Flytest Logic.
Responsible for validating symbols before the bot starts in MULTI mode.
"""

import asyncio
import logging
from typing import Dict, List, Tuple

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

    async def run_flytest(
        self,
        target_symbols: List[str],
        total_balance: float,
        bet_size: float,
        sizing_mode: str = "FIXED_NOTIONAL",
        stop_loss: float = 0.01,
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

        Returns:
            Tuple[List[str], Dict]: (valid symbols, precision_profile)
        """
        logger.info(f"✈️ Starting Flytest for {len(target_symbols)} symbols...")
        logger.info(f"💰 Balance: {total_balance:.2f} | Bet Size: {bet_size:.2%}")

        valid_symbols = []
        precision_profile = {}

        # Pre-fetch all tickers and book tickers for efficiency
        logger.info("📊 Pre-fetching market data for validation...")
        try:
            # Get bulk 24h tickers (Volume)
            all_tickers = await self.adapter.fetch_tickers()
            # Get bulk book tickers (Spread)
            all_books = {}
            if hasattr(self.adapter, "fetch_book_tickers"):
                all_books = await self.adapter.fetch_book_tickers()

            logger.info(f"📊 Market data pre-fetched: {len(all_tickers)} 24h tickers, {len(all_books)} book tickers.")
        except Exception as e:
            logger.error(f"❌ Failed to pre-fetch market data: {e}")
            return [], {}

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
                    logger.warning(
                        f"❌ Rejected {target_symbol}: Calculated Notional ({alloc_per_pos:.2f}) < "
                        f"Exchange Min Notional ({min_req:.2f})"
                    )
                    continue

                # B. Load precision data from Exchange
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
                        logger.warning(
                            f"❌ Rejected {target_symbol}: Low 24h Volume (${quote_vol:,.0f} < ${min_vol:,.0f})"
                        )
                        continue

                    # C2. Spread Check
                    if bid > 0 and ask > 0:
                        spread_pct = (ask - bid) / ((ask + bid) / 2)
                        if spread_pct > max_spread_pct:
                            logger.warning(
                                f"❌ Rejected {symbol}: Wide Spread ({spread_pct:.2%} > {max_spread_pct:.2%})"
                            )
                            continue

                        # Use midpoint as reference price if last is missing
                        if price == 0:
                            price = (bid + ask) / 2
                    else:
                        logger.warning(f"❌ Rejected {symbol}: Invalid Order Book (Empty Bid/Ask)")
                        continue

                    # C3. LOT_SIZE check
                    min_qty = step_size  # Minimum is 1 step
                    min_tradeable_value = min_qty * price

                    if alloc_per_pos < min_tradeable_value:
                        logger.warning(
                            f"❌ Rejected {symbol}: Bet ({alloc_per_pos:.2f}) < Min Tradeable "
                            f"({min_tradeable_value:.2f} = {min_qty} × ${price:.2f})"
                        )
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

                except Exception as e:
                    logger.warning(f"❌ Rejected {symbol}: Failed to validate market depth/liquidity ({e})")
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
