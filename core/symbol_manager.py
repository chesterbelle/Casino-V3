import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)


class CanonicalSymbolMapper:
    """
    Architecture Layer: Identity Management
    Normalizes diverse exchange symbol formats into a single Canonical ID.
    Prevents data fragmentation and registry lookup failures.
    """

    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(CanonicalSymbolMapper, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # Maps Normalized Name -> Original Format
        self._registry: Dict[str, str] = {}
        # Known patterns to strip
        self._strip_patterns = [r"/", r":USDT", r":", r"-", r"\.P"]

    def normalize(self, symbol: str) -> str:
        """
        Transforms any format (ADA/USDT:USDT, ADA-USDT, ada_usdt)
        into a canonical 'ADAUSDT'.
        """
        if not symbol:
            return ""

        clean = symbol.upper()
        for pattern in self._strip_patterns:
            clean = re.sub(pattern, "", clean)

        # Specific edge case: Handle 'ADA_USDT_USDT' from some CSVs
        if "USDT_USDT" in clean:
            clean = clean.replace("USDT_USDT", "USDT")

        return clean

    def register(self, raw_symbol: str):
        """Registers a raw symbol from an external source."""
        canonical = self.normalize(raw_symbol)
        if canonical not in self._registry:
            self._registry[canonical] = raw_symbol
            logger.debug(f"🆔 [SymbolMapper] Registered Canonical: {canonical} <- {raw_symbol}")


# Global Access
symbol_mapper = CanonicalSymbolMapper()
