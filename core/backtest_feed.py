"""
Backtest Feed for Casino-V3.
Replays historical data as TickEvents.
"""

import asyncio
import logging

import pandas as pd

from .events import EventType, TickEvent

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

        # This is a bit hacky: we need an adapter that Croupier accepts
        # but that doesn't actually connect to anything.
        # For V3 backtesting, we might need a VirtualExchangeConnectorV3
        # For now, let's use a dummy object that has 'symbol'
        class MockAdapter:
            def __init__(self, symbol):
                self.name = "BacktestAdapter"
                self.symbol = symbol
                # Mock connector for ExchangeStateSync
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

    def load_data(self):
        """Load data from CSV/Parquet."""
        logger.info(f"📂 Loading backtest data from {self.data_path}...")
        if self.data_path.endswith(".csv"):
            self.data = pd.read_csv(self.data_path)
        elif self.data_path.endswith(".parquet"):
            self.data = pd.read_parquet(self.data_path)
        else:
            raise ValueError("Unsupported file format")

        # Check for Trade Data format
        if all(col in self.data.columns for col in ["timestamp", "price", "volume", "side"]):
            self.mode = "TRADES"
            logger.info("✅ Detected Real Trade Data format.")
        # Check for Candle Data format
        elif all(col in self.data.columns for col in ["timestamp", "open", "high", "low", "close", "volume"]):
            self.mode = "CANDLES"
            logger.info("✅ Detected Candle Data format.")
        else:
            raise ValueError(f"Data missing required columns. Found: {self.data.columns}")

        # Convert timestamp to datetime and then to epoch seconds if needed
        if not pd.api.types.is_numeric_dtype(self.data["timestamp"]):
            self.data["timestamp"] = pd.to_datetime(self.data["timestamp"])
            self.data["timestamp"] = self.data["timestamp"].astype(int) // 10**9

        self.data["event_type"] = "TICK"

        # Phase 1300: Load depth snapshots from SQLite DB if provided
        if getattr(self, "depth_db_path", None) and self.depth_db_path is not None:
            import os
            import sqlite3

            if os.path.exists(self.depth_db_path):
                try:
                    logger.info(f"📂 Loading depth snapshots from {self.depth_db_path}...")
                    conn = sqlite3.connect(self.depth_db_path)
                    depth_df = pd.read_sql_query(
                        f"SELECT timestamp, symbol, bids, asks FROM depth_snapshots WHERE symbol = '{self.symbol}'",
                        conn,
                    )
                    conn.close()

                    if not depth_df.empty:
                        depth_df["event_type"] = "DEPTH"
                        # concat and sort
                        self.data = pd.concat([self.data, depth_df], ignore_index=True)
                        logger.info(f"✅ Loaded {len(depth_df)} depth snapshots.")
                    else:
                        logger.warning("⚠️ No depth snapshots found for symbol in given DB.")
                except Exception as e:
                    logger.error(f"❌ Failed to load depth snapshots: {e}")
            else:
                logger.warning(f"⚠️ Depth DB file not found: {self.depth_db_path}")

        # Sort combined feed by timestamp
        self.data = self.data.sort_values("timestamp").reset_index(drop=True)
        logger.info(f"✅ Total merged feed size: {len(self.data)} rows.")

    async def run(self):
        """Start the replay and wait for completion."""
        self.running = True
        self.load_data()
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
        """Replay data row by row."""
        logger.info(f"▶️ Starting Backtest Replay (Mode: {self.mode})...")

        for index, row in self.data.iterrows():
            if not self.running:
                break

            if self.limit and index >= self.limit:
                logger.info(f"🛑 Reached backtest limit: {self.limit} events")
                break

            event_type = row.get("event_type", "TICK")

            if event_type == "DEPTH":
                await self._emit_depth(row["timestamp"], row["bids"], row["asks"])
            elif self.mode == "TRADES":
                # Shadow Orderbook Synthesizer (Fallback for historical long runs)
                if not getattr(self, "depth_db_path", None):
                    if row["timestamp"] - self._last_synth_depth_ts >= 1.0:
                        await self._synthesize_depth(row["timestamp"], row["price"], row["volume"])
                        self._last_synth_depth_ts = row["timestamp"]

                # Direct Replay of Real Trades
                await self._emit_tick(row["timestamp"], row["price"], row["volume"], row["side"])

            elif self.mode == "CANDLES":
                is_green = row["close"] > row["open"]
                total_vol = row["volume"]

                await self._emit_tick(row["timestamp"], row["open"], total_vol * 0.1, "BUY" if is_green else "SELL")
                if is_green:
                    await self._emit_tick(row["timestamp"], row["low"], total_vol * 0.2, "BUY")
                    await self._emit_tick(row["timestamp"], row["high"], total_vol * 0.4, "SELL")
                else:
                    await self._emit_tick(row["timestamp"], row["high"], total_vol * 0.2, "SELL")
                    await self._emit_tick(row["timestamp"], row["low"], total_vol * 0.4, "BUY")
                await self._emit_tick(row["timestamp"], row["close"], total_vol * 0.3, "SELL" if is_green else "BUY")

            if self.delay > 0:
                await asyncio.sleep(self.delay)

        logger.info("🏁 Backtest Replay Finished.")
        self.engine.running = False

    async def _emit_tick(self, timestamp, price, volume, side="UNKNOWN"):
        """Emit a single tick event."""
        # System now expects BUY/SELL (Binance Style) for 100% parity
        normalized_side = side.upper()
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
        import json

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

    async def _synthesize_depth(self, timestamp: float, current_price: float, current_vol: float):
        """Synthesize a probabilistic L2 orderbook snapshot (Shadow Orderbook)."""
        import random

        from core.events import OrderBookEvent

        price = float(current_price)
        # Assuming minimal tick size mapping (LTC: 0.01, BTC: 0.1)
        tick_size = 0.01 if price < 1000 else 0.10

        bids = []
        asks = []

        # Base synthetic liquidity on recent volume
        base_liq = max(5.0, float(current_vol) * 1.5)

        for i in range(1, 6):
            b_price = price - (i * tick_size)
            a_price = price + (i * tick_size)

            # Stochastic variance around the base liquidity
            b_qty = base_liq * random.uniform(0.7, 1.3)
            a_qty = base_liq * random.uniform(0.7, 1.3)

            bids.append([f"{b_price:.2f}", f"{b_qty:.3f}"])
            asks.append([f"{a_price:.2f}", f"{a_qty:.3f}"])

        event = OrderBookEvent(
            type=EventType.ORDER_BOOK,
            timestamp=float(timestamp),
            symbol=self.symbol,
            bids=bids,
            asks=asks,
        )
        await self.engine.dispatch(event)
