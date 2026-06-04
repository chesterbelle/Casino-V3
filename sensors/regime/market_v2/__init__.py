"""
Regime Sensor V2 — 2-Layer Architecture

Price Action (lead) + Volume Profile (confirmation) + Markov (memory)
"""

from sensors.regime.market_v2.core_detector import MarketRegimeSensorV2

__all__ = ["MarketRegimeSensorV2"]
