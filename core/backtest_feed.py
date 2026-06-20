"""
Backtest Feed for Casino-V3.
Replays historical data as TickEvents.
"""

import asyncio
import logging
import os

import aiosqlite
import pandas as pd

from utils.symbol_norm import normalize_symbol

from .events import EventType, TickEvent

# Use orjson for faster JSON parsing (10-50x faster than stdlib json)
try:
    import orjson as json
except ImportError:
    import json

logger = logging.getLogger(__name__)


class BacktestFeed:
    """
    Simulates a live data feed by replaying historical data.
    """

    def __init__(
        self,
        engine,
        data_path: str,
        symbol: str,
        delay: float = 0.001,
        exchange_connector=None,
        limit: int = None,
        depth_db_path: str = None,
    ):
        self.engine = engine
        self.data_path = data_path
        self.symbol = symbol
        self.delay = delay  # Delay between events to simulate time
        self.exchange_connector = exchange_connector  # Connector to update with price data
        self.running = False
        self.data = None
        self.limit = limit
        self.depth_db_path = depth_db_path
        self._last_synth_depth_ts = 0.0

        # Mock Adapter for Croupier (Legacy support if no connector provided)
        self.adapter = self._create_mock_adapter()

    def _create_mock_adapter(self):
        """Create a mock adapter that Croupier can use."""

        class MockAdapter:
            def __init__(self, symbol):
                self.name = "BacktestAdapter"
                self.symbol = symbol
                self.connector = type("MockConnector", (), {"exchange": type("Exchange", (), {"id": "mock"})()})()

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def start(self):
                pass

            async def stop(self):
                pass

            async def tick(self, timestamp):
                pass

        return MockAdapter(self.symbol)

    async def load_data(self):
        """Load data from CSV/Parquet or prepare SQLite connection. Non-blocking."""
        self.data = pd.DataFrame()
        if self.data_path:
            logger.info(f"📂 Loading backtest data from {self.data_path}...")
            if self.data_path.endswith(".csv"):
                self.data = pd.read_csv(self.data_path)
            elif self.data_path.endswith(".parquet"):
                self.data = pd.read_parquet(self.data_path)
            else:
                raise ValueError("Unsupported file format")

            # Detect data format (trades or candles)
            if all(col in self.data.columns for col in ["timestamp", "price", "volume", "side"]):
                self.mode = "TRADES"
                logger.info("✅ Detected Real Trade Data format.")
            elif all(col in self.data.columns for col in ["timestamp", "open", "high", "low", "close", "volume"]):
                self.mode = "CANDLES"
                logger.info("✅ Detected Candle Data format.")
            else:
                raise ValueError(f"Data missing required columns. Found: {self.data.columns}")

            # Convert timestamp to epoch seconds if needed
            if not pd.api.types.is_numeric_dtype(self.data["timestamp"]):
                self.data["timestamp"] = pd.to_datetime(self.data["timestamp"]).astype(int) // 10**9

            # Add a column to identify event type later
            self.data["event_type"] = "TICK"

            # Sort combined feed by timestamp
            if not self.data.empty:
                self.data = self.data.sort_values("timestamp").reset_index(drop=True)
                logger.info(f"✅ Total feed size: {len(self.data)} rows.")
            else:
                logger.error("❌ Final backtest feed is empty! Check data sources.")

        else:
            self.mode = "DB_ONLY"
            if not getattr(self, "depth_db_path", None) or not os.path.exists(self.depth_db_path):
                logger.warning(f"⚠️ DB file not found: {self.depth_db_path}")

    async def run(self):
        """Start the replay and wait for completion."""
        self.running = True
        await self.load_data()
        await self._replay_loop()

    async def connect(self):
        """Legacy connect method."""
        pass

    async def disconnect(self):
        """Stop the replay."""
        self.running = False

    async def subscribe_ticker(self, symbol: str):
        """Mock subscription."""
        logger.info(f"📡 Backtest subscribed to ticker: {symbol}")

    async def _replay_loop(self):
        """Replay data using an async streaming generator for SQLite or itertuples for CSV."""
        logger.info(f"▶️ Starting Backtest Replay (Mode: {self.mode})...")

        if self.data_path and not self.data.empty:
            # Legacy in-memory loop for CSV/Parquet
            for row in self.data.itertuples(index=True):
                if not self.running:
                    break

                if self.limit and row.Index >= self.limit:
                    logger.info(f"🛑 Reached backtest limit: {self.limit} events")
                    break

                event_type = getattr(row, "event_type", "TICK")

                if event_type == "DEPTH":
                    await self._emit_depth(row.timestamp, row.bids, row.asks)
                elif event_type == "TICK":
                    await self._emit_tick(row.timestamp, row.price, row.volume, row.side)
                elif event_type == "CANDLE" and self.mode == "CANDLES":
                    await self._emit_candle_ticks(row.timestamp, row.open, row.high, row.low, row.close, row.volume)

                if self.delay > 0:
                    await asyncio.sleep(self.delay)

            logger.info("🏁 Backtest Replay Finished.")
            self.engine.running = False
            return

        # --- STREAMING LOOP FOR SQLITE ---
        if self.mode == "DB_ONLY" and getattr(self, "depth_db_path", None):
            norm_symbol = normalize_symbol(self.symbol)
            async with aiosqlite.connect(self.depth_db_path) as db:
                limit_clause = f" LIMIT {self.limit}" if self.limit else ""

                # Check tables
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_trades'")
                has_trades = bool(await cursor.fetchone())

                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_candles'")
                has_candles = bool(await cursor.fetchone())

                if has_trades:
                    self.mode = "TRADES"
                    trades_cursor = await db.execute(
                        f"SELECT timestamp, 'TICK', price, amount, side FROM market_trades WHERE symbol = ? ORDER BY timestamp ASC{limit_clause}",
                        (norm_symbol,),
                    )
                elif has_candles:
                    self.mode = "CANDLES"
                    trades_cursor = await db.execute(
                        f"SELECT timestamp, 'CANDLE', open, high, low, close, volume FROM price_candles WHERE symbol = ? ORDER BY timestamp ASC{limit_clause}",
                        (norm_symbol,),
                    )
                else:
                    trades_cursor = None

                depth_cursor = await db.execute(
                    f"SELECT timestamp, 'DEPTH', bids, asks FROM depth_snapshots WHERE symbol = ? ORDER BY timestamp ASC{limit_clause}",
                    (norm_symbol,),
                )

                # Async Two-Pointer Merge
                from collections import deque

                CHUNK_SIZE = 100000

                buf_depth = deque(await depth_cursor.fetchmany(CHUNK_SIZE))
                buf_trades = deque(await trades_cursor.fetchmany(CHUNK_SIZE)) if trades_cursor else deque()

                events_processed = 0

                while (buf_depth or buf_trades) and self.running:
                    if self.limit and events_processed >= self.limit:
                        logger.info(f"🛑 Reached backtest limit: {self.limit} events")
                        break

                    # Refill buffers
                    if not buf_depth and depth_cursor:
                        fetched = await depth_cursor.fetchmany(CHUNK_SIZE)
                        if fetched:
                            buf_depth.extend(fetched)
                        else:
                            depth_cursor = None

                    if not buf_trades and trades_cursor:
                        fetched = await trades_cursor.fetchmany(CHUNK_SIZE)
                        if fetched:
                            buf_trades.extend(fetched)
                        else:
                            trades_cursor = None

                    # Pick next event
                    if buf_depth and buf_trades:
                        if buf_depth[0][0] <= buf_trades[0][0]:
                            row = buf_depth.popleft()
                        else:
                            row = buf_trades.popleft()
                    elif buf_depth:
                        row = buf_depth.popleft()
                    elif buf_trades:
                        row = buf_trades.popleft()
                    else:
                        break

                    events_processed += 1

                    # Process event
                    event_type = row[1]
                    if event_type == "DEPTH":
                        await self._emit_depth(row[0], row[2], row[3])
                    elif event_type == "TICK":
                        await self._emit_tick(row[0], row[2], row[3], row[4])
                    elif event_type == "CANDLE":
                        await self._emit_candle_ticks(row[0], row[2], row[3], row[4], row[5], row[6])

                    if self.delay > 0:
                        await asyncio.sleep(self.delay)

        logger.info("🏁 Backtest Replay Finished.")
        self.engine.running = False

    async def _emit_candle_ticks(self, timestamp, open_p, high_p, low_p, close_p, volume):
        is_green = close_p > open_p
        await self._emit_tick(timestamp, open_p, volume * 0.1, "BUY" if is_green else "SELL")
        if is_green:
            await self._emit_tick(timestamp, low_p, volume * 0.2, "BUY")
            await self._emit_tick(timestamp, high_p, volume * 0.4, "SELL")
        else:
            await self._emit_tick(timestamp, high_p, volume * 0.2, "SELL")
            await self._emit_tick(timestamp, low_p, volume * 0.4, "BUY")
        await self._emit_tick(timestamp, close_p, volume * 0.3, "SELL" if is_green else "BUY")

    async def _emit_tick(self, timestamp, price, volume, side="UNKNOWN"):
        """Emit a single tick event."""
        # System now expects BUY/SELL (Binance Style) for 100% parity
        normalized_side = str(side).upper()
        if normalized_side == "BID":
            normalized_side = "SELL"
        elif normalized_side == "ASK":
            normalized_side = "BUY"
        # Ensure it's never anything else for parity
        if normalized_side not in ["BUY", "SELL"]:
            normalized_side = "BUY" if normalized_side.startswith("B") else "SELL"

        # Update Virtual Exchange first
        if self.exchange_connector:
            if hasattr(self.exchange_connector, "process_tick"):
                tick_data = {"price": price, "timestamp": timestamp}
                await self.exchange_connector.process_tick(tick_data)

        event = TickEvent(
            type=EventType.TICK,
            timestamp=timestamp,  # Use historical timestamp
            symbol=self.symbol,
            price=float(price),
            volume=float(volume),
            side=normalized_side,
        )
        await self.engine.dispatch(event)

    async def _emit_depth(self, timestamp, bids_json, asks_json):
        """Emit a single depth event."""
        from core.events import OrderBookEvent

        try:
            bids = json.loads(bids_json) if isinstance(bids_json, str) else bids_json
            asks = json.loads(asks_json) if isinstance(asks_json, str) else asks_json
            event = OrderBookEvent(
                type=EventType.ORDER_BOOK,
                timestamp=float(timestamp),
                symbol=self.symbol,
                bids=bids,
                asks=asks,
            )
            await self.engine.dispatch(event)
        except Exception as e:
            logger.error(f"Failed to parse and emit depth event: {e}")
