"""
Players module - Bet sizing strategies for Casino V3.

Available players:
- AdaptivePlayer: Kelly-based sizing with fixed fallback

Author: Casino V3 Team
"""

from .adaptive import AdaptivePlayer

__all__ = ["AdaptivePlayer"]
