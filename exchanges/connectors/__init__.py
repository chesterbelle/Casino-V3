"""
Exchange Connectors Module.

This module provides standardized connectors for different cryptocurrency exchanges.
Each connector implements the BaseConnector interface and handles exchange-specific
communication, authentication, and data normalization.

Available Connectors:
    - BinanceNativeConnector: Binance Futures (Native SDK)
    - HyperliquidNativeConnector: Hyperliquid (Native SDK)
    - VirtualExchangeConnector: Virtual exchange for backtesting
    - ResilientConnector: Wrapper que agrega resiliencia a cualquier conector

Usage:
    ```python
    from exchanges.connectors import BinanceNativeConnector, ResilientConnector

    # Create connector
    connector = BinanceNativeConnector(...)

    # Wrap with resilience (optional)
    resilient_connector = ResilientConnector(
        connector=connector,
        state_recovery_config={'state_dir': './state'}
    )

    # Connect
    await resilient_connector.connect()
    ```
"""

from .binance import BinanceNativeConnector
from .connector_base import BaseConnector
from .hyperliquid import HyperliquidNativeConnector
from .resilient_connector import ResilientConnector
from .virtual_exchange import VirtualExchangeConnector

__all__ = [
    "BaseConnector",
    "BinanceNativeConnector",
    "HyperliquidNativeConnector",
    "VirtualExchangeConnector",
    "ResilientConnector",
]
