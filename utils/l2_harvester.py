import argparse
import asyncio
import logging
import os
import signal

from core.observability.historian import TradeHistorian
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("L2Harvester")


class HarvesterApp:
    def __init__(self, symbol: str, mode: str = "live"):
        self.symbol = symbol
        self.mode = mode
        self.running = True
        self.historian = TradeHistorian()
        # Note: Historian starts its worker lazily when record_depth_snapshot is called.

        # Initialize connector with proper mode
        self.connector = BinanceNativeConnector(mode=self.mode)

    async def run(self):
        logger.info(f"🌾 Starting L2 Harvester for {self.symbol} in {self.mode} mode...")

        # Connect to Binance
        await self.connector.connect()

        # Listen to depth via the standard _depth_event_callback
        # The connector expects this to be an async function (or return a coroutine)
        async def harvesting_callback(event: dict):
            # Record high-speed snapshot
            # event is a dict: {"symbol": symbol, "bids": bids, "asks": asks, "timestamp": timestamp}
            try:
                self.historian.record_depth_snapshot(
                    symbol=event["symbol"],
                    timestamp=event["timestamp"],
                    bids=str(event["bids"]),
                    asks=str(event["asks"]),
                )
            except Exception as e:
                logger.error(f"Error recording depth snapshot: {e}")

        self.connector._depth_event_callback = harvesting_callback

        logger.info(f"📡 Subscribing to Depth @100ms for {self.symbol}")
        await self.connector.subscribe_depth(self.symbol, levels=5)

        logger.info("✅ Harvesting active. Press Ctrl+C to stop.")
        while self.running:
            await asyncio.sleep(1)

    async def shutdown(self):
        logger.info("🛑 Shutting down harvester...")
        self.running = False
        await self.connector.close()
        self.historian.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance L2 Data Harvester")
    parser.add_argument("--symbol", type=str, default="LTC/USDT:USDT", help="Trading pair (e.g. LTC/USDT:USDT)")
    parser.add_argument("--mode", type=str, default="live", choices=["live", "demo"], help="Exchange mode")
    args = parser.parse_args()

    app = HarvesterApp(args.symbol, args.mode)

    def handle_sigint(*args):
        # We need to use the loop to schedule shutdown if it's not already running
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(app.shutdown())
        except RuntimeError:
            pass

    # Use a more robust way to handle signals in asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))
        except NotImplementedError:
            # Signal handlers not implemented on some platforms (Windows)
            pass

    try:
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
