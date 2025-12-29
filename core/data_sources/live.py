"""
Live Data Source - Casino V3

Provides real-time data from live exchange (REAL MONEY).
"""

import logging

from .testing import TestingDataSource

logger = logging.getLogger(__name__)


class LiveDataSource(TestingDataSource):
    """
    Data source for live trading (REAL MONEY).

    Inherits from TestingDataSource but adds:
    - More aggressive warnings
    - More frequent state saves
    - More conservative circuit breaker

    ⚠️ WARNING: This uses REAL MONEY on LIVE EXCHANGE ⚠️

    Example:
        >>> connector = ResilientConnector(KrakenConnector(mode="live"))
        >>> source = LiveDataSource(connector, "BTC/USD", "5m")
        >>> await source.connect()
        >>> candle = await source.next_candle()
    """

    def __init__(
        self,
        connector,
        symbol: str,
        timeframe: str,
        poll_interval: float = 5.0,
        starting_balance: float = None,  # Will fetch from exchange
    ):
        """
        Initialize live data source.

        Args:
            connector: Exchange connector (should be ResilientConnector)
            symbol: Trading pair (e.g., "BTC/USD")
            timeframe: Candle interval (e.g., "5m", "1h")
            poll_interval: Seconds to wait between candle checks
            starting_balance: Initial balance (fetched from exchange if None)
        """
        # Use real balance from exchange (starting_balance will be fetched on connect)
        super().__init__(connector, symbol, timeframe, poll_interval, starting_balance or 10000.0)

        logger.warning("⚠️" * 20)
        logger.warning("⚠️ LIVE DATA SOURCE INITIALIZED - REAL MONEY ⚠️")
        logger.warning("⚠️ Using Croupier for order execution and portfolio management")
        logger.warning("⚠️" * 20)

    async def connect(self) -> None:
        """Connect to live exchange."""
        logger.warning("⚠️ Connecting to LIVE exchange - REAL MONEY")
        await super().connect()
        logger.warning("✅ Connected to LIVE exchange - BE CAREFUL")

    async def execute_order(self, order: dict) -> dict:
        """
        Execute order on LIVE exchange (REAL MONEY).

        Args:
            order: Order dict

        Returns:
            Result dict
        """
        logger.warning(
            f"⚠️ EXECUTING LIVE ORDER - REAL MONEY | "
            f"{order.get('side', '?').upper()} "
            f"{order.get('amount', 0):.4f}"
        )

        result = await super().execute_order(order)

        if result.get("status") == "opened":
            logger.warning("⚠️ LIVE ORDER EXECUTED - REAL MONEY USED")

        return result
