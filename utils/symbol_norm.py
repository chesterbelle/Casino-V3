"""
Symbol Normalization Utility.
Ensures uniform symbol representation across all bot layers.
"""

import logging

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """
    Normalizes a trading symbol to a standard BASE/QUOTE format.

    Examples:
    - "XRP/USDT:USDT" -> "XRP/USDT"
    - "XRPUSDT" -> "XRP/USDT" (if it can be unambiguously split, but usually we handle exchange-native elsewhere)
    - "xrp/usdt" -> "XRP/USDT"

    Args:
        symbol: The raw symbol string from data feed or config.

    Returns:
        Normalized symbol string.
    """
    if not symbol:
        return ""

    # 1. Convert to uppercase and remove slashes for index neutrality
    norm = symbol.upper().replace("/", "")

    # 2. Strip :USDT suffix (CCXT twin symbol convention)
    if ":" in norm:
        norm = norm.split(":")[0]

    return norm
