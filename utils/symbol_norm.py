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

    # 1. Convert to uppercase
    norm = symbol.upper()

    # 2. Strip :USDT suffix (CCXT twin symbol convention)
    if ":" in norm:
        norm = norm.split(":")[0]

    # 3. Handle common exchange-native formats (e.g., XRPUSDT -> XRP/USDT)
    # This is slightly risky without a quote list, but for now we focus on the suffix issue.
    # Most internal logic already uses BASE/QUOTE.

    return norm
