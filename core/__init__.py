"""
Core modules for Casino V3 trading system.

This package contains:
- Trading session and pipeline (core.trading)
- Data sources (core.data_sources)
- Portfolio management (core.portfolio)
- Configuration (core.config - backward compatible wrapper)
"""

from . import config

__all__ = [
    "config",
]
