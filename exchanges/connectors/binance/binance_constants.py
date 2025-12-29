"""
Binance Futures Constants and Configuration.

This module contains all Binance-specific constants, configuration,
and symbol normalization functions.
"""

from typing import Dict, Literal

# =========================================================
# 🌐 EXCHANGE URLS
# =========================================================

BINANCE_TESTNET_URL = "https://testnet.binancefuture.com"
BINANCE_LIVE_URL = "https://fapi.binance.com"


def get_urls(mode: Literal["testnet", "live"]) -> Dict[str, str]:
    """
    Get Binance URLs based on mode.

    Args:
        mode: "testnet" for testnet, "live" for production

    Returns:
        Dict with API URLs
    """
    if mode == "testnet":
        return {
            "api": BINANCE_TESTNET_URL,
            "ws": "wss://stream.binancefuture.com",
        }
    else:
        return {
            "api": BINANCE_LIVE_URL,
            "ws": "wss://fstream.binance.com",
        }


# =========================================================
# ⚙️  EXCHANGE CONFIGURATION
# =========================================================

BINANCE_DEFAULT_CONFIG = {
    "enableRateLimit": True,
    "rateLimit": 50,  # ms between requests
    "timeout": 30000,  # 30 seconds
    "options": {
        "defaultType": "future",  # USDT Futures
        "defaultSubType": "linear",  # Linear contracts (not inverse)
    },
}

# Base currency for balance
BASE_CURRENCY = "USDT"

# =========================================================
# 🔄 SYMBOL NORMALIZATION
# =========================================================


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol from bot format to Binance format.

    Bot format: "BTC/USD:USD", "ETH/USD:USD", "LTC/USD:USD"
    Binance format: "BTC/USDT:USDT", "ETH/USDT:USDT", "LTC/USDT:USDT"

    Args:
        symbol: Symbol in bot format (e.g., "BTC/USD:USD")

    Returns:
        Symbol in Binance format (e.g., "BTC/USDT:USDT")

    Examples:
        >>> normalize_symbol("BTC/USD:USD")
        'BTC/USDT:USDT'
        >>> normalize_symbol("ETH/USD:USD")
        'ETH/USDT:USDT'
        >>> normalize_symbol("LTC/USD:USD")
        'LTC/USDT:USDT'
    """
    # If already in correct format, return as is
    if symbol.endswith("/USDT:USDT"):
        return symbol

    # Extract base currency
    if "/" in symbol:
        base = symbol.split("/")[0]
    else:
        # Assume it's just the base currency
        return f"{symbol}/USDT:USDT"

    # Binance uses USDT for perpetuals
    return f"{base}/USDT:USDT"


def denormalize_symbol(binance_symbol: str) -> str:
    """
    Denormalize symbol from Binance format to bot format.

    Binance format: "BTCUSDT", "ETHUSDT", "LTCUSDT"
    Bot format: "BTC/USD:USD", "ETH/USD:USD", "LTC/USD:USD"

    Args:
        binance_symbol: Symbol in Binance format (e.g., "BTCUSDT")

    Returns:
        Symbol in bot format (e.g., "BTC/USD:USD")

    Examples:
        >>> denormalize_symbol("BTCUSDT")
        'BTC/USD:USD'
        >>> denormalize_symbol("ETHUSDT")
        'ETH/USD:USD'
        >>> denormalize_symbol("LTCUSDT")
        'LTC/USD:USD'
    """
    # Remove USDT suffix
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}/USDT:USDT"

    # If not USDT pair, return as is
    return f"{binance_symbol}/USDT:USDT"


def symbol_to_binance_api_format(symbol: str) -> str:
    """
    Convert symbol to Binance API format (no separators).

    Args:
        symbol: Symbol in any format (e.g., "LTC/USDT:USDT", "LTC/USD:USD")

    Returns:
        Symbol in Binance API format (e.g., "LTCUSDT")

    Examples:
        >>> symbol_to_binance_api_format("LTC/USDT:USDT")
        'LTCUSDT'
        >>> symbol_to_binance_api_format("BTC/USD:USD")
        'BTCUSDT'
    """
    # First normalize to Binance format
    normalized = normalize_symbol(symbol)

    # Extract base currency from normalized format (e.g., "LTC/USDT:USDT" -> "LTC")
    if "/" in normalized:
        base = normalized.split("/")[0]
        return f"{base}USDT"

    # If already in API format, return as is
    if normalized.endswith("USDT"):
        return normalized

    # Fallback: assume it's base currency only
    return f"{normalized}USDT"


# =========================================================
# 📊 ORDER PARAMETERS
# =========================================================

# Position modes
POSITION_MODE_ONE_WAY = "ONE_WAY"
POSITION_MODE_HEDGE = "HEDGE"

# Order types
ORDER_TYPE_MARKET = "MARKET"
ORDER_TYPE_LIMIT = "LIMIT"
ORDER_TYPE_STOP_MARKET = "STOP_MARKET"
ORDER_TYPE_TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
ORDER_TYPE_STOP = "STOP"
ORDER_TYPE_TAKE_PROFIT = "TAKE_PROFIT"

# Time in force
TIME_IN_FORCE_GTC = "GTC"  # Good Till Cancel
TIME_IN_FORCE_IOC = "IOC"  # Immediate or Cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill or Kill
TIME_IN_FORCE_GTX = "GTX"  # Good Till Crossing (Post Only)
TIME_IN_FORCE_GTE_GTC = "GTE_GTC"  # Good Till Executed - GTC (Enables OCO behavior for TP/SL)

# Working type (for stop orders)
WORKING_TYPE_MARK_PRICE = "MARK_PRICE"
WORKING_TYPE_CONTRACT_PRICE = "CONTRACT_PRICE"
