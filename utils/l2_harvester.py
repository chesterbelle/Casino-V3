import argparse
import asyncio
import logging
import signal

from core.observability.historian import TradeHistorian
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("L2Harvester")


class HarvesterApp:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.running = True
        self.historian = TradeHistorian()
        self.historian.start()

        self.connector = BinanceNativeConnector(exchange_id="binance_futures", testnet=False, config={})

    async def run(self):
        logger.info(f"🌾 Starting L2 Harvester for {self.symbol}...")

        # Connect to real Binance
        await self.connector.connect()

        # Listen to depth via the standard _depth_event_callback,
        # but inject our save logic
        original_callback = self.connector._depth_event_callback

        def harvesting_callback(event):
            # Pass to original to keep connector internal state updated
            if original_callback:
                original_callback(event)

            # Record high-speed snapshot
            self.historian.record_depth_snapshot(
                symbol=event.symbol, timestamp=event.timestamp, bids=event.bids, asks=event.asks
            )

        self.connector._depth_event_callback = harvesting_callback

        logger.info(f"📡 Subscribing to Depth @100ms for {self.symbol}")
        # Note: We need to manually add the stream to the stream manager
        stream_name = f"{self.symbol.split(':')[0].lower().replace('/', '')}@depth5@100ms"
        await self.connector._stream_manager.subscribe(stream_name)

        logger.info("✅ Harvesting active. Press Ctrl+C to stop.")
        while self.running:
            await asyncio.sleep(1)

    async def shutdown(self):
        logger.info("🛑 Shutting down harvester...")
        self.running = False
        await self.connector.disconnect()
        self.historian.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance L2 Data Harvester")
    parser.add_argument("--symbol", type=str, default="LTC/USDT:USDT", help="Trading pair")
    args = parser.parse_args()

    app = HarvesterApp(args.symbol)

    def handle_sigint(*args):
        asyncio.create_task(app.shutdown())

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
