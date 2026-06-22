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


def resolve_db_symbol(symbol: str, db_path: str = None) -> str:
    """
    Resuelve el símbolo exacto como está guardado en la DB.

    Estrategia:
    1. Extraer el símbolo base del filename SI el símbolo parece derivado del filename
    2. Si el símbolo ya es válido (ej: SOLUSDT), usarlo
    3. Fallback: normalizar y agregar USDT

    Ejemplos:
    - resolve_db_symbol("SOL_monthly_2026_03/USDT:USDT", "SOL_monthly_2026_03.db") -> "SOLUSDT"
    - resolve_db_symbol("SOLUSDT", "...") -> "SOLUSDT"
    - resolve_db_symbol("XRP/USDT", "...") -> "XRPUSDT"
    """
    import re

    # Estrategia principal: extraer del filename si está disponible
    if db_path:
        filename = os.path.basename(db_path).replace(".db", "")

        # Pattern: SYMBOL_anything (ej: SOL_monthly_2026_03, ADAUSDT_BALANCE_2025-11)
        match = re.match(r"^([A-Z]+USDT|[A-Z]+)_", filename)
        if match:
            extracted = match.group(1)
            # Si el extraído ya tiene USDT, usarlo
            if "USDT" in extracted:
                return extracted
            # Si no, agregar USDT
            return extracted + "USDT"

    # Fallback: usar el símbolo normalizado
    base = normalize_symbol(symbol)

    if "USDT" in base:
        return base

    return base + "USDT"


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
        """Replay data using Pandas itertuples over Time-Window chunks."""
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

        # --- TIME-WINDOW STREAMING FOR SQLITE ---
        if self.mode == "DB_ONLY" and getattr(self, "depth_db_path", None):
            # Resolve exact symbol as stored in DB
            db_symbol = resolve_db_symbol(self.symbol, self.depth_db_path)

            async with aiosqlite.connect(self.depth_db_path) as db:
                # 1. Get min and max timestamps
                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_trades'")
                has_trades = bool(await cursor.fetchone())

                cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_candles'")
                has_candles = bool(await cursor.fetchone())

                # Find overall time boundaries
                min_ts = float("inf")
                max_ts = 0

                if has_trades:
                    self.mode = "TRADES"
                    cursor = await db.execute(
                        "SELECT MIN(timestamp), MAX(timestamp) FROM market_trades WHERE symbol = ?", (db_symbol,)
                    )
                    row = await cursor.fetchone()
                    if row and row[0]:
                        min_ts = min(min_ts, row[0])
                        max_ts = max(max_ts, row[1])
                elif has_candles:
                    self.mode = "CANDLES"
                    cursor = await db.execute(
                        "SELECT MIN(timestamp), MAX(timestamp) FROM price_candles WHERE symbol = ?", (db_symbol,)
                    )
                    row = await cursor.fetchone()
                    if row and row[0]:
                        min_ts = min(min_ts, row[0])
                        max_ts = max(max_ts, row[1])

                cursor = await db.execute(
                    "SELECT MIN(timestamp), MAX(timestamp) FROM depth_snapshots WHERE symbol = ?", (db_symbol,)
                )
                row = await cursor.fetchone()
                if row and row[0]:
                    min_ts = min(min_ts, row[0])
                    max_ts = max(max_ts, row[1])

                if min_ts == float("inf"):
                    logger.error("❌ No data found in database!")
                    self.engine.running = False
                    return

                logger.info(f"📅 Backtest Time Range: {min_ts} -> {max_ts} ({max_ts - min_ts} seconds)")

                # 2. Create covering indices for faster UNION ALL queries
                await self._create_optimized_indices(db, db_symbol)

                # 3. Time-Window Chunking (e.g. 24 hours = 86400 seconds)
                WINDOW_SIZE = 86400
                current_start = min_ts
                events_processed = 0

                while current_start <= max_ts and self.running:
                    current_end = current_start + WINDOW_SIZE
                    logger.info(f"⏳ Loading Time Window: {current_start} to {current_end}...")

                    # UNION ALL query - let SQLite C engine do the merge and sort
                    if has_trades:
                        union_query = """
                            SELECT timestamp, 0 as event_type, bids, asks, NULL as price, NULL as volume, NULL as side
                            FROM depth_snapshots
                            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
                            UNION ALL
                            SELECT timestamp, 1 as event_type, NULL, NULL, price, amount, side
                            FROM market_trades
                            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
                            ORDER BY timestamp ASC
                        """
                        params = (db_symbol, current_start, current_end, db_symbol, current_start, current_end)
                    elif has_candles:
                        # Candles need special handling - we'll fetch separately to avoid column mismatch
                        union_query = """
                            SELECT timestamp, 0 as event_type, bids, asks, NULL, NULL, NULL
                            FROM depth_snapshots
                            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
                            ORDER BY timestamp ASC
                        """
                        params = (db_symbol, current_start, current_end)
                        candle_query = """
                            SELECT timestamp, open, high, low, close, volume
                            FROM price_candles
                            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
                            ORDER BY timestamp ASC
                        """
                        candle_params = (db_symbol, current_start, current_end)
                    else:
                        logger.error("No data source available")
                        break

                    cursor = await db.execute(union_query, params)

                    # Batch streaming with fetchmany to reduce Python overhead
                    BATCH_SIZE = 10000
                    window_events = 0

                    while True:
                        rows = await cursor.fetchmany(BATCH_SIZE)
                        if not rows:
                            break

                        # LIMIT clause emulation
                        if self.limit:
                            remaining = self.limit - events_processed
                            if len(rows) > remaining:
                                rows = rows[:remaining]

                        logger.info(f"🚀 Processing batch: {len(rows)} events...")

                        for row in rows:
                            if not self.running:
                                break

                            event_type = row[1]  # 0=DEPTH, 1=TICK

                            if event_type == 0:  # DEPTH
                                await self._emit_depth(row[0], row[2], row[3])
                            elif event_type == 1:  # TICK
                                await self._emit_tick(row[0], row[4], row[5], row[6])

                            if self.delay > 0:
                                await asyncio.sleep(self.delay)

                        window_events += len(rows)
                        events_processed += len(rows)

                        if self.limit and events_processed >= self.limit:
                            logger.info(f"🛑 Reached backtest limit: {self.limit} events")
                            break

                    # Process candles separately if in CANDLE mode
                    if has_candles:
                        candle_cursor = await db.execute(candle_query, candle_params)
                        while True:
                            candle_rows = await candle_cursor.fetchmany(BATCH_SIZE)
                            if not candle_rows:
                                break

                            if self.limit:
                                remaining = self.limit - events_processed
                                if len(candle_rows) > remaining:
                                    candle_rows = candle_rows[:remaining]

                            logger.info(f"🕯️ Processing candle batch: {len(candle_rows)} candles...")

                            for candle in candle_rows:
                                if not self.running:
                                    break

                                ts, open_p, high_p, low_p, close_p, volume = candle
                                await self._emit_candle_ticks(ts, open_p, high_p, low_p, close_p, volume)

                                if self.delay > 0:
                                    await asyncio.sleep(self.delay)

                            events_processed += len(candle_rows)

                            if self.limit and events_processed >= self.limit:
                                logger.info(f"🛑 Reached backtest limit: {self.limit} events")
                                break

                        if self.limit and events_processed >= self.limit:
                            break

                    current_start = current_end

        logger.info("🏁 Backtest Replay Finished.")
        self.engine.running = False

    async def _create_optimized_indices(self, db, symbol):
        """Create covering indices for faster UNION ALL queries if they don't exist."""
        # Check existing indices
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indices = {row[0] for row in await cursor.fetchall()}

        # Create compound indices for (symbol, timestamp) if missing
        if "idx_depth_symbol_ts" not in existing_indices:
            logger.info("📌 Creating index: idx_depth_symbol_ts...")
            await db.execute("CREATE INDEX idx_depth_symbol_ts ON depth_snapshots(symbol, timestamp)")

        if "idx_trades_symbol_ts" not in existing_indices:
            logger.info("📌 Creating index: idx_trades_symbol_ts...")
            await db.execute("CREATE INDEX idx_trades_symbol_ts ON market_trades(symbol, timestamp)")

        if "idx_candles_symbol_ts" not in existing_indices:
            # Check if price_candles table exists first
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_candles'")
            if await cursor.fetchone():
                logger.info("📌 Creating index: idx_candles_symbol_ts...")
                await db.execute("CREATE INDEX idx_candles_symbol_ts ON price_candles(symbol, timestamp)")

        await db.commit()
        logger.info("✅ Optimized indices created/verified")

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
