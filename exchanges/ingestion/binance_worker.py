import asyncio
import logging
import multiprocessing
import os
import signal
import time
from typing import Dict, List, Optional, Set

import aiohttp

# Phase 2: High-Performance Serialization (Project Supersonic)
try:
    import orjson

    # orjson returns bytes, aiohttp expects str for text frames
    json_loads = orjson.loads

    def json_dumps(x):
        return orjson.dumps(x).decode("utf-8")

    USING_ORJSON = True
except ImportError:
    import json

    json_loads = json.loads
    json_dumps = json.dumps
    USING_ORJSON = False

# Configure minimal logging for the worker
logger = logging.getLogger("BinanceWorker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # Console (mirrored to parent)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | WORKER:%(process)d:%(name)s | %(levelname)s | %(message)s"))
    logger.addHandler(ch)
    # Dedicated debug file
    fh = logging.FileHandler("logs/workers.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)


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
        worker_id: str = "Shard-0",
    ):
        super().__init__(name=f"Binance-{worker_id}")
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.base_url = base_url
        self.worker_id = worker_id

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

        logger.info(f"🚀 {self.worker_id} Started (PID: {os.getpid()})")

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
        logger.info(f"🔌 Connecting to {self.base_url}... (ORJSON: {USING_ORJSON})")

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
        """Read loop from WebSocket with Phase 240 Ingestion Airlock."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = msg.json(loads=json_loads)

                    # Phase 240: In-Worker Normalization (The Airlock)
                    # We unwrap the "stream" wrapper here if present
                    if "stream" in data and "data" in data:
                        stream_name = data["stream"]
                        payload = data["data"]
                        if "@depth" in stream_name and "s" not in payload:
                            payload["s"] = stream_name.split("@")[0].upper()
                        data = payload

                    event_type = data.get("e")

                    # Check for depth snapshots (no "e" field but has "b" and "a")
                    if not event_type and "b" in data and "a" in data:
                        event_type = "depthSnapshot"
                    elif event_type == "depthUpdate" and "b" in data and "a" in data:
                        event_type = "depthSnapshot"

                    # Normalized Packet Structure: (TYPE_CODE, WORKER_TS, DATA)
                    # TYPE_CODES: 1: aggTrade, 2: ticker, 3: depth, 4: orderUpdate, 5: accountUpdate, 0: raw/other
                    normalized = None
                    worker_ts = time.time()

                    if event_type == "aggTrade":
                        # (1, symbol, price, qty, ts, is_maker, trade_id)
                        normalized = (
                            1,
                            worker_ts,
                            (
                                data.get("s"),
                                float(data.get("p", 0)),
                                float(data.get("q", 0)),
                                data.get("T"),
                                data.get("m"),
                                data.get("a"),
                            ),
                        )
                    elif event_type in ("24hrTicker", "bookTicker", "@ticker", "ticker") or (
                        not event_type and "c" in data and "b" in data
                    ):
                        # (2, symbol, last, bid, ask, ts)
                        normalized = (
                            2,
                            worker_ts,
                            (
                                data.get("s"),
                                float(data.get("c", 0)),
                                float(data.get("b", 0)),
                                float(data.get("a", 0)),
                                data.get("E", int(worker_ts * 1000)),
                            ),
                        )
                    elif event_type == "depthSnapshot":
                        # (3, symbol, bids, asks, ts)
                        normalized = (
                            3,
                            worker_ts,
                            (
                                data.get("s"),
                                [[float(p), float(q)] for p, q in data.get("b", [])],
                                [[float(p), float(q)] for p, q in data.get("a", [])],
                                data.get("T") or data.get("E") or int(worker_ts * 1000),
                            ),
                        )
                    elif event_type == "ORDER_TRADE_UPDATE":
                        normalized = (4, worker_ts, data)
                    elif event_type == "ACCOUNT_UPDATE":
                        normalized = (5, worker_ts, data)
                    else:
                        # Raw Fallback for other types
                        data["_worker_ts"] = worker_ts
                        normalized = (0, worker_ts, data)

                    # Push to main process
                    try:
                        self.output_queue.put_nowait(normalized)
                        self.msg_count += 1
                    except Exception:
                        if self.msg_count % 100 == 0:
                            logger.warning(f"⚠️ [{self.worker_id}] Output queue full, dropping message")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket Error: {ws.exception()}")
                break
            else:
                logger.info(f"📥 Received non-text message: {msg.type}")

    async def _process_commands(self):
        """Read commands from main process via input_queue."""
        loop = asyncio.get_running_loop()

        while self.running:
            try:
                cmd = await loop.run_in_executor(None, self._queue_get_timeout)
                if cmd:
                    logger.info(f"📥 Received Command: {cmd.get('action')}")
                    await self._handle_command(cmd)
                else:
                    await asyncio.sleep(0.05)  # Yield if empty
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
            await self.ws.send_json(payload, dumps=json_dumps)
            logger.info(f"📤 Subscribed to {len(streams)} streams")
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")

    async def _send_unsubscribe(self, streams: List[str]):
        """Send UNSUBSCRIBE command."""
        if not self.ws or not streams:
            return

        payload = {"method": "UNSUBSCRIBE", "params": streams, "id": int(time.time() * 1000)}
        try:
            await self.ws.send_json(payload, dumps=json_dumps)
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
