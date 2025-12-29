"""
Decision Module

This module is responsible for aggregating signals from sensors and making
high-level trading decisions (LONG/SHORT/SKIP).

It acts as the 'brain' of the system, processing raw inputs into actionable verdicts.
"""

from .aggregator import SignalAggregatorV3

__all__ = ["SignalAggregatorV3"]
