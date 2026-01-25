import asyncio
import logging
import multiprocessing
import os
import signal
import time
from typing import Dict, List, Optional, Set

import aiohttp

# Configure minimal logging for the worker
logging.basicConfig(level=logging.INFO, format="%(asctime)s | WORKER:%(process)d | %(levelname)s | %(message)s")
logger = logging.getLogger("BinanceWorker")


class BinanceWorker(multiprocessing.Process):
    """
    Sentinel Process for Binance WebSocket Ingestion.

    Role:
    - Dedicated process (isolated GIL)
    - Maintains WebSocket connection at all costs
    - Pushes raw events to output_queue
    - Accepts commands (SUBSCRIBE, UNSUBSCRIBE) from input_queue

    Architecture:
    - Uses aiohttp for async WebSocket
    - Infinite reconnection loop
    - Zero business logic (dumb pipe)
    """

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
        base_url: str = "wss://fstream.binance.com/ws",
    ):
        super().__init__(name="BinanceIngestionWorker")
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.base_url = base_url

        # State
        self.running = True
        self.subscriptions: Set[str] = set()
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.last_stats_ts = 0
        self.msg_count = 0

    def run(self):
        """Entry point for the separate process."""
        # Reset signal handlers to default behavior
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        logger.info(f"🚀 Sentinel Worker Started (PID: {os.getpid()})")

        # Run isolated asyncio loop
        try:
            asyncio.run(self._main_loop())
        except KeyboardInterrupt:
            logger.info("🛑 Worker stopping (KeyboardInterrupt)")
        except Exception as e:
            logger.critical(f"💥 Worker crashed: {e}", exc_info=True)
        finally:
            logger.info("💀 Worker Process Terminated")

    async def _main_loop(self):
        """Main async loop handles connection and queues."""
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    await self._connect_and_listen(session)
                except Exception as e:
                    logger.error(f"❌ Connection error: {e}. Reconnecting in 2s...")
                    await asyncio.sleep(2)

    async def _connect_and_listen(self, session: aiohttp.ClientSession):
        """Manage single connection lifecycle."""
        logger.info(f"🔌 Connecting to {self.base_url}...")

        async with session.ws_connect(self.base_url, heartbeat=20) as ws:
            self.ws = ws
            logger.info("✅ Connected! Resubscribing...")

            # Resubscribe to existing topics
            if self.subscriptions:
                await self._send_subscribe(list(self.subscriptions))

            # Consumer tasks
            socket_task = asyncio.create_task(self._read_socket(ws))
            command_task = asyncio.create_task(self._process_commands())
            stats_task = asyncio.create_task(self._stats_loop())

            # Wait for disconnection or stop
            done, pending = await asyncio.wait(
                [socket_task, command_task, stats_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cleanup
            for task in pending:
                task.cancel()

            self.ws = None
            logger.warning("⚠️ WebSocket disconnected or task ended.")

    async def _read_socket(self, ws: aiohttp.ClientWebSocketResponse):
        """Read loop from WebSocket."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = msg.json()
                    # Push to main process (non-blocking if queue has space)
                    # Use put_nowait to crash early if queue is full (backpressure signal)
                    # or handle full queue gracefully?
                    # For critical financial data, we prefer latest data, BUT trade events must be reliable.
                    # Queue should be large enough.
                    self.output_queue.put(data)
                    self.msg_count += 1
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket Error: {ws.exception()}")
                break

    async def _process_commands(self):
        """Read commands from main process via input_queue."""
        # Since Queue.get() is blocking and not async-friendly, we use a run_in_executor
        # or polling. Polling is safer for simple multiprocessing queue adaptability.
        loop = asyncio.get_running_loop()

        while self.running:
            try:
                # Use executor to avoid blocking the asyncio loop with Queue.get
                # We fetch with a short timeout to yield control back to asyncio
                cmd = await loop.run_in_executor(None, self._queue_get_timeout)

                if cmd:
                    await self._handle_command(cmd)
            except Exception as e:
                logger.error(f"Command processing error: {e}")
                await asyncio.sleep(0.1)

    def _queue_get_timeout(self):
        """Blocking get with timeout wrapper."""
        try:
            return self.input_queue.get(timeout=0.1)
        except multiprocessing.queues.Empty:
            return None

    async def _handle_command(self, cmd: Dict):
        """Execute command."""
        action = cmd.get("action")
        payload = cmd.get("payload")

        if action == "SUBSCRIBE":
            streams = payload if isinstance(payload, list) else [payload]
            new_streams = [s for s in streams if s not in self.subscriptions]
            if new_streams:
                self.subscriptions.update(new_streams)
                await self._send_subscribe(new_streams)

        elif action == "UNSUBSCRIBE":
            streams = payload if isinstance(payload, list) else [payload]
            to_remove = [s for s in streams if s in self.subscriptions]
            if to_remove:
                for s in to_remove:
                    self.subscriptions.discard(s)
                await self._send_unsubscribe(to_remove)

        elif action == "STOP":
            self.running = False
            if self.ws:
                await self.ws.close()

    async def _send_subscribe(self, streams: List[str]):
        """Send SUBSCRIBE command to Binance."""
        if not self.ws or not streams:
            return

        payload = {"method": "SUBSCRIBE", "params": streams, "id": int(time.time() * 1000)}
        try:
            await self.ws.send_json(payload)
            logger.info(f"📤 Subscribed to {len(streams)} streams")
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")

    async def _send_unsubscribe(self, streams: List[str]):
        """Send UNSUBSCRIBE command."""
        if not self.ws or not streams:
            return

        payload = {"method": "UNSUBSCRIBE", "params": streams, "id": int(time.time() * 1000)}
        try:
            await self.ws.send_json(payload)
            logger.info(f"📤 Unsubscribed from {len(streams)} streams")
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")

    async def _stats_loop(self):
        """Log stats periodically."""
        while self.running:
            await asyncio.sleep(60)
            now = time.time()
            if self.last_stats_ts > 0:
                elapsed = now - self.last_stats_ts
                rate = self.msg_count / elapsed
                logger.info(
                    f"📊 Stats: {self.msg_count} msgs in {elapsed:.1f}s ({rate:.1f} msg/s) | Subs: {len(self.subscriptions)}"
                )

            self.msg_count = 0
            self.last_stats_ts = now
