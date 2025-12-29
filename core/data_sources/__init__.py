"""
Data Sources Module - Casino V3

Provides unified interface for different data sources:
- BacktestDataSource: Historical data (CSV, Parquet, DataFrame)
- TestingDataSource: Exchange demo/testnet
- LiveDataSource: Real exchange (production)

All sources implement the same interface, allowing the trading logic
to work identically regardless of the data source.
"""

from .backtest import BacktestDataSource
from .base import Candle, DataSource
from .live import LiveDataSource
from .testing import TestingDataSource

__all__ = [
    "DataSource",
    "Candle",
    "BacktestDataSource",
    "TestingDataSource",
    "LiveDataSource",
]
