"""
AMT Scenarios Factory and Exports.

Architecture:
- instant/: Tactical scenarios that bypass SignalArbitrator (latency-critical).
- confirmation/: Scenarios that flow through SignalArbitrator (VA_GATE + arbitration).
"""

from .confirmation.failed_breakout import FailedBreakoutDetector
from .confirmation.liquidity_exhaustion import LiquidityExhaustionDetector
from .confirmation.trend_acceptance import TrendAcceptanceDetector
from .instant.tactical_absorption import AbsorptionDetector

__all__ = [
    "AbsorptionDetector",  # Instant
    "FailedBreakoutDetector",  # Confirmation
    "LiquidityExhaustionDetector",  # Confirmation
    "TrendAcceptanceDetector",  # Confirmation
]
