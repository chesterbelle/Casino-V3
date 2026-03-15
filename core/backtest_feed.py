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
        self, engine, data_path: str, symbol: str, delay: float = 0.001, exchange_connector=None, limit: int = None
    ):
        self.engine = engine
        self.data_path = data_path
        self.symbol = symbol
        self.delay = delay  # Delay between events to simulate time
        self.exchange_connector = exchange_connector  # Connector to update with price data
        self.running = False
        self.data = None
        self.limit = limit

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

        # Sort by timestamp
        self.data = self.data.sort_values("timestamp").reset_index(drop=True)
        logger.info(f"✅ Loaded {len(self.data)} rows.")

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

            if self.mode == "TRADES":
                # Direct Replay of Real Trades
                await self._emit_tick(row["timestamp"], row["price"], row["volume"], row["side"])

            elif self.mode == "CANDLES":
                is_green = row["close"] > row["open"]
                total_vol = row["volume"]

                await self._emit_tick(row["timestamp"], row["open"], total_vol * 0.1, "BID" if is_green else "ASK")
                if is_green:
                    await self._emit_tick(row["timestamp"], row["low"], total_vol * 0.2, "BID")
                    await self._emit_tick(row["timestamp"], row["high"], total_vol * 0.4, "ASK")
                else:
                    await self._emit_tick(row["timestamp"], row["high"], total_vol * 0.2, "ASK")
                    await self._emit_tick(row["timestamp"], row["low"], total_vol * 0.4, "BID")
                await self._emit_tick(row["timestamp"], row["close"], total_vol * 0.3, "ASK" if is_green else "BID")

            if self.delay > 0:
                await asyncio.sleep(self.delay)

        logger.info("🏁 Backtest Replay Finished.")
        self.engine.running = False

    async def _emit_tick(self, timestamp, price, volume, side="UNKNOWN"):
        """Emit a single tick event."""
        # Convert side format: SELL/BUY → ASK/BID
        # CSV uses SELL/BUY, but system expects BID/ASK
        normalized_side = side.upper()
        if normalized_side == "SELL":
            normalized_side = "ASK"
        elif normalized_side == "BUY":
            normalized_side = "BID"

        # Update Virtual Exchange first
        if self.exchange_connector:
            if hasattr(self.exchange_connector, "process_tick"):
                tick_data = {"price": price, "timestamp": timestamp}
                self.exchange_connector.process_tick(tick_data)

        event = TickEvent(
            type=EventType.TICK,
            timestamp=timestamp,  # Use historical timestamp
            symbol=self.symbol,
            price=float(price),
            volume=float(volume),
            side=normalized_side,
        )
        await self.engine.dispatch(event)
