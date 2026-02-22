import asyncio
import hashlib
import hmac
import logging
import multiprocessing
import signal
import time
import traceback
from enum import IntEnum
from typing import Dict, Optional
from urllib.parse import urlencode

import aiohttp

# Attempt to use orjson for speed (Step 2 of Protocol), fallback to json
try:
    import orjson as json
except ImportError:
    import json


class Priority(IntEnum):
    """Order Priority Levels."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class ExecutionProcess(multiprocessing.Process):
    """
    Dedicated process for executing orders.
    Isolates network I/O and serialization overhead from the main strategy loop.
    """

    def __init__(
        self,
        command_pipe: multiprocessing.connection.Connection,
        res_queue: multiprocessing.Queue,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
    ):
        super().__init__(name="ExecutionAirlock")
        self.cmd_pipe = command_pipe
        self.res_queue = res_queue
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.stop_event = multiprocessing.Event()
        self._session: Optional[aiohttp.ClientSession] = None

    def run(self):
        """Entry point for the separate process."""
        # 1. Setup Signal Handlers (Ignore SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # 2. Setup Logging
        self._setup_logging()
        self.logger.info("🚀 Execution Process (Airlock) Started")

        # 3. Start Async Event Loop
        try:
            # We use a custom event loop setup for highest performance
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._main_loop())
        except Exception as e:
            self.logger.critical(f"💥 Execution Process Crashed: {e}\n{traceback.format_exc()}")
        finally:
            self.logger.info("🛑 Execution Process Stopped")

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        )
        self.logger = logging.getLogger("ExecutionAirlock")

    async def _main_loop(self):
        """Main async loop consuming the pipe."""
        connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            self._session = session
            # Phase 4: WebSocket Execution Connection
            self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
            self._ws_futures: Dict[str, asyncio.Future] = {}
            ws_task = asyncio.create_task(self._maintain_ws(session))

            self.logger.info("✅ HTTP Keep-Alive Session Established")

            # Phase 8: Pipe-based Event Reactor
            # We register the pipe's file descriptor to the event loop.
            # This allows the loop to wake up ONLY when there is data, with sub-ms precision.
            loop = asyncio.get_running_loop()

            def handle_command():
                try:
                    while self.cmd_pipe.poll():
                        item = self.cmd_pipe.recv()
                        if item is None:
                            self.logger.info("🧪 Poison pill received. Exiting.")
                            self.stop_event.set()
                            return

                        # Parse Item: (priority, request_id, endpoint, method, payload, signed)
                        priority, request_id, endpoint, method, payload, signed = item

                        # Fire-and-Forget execution task
                        asyncio.create_task(self._execute_request(request_id, endpoint, method, payload, signed))
                except EOFError:
                    self.logger.warning("🔌 Command Pipe closed unexpectedly.")
                    self.stop_event.set()
                except Exception as e:
                    self.logger.error(f"⚠️ Reactor Error: {e}")

            loop.add_reader(self.cmd_pipe.fileno(), handle_command)
            self.logger.info("🔥 Pipe Reactor Registered (Zero-Latency)")

            while not self.stop_event.is_set():
                await asyncio.sleep(0.1)  # Keep loop alive, actual work triggered by handler

            loop.remove_reader(self.cmd_pipe.fileno())
            if ws_task:
                ws_task.cancel()

            if ws_task:
                ws_task.cancel()

    async def _maintain_ws(self, session: aiohttp.ClientSession):
        """Maintains the WebSocket connection for execution."""
        ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws-fapi/v1"
        # Adjust URL for testnet/live matching
        if "testnet" in self.base_url:
            ws_url = "wss://testnet.binancefuture.com/ws-fapi/v1"
        else:
            ws_url = "wss://ws-fapi.binance.com/ws-fapi/v1"

        while not self.stop_event.is_set():
            try:
                self.logger.info(f"🔌 Execution WS Connecting to {ws_url}...")
                async with session.ws_connect(ws_url, heartbeat=20) as ws:
                    self._ws = ws
                    self.logger.info("✅ Execution WS Connected")

                    # Authenticate / Logon if required?
                    # Binance Futures WS API often uses signed requests per message,
                    # OR a logon session. For 'ws-fapi/v1', we usually send order.place requests.
                    # Standard API doesn't have a specific 'logon' for ordering, usually.
                    # But if we are using the specific 'order' endpoint, we treat it request-response.

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                # Handle response mapping to futures
                                req_id = data.get("id")
                                if req_id and req_id in self._ws_futures:
                                    if not self._ws_futures[req_id].done():
                                        self._ws_futures[req_id].set_result(data)
                            except Exception as e:
                                self.logger.error(f"WS Parse Error: {e}")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            break
            except Exception as e:
                self.logger.error(f"⚠️ Execution WS Disconnected: {e}")
                self._ws = None
                await asyncio.sleep(5)

    async def _execute_request(self, request_id: str, endpoint: str, method: str, payload: Dict, signed: bool):
        start_ts = time.time()

        # Phase 4: WebSocket Routing
        # If WS is connected and this is a supported operation (POST /order, DELETE /order)
        # We route via WS.
        use_ws = False
        if self._ws is not None and not self._ws.closed:
            if method == "POST" and endpoint == "/fapi/v1/order":
                use_ws = True
            elif method == "DELETE" and endpoint == "/fapi/v1/order":
                use_ws = True
            # Batch orders via WS? Not supported on standard WS API usually, check docs.
            # Assuming NO for batch currently.

        if use_ws:
            try:
                # Construct WS Payload
                # https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Trade-Streams
                # Actually, for V1 it is:
                # { "id": "req_id", "method": "order.place", "params": { ... } }

                ws_method = "order.place"
                if method == "DELETE":
                    ws_method = "order.cancel"

                # Sign the payload parameters
                signed_params = self._sign_payload(payload.copy())

                # Phase 240: WS-FAPI requires apiKey inside the params object
                # (unlike REST which uses the X-MBX-APIKEY header)
                signed_params["apiKey"] = self.api_key

                # Binance WS Params are usually pure key-values
                ws_req = {"id": request_id, "method": ws_method, "params": signed_params}

                # Register Future
                future = asyncio.get_running_loop().create_future()
                self._ws_futures[request_id] = future

                # Send
                await self._ws.send_json(ws_req, dumps=json.dumps)

                # Wait for response (High Performance Wait)
                try:
                    res_data = await asyncio.wait_for(future, timeout=2.0)

                    # Transform Response to match REST format if needed
                    # WS Success: { "id": "...", "result": { ... }, "rateLimits": ... }
                    # WS Error: { "id": "...", "error": { "code": -1111, "msg": "..." } }

                    success = "result" in res_data
                    data = res_data.get("result", {})
                    if "error" in res_data:
                        success = False
                        data = res_data["error"]

                    latency_ms = (time.time() - start_ts) * 1000

                    self.res_queue.put(
                        {
                            "request_id": request_id,
                            "status": 200 if success else 400,  # Approximate status
                            "data": data,
                            "latency_ms": latency_ms,
                            "success": success,
                        }
                    )
                    return

                except asyncio.TimeoutError:
                    self.logger.warning(f"⏰ WS Request Timed Out: {request_id}")
                    # Fallback to REST if WS times out?
                    # For now just let it fail or fall through to REST below if we catch it?
                    # Let's fall through to REST by unsetting use_ws?
                    # No, timeout means uncertain state. Better to fail or check.
                    # But if we want robust fallback, we should try REST.
                    pass
                finally:
                    self._ws_futures.pop(request_id, None)

            except Exception as e:
                self.logger.error(f"❌ WS Send Error: {e}")
                # Fallback to REST

        # ... Fallback to REST ...

        # Prepare URL
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}

        # Sign if needed
        if signed:
            payload = self._sign_payload(payload)

        try:
            # Use params for GET/DELETE, data/json for POST/PUT?
            # Binance uses query params for everything usually, or body for some POSTs.
            # Standard connector uses params for most.
            # Let's assume params for now as per `binance_native_connector._request` logic
            # which usually passes `params=signed_params`.

            # Phase 240: Use list of tuples to ensure aiohttp preserves parameter order
            # Matching the signature exactly is critical for HFT.
            payload_items = list(payload.items())

            async with self._session.request(method, url, params=payload_items, headers=headers, timeout=5.0) as resp:
                text = await resp.text()

                try:
                    data = json.loads(text)
                except Exception:
                    data = {"error": "json_parse_error", "raw": text}

                success = 200 <= resp.status < 300
                latency_ms = (time.time() - start_ts) * 1000

                self.res_queue.put(
                    {
                        "request_id": request_id,
                        "status": resp.status,
                        "data": data,
                        "latency_ms": latency_ms,
                        "success": success,
                    }
                )

                if latency_ms > 100:
                    self.logger.warning(f"🐢 Slow Request: {method} {endpoint} took {latency_ms:.2f}ms")

        except Exception as e:
            self.logger.error(f"❌ Network Error for {request_id}: {e}")
            self.res_queue.put({"request_id": request_id, "status": 0, "data": {"error": str(e)}, "success": False})

    def _sign_payload(self, payload: Dict) -> Dict:
        """Signs the payload using HMAC SHA256 with strict parameter sorting."""
        if "timestamp" not in payload:
            payload["timestamp"] = int(time.time() * 1000)

        # Phase 240: Strict parameter sorting to prevent -1022 (Signature mismatch)
        # We must ensure the query string used for signing matches the one sent.
        items = sorted([(k, v) for k, v in payload.items() if v is not None])
        query_string = urlencode(items)

        signature = hmac.new(self.api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

        # Reconstruct as an ordered dict with signature at the end
        signed_payload = dict(items)
        signed_payload["signature"] = signature
        return signed_payload
