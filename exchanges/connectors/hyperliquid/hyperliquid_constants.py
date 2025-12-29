"""
Hyperliquid Constants and Configuration.

This module contains all Hyperliquid-specific constants, configuration,
and symbol normalization functions.
"""

# =========================================================
# ⚙️  EXCHANGE CONFIGURATION
# =========================================================

HYPERLIQUID_DEFAULT_CONFIG = {
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap",  # Perpetual swaps
    },
}

# Base currency for balance (Hyperliquid uses USDC)
BASE_CURRENCY = "USDC"

# =========================================================
# 🔄 SYMBOL NORMALIZATION
# =========================================================


def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol from bot format to Hyperliquid format (CCXT).

    Bot format: "BTC/USD:USD" (or similar generic format)
    Hyperliquid CCXT format: "BTC/USDC:USDC"

    Args:
        symbol: Symbol in bot format (e.g., "BTC/USD:USD")

    Returns:
        Symbol in Hyperliquid CCXT format (e.g., "BTC/USDC:USDC")
    """
    # If already in correct format, return as is
    if symbol.endswith("/USDC:USDC"):
        return symbol

    # Extract base currency
    if "/" in symbol:
        base = symbol.split("/")[0]
    else:
        # Assume it's just the base currency
        base = symbol

    # Hyperliquid uses USDC for linear swaps
    return f"{base}/USDC:USDC"


def denormalize_symbol(hyperliquid_symbol: str) -> str:
    """
    Denormalize symbol from Hyperliquid format to bot format.

    Hyperliquid CCXT format: "BTC/USDC:USDC"
    Bot format: "BTC/USD:USD"

    Args:
        hyperliquid_symbol: Symbol in Hyperliquid CCXT format

    Returns:
        Symbol in bot format
    """
    # Remove USDC suffix
    if "/USDC:USDC" in hyperliquid_symbol:
        base = hyperliquid_symbol.split("/")[0]
        return f"{base}/USD:USD"

    # Handle simple "BTC/USDC" if that ever appears
    if hyperliquid_symbol.endswith("/USDC"):
        base = hyperliquid_symbol.split("/")[0]
        return f"{base}/USD:USD"

    # Fallback
    return f"{hyperliquid_symbol}/USD:USD"


"""Placeholder constants for Hyperliquid connector (v2.1 planned)."""

API_URL = "https://api.hyperliquid.xyz"
WS_URL = "wss://api.hyperliquid.xyz/ws"
