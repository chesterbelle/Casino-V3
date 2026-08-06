import asyncio
import logging
import multiprocessing as mp
import time


class ReconciliationWorker(mp.Process):
    """
    Independent Multiprocessing Worker for Phase 4 HFT Decoupling.
    Handles continuous REST API polling for positions and open orders
    without blocking the main Croupier asyncio event loop.
    """

    def __init__(self, api_key: str, secret_key: str, testnet: bool, output_queue: mp.Queue, interval: float = 45.0):
        super().__init__(name="ReconWorker")
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        self.output_queue = output_queue
        self.interval = interval
        self._stop_event = mp.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        asyncio.run(self._async_run())

    async def _async_run(self):
        # Isolate imports to avoid triggering heavy machinery in the main thread
        from exchanges.connectors.binance.binance_native_connector import (
            BinanceNativeConnector,
        )

        mode = "demo" if self.testnet else "live"
        connector = BinanceNativeConnector(
            api_key=self.api_key, secret=self.secret_key, mode=mode, enable_websocket=False
        )

        # We only need the REST capabilities, no streams
        try:
            await connector.connect()
        except BaseException:
            pass

        logger = logging.getLogger("ReconWorker")
        # Ensure log format propagates
        if not logger.handlers:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s")

        logger.info("✅ ReconciliationWorker started")

        # Phase 250: Track symbols we've seen to also fetch orders for symbols
        # that recently closed positions (residual SL/TP orders still pending).
        known_symbols: set = set()

        while not self._stop_event.is_set():
            try:
                start_time = time.time()

                # Fetch positions first (no symbol required by Binance)
                exchange_positions = await connector.fetch_positions(symbol=None)

                # Build the symbol set: positions + previously seen symbols
                pos_symbols = {
                    p.get("symbol")
                    for p in (exchange_positions or [])
                    if abs(float(p.get("contracts", 0) or p.get("size", 0) or 0)) > 1e-8
                }
                query_symbols = sorted(known_symbols | pos_symbols)
                known_symbols |= pos_symbols
                # Cap the symbol list to avoid runaway memory (sliding window)
                if len(known_symbols) > 50:
                    known_symbols = set(list(known_symbols)[-50:])

                # Phase 250: Binance Testnet requires explicit symbol per call.
                # Pass the list of candidate symbols derived from positions.
                open_orders = await connector.fetch_open_orders(query_symbols) if query_symbols else []

                # Construct data payload
                payload = {
                    "exchange_positions": exchange_positions,
                    "open_orders": open_orders,
                    "timestamp": time.time(),
                }

                # Keep the queue fresh with only the latest state
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except Exception:
                        pass

                self.output_queue.put_nowait(payload)

                logger.debug(
                    f"🔄 Synced {len(exchange_positions) if exchange_positions else 0} positions "
                    f"and {len(open_orders) if open_orders else 0} orders in {time.time()-start_time:.3f}s"
                )

            except Exception as e:
                logger.error(f"❌ ReconciliationWorker fetch error: {e}")

            # Sleep in intervals to allow interrupt
            slept = 0.0
            while slept < self.interval and not self._stop_event.is_set():
                await asyncio.sleep(1.0)
                slept += 1.0

        try:
            await connector.close()
            logger.info("🛑 ReconciliationWorker cleanly shut down.")
        except Exception:
            pass
