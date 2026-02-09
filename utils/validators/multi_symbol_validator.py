"""
Multi-Symbol Validator - Parallel Stress Test
-----------------------------------------------
This tool validates that the bot can handle multiple symbols concurrently
without state corruption, execution lag, or orphan creation.

Usage:
    python -m utils.validators.multi_symbol_validator \\
        --symbols LTCUSDT,BTCUSDT,ETHUSDT \\
        --mode demo \\
        --size 0.05
"""

# Standard Lib
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add root to sys.path to ensure absolute imports work
sys.path.append(os.getcwd())

from dotenv import load_dotenv

from croupier.components.reconciliation_service import ReconciliationService
from croupier.croupier import Croupier
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# OCOManager is usually part of Croupier but we need the class for typing or instantiation if needed
# Although we use self.croupier.oco_manager, we imported it?
# The error was on import line.
# from core.portfolio.oco_manager import OCOManager # Removed to avoid import issues is usually part of Croupier but we need the class for typing or instantiation if needed


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/multi_symbol_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
    )

    # We want to see the details of the orchestration
    logging.getLogger("OCOManager").setLevel(logging.DEBUG)
    logging.getLogger("BinanceNativeConnector").setLevel(logging.DEBUG)
    logging.getLogger("OrderExecutor").setLevel(logging.DEBUG)
    logging.getLogger("Croupier").setLevel(logging.DEBUG)
    logging.getLogger("ReconciliationService").setLevel(logging.DEBUG)


logger = logging.getLogger("MultiSymbolValidator")


class MultiSymbolValidator:
    def __init__(self, exchange_id="binance", symbols=["LTCUSDT", "BTCUSDT", "ETHUSDT"], mode="demo", size=500.0):
        self.exchange_id = exchange_id
        self.symbols = [s.strip().upper() for s in symbols]
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
            enable_websocket=True,
        )

        self.multi_adapter = None
        self.croupier = None
        self.initial_balance = 0.0

    async def setup(self):
        logger.info("=" * 70)
        logger.info(" MULTI-SYMBOL VALIDATOR - SETUP")
        logger.info("=" * 70)
        logger.info(f"Exchange: {self.exchange_id.upper()} | Symbols: {self.symbols} | Mode: {self.mode}")

        # 1. Connect
        logger.info("🔌 Connecting to exchange...")
        await self.connector.connect()
        logger.info("✅ Connected")

        # 2. Create multi-symbol adapter
        # In MULTI mode, the adapter symbol is "MULTI"
        self.multi_adapter = ExchangeAdapter(self.connector, "MULTI")
        logger.info("✅ Multi-symbol Adapter created")

        # 3. Fetch balance
        balance_data = await self.connector.fetch_balance()
        self.initial_balance = balance_data.get("total", {}).get("USDT", 0.0)

        if self.initial_balance < 15:  # Need at least 5 USDT per symbol for 3 symbols
            raise ValueError(f"Insufficient balance for multi-test: ${self.initial_balance:.2f}")

        logger.info(f"💰 Balance: ${self.initial_balance:,.2f}")

        self.croupier = Croupier(
            exchange_adapter=self.multi_adapter, initial_balance=self.initial_balance, max_concurrent_positions=20
        )
        # LIFECYCLE SUPPORT: Initialize Reconciliation Service for GC
        # We need this to cleanup OFF_BOARDING positions
        self.oco_manager = self.croupier.oco_manager
        self.recon_service = ReconciliationService(
            self.multi_adapter, self.croupier.position_tracker, self.oco_manager, self.croupier
        )
        self.croupier.reconciliation_service = self.recon_service

        logger.info("✅ Croupier & Reconciliation initialized (Multi-symbol mode)")

        # 4.1 Register order update callback (matches main.py)
        # This is CRITICAL for PositionTracker to see fills and close positions!
        async def async_order_update_handler(order):
            # 1. Update Position Tracker (Current Limit/Stop management)
            self.croupier.position_tracker.handle_order_update(order)
            # 2. Update OCO Manager (Initial entry wait)
            await self.croupier.oco_manager.on_order_update(order)

        self.connector.set_order_update_callback(async_order_update_handler)
        logger.info("✅ Order update callback registered for tracker/OCO")

        # 5. Pre-test cleanup
        await self._force_cleanup_all()
        logger.info("✅ Setup complete\n")

    async def _force_cleanup_all(self):
        """Force cleanup for all target symbols."""
        logger.info("🧹 Force cleanup for all target symbols...")
        for symbol in self.symbols:
            try:
                # 1. Cancel all open orders for this symbol first (to unlock reduceOnly)
                open_orders = await self.connector.fetch_open_orders(symbol)
                for order in open_orders:
                    logger.info(f"   Cancelling {symbol} order: {order['id']}")
                    await self.connector.cancel_order(order["id"], symbol)

                # 2. Close positions for this specific symbol
                positions = await self.connector.fetch_positions([symbol])
                for pos in positions:
                    # Binance Native returns 'contracts' for amount. Fallback to 'size' for cross-adapter safety.
                    size = abs(float(pos.get("contracts") or pos.get("size") or 0))
                    if size > 0:
                        side = "sell" if pos.get("side") == "LONG" else "buy"
                        logger.info(f"   Closing {symbol} position: {pos.get('side')} {size}")
                        await self.connector.create_order(
                            symbol=symbol, order_type="market", side=side, amount=size, params={"reduceOnly": "true"}
                        )

            except Exception as e:
                logger.warning(f"⚠️ Cleanup error for {symbol}: {e}")

        # Allow time for exchange to sync
        await asyncio.sleep(2)

    async def run_symbol_flow(self, symbol: str) -> bool:
        """Run a single symbol flow: Open OCO -> Wait -> Verify -> Close."""
        logger.info(f"🚀 [START] Concurrent flow for {symbol}")
        try:
            # 1. Execute OCO Bracket
            # Price delta must be large enough to not fill TP/SL during test

            # Phase 42: Manual Amount Calculation for Master Sizing
            ticker = await self.connector.fetch_ticker(symbol)
            current_price = float(ticker["last"])
            # Ensure size is enough for at least 1 contract (especially for SOL on testnet)
            test_size = self.size
            if symbol == "SOLUSDT":
                test_size = max(test_size, current_price * 1.1)  # 1.1 SOL to be safe

            amount = float(self.multi_adapter.amount_to_precision(symbol, test_size / current_price))
            logger.info(f"🔍 [{symbol}] Calculated amount: {amount} (Raw: {test_size / current_price})")

            order = {
                "symbol": symbol,
                "side": "LONG",
                "size": self.size,
                "amount": amount,
                "qty": amount,
                "take_profit": 0.05,  # +5%
                "stop_loss": 0.05,  # -5%
                "trade_id": f"multi_{symbol}_{int(time.time())}",
            }

            logger.info(f"📥 [{symbol}] Sending OCO request...")
            result = await self.croupier.execute_order(order)

            if result.get("status") == "error":
                logger.error(f"❌ [{symbol}] OCO Creation failed: {result.get('message')}")
                return False

            main_id = result["main_order"].get("order_id") or result["main_order"].get("id")
            tp_id = result["tp_order"].get("order_id") or result["tp_order"].get("id")
            sl_id = result["sl_order"].get("order_id") or result["sl_order"].get("id")

            logger.info(f"✅ [{symbol}] Bracket Created: Main={main_id}, TP={tp_id}, SL={sl_id}")

            # Universal Funnel Verification: Check CASINO_ Prefix
            async def get_client_id(oid):
                try:
                    o = await self.connector.fetch_order(oid, symbol)
                    return o.get("client_order_id") or o.get("clientOrderId", "")
                except Exception as e:
                    logger.error(f"❌ Error during cleanup: {e}")
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
                logger.error(f"❌ [{symbol}] Main ClientID mismatch (no CASINO_): {main_cid}")
                return False
            if not tp_cid.startswith("CASINO_"):
                logger.error(f"❌ [{symbol}] TP ClientID mismatch (no CASINO_): {tp_cid}")
                return False
            if not sl_cid.startswith("CASINO_"):
                logger.error(f"❌ [{symbol}] SL ClientID mismatch (no CASINO_): {sl_cid}")
                return False

            logger.info(f"✅ [{symbol}] Universal Funnel Verified: All IDs start with CASINO_")

            # 2. Simulation phase (Wait and check integrity)
            await asyncio.sleep(5)

            # 3. Local State Check
            pos = next((p for p in self.croupier.position_tracker.open_positions if p.symbol == symbol), None)
            if not pos:
                logger.error(f"❌ [{symbol}] Local state corrupted: Position not found in tracker!")
                return False

            # Note: tp_order_id might be clientOrderId, so we compare exchange_tp_id
            if str(pos.exchange_tp_id) != str(tp_id) or str(pos.exchange_sl_id) != str(sl_id):
                logger.error(f"❌ [{symbol}] Local state mismatch:")
                logger.error(f"   Tracker: TP={pos.exchange_tp_id}, SL={pos.exchange_sl_id}")
                logger.error(f"   Created: TP={tp_id}, SL={sl_id}")
                return False

            # 4. Exchange Consistency Check
            # Ensure TP and SL are actually on the exchange
            open_orders = await self.connector.fetch_open_orders(symbol)
            ex_ids = [o["id"] for o in open_orders]
            if tp_id not in ex_ids or sl_id not in ex_ids:
                logger.error(f"❌ [{symbol}] Exchange state mismatch: TP/SL orders missing from exchange!")
                return False

            # 5. Close position via Croupier (verifies OCO cancellation)
            logger.info(f"📤 [{symbol}] Closing position via Croupier...")
            await self.croupier.close_position(pos.trade_id)

            # Verify clean up
            await asyncio.sleep(2)
            open_orders_after = await self.connector.fetch_open_orders(symbol)
            if any(oid in [o["id"] for o in open_orders_after] for oid in [tp_id, sl_id]):
                logger.error(f"❌ [{symbol}] Cleanup failed: TP/SL orders still exist after close!")
                return False

            logger.info(f"🏁 [FINISH] Flow for {symbol} PASSED")
            return True

        except Exception as e:
            logger.error(f"💥 [{symbol}] UNEXPECTED EXCEPTION: {e}", exc_info=True)
            return False

    async def test_concurrency(self) -> bool:
        """Test concurrent execution of multiple symbol flows."""
        logger.info("=" * 70)
        logger.info("TEST: Concurrent Multi-Symbol Execution")
        logger.info("=" * 70)

        start_time = time.time()

        # Launch all flows concurrently
        tasks = [self.run_symbol_flow(s) for s in self.symbols]
        results = await asyncio.gather(*tasks)

        end_time = time.time()
        duration = end_time - start_time

        logger.info(f"⏱️ Multi-symbol concurrency test took {duration:.2f} seconds")

        # Check all results
        all_passed = all(results)
        for i, symbol in enumerate(self.symbols):
            status = "✅ PASS" if results[i] else "❌ FAIL"
            logger.info(f"   - {symbol}: {status}")

        return all_passed

    async def test_global_integrity(self) -> bool:
        """Final audit to ensure NO orphans and NO mixed states."""
        logger.info("=" * 70)
        logger.info("TEST: Global Integrity Audit")
        logger.info("=" * 70)

        try:
            # 0. Trigger Garbage Collection (Lifecycle Architecture)
            logger.info("🧹 Triggering final reconciliation sweep...")
            await self.recon_service.reconcile_all()

            # 1. Tracker should be empty
            open_pos = self.croupier.position_tracker.open_positions
            if open_pos:
                logger.error(
                    f"❌ Tracker not empty: {len(open_pos)} positions remaining: {[p.symbol for p in open_pos]}"
                )
                return False
            logger.info("✅ Tracker is clean")

            # 2. Exchange should be clean for all symbols
            for symbol in self.symbols:
                orders = await self.connector.fetch_open_orders(symbol)
                if orders:
                    logger.error(f"❌ exchange not clean: {symbol} has {len(orders)} orphan orders!")
                    return False

                ex_pos = await self.connector.fetch_positions([symbol])
                for p in ex_pos:
                    size = abs(float(p.get("contracts") or p.get("size") or 0))
                    if size > 0.005:
                        logger.error(f"❌ exchange not clean: {symbol} still has an open position!")
                        return False
            logger.info("✅ Exchange is clean for all tested symbols")

            return True
        except Exception as e:
            logger.error(f"❌ Audit failed: {e}")
            return False

    async def run_all(self) -> bool:
        """Main test runner."""
        try:
            await self.setup()

            # Step 1: Concurrency Test
            concurrent_passed = await self.test_concurrency()

            # Step 2: Global Integrity
            integrity_passed = await self.test_global_integrity()

            final_success = concurrent_passed and integrity_passed

            # Final Report
            logger.info("\n" + "=" * 70)
            logger.info(" MULTI-SYMBOL VALIDATION SUMMARY")
            logger.info("=" * 70)
            logger.info(f"  CONCURRENCY: {'✅ PASS' if concurrent_passed else '❌ FAIL'}")
            logger.info(f"  INTEGRITY:   {'✅ PASS' if integrity_passed else '❌ FAIL'}")
            logger.info("-" * 70)

            if final_success:
                logger.info("✅ ALL SCALABILITY TESTS PASSED. Bot is ready for multi-symbol operation.")
            else:
                logger.error("❌ SCALABILITY TEST FAILED. Check logs for details.")
            logger.info("=" * 70 + "\n")

            return final_success

        except Exception as e:
            logger.error(f"🛑 TEST RUNNER CRASHED: {e}", exc_info=True)
            return False
        finally:
            await self.connector.close()


async def main():
    parser = argparse.ArgumentParser(description="Multi-Symbol Stress Test Validator")
    parser.add_argument(
        "--symbols", default="LTCUSDT,DOGEUSDT,ETHUSDT", help="Comma separated symbols (e.g. LTCUSDT,DOGEUSDT)"
    )
    parser.add_argument("--mode", default="demo", choices=["demo", "live"], help="Exchange mode")
    parser.add_argument("--size", type=float, default=500.0, help="Position size fraction")

    args = parser.parse_args()

    setup_logging()

    symbols_list = args.symbols.split(",")
    validator = MultiSymbolValidator(symbols=symbols_list, mode=args.mode, size=args.size)

    success = await validator.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
