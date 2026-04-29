"""
Confirmation Sensors for Absorption Scalping V2 — Phase 2.

Three sensors that verify the aggressor has surrendered after an absorption candidate
is detected by AbsorptionDetector (Phase 1).

These sensors run in the MAIN PROCESS, called by AbsorptionReversalGuardian
on each subsequent candle after a candidate is detected.

Architecture:
  AbsorptionDetector → candidate (Phase 1)
       ↓
  AbsorptionReversalGuardian monitors 3 sensors (Phase 2):
       ├── DeltaReversalSensor: "Delta flipped to opposite direction"
       ├── PriceBreakSensor:   "Price broke through absorption level"
       └── CVDFlipSensor:      "CVD slope changed direction"
       ↓
  ≥2 of 3 confirmed → Entry signal
"""

import logging
import math
from typing import Dict, Optional

from core.footprint_registry import footprint_registry

logger = logging.getLogger(__name__)


class DeltaReversalSensor:
    """
    Detects when delta flips to the opposite direction of the original attack.

    If absorption was SELL_EXHAUSTION (sellers attacked), we look for
    positive delta (buyers now aggressive) in subsequent candles.

    This confirms the defender stopped absorbing passively and
    started counter-attacking aggressively.
    """

    def __init__(self):
        self.name = "DeltaReversalSensor"
        self.min_flip_ratio = 0.20  # Opposite delta must be ≥20% of original |delta|

    def check(self, symbol: str, candidate: dict, current_delta: float) -> bool:
        """
        Check if delta has flipped relative to the absorption candidate.

        Args:
            symbol: Trading symbol
            candidate: Original absorption candidate dict
            current_delta: Current candle's net delta

        Returns:
            True if delta reversal detected
        """
        original_delta = candidate["delta"]
        original_direction = candidate["direction"]

        # SELL_EXHAUSTION: original delta was negative → look for positive delta now
        # BUY_EXHAUSTION: original delta was positive → look for negative delta now
        if original_direction == "SELL_EXHAUSTION":
            if current_delta > 0 and abs(current_delta) >= abs(original_delta) * self.min_flip_ratio:
                logger.info(
                    f"✅ [DELTA_REVERSAL] {symbol} delta flipped positive "
                    f"(orig={original_delta:.1f}, now={current_delta:.1f})"
                )
                return True
        else:  # BUY_EXHAUSTION
            if current_delta < 0 and abs(current_delta) >= abs(original_delta) * self.min_flip_ratio:
                logger.info(
                    f"✅ [DELTA_REVERSAL] {symbol} delta flipped negative "
                    f"(orig={original_delta:.1f}, now={current_delta:.1f})"
                )
                return True

        return False


class PriceBreakSensor:
    """
    Detects when price breaks through the absorption level in the reversal direction.

    If absorption was SELL_EXHAUSTION at level 100.50 (sellers couldn't push below),
    we look for price moving ABOVE 100.50 — confirming buyers took control.
    """

    def __init__(self):
        self.name = "PriceBreakSensor"
        self.min_break_pct = 0.02  # Price must break level by at least 0.02%

    def check(self, symbol: str, candidate: dict, current_price: float) -> bool:
        """
        Check if price has broken through the absorption level.

        Args:
            symbol: Trading symbol
            candidate: Original absorption candidate dict
            current_price: Current market price

        Returns:
            True if price break detected
        """
        absorption_level = candidate["absorption_level"]
        original_direction = candidate["direction"]

        if absorption_level <= 0:
            return False

        if original_direction == "SELL_EXHAUSTION":
            # Sellers were absorbed → look for price ABOVE the level
            break_pct = (current_price - absorption_level) / absorption_level * 100
            if break_pct > self.min_break_pct:
                logger.info(
                    f"✅ [PRICE_BREAK] {symbol} price broke above absorption "
                    f"(level={absorption_level:.2f}, price={current_price:.2f}, +{break_pct:.3f}%)"
                )
                return True
        else:  # BUY_EXHAUSTION
            # Buyers were absorbed → look for price BELOW the level
            break_pct = (absorption_level - current_price) / absorption_level * 100
            if break_pct > self.min_break_pct:
                logger.info(
                    f"✅ [PRICE_BREAK] {symbol} price broke below absorption "
                    f"(level={absorption_level:.2f}, price={current_price:.2f}, -{break_pct:.3f}%)"
                )
                return True

        return False


class CVDFlipSensor:
    """
    Detects when CVD slope changes direction (inflection).

    If absorption was SELL_EXHAUSTION (CVD was falling), we look for
    CVD slope turning positive — confirming the flow reversed.

    Compares current CVD slope to the slope at the time of the candidate.
    """

    def __init__(self):
        self.name = "CVDFlipSensor"
        self.min_slope_change = 0.5  # Slope must change by this factor

    def check(self, symbol: str, candidate: dict) -> bool:
        """
        Check if CVD has flipped direction since the candidate was detected.

        Args:
            symbol: Trading symbol
            candidate: Original absorption candidate dict (stores cvd_slope_at_detection)

        Returns:
            True if CVD flip detected
        """
        footprint = footprint_registry.get_footprint(symbol)
        if not footprint:
            return False

        current_slope = footprint.get_cvd_slope(window_seconds=5)
        original_direction = candidate["direction"]
        original_slope = candidate.get("cvd_slope_at_detection", 0.0)

        # SELL_EXHAUSTION: CVD was falling (negative slope) → look for positive slope now
        # BUY_EXHAUSTION: CVD was rising (positive slope) → look for negative slope now
        if original_direction == "SELL_EXHAUSTION":
            if current_slope > 0 and abs(current_slope) > self.min_slope_change:
                logger.info(
                    f"✅ [CVD_FLIP] {symbol} CVD slope turned positive "
                    f"(at_detection={original_slope:.2f}, now={current_slope:.2f})"
                )
                return True
        else:  # BUY_EXHAUSTION
            if current_slope < 0 and abs(current_slope) > self.min_slope_change:
                logger.info(
                    f"✅ [CVD_FLIP] {symbol} CVD slope turned negative "
                    f"(at_detection={original_slope:.2f}, now={current_slope:.2f})"
                )
                return True

        return False
