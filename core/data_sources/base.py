"""
Base DataSource Interface - Casino V3

Defines the contract that all data sources must implement.
This ensures that trading logic can work with any data source
(backtest, testing, live) without modification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Candle:
    """
    Normalized candle data structure (immutable).

    All data sources return candles in this format, ensuring
    consistency across backtest, testing, and live modes.

    Attributes:
        timestamp: Unix timestamp in milliseconds
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
        symbol: Trading pair (e.g., "BTC/USD")
        timeframe: Candle interval (e.g., "1h", "5m")
        equity: Current equity (balance + unrealized PnL)
        balance: Available balance
        unrealized_pnl: Unrealized profit/loss from open positions
    """

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str

    # Optional enriched state
    equity: Optional[float] = None
    balance: Optional[float] = None
    unrealized_pnl: Optional[float] = None


class DataSource(ABC):
    """
    Abstract base class for all data sources.

    Defines the contract that BacktestDataSource, TestingDataSource,
    and LiveDataSource must implement.

    This allows TradingSession to work with any data source without
    knowing the implementation details.
    """

    @abstractmethod
    async def next_candle(self) -> Optional[Candle]:
        """
        Get the next candle.

        Returns:
            Candle object or None if no more data available

        Note:
            - Backtest: Returns next historical candle (instant)
            - Testing: Waits for next real candle from demo exchange
            - Live: Waits for next real candle from live exchange
        """
        pass

    @abstractmethod
    async def execute_order(self, order: Dict) -> Dict:
        """
        Execute a trading order.

        Args:
            order: Order dictionary with keys:
                - symbol: Trading pair
                - side: "buy" or "sell"
                - amount: Order size
                - type: "market" or "limit"
                - price: Limit price (optional)
                - take_profit: TP multiplier (e.g., 1.01)
                - stop_loss: SL multiplier (e.g., 0.99)

        Returns:
            Result dictionary with keys:
                - status: "opened", "rejected", etc.
                - trade_id: Unique trade identifier
                - entry_price: Actual execution price
                - fee: Trading fee
                - balance: Updated balance

        Note:
            - Backtest: Simulates execution with slippage/fees
            - Testing: Real execution on demo exchange
            - Live: Real execution on live exchange
        """
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """
        Get current available balance.

        Returns:
            Balance in account currency (e.g., USD)

        Note:
            This is the "free" balance, not including unrealized PnL
        """
        pass

    @abstractmethod
    def get_equity(self) -> float:
        """
        Get current equity (balance + unrealized PnL).

        Returns:
            Total equity in account currency

        Note:
            Equity = Balance + Unrealized PnL from open positions
        """
        pass

    @abstractmethod
    async def connect(self) -> None:
        """
        Initialize connection to data source.

        Note:
            - Backtest: Validates data is loaded
            - Testing: Connects to demo exchange
            - Live: Connects to live exchange
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to data source.

        Note:
            - Backtest: No-op (nothing to disconnect)
            - Testing: Closes demo exchange connection
            - Live: Closes live exchange connection
        """
        pass
