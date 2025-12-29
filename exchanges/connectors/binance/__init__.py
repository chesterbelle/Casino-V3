"""
Binance Futures Connector Package.

This package provides a connector for Binance Futures exchange (USDT Perpetual).

Main features:
- Testnet and Live trading support
- Native TP/SL support (3 separate orders)
- Modern API
- Full CCXT integration

Usage:
    >>> from exchanges.connectors.binance import BinanceConnector
    >>> connector = BinanceConnector(mode="testnet")
    >>> await connector.connect()
    >>> order = await connector.create_order_with_tpsl(
    ...     symbol="BTC/USD:USD",
    ...     side="buy",
    ...     amount=0.01,
    ...     order_type="market",
    ...     tp_price=50000,
    ...     sl_price=48000
    ... )
"""

from .binance_native_connector import BinanceNativeConnector

__all__ = ["BinanceNativeConnector"]
