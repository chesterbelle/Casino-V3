"""
Trading Flow Validator - Rigorous Preflight Test
-------------------------------------------------
CRITICAL: This validator must pass before the bot can operate safely.

Tests the complete bot lifecycle to ensure:
- Order execution works correctly
- OCO brackets (main + TP + SL) are created atomically
- Positions are tracked accurately
- Orders can be cancelled reliably
- cleanup_symbol properly cleans orphaned orders/positions
- Shutdown flow works correctly

This mirrors the actual bot flow from main.py to catch issues
before they cause orphaned orders or positions in production.

Usage:
    python -m utils.validators.trading_flow_validator \\
        --exchange binance \\
        --symbol LTCUSDT \\
        --mode demo \\
        --size 0.05 \\
        --execute-orders
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from croupier.components.reconciliation_service import ReconciliationService
from croupier.croupier import Croupier
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/preflight_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
    )

    # Enable DEBUG for critical components
    logging.getLogger("OCOManager").setLevel(logging.DEBUG)
    logging.getLogger("BinanceNativeConnector").setLevel(logging.DEBUG)
    logging.getLogger("OrderExecutor").setLevel(logging.DEBUG)
    logging.getLogger("Croupier").setLevel(logging.DEBUG)
    logging.getLogger("ReconciliationService").setLevel(logging.DEBUG)


logger = logging.getLogger("PreflightValidator")


class PreflightValidator:
    """
    Rigorous preflight test that mirrors the bot's actual flow.

    CRITICAL: If any test fails, the bot should NOT be started.
    """

    def __init__(self, exchange_id="binance", symbol="LTCUSDT", mode="demo", size=0.05):
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.mode = mode
        self.size = size
        self.test_results: Dict[str, bool] = {}

        # Load credentials
        load_dotenv()
        if mode == "demo":
            api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            secret = os.getenv("BINANCE_TESTNET_SECRET")
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not secret:
            raise ValueError(f"Missing API keys for mode {mode}")

        # Setup connector (matches main.py)
        self.connector = BinanceNativeConnector(
            api_key=api_key,
            secret=secret,
            mode=mode,
            enable_websocket=True,  # Same as bot
        )

        self.adapter = None
        self.croupier = None
        self.initial_balance = 0.0

    async def setup(self):
        """
        Initialize components exactly as main.py does.
        This ensures we test the same code paths.
        """
        logger.info("=" * 70)
        logger.info(" PREFLIGHT VALIDATOR - SETUP")
        logger.info("=" * 70)
        logger.info(f"Exchange: {self.exchange_id.upper()} | Symbol: {self.symbol} | Mode: {self.mode}")

        # 1. Connect (matches main.py line 143)
        logger.info("🔌 Connecting to exchange...")
        await self.connector.connect()
        logger.info("✅ Connected")

        # 2. Create adapter (matches main.py line 136)
        self.adapter = ExchangeAdapter(self.connector, self.symbol)
        logger.info("✅ Adapter created")

        # 3. Fetch balance (matches main.py line 144-145)
        balance_data = await self.connector.fetch_balance()
        self.initial_balance = balance_data.get("total", {}).get("USDT", 0.0)

        if self.initial_balance < 10:
            raise ValueError(f"Insufficient balance: ${self.initial_balance:.2f}")

        logger.info(f"💰 Balance: ${self.initial_balance:,.2f}")

        # 4. Create croupier (matches main.py line 148)
        self.croupier = Croupier(exchange_adapter=self.adapter, initial_balance=self.initial_balance)
        # LIFECYCLE SUPPORT: Initialize Reconciliation Service for GC (Phase 48)
        self.recon_service = ReconciliationService(
            self.adapter, self.croupier.position_tracker, self.croupier.oco_manager, self.croupier
        )
        self.croupier.reconciliation_service = self.recon_service
        logger.info("✅ Croupier & Reconciliation initialized")

        # 4.1 Register order update callback (matches main.py)
        # This is CRITICAL for PositionTracker to see fills and close positions!
        async def async_order_update_handler(order):
            self.croupier.position_tracker.handle_order_update(order)
            await self.croupier.oco_manager.on_order_update(order)

        self.connector.set_order_update_callback(async_order_update_handler)
        logger.info("✅ Order update callback registered")

        # 4.2 Signal Handling (Phase 243 Resilience)
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, lambda: asyncio.create_task(self.shutdown_handler()))

        # 5. Pre-test cleanup - ensure clean slate
        await self._force_cleanup()
        logger.info("✅ Setup complete\n")

    async def shutdown_handler(self):
        """Signal handler for graceful shutdown."""
        logger.warning("⚠️ Signal received. Initiating emergency response...")
        await self._force_cleanup()
        sys.exit(0)

    async def _force_cleanup(self):
        """Phase 243: Force cleanup using emergency_sweep governance."""
        logger.info("🧹 Initiating Global Emergency Sweep...")
        if self.croupier:
            # Set shutdown mode to suppress ExitManager triggers
            self.croupier.error_handler.shutdown_mode = True
            await self.croupier.emergency_sweep(close_positions=True)
            logger.info("✅ Emergency sweep complete.")
        else:
            # Fallback legacy cleanup if croupier not ready
            logger.warning("⚠️ Croupier not initialized, using legacy fallback cleanup.")
            try:
                # [Legacy fallback code omitted for brevity in thought, but included in actual tool call]
                positions = await self.connector.fetch_positions()
                for pos in positions:
                    pos_symbol = pos.get("symbol", "")
                    is_match = pos_symbol == self.symbol or pos_symbol.split(":")[0].replace("/", "") == self.symbol
                    if is_match:
                        size = abs(float(pos.get("contracts") or pos.get("size") or 0))
                        if size > 0:
                            side_str = str(pos.get("side", "")).upper()
                            target_side = "sell" if side_str == "LONG" else "buy"
                            await self.connector.create_order(
                                symbol=self.symbol, order_type="market", side=target_side, amount=size
                            )
                open_orders = await self.connector.fetch_open_orders(self.symbol)
                for order in open_orders:
                    await self.connector.cancel_order(order["id"], self.symbol)
            except Exception as e:
                logger.warning(f"⚠️ Legacy cleanup error: {e}")

    # =========================================================================
    # TEST 1: Connection & Basic Operations
    # =========================================================================
    async def test_1_connection(self) -> bool:
        """Test exchange connection and basic operations."""
        logger.info("=" * 70)
        logger.info("TEST 1: Connection & Basic Operations")
        logger.info("=" * 70)

        try:
            # Verify connection
            assert self.connector.is_connected, "Connector not connected"

            # Fetch current price
            price = await self.adapter.get_current_price(self.symbol)
            assert price > 0, f"Invalid price: {price}"
            logger.info(f"✅ Current price: {price:.2f}")

            # Fetch open orders
            orders = await self.connector.fetch_open_orders(self.symbol)
            logger.info(f"✅ Open orders check: {len(orders)} orders")

            # Fetch positions
            positions = await self.connector.fetch_positions()
            symbol_positions = [
                p
                for p in positions
                if p.get("symbol") == self.symbol or p.get("symbol", "").split(":")[0].replace("/", "") == self.symbol
            ]
            logger.info(f"✅ Positions check: {len(symbol_positions)} positions")

            logger.info("✅ TEST 1 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 1 FAILED: {e}")
            return False

    # =========================================================================
    # TEST 2: Single Order Execution & Cancellation
    # =========================================================================
    async def test_2_order_execution_and_cancel(self) -> bool:
        """Test order execution and cancellation - CRITICAL for cleanup."""
        logger.info("=" * 70)
        logger.info("TEST 2: Order Execution & Cancellation")
        logger.info("=" * 70)

        order_id = None
        try:
            # Get current price
            price = await self.adapter.get_current_price(self.symbol)

            # Calculate limit price far from market (won't fill)
            limit_price = round(price * 0.90, 2)  # 10% below

            # Create limit order via OrderExecutor
            # Dynamic sizing: Ensure > 100 USD (Binance Testnet restriction observed)
            target_notional = 110.0

            # 1. Calculate raw amount
            raw_amount = target_notional / limit_price

            # 2. Get Precision
            # If adapter has precision info, ensure we meet min quantity
            test_amount = float(self.adapter.amount_to_precision(self.symbol, raw_amount))

            # 3. Last resort safety check for BTC (if amount is 0 due to truncation)
            if test_amount == 0.0:
                logger.warning(f"⚠️ Calculated test amount was 0.0 (Price: {limit_price}). Forcing 0.001 minimum.")
                test_amount = 0.001

            logger.info(f"📤 Creating limit order: buy {test_amount} @ {limit_price}")
            result = await self.croupier.order_executor.execute_limit_order(
                symbol=self.symbol, side="buy", amount=test_amount, price=limit_price
            )

            order_id = result.get("order_id") or result.get("id")
            assert order_id, "No order_id returned"
            logger.info(f"✅ Order created: {order_id}")

            # Verify order exists in exchange
            await asyncio.sleep(1)
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            order_ids = [o["id"] for o in open_orders]
            assert order_id in order_ids, f"Order {order_id} not found in exchange"
            logger.info(f"✅ Order verified in exchange")

            # Cancel the order - THIS IS CRITICAL
            logger.info(f"📤 Cancelling order: {order_id}")
            await self.adapter.cancel_order(order_id, self.symbol)

            # Verify cancellation
            await asyncio.sleep(1)
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            order_ids = [o["id"] for o in open_orders]
            assert order_id not in order_ids, f"Order {order_id} was NOT cancelled!"
            logger.info(f"✅ Order successfully cancelled")

            logger.info("✅ TEST 2 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 2 FAILED: {e}")
            # Attempt cleanup
            if order_id:
                try:
                    await self.adapter.cancel_order(order_id, self.symbol)
                except Exception:
                    pass
            return False

    # =========================================================================
    # TEST 3: OCO Bracket Creation
    # =========================================================================
    async def test_3_oco_bracket(self) -> bool:
        """Test OCO bracket creation - main + TP + SL."""
        logger.info("=" * 70)
        logger.info("TEST 3: OCO Bracket Creation (Main + TP + SL)")
        logger.info("=" * 70)

        try:
            # Create order with OCO
            # Calculate amount (Master Sizing simulation - SAFE 110 NOTIONAL)
            price = await self.adapter.get_current_price(self.symbol)
            target_notional = 110.0
            raw_amount = target_notional / price
            amount = float(self.adapter.amount_to_precision(self.symbol, raw_amount))
            if amount == 0.0:
                amount = 0.001

            # Phase 800: Create order with absolute TP/SL prices
            # This validates the full pipeline: adaptive -> execution -> oco_manager
            tp_distance_pct = 0.02  # 2% TP distance
            sl_distance_pct = 0.02  # 2% SL distance
            tp_price = round(price * (1 + tp_distance_pct), 2)
            sl_price = round(price * (1 - sl_distance_pct), 2)

            order = {
                "symbol": self.symbol,
                "side": "LONG",
                "size": self.size,
                "amount": amount,  # REQUIRED by Phase 42
                "tp_price": tp_price,  # Absolute TP price
                "sl_price": sl_price,  # Absolute SL price
                "trade_id": f"preflight_{int(time.time())}",
            }

            logger.info(f"📤 Creating OCO bracket: {order}")
            result = await self.croupier.execute_order(order)

            # Handle Phase 240: Project Supersonic async batching
            if result.get("status") == "optimistic_sent":
                position = result.get("position")
                assert position, "Optimistic launch missing position object"

                # Wait for supersonic batch to finalize in background
                timeout = 5.0
                start_t = time.time()
                while time.time() - start_t < timeout:
                    if position.tp_order_id and position.sl_order_id:
                        break
                    await asyncio.sleep(0.1)

                assert position.tp_order_id, "Supersonic batch failed to assign TP order ID"
                assert position.sl_order_id, "Supersonic batch failed to assign SL order ID"

                # For compatibility with universal funnel check:
                # We know the client IDs from the optimistic return or the position
                main_id = position.trade_id  # Actually the client_order_id for main
                tp_id = position.tp_order_id
                sl_id = position.sl_order_id

                # We need to construct a compatible result dict for the ID lookup code below
                result["main_order"] = {"client_order_id": main_id}
                result["tp_order"] = {"client_order_id": tp_id, "order_id": position.exchange_tp_id}
                result["sl_order"] = {"client_order_id": sl_id, "order_id": position.exchange_sl_id}
                result["fill_price"] = position.entry_price
            else:
                # Legacy / synchronous fallback
                assert "main_order" in result, "Missing main_order"
                assert "tp_order" in result, "Missing tp_order"
                assert "sl_order" in result, "Missing sl_order"
                assert result["fill_price"] > 0, "Invalid fill_price"

                main_id = result["main_order"].get("order_id") or result["main_order"].get("id")
                tp_id = result["tp_order"].get("order_id") or result["tp_order"].get("id")
                sl_id = result["sl_order"].get("order_id") or result["sl_order"].get("id")

            logger.info(f"✅ Main order: {main_id}")
            logger.info(f"✅ TP order: {tp_id}")
            logger.info(f"✅ SL order: {sl_id}")
            logger.info(f"✅ Fill price: {result.get('fill_price', 0):.2f}")

            # Universal Funnel Verification: Check CASINO_ Prefix
            # Note: We check the client_order_id, which is what we sent.
            # The result keys vary by exchange adapter, but usually we have 'clientOrderId' or we need to fetch it.

            # Helper to get client ID from result or fetch
            async def get_client_id(oid):
                try:
                    o = await self.connector.fetch_order(oid, self.symbol)
                    return o.get("client_order_id") or o.get("clientOrderId", "")
                except Exception as e:
                    logger.error(f"❌ Error fetching order for client ID: {e}")
                    return ""

            main_cid = (
                result["main_order"].get("client_order_id")
                or result["main_order"].get("clientOrderId")
                or await get_client_id(main_id)
            )
            tp_cid = (
                result["tp_order"].get("client_order_id")
                or result["tp_order"].get("clientOrderId")
                or await get_client_id(tp_id)
            )
            sl_cid = (
                result["sl_order"].get("client_order_id")
                or result["sl_order"].get("clientOrderId")
                or await get_client_id(sl_id)
            )

            if not main_cid.startswith("CASINO_"):
                logger.error(f"❌ Main ClientID does not start with CASINO_: {main_cid}")
                return False
            if not tp_cid.startswith("CASINO_"):
                logger.error(f"❌ TP ClientID does not start with CASINO_: {tp_cid}")
                return False
            if not sl_cid.startswith("CASINO_"):
                logger.error(f"❌ SL ClientID does not start with CASINO_: {sl_cid}")
                return False

            logger.info(f"✅ Universal Funnel Verified: All ClientIDs start with CASINO_")

            # Verify TP/SL exist in exchange
            await asyncio.sleep(2)
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            order_ids = [o["id"] for o in open_orders]

            assert tp_id in order_ids, f"TP order {tp_id} not in exchange!"
            assert sl_id in order_ids, f"SL order {sl_id} not in exchange!"
            logger.info(f"✅ TP/SL verified in exchange")

            # Phase 800: Validate TP/SL prices are within expected bounds
            fill_price = result.get("fill_price", 0)
            if fill_price > 0:
                tp_dist = abs(tp_price - fill_price) / fill_price
                sl_dist = abs(sl_price - fill_price) / fill_price
                # TP/SL should be within 0.1% - 5% of fill price
                assert 0.001 < tp_dist < 0.05, f"TP distance {tp_dist:.4%} out of bounds!"
                assert 0.001 < sl_dist < 0.05, f"SL distance {sl_dist:.4%} out of bounds!"
                logger.info(
                    f"✅ TP/SL price validation: TP={tp_price:.2f} ({tp_dist:.2%} from fill) | "
                    f"SL={sl_price:.2f} ({sl_dist:.2%} from fill)"
                )

            # Store for next tests
            self._last_result = result

            logger.info("✅ TEST 3 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 3 FAILED: {e}")
            return False

    # =========================================================================
    # TEST 4: Position Tracking
    # =========================================================================
    async def test_4_position_tracking(self) -> bool:
        """Test PositionTracker state consistency."""
        logger.info("=" * 70)
        logger.info("TEST 4: Position Tracking")
        logger.info("=" * 70)

        try:
            positions = self.croupier.position_tracker.open_positions
            assert len(positions) == 1, f"Expected 1 position, got {len(positions)}"

            pos = positions[0]
            assert self.adapter.normalize_symbol(pos.symbol) == self.adapter.normalize_symbol(
                self.symbol
            ), f"Wrong symbol: {pos.symbol}"
            assert pos.side == "LONG", f"Wrong side: {pos.side}"
            assert pos.tp_order_id is not None, "Missing TP order ID"
            assert pos.sl_order_id is not None, "Missing SL order ID"

            logger.info(f"✅ Position: {pos.trade_id}")
            logger.info(f"✅ TP ID: {pos.tp_order_id}")
            logger.info(f"✅ SL ID: {pos.sl_order_id}")

            logger.info("✅ TEST 4 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 4 FAILED: {e}")
            return False

    # =========================================================================
    # TEST 5: Close Position (Manual)
    # =========================================================================
    async def test_5_close_position(self) -> bool:
        """Test manual position close - CRITICAL for cleanup."""
        logger.info("=" * 70)
        logger.info("TEST 5: Close Position & Cancel TP/SL")
        logger.info("=" * 70)

        try:
            positions = self.croupier.position_tracker.open_positions
            assert len(positions) == 1, "No position to close"

            pos = positions[0]
            tp_id = pos.tp_order_id
            sl_id = pos.sl_order_id
            trade_id = pos.trade_id

            logger.info(f"📤 Closing position: {trade_id}")
            logger.info(f"   Expected cancellation: TP={tp_id}, SL={sl_id}")

            # Close position (should cancel TP/SL)
            await self.croupier.close_position(trade_id)

            # Trigger GC to remove OFF_BOARDING position
            logger.info("🧹 Triggering GC (ReconciliationService) to finalize removal...")
            await self.recon_service.reconcile_all()

            # Verify position removed from tracker
            await asyncio.sleep(1)
            positions = self.croupier.position_tracker.open_positions
            assert len(positions) == 0, f"Position not closed! Still {len(positions)} open"
            logger.info(f"✅ Position removed from tracker")

            # CRITICAL: Verify TP/SL were cancelled
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            order_ids = [o["id"] for o in open_orders]

            if tp_id in order_ids:
                logger.error(f"❌ TP order {tp_id} was NOT cancelled!")
                return False
            if sl_id in order_ids:
                logger.error(f"❌ SL order {sl_id} was NOT cancelled!")
                return False

            logger.info(f"✅ TP order cancelled")
            logger.info(f"✅ SL order cancelled")

            # Verify no position in exchange
            positions = await self.connector.fetch_positions()
            for pos in positions:
                pos_symbol = pos.get("symbol", "")
                is_match = pos_symbol == self.symbol or pos_symbol.split(":")[0].replace("/", "") == self.symbol
                if is_match:
                    size = abs(float(pos.get("contracts") or pos.get("size") or 0))
                    if size > 0.001:  # Small tolerance
                        logger.error(f"❌ Position still exists in exchange: {size}")
                        return False

            logger.info(f"✅ No position in exchange")

            logger.info("✅ TEST 5 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 5 FAILED: {e}")
            return False

    # =========================================================================
    # TEST 6: Orphan Detection & Cleanup
    # =========================================================================
    async def test_6_orphan_cleanup(self) -> bool:
        """Test orphan detection and cleanup_symbol method."""
        logger.info("=" * 70)
        logger.info("TEST 6: Orphan Detection & Cleanup")
        logger.info("=" * 70)

        order_ids = []
        try:
            # Create orphan orders (orders without tracked position)
            price = await self.adapter.get_current_price(self.symbol)

            # Create 2 limit orders that won't fill
            for i in range(2):
                limit_price = round(price * 0.85, 2)  # 15% below
                # Dynamic sizing: Ensure > 20 USD (ETH MinNotional is 20)
                target_notional = 25.0
                raw_amount = target_notional / limit_price
                test_amount = float(self.adapter.amount_to_precision(self.symbol, raw_amount))

                result = await self.croupier.order_executor.execute_limit_order(
                    symbol=self.symbol, side="buy", amount=test_amount, price=limit_price
                )
                order_id = result.get("order_id") or result.get("id")
                order_ids.append(order_id)
                logger.info(f"  Created orphan order: {order_id}")

            await asyncio.sleep(1)

            # Verify orders exist
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            exchange_ids = [o["id"] for o in open_orders]
            for oid in order_ids:
                assert oid in exchange_ids, f"Orphan order {oid} not in exchange"
            logger.info(f"✅ {len(order_ids)} orphan orders verified")

            # Call cleanup_symbol - should cancel all orders
            logger.info(f"📤 Calling croupier.cleanup_symbol({self.symbol})")
            await self.croupier.cleanup_symbol(self.symbol)

            # Verify all orders cancelled
            await asyncio.sleep(2)
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            exchange_ids = [o["id"] for o in open_orders]

            orphans_remaining = [oid for oid in order_ids if oid in exchange_ids]
            if orphans_remaining:
                logger.error(f"❌ Orphan orders NOT cleaned: {orphans_remaining}")
                return False

            logger.info(f"✅ All orphan orders cleaned")

            logger.info("✅ TEST 6 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 6 FAILED: {e}")
            # Cleanup
            for oid in order_ids:
                try:
                    await self.adapter.cancel_order(oid, self.symbol)
                except Exception:
                    pass
            return False

    # =========================================================================
    # TEST 7: Simulate Shutdown Flow
    # =========================================================================
    async def test_7_shutdown_flow(self) -> bool:
        """Simulate the bot shutdown flow from main.py."""
        logger.info("=" * 70)
        logger.info("TEST 7: Simulate Shutdown Flow")
        logger.info("=" * 70)

        try:
            # Calculate amount (Master Sizing simulation)
            price = await self.adapter.get_current_price(self.symbol)
            notional = 25.0
            raw_amount = notional / price
            amount = float(self.adapter.amount_to_precision(self.symbol, raw_amount))

            # Phase 800: Create SHORT position with absolute TP/SL prices
            tp_price = round(price * (1 - 0.02), 2)  # TP 2% below (SHORT)
            sl_price = round(price * (1 + 0.02), 2)  # SL 2% above (SHORT)

            order = {
                "symbol": self.symbol,
                "side": "SHORT",
                "size": self.size,
                "amount": amount,  # REQUIRED by Phase 42
                "tp_price": tp_price,  # Absolute TP price (below for SHORT)
                "sl_price": sl_price,  # Absolute SL price (above for SHORT)
                "trade_id": f"shutdown_test_{int(time.time())}",
            }

            logger.info(f"📤 Creating position for shutdown test: {order}")
            result = await self.croupier.execute_order(order)

            tp_id = result["tp_order"].get("order_id") or result["tp_order"].get("id")
            sl_id = result["sl_order"].get("order_id") or result["sl_order"].get("id")

            logger.info(f"✅ Position created | TP: {tp_id} | SL: {sl_id}")
            await asyncio.sleep(2)

            # Simulate shutdown flow (from main.py lines 259-274)
            logger.info("🛑 Simulating shutdown flow...")

            open_positions = self.croupier.get_open_positions()
            logger.info(f"   Open positions: {len(open_positions)}")

            if open_positions:
                for pos in open_positions:
                    logger.info(f"   Closing: {pos.trade_id}")
                    await self.croupier.close_position(pos.trade_id)

            # Call cleanup_symbol (from main.py line 272)
            await self.croupier.cleanup_symbol(self.symbol)

            # Verify clean state
            await asyncio.sleep(2)

            # No positions in tracker
            positions = self.croupier.get_open_positions()
            if positions:
                logger.error(f"❌ Positions still in tracker: {len(positions)}")
                return False
            logger.info(f"✅ No positions in tracker")

            # No orders in exchange
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            if open_orders:
                logger.error(f"❌ Orders still in exchange: {[o['id'] for o in open_orders]}")
                return False
            logger.info(f"✅ No orders in exchange")

            # No positions in exchange
            positions = await self.connector.fetch_positions()
            for pos in positions:
                if pos.get("symbol") == self.symbol:
                    size = abs(float(pos.get("size", 0)))
                    if size > 0.001:
                        logger.error(f"❌ Position still in exchange: {size}")
                        return False
            logger.info(f"✅ No positions in exchange")

            logger.info("✅ TEST 7 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 7 FAILED: {e}")
            return False

    # =========================================================================
    # TEST 8: Error Handling
    # =========================================================================
    async def test_8_error_handling(self) -> bool:
        """Test error handling doesn't leave orphans."""
        logger.info("=" * 70)
        logger.info("TEST 8: Error Handling")
        logger.info("=" * 70)

        try:
            # Test 1: Order without required fields (Phase 800: tp_price/sl_price required)
            try:
                await self.croupier.execute_order(
                    {
                        "symbol": self.symbol,
                        "side": "LONG",
                        # Missing amount, tp_price, sl_price
                    }
                )
                logger.error("❌ Should have raised ValueError")
                return False
            except ValueError as e:
                logger.info(f"✅ Caught expected error: {e}")

            # Verify no orphan orders created
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            if open_orders:
                logger.error(f"❌ Orphan orders created during error: {len(open_orders)}")
                return False
            logger.info(f"✅ No orphan orders after error")

            # Verify no orphan positions
            positions = await self.connector.fetch_positions()
            for pos in positions:
                if pos.get("symbol") == self.symbol:
                    size = abs(float(pos.get("size", 0)))
                    if size > 0.001:
                        logger.error(f"❌ Orphan position created: {size}")
                        return False
            logger.info(f"✅ No orphan positions after error")

            logger.info("✅ TEST 8 PASSED\n")
            return True

        except Exception as e:
            logger.error(f"❌ TEST 8 FAILED: {e}")
            return False

    # =========================================================================
    # Main Runner
    # =========================================================================
    async def run_all_tests(self) -> bool:
        """Run all preflight tests."""
        logger.info("\n" + "=" * 70)
        logger.info(" PREFLIGHT VALIDATOR - RIGOROUS BOT LIFECYCLE TEST")
        logger.info("=" * 70)
        logger.info(" CRITICAL: All tests must pass before running the bot!")
        logger.info("=" * 70 + "\n")

        await self.setup()

        tests = [
            ("CONNECTION", self.test_1_connection),
            ("ORDER_CANCEL", self.test_2_order_execution_and_cancel),
            ("OCO_BRACKET", self.test_3_oco_bracket),
            ("POSITION_TRACKING", self.test_4_position_tracking),
            ("CLOSE_POSITION", self.test_5_close_position),
            ("ORPHAN_CLEANUP", self.test_6_orphan_cleanup),
            ("SHUTDOWN_FLOW", self.test_7_shutdown_flow),
            ("ERROR_HANDLING", self.test_8_error_handling),
        ]

        all_passed = True

        try:
            for name, test_func in tests:
                result = await test_func()
                self.test_results[name] = result
                if not result:
                    all_passed = False
                    logger.error(f"⛔ Stopping tests - {name} failed")
                    break

        except Exception as e:
            logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
            all_passed = False

        finally:
            # Phase 243: Final Scorched Earth Teardown
            await self._force_cleanup()

            # Close connector
            try:
                await self.connector.close()
            except Exception:
                pass

        # Print summary
        logger.info("\n" + "=" * 70)
        logger.info(" PREFLIGHT RESULTS")
        logger.info("=" * 70)

        for name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"  {name}: {status}")

        if all_passed:
            logger.info("\n" + "=" * 70)
            logger.info("✅ ALL PREFLIGHT TESTS PASSED - BOT IS SAFE TO RUN")
            logger.info("=" * 70 + "\n")
        else:
            logger.info("\n" + "=" * 70)
            logger.info("❌ PREFLIGHT FAILED - DO NOT START THE BOT")
            logger.info("=" * 70 + "\n")

        return all_passed


async def main():
    parser = argparse.ArgumentParser(description="Preflight Validator - Rigorous Bot Lifecycle Test")
    parser.add_argument("--exchange", required=True, help="Exchange ID (binance)")
    parser.add_argument("--symbol", required=True, help="Trading symbol (LTCUSDT)")
    parser.add_argument("--mode", default="demo", choices=["demo", "live"], help="Mode")
    parser.add_argument("--size", type=float, default=0.05, help="Position size fraction (0.05 = 5%%)")
    parser.add_argument(
        "--execute-orders", action="store_true", help="Execute real orders (always true for this validator)"
    )

    args = parser.parse_args()

    setup_logging()

    validator = PreflightValidator(exchange_id=args.exchange, symbol=args.symbol, mode=args.mode, size=args.size)

    success = await validator.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
