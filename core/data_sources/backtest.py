"""
Backtest Data Source - Casino V3

Provides historical data for backtesting strategies.
Uses Croupier + CCXTAdapter + VirtualExchangeConnector for modular architecture.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from .base import Candle, DataSource

logger = logging.getLogger(__name__)


class BacktestDataSource(DataSource):
    """
    Data source for backtesting with historical data.

    Features:
    - Load from CSV, Parquet, or DataFrame
    - Uses VirtualExchangeConnector to simulate a real exchange
    - Uses CCXTAdapter (same as Live/Demo)
    - Uses Croupier (same as Live/Demo)
    - Instant execution (simulated by VirtualExchange)

    Example:
        >>> source = BacktestDataSource.from_csv("BTC_1h.csv")
        >>> await source.connect()
        >>> candle = await source.next_candle()
        >>> await source.disconnect()
    """

    def __init__(
        self,
        data: pd.DataFrame,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.0004,  # Deprecated, use taker_fee_rate
        taker_fee_rate: float = 0.0004,  # 0.04% (Binance Futures taker)
        maker_fee_rate: float = 0.0002,  # 0.02% (Binance Futures maker)
        slippage_rate: float = 0.0001,  # 0.01%
        spread_rate: float = 0.0001,  # 0.01% spread bid/ask
        funding_rate: float = 0.0001,  # 0.01% funding fee per 8h
    ):
        """
        Initialize backtest data source.

        Args:
            data: DataFrame with columns [timestamp, open, high, low, close, volume]
            initial_balance: Starting balance for simulation
            fee_rate: DEPRECATED - use taker_fee_rate instead
            taker_fee_rate: Taker fee rate for market orders (0.0004 = 0.04%)
            maker_fee_rate: Maker fee rate for limit orders (0.0002 = 0.02%)
            slippage_rate: Simulated slippage (0.0001 = 0.01%)
            spread_rate: Bid/ask spread (0.0001 = 0.01%)
            funding_rate: Funding fee rate per 8h (0.0001 = 0.01%)
        """
        self.data = data.reset_index(drop=True)
        self.index = 0
        self.initial_balance = initial_balance

        # Support legacy fee_rate parameter
        self.taker_fee_rate = taker_fee_rate if fee_rate == 0.0004 else fee_rate
        self.maker_fee_rate = maker_fee_rate
        self.slippage_rate = slippage_rate
        self.spread_rate = spread_rate
        self.funding_rate = funding_rate

        # Track candle timestamps for validation
        self.candle_timestamps = []

        # Metadata
        self.symbol = data.get("symbol", pd.Series(["BTC/USD"]))[0] if "symbol" in data.columns else "BTC/USD"
        self.timeframe = data.get("timeframe", pd.Series(["1h"]))[0] if "timeframe" in data.columns else "1h"

        # Create modular architecture: Connector → Adapter → Croupier
        # Import here to avoid circular imports
        from exchanges.connectors.virtual_exchange import VirtualExchangeConnector

        # 1. Virtual Exchange (The "Real" Exchange Simulation)
        self.connector = VirtualExchangeConnector(
            initial_balance=initial_balance,
            fee_rate=self.taker_fee_rate,
            maker_fee_rate=self.maker_fee_rate,
            slippage_rate=slippage_rate,
        )

        # 2. CCXT Adapter (The Standard Adapter used in Live/Demo)
        # Import here to avoid circular imports
        from exchanges.adapters import ExchangeAdapter
        from exchanges.connectors.virtual.virtual_connector import VirtualConnector

        self.adapter = ExchangeAdapter(
            connector=VirtualConnector(initial_balance=10000.0, data_path="data/historical"),
            symbol=self.symbol,
        )
        # 3. Croupier (The Brain) - Se inicializará via set_gemini_instance
        self.croupier = None

        self._connected = False

        logger.info(
            f"📊 BacktestDataSource initialized | "
            f"Symbol: {self.symbol} | "
            f"Timeframe: {self.timeframe} | "
            f"Candles: {len(self.data)} | "
            f"Balance: {initial_balance:.2f} | "
            f"Architecture: VirtualExchange -> CCXTAdapter -> Croupier"
        )

    @classmethod
    def from_csv(
        cls,
        filepath: str,
        initial_balance: float = 10000.0,
        normalize_symbol: bool = True,
        force_timeframe: str = None,
        **kwargs,
    ) -> "BacktestDataSource":
        """
        Load data from CSV file.
        """
        df = pd.read_csv(filepath)

        # Convert timestamp to int if it's a string (ISO format)
        if df["timestamp"].dtype == "object":
            df["timestamp"] = pd.to_datetime(df["timestamp"]).astype(int) // 10**6

        # Try to infer symbol and timeframe from filename
        import re
        from pathlib import Path

        filename = Path(filepath).stem  # Get filename without extension

        # Try to extract timeframe from filename (e.g., "5m", "1h", "15m")
        detected_timeframe = None
        timeframe_match = re.search(r"_(\d+[mhd])", filename)
        if timeframe_match:
            detected_timeframe = timeframe_match.group(1)

        # Apply timeframe: force_timeframe > detected > column > default
        if "timeframe" not in df.columns:
            if force_timeframe:
                df["timeframe"] = force_timeframe
                if detected_timeframe and detected_timeframe != force_timeframe:
                    logger.warning(
                        f"⚠️ Timeframe forced: {detected_timeframe} → {force_timeframe} "
                        f"(for Gemini memory compatibility)."
                    )
            elif detected_timeframe:
                df["timeframe"] = detected_timeframe

        # Try to extract symbol from filename (e.g., "BTCUSDT" -> "BTC/USD")
        if "symbol" not in df.columns:
            symbol_match = re.match(r"([A-Z]+)(USDT|USDC|BUSD|USD)", filename)
            if symbol_match:
                base = symbol_match.group(1)
                quote = symbol_match.group(2)

                if normalize_symbol and quote in ["USDT", "USDC", "BUSD"]:
                    normalized_quote = "USDC"  # Kraken uses USDC
                    df["symbol"] = f"{base}/{normalized_quote}:{normalized_quote}"
                    logger.info(
                        f"📝 Symbol normalized: {base}/{quote} → {base}/{normalized_quote}:{normalized_quote} "
                        f"(Kraken format for Gemini memory compatibility)"
                    )
                else:
                    df["symbol"] = f"{base}/{quote}"

        return cls(df, initial_balance, **kwargs)

    @classmethod
    def from_parquet(
        cls,
        filepath: str,
        initial_balance: float = 10000.0,
        **kwargs,
    ) -> "BacktestDataSource":
        """Load data from Parquet file."""
        df = pd.read_parquet(filepath)
        return cls(df, initial_balance, **kwargs)

    async def connect(self) -> None:
        """Initialize backtest."""
        if len(self.data) == 0:
            raise ValueError("No data loaded for backtest")

        await self.connector.connect()
        self._connected = True
        logger.info("✅ Backtest data source connected")

    async def disconnect(self) -> None:
        """Close backtest and force-close any open positions."""
        # Force-close all open positions at market price
        positions = await self.connector.fetch_positions()

        if positions:
            logger.info(f"🔒 Force-closing {len(positions)} open position(s) at session end...")

            for position in positions:
                symbol = position["symbol"]
                amount = position["contracts"]  # VirtualExchange uses 'contracts' not 'amount'
                side = "sell" if position["side"] == "LONG" else "buy"

                # Get current market price from last candle
                if self.index > 0:
                    last_candle = self.data.iloc[self.index - 1]
                    close_price = float(last_candle["close"])
                else:
                    close_price = position["entryPrice"]  # VirtualExchange uses 'entryPrice'

                # Create market order to close position
                try:
                    await self.connector.create_order(
                        symbol=symbol,
                        type="market",
                        side=side,
                        amount=amount,
                        price=close_price,
                    )
                    logger.info(
                        f"✅ Closed {position['side']} position for {symbol} | "
                        f"Amount: {amount} | Price: {close_price:.2f}"
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to close position {symbol}: {e}")

        await self.connector.close()
        self._connected = False
        logger.info("🔌 Backtest data source disconnected")

    async def next_candle(self) -> Optional[Candle]:
        """
        Get next historical candle and update Virtual Exchange.
        """
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")

        if self.index >= len(self.data):
            return None

        row = self.data.iloc[self.index]
        self.index += 1

        # Track timestamp for validation
        timestamp = int(row["timestamp"])
        self.candle_timestamps.append(timestamp)

        # Convert row to dict for Virtual Exchange
        candle_dict = {
            "timestamp": timestamp,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }

        # CRITICAL: Update Virtual Exchange state
        # This triggers TP/SL checks, order execution, and PnL updates
        self.connector.update_market_state(candle_dict)

        # Get updated account state from Croupier (which queries Connector via Adapter)
        balance = self.croupier.get_balance()
        equity = self.croupier.get_equity()

        # Calculate unrealized PnL (Equity - Balance)
        unrealized_pnl = equity - balance

        return Candle(
            timestamp=timestamp,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=self.symbol,
            timeframe=self.timeframe,
            equity=equity,
            balance=balance,
            unrealized_pnl=unrealized_pnl,
        )

    async def execute_order(self, order: Dict) -> Dict:
        """
        Execute order through Croupier.

        This is kept for compatibility but the TradingSession should use
        pipeline -> Croupier directly. If called, we delegate to Croupier.
        """
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")

        return await self.croupier.execute_order(order)

    def get_balance(self) -> float:
        """Get current balance."""
        return self.croupier.get_balance()

    def get_equity(self) -> float:
        """Get current equity."""
        return self.croupier.get_equity()

    async def get_stats(self) -> Dict:
        """
        Get backtest statistics from Virtual Exchange.
        """
        # Fetch data from connector
        balance_data = await self.connector.fetch_balance()
        final_balance = balance_data["total"][self.connector.base_currency]

        positions = await self.connector.fetch_positions()
        # Calculate final equity
        unrealized_pnl = sum(p["unrealizedPnl"] for p in positions)
        final_equity = final_balance + unrealized_pnl

        trades = self.connector._trades  # Access internal history

        # Calculate stats
        # Filter out opening trades (pnl is None)
        closed_trades = [t for t in trades if t.get("pnl") is not None]

        realized_pnl = sum(t["pnl"] for t in closed_trades)
        total_pnl = realized_pnl + unrealized_pnl  # Include unrealized PnL from open positions
        total_fees = sum(t["fee"] for t in trades)

        wins = [t for t in closed_trades if t["pnl"] > 0]
        losses = [t for t in closed_trades if t["pnl"] <= 0]

        return {
            "initial_balance": self.initial_balance,
            "final_balance": final_balance,
            "final_equity": final_equity,
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "net_pnl": total_pnl,  # Already net in VirtualExchange
            "total_trades": len(closed_trades),  # Count only completed trades (with PnL)
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed_trades) if closed_trades else 0,
            "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
            "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
            "candle_timestamps": self.candle_timestamps,
            "closed_trades": closed_trades,
        }

    def set_gemini_instance(self, gemini):
        """Set Gemini instance and initialize Croupier."""
        from croupier.croupier import Croupier

        self.gemini = gemini
        if self.croupier is not None:
            return  # Evitar reinicialización
        self.croupier = Croupier(
            exchange_adapter=self.adapter,
            initial_balance=self.initial_balance,
            gemini=gemini,
        )
        logger.info("✅ Croupier initialized with Gemini instance.")

    # =========================================================
    # HELPER METHODS (for compatibility)
    # =========================================================

    def _get_current_timestamp(self) -> int:
        """Get current timestamp from data."""
        if self.index > 0:
            return int(self.data.iloc[self.index - 1]["timestamp"])
        else:
            return int(self.data.iloc[0]["timestamp"])

    def _get_ohlcv(self, limit: int = 1) -> List[Dict]:
        """Get OHLCV data."""
        if self.index == 0:
            return []

        start_idx = max(0, self.index - limit)
        end_idx = self.index

        candles = []
        for idx in range(start_idx, end_idx):
            row = self.data.iloc[idx]
            candles.append(
                {
                    "timestamp": int(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )

        return candles
