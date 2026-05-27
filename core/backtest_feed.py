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
        """Load data from CSV/Parquet and optionally from the SQLite depth/price DB. Non-blocking."""
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
        else:
            self.mode = "DB_ONLY"

        # --- Load all data from SQLite using a single connection ---
        if getattr(self, "depth_db_path", None) and self.depth_db_path is not None:
            if os.path.exists(self.depth_db_path):
                norm_symbol = normalize_symbol(self.symbol)
                try:
                    logger.info(f"📂 Loading data from {self.depth_db_path}...")
                    async with aiosqlite.connect(self.depth_db_path) as db:
                        # 1. Depth snapshots
                        cursor = await db.execute(
                            "SELECT timestamp, symbol, bids, asks FROM depth_snapshots WHERE symbol = ?",
                            (norm_symbol,),
                        )
                        rows = await cursor.fetchall()
                        columns = [desc[0] for desc in cursor.description]
                        depth_df = pd.DataFrame(rows, columns=columns)
                        if not depth_df.empty:
                            depth_df["event_type"] = "DEPTH"
                            self.data = pd.concat([self.data, depth_df], ignore_index=True)
                            logger.info(f"✅ Loaded {len(depth_df)} depth snapshots.")
                        else:
                            logger.warning("⚠️ No depth snapshots found for symbol in given DB.")

                        # 2. Price candles
                        cursor = await db.execute(
                            "SELECT timestamp, open, high, low, close, volume FROM price_candles WHERE symbol = ?",
                            (norm_symbol,),
                        )
                        rows = await cursor.fetchall()
                        columns = [desc[0] for desc in cursor.description]
                        price_df = pd.DataFrame(rows, columns=columns)
                        if not price_df.empty:
                            price_df["event_type"] = "CANDLE"
                            self.data = pd.concat([self.data, price_df], ignore_index=True)
                            logger.info(f"✅ Loaded {len(price_df)} price candles.")
                        else:
                            logger.warning("⚠️ No price candles found for symbol in given DB.")

                        # 3. Market trades
                        cursor = await db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_trades'"
                        )
                        if await cursor.fetchone():
                            cursor = await db.execute(
                                "SELECT timestamp, price, amount as volume, side FROM market_trades WHERE symbol = ?",
                                (norm_symbol,),
                            )
                            rows = await cursor.fetchall()
                            columns = [desc[0] for desc in cursor.description]
                            trades_df = pd.DataFrame(rows, columns=columns)
                            if not trades_df.empty:
                                trades_df["event_type"] = "TICK"
                                self.data = pd.concat([self.data, trades_df], ignore_index=True)
                                self.mode = "TRADES"
                                logger.info(f"✅ Loaded {len(trades_df)} market trades.")
                            else:
                                logger.warning("⚠️ No market trades found for symbol in given DB.")
                except Exception as e:
                    logger.error(f"❌ Failed to load data: {e}")
            else:
                logger.warning(f"⚠️ DB file not found: {self.depth_db_path}")

        # Sort combined feed by timestamp
        if not self.data.empty:
            self.data = self.data.sort_values("timestamp").reset_index(drop=True)
            logger.info(f"✅ Total merged feed size: {len(self.data)} rows.")

            # --- MANDATORY L2 CHECK (High-Fidelity Guard) ---
            if self.depth_db_path:
                depth_count = len(self.data[self.data["event_type"] == "DEPTH"])
                if depth_count == 0:
                    logger.error("❌ FATAL: High-Fidelity mode enabled but NO depth snapshots found!")
                    raise ValueError("Casino-V3 requires REAL L2 data. Use l2_processor.py to prepare your dataset.")
                logger.info(f"🛡️ High-Fidelity Guard: {depth_count} real L2 snapshots verified.")
        else:
            logger.error("❌ Final backtest feed is empty! Check data sources.")

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
        """Replay data row by row using itertuples for 10-100x faster iteration."""
        logger.info(f"▶️ Starting Backtest Replay (Mode: {self.mode})...")

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
                is_green = row.close > row.open
                total_vol = row.volume

                await self._emit_tick(row.timestamp, row.open, total_vol * 0.1, "BUY" if is_green else "SELL")
                if is_green:
                    await self._emit_tick(row.timestamp, row.low, total_vol * 0.2, "BUY")
                    await self._emit_tick(row.timestamp, row.high, total_vol * 0.4, "SELL")
                else:
                    await self._emit_tick(row.timestamp, row.high, total_vol * 0.2, "SELL")
                    await self._emit_tick(row.timestamp, row.low, total_vol * 0.4, "BUY")
                await self._emit_tick(row.timestamp, row.close, total_vol * 0.3, "SELL" if is_green else "BUY")

            if self.delay > 0:
                await asyncio.sleep(self.delay)

        logger.info("🏁 Backtest Replay Finished.")
        self.engine.running = False

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
