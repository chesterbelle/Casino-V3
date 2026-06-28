"""
Confirmation Scenarios — AMT scenarios that flow through SignalArbitrator.

These scenarios require:
1. VA_GATE regime filtering
2. Conflict arbitration (priority × score)
3. Multi-signal fusion

Scenarios:
- FailedBreakout: Breakout con delta divergente → re-entrada.
- LiquidityExhaustion: Múltiples tests con delta declinante.
- TrendAcceptance: Breakout + CVD confirm + pullback.
"""

from .failed_breakout import FailedBreakoutDetector
from .liquidity_exhaustion import LiquidityExhaustionDetector
from .trend_acceptance import TrendAcceptanceDetector

__all__ = [
    "FailedBreakoutDetector",
    "LiquidityExhaustionDetector",
    "TrendAcceptanceDetector",
]
