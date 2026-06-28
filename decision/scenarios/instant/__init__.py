"""
Instant Scenarios — AMT scenarios that bypass SignalArbitrator.

These scenarios execute with zero latency:
- Direct signal to SetupEngine (no VA_GATE, no arbitration)
- Critical for catching institutional absorption at the exact tick

Scenarios:
- TacticalAbsorption: Absorción con CVD divergente en un tick.
"""

from .tactical_absorption import AbsorptionDetector

__all__ = ["AbsorptionDetector"]
