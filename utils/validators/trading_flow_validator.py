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
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

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
        self.croupier = Croupier(
            exchange_adapter=self.adapter, initial_balance=self.initial_balance, max_concurrent_positions=10
        )
        logger.info("✅ Croupier initialized")

        # 5. Pre-test cleanup - ensure clean slate
        await self._force_cleanup()
        logger.info("✅ Setup complete\n")

    async def _force_cleanup(self):
        """Force cleanup all positions and orders for the symbol."""
        logger.info("🧹 Force cleanup before tests...")

        try:
            # Close all positions
            positions = await self.connector.fetch_positions()
            for pos in positions:
                if pos.get("symbol") == self.symbol:
                    size = abs(float(pos.get("size", 0)))
                    if size > 0:
                        side = "sell" if pos.get("side") == "LONG" else "buy"
                        await self.connector.create_order(
                            symbol=self.symbol, order_type="market", side=side, amount=size
                        )
                        logger.info(f"  ✓ Closed position: {pos.get('side')} {size}")

            # Cancel all orders
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            for order in open_orders:
                await self.connector.cancel_order(order["id"], self.symbol)
                logger.info(f"  ✓ Cancelled order: {order['id']}")

            await asyncio.sleep(2)

        except Exception as e:
            logger.warning(f"⚠️ Cleanup error (non-fatal): {e}")

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
            symbol_positions = [p for p in positions if p.get("symbol") == self.symbol]
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
            # Dynamic sizing: Ensure > 5 USD (Target 10 USD)
            target_notional = 10.0
            raw_amount = target_notional / limit_price
            test_amount = float(self.adapter.amount_to_precision(self.symbol, raw_amount))

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
            order = {
                "symbol": self.symbol,
                "side": "LONG",
                "size": self.size,
                "take_profit": 0.02,  # +2%
                "stop_loss": 0.02,  # -2%
                "trade_id": f"preflight_{int(time.time())}",
            }

            logger.info(f"📤 Creating OCO bracket: {order}")
            result = await self.croupier.execute_order(order)

            # Validate result structure
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
            logger.info(f"✅ Fill price: {result['fill_price']:.2f}")

            # Verify TP/SL exist in exchange
            await asyncio.sleep(2)
            open_orders = await self.connector.fetch_open_orders(self.symbol)
            order_ids = [o["id"] for o in open_orders]

            assert tp_id in order_ids, f"TP order {tp_id} not in exchange!"
            assert sl_id in order_ids, f"SL order {sl_id} not in exchange!"
            logger.info(f"✅ TP/SL verified in exchange")

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
            assert pos.symbol == self.symbol, f"Wrong symbol: {pos.symbol}"
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

            # Verify position removed from tracker
            await asyncio.sleep(2)
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
                if pos.get("symbol") == self.symbol:
                    size = abs(float(pos.get("size", 0)))
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
                # Dynamic sizing: Ensure > 5 USD (Target 10 USD)
                target_notional = 10.0
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
            # Create a new position with OCO
            order = {
                "symbol": self.symbol,
                "side": "SHORT",
                "size": self.size,
                "take_profit": 0.02,
                "stop_loss": 0.02,
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
            # Test 1: Order without required fields
            try:
                await self.croupier.execute_order(
                    {
                        "symbol": self.symbol,
                        "side": "LONG",
                        # Missing size/amount, take_profit, stop_loss
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
            # Final cleanup
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
    parser.add_argument("--size", type=float, default=0.05, help="Position size fraction (0.05 = 5%)")
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
