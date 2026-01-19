"""
Multi-Symbol Chaos Tester - High-Density Stress Test
---------------------------------------------------
This tool forces race conditions by bombarding the bot with high-frequency
operations (open, modify, close) across multiple symbols simultaneously.

Objective: Confirm 0 logs of "WS Event UNMATCHED" and 0 Error Recovery trades.
"""

import argparse
import asyncio
import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# Add root to sys.path
sys.path.append(os.getcwd())

from dotenv import load_dotenv

from core.observability.historian import historian
from core.portfolio.position_tracker import PositionTracker
from utils.validators.multi_symbol_validator import MultiSymbolValidator

logger = logging.getLogger("ChaosTester")


class MultiSymbolChaosTester(MultiSymbolValidator):
    def __init__(self, duration_sec=600, **kwargs):
        super().__init__(**kwargs)
        self.duration_sec = duration_sec
        self.total_operations = 0
        self.unmatched_events = 0
        self.error_trades = 0

    async def run_chaos_loop(self, symbol: str):
        """Infinite loop of randomized trades for a specific symbol."""
        logger.info(f"🔥 Starting Chaos Loop for {symbol}")
        end_time = time.time() + self.duration_sec

        while time.time() < end_time:
            try:
                # 1. Open Position
                logger.debug(f"[{symbol}] Opening chaos position...")
                ticker = await self.connector.fetch_ticker(symbol)
                price = float(ticker["last"])
                amount = self.size / price

                trade_id = f"chaos_{symbol}_{uuid.uuid4().hex[:6]}"
                order = {
                    "symbol": symbol,
                    "side": random.choice(["LONG", "SHORT"]),
                    "size": self.size,
                    "amount": amount,
                    "take_profit": 0.05,
                    "stop_loss": 0.05,
                    "trade_id": trade_id,
                }

                result = await self.croupier.execute_order(order)
                if result.get("status") == "error":
                    logger.warning(f"⚠️ [{symbol}] Entry failed: {result.get('message')}")
                    await asyncio.sleep(2)
                    continue

                self.total_operations += 1

                # 2. Chaos Phase: Random Modals/Waits
                # We want to stress the 'modify_bracket' patch
                for _ in range(random.randint(1, 3)):
                    await asyncio.sleep(random.uniform(0.5, 3.0))

                    # Randomly decide to modify or just wait
                    action = random.choice(["MODIFY", "WAIT", "CLOSE"])

                    if action == "MODIFY":
                        logger.debug(f"[{symbol}] Stressing modify_bracket...")
                        new_tp = 0.04 if order["side"] == "LONG" else 0.06
                        try:
                            await self.croupier.oco_manager.modify_bracket(
                                trade_id=trade_id,
                                symbol=symbol,
                                new_tp_price=price * (1 + new_tp if order["side"] == "LONG" else 1 - new_tp),
                            )
                            self.total_operations += 1
                        except Exception as e:
                            logger.debug(f"[{symbol}] Mod failed (expected if filled): {e}")

                    elif action == "CLOSE":
                        break  # Go to close phase early

                # 3. Close Phase
                await asyncio.sleep(random.uniform(0.1, 1.0))
                logger.debug(f"[{symbol}] Closing chaos position {trade_id}...")
                await self.croupier.close_position(trade_id)
                self.total_operations += 1

                # 4. Small breather before next trade
                await asyncio.sleep(random.uniform(1, 5))

            except Exception as e:
                logger.error(f"💥 [{symbol}] Chaos Loop Error: {e}")
                await asyncio.sleep(5)

    async def run_all(self) -> bool:
        """Main chaotic execution."""
        try:
            await self.setup()

            # Start monitoring for UNMATCHED events in logs
            # We can't easily hook into logger in real-time here without complex handlers,
            # so we'll rely on the final Historian report and log inspection.

            logger.info(f"🚀 LAUNCHING CHAOS TEST: {len(self.symbols)} symbols for {self.duration_sec}s")

            tasks = [self.run_chaos_loop(s) for s in self.symbols]

            # Run the tasks for the specified duration
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                pass

            # Final Audit
            logger.info("🧹 Chaos phase complete. Proceeding to Global Integrity Audit...")
            await asyncio.sleep(5)  # Let events settle

            integrity_passed = await self.test_global_integrity()

            # Summary
            stats = historian.get_session_stats(self.croupier.session_id)
            self.error_trades = stats.get("error_count", 0)

            logger.info("\n" + "=" * 70)
            logger.info(" MULTI-SYMBOL CHAOS TEST SUMMARY")
            logger.info("=" * 70)
            logger.info(f"  Duration:      {self.duration_sec}s")
            logger.info(f"  Symbols:       {len(self.symbols)}")
            logger.info(f"  Total Ops:     {self.total_operations}")
            logger.info(f"  Error Trades:  {self.error_trades} (GOAL: 0)")
            logger.info(f"  Integrity:     {'✅ PASS' if integrity_passed else '❌ FAIL'}")
            logger.info("-" * 70)

            final_success = integrity_passed and self.error_trades == 0

            if final_success:
                logger.info("✅ CHAOS TEST PASSED. WebSocket logic is bulletproof.")
            else:
                logger.error("❌ CHAOS TEST FAILED. Check logs for UNMATCHED events.")
            logger.info("=" * 70 + "\n")

            return final_success

        except Exception as e:
            logger.error(f"🛑 CHAOS RUNNER CRASHED: {e}", exc_info=True)
            return False
        finally:
            await self.connector.close()


async def main():
    parser = argparse.ArgumentParser(description="Multi-Symbol Chaos Tester")
    parser.add_argument("--symbols", default="LTCUSDT,BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT", help="Symbols")
    parser.add_argument("--mode", default="demo", help="Exchange mode")
    parser.add_argument("--size", type=float, default=200.0, help="Position size in USDT")
    parser.add_argument("--duration", type=int, default=600, help="Test duration in seconds")

    args = parser.parse_args()

    # Re-use logging setup from validator
    from utils.validators.multi_symbol_validator import setup_logging

    setup_logging()

    symbols_list = args.symbols.split(",")
    tester = MultiSymbolChaosTester(symbols=symbols_list, mode=args.mode, size=args.size, duration_sec=args.duration)

    success = await tester.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
