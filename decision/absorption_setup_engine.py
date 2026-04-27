"""
Absorption Setup Engine for Absorption Scalping V1.

Converts AbsorptionDetector signals into executable setups with dynamic TP/SL.

Phase 2.3: Initial implementation.
"""

import logging
from typing import Optional

from core.footprint_registry import footprint_registry

logger = logging.getLogger(__name__)


class AbsorptionSetupEngine:
    """
    Converts absorption signals into executable setups.

    Dynamic TP/SL calculation:
    - TP: First low-volume node (LVN) in direction (resistance for SELL_EXHAUSTION, support for BUY_EXHAUSTION)
    - SL: Absorption level + buffer (based on extreme delta magnitude)

    Confirmation filters:
    1. CVD flattening (slope near zero after extreme delta)
    2. Price holding near absorption level (not breaking through)
    3. Minimum distance to TP (at least 0.10% edge)
    """

    def __init__(self, fast_track: bool = False):
        self.name = "AbsorptionSetupEngine"
        self.fast_track = fast_track

        # Configuration (from config/absorption.py later)
        self.min_tp_distance_pct = 0.10  # Minimum TP distance (0.10%)
        self.max_tp_distance_pct = 0.50  # Maximum TP distance (0.50%)
        self.sl_buffer_multiplier = 1.5  # SL buffer = delta_magnitude * multiplier
        self.cvd_slope_threshold = 5.0  # CVD slope threshold for flattening confirmation (relaxed for Phase 2.3)
        self.price_hold_window = 5.0  # Seconds to check if price holds near level

        logger.info(f"✅ {self.name} initialized{' (FAST-TRACK MODE)' if fast_track else ''}")

    def process_signal(self, signal: dict, current_price: float, timestamp: float) -> Optional[dict]:
        """
        Process absorption signal and generate setup.

        Args:
            signal: AbsorptionDetector signal
            current_price: Current market price
            timestamp: Current timestamp

        Returns:
            Setup dict or None
        """
        symbol = signal["symbol"]
        direction = signal["direction"]
        level = signal["level"]
        delta = signal["delta"]

        # Confirmation 1: CVD flattening
        if not self._check_cvd_flattening(symbol):
            logger.debug(f"❌ [ABSORPTION] CVD not flattening for {symbol}")
            return None

        # Confirmation 2: Price holding near level
        if not self._check_price_holding(current_price, level, timestamp):
            logger.debug(f"❌ [ABSORPTION] Price not holding near level {level} (current={current_price})")
            return None

        # Calculate TP (dynamic based on volume profile)
        tp_price = self._calculate_tp(symbol, level, direction, current_price)
        if tp_price is None:
            logger.debug(f"❌ [ABSORPTION] No valid TP found for {symbol}")
            return None

        # Confirmation 3: Minimum TP distance
        tp_distance_pct = abs(tp_price - current_price) / current_price * 100
        if tp_distance_pct < self.min_tp_distance_pct:
            logger.debug(
                f"❌ [ABSORPTION] TP too close: {tp_distance_pct:.2f}% < {self.min_tp_distance_pct}% (symbol={symbol})"
            )
            return None

        if tp_distance_pct > self.max_tp_distance_pct:
            logger.debug(
                f"❌ [ABSORPTION] TP too far: {tp_distance_pct:.2f}% > {self.max_tp_distance_pct}% (symbol={symbol})"
            )
            return None

        # Calculate SL (based on delta magnitude)
        sl_price = self._calculate_sl(level, delta, direction)

        # Generate setup
        side = "LONG" if direction == "SELL_EXHAUSTION" else "SHORT"

        setup = {
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "absorption_level": level,
            "delta": delta,
            "z_score": signal["z_score"],
            "concentration": signal["concentration"],
            "noise": signal["noise"],
            "timestamp": timestamp,
            "strategy": "AbsorptionScalpingV1",
        }

        logger.info(
            f"🎯 [ABSORPTION] Setup generated: {symbol} {side} @ {current_price:.2f} "
            f"(TP={tp_price:.2f} +{tp_distance_pct:.2f}%, SL={sl_price:.2f})"
        )

        return setup

    def _check_cvd_flattening(self, symbol: str) -> bool:
        """
        Check if CVD is flattening (slope near zero).

        Returns:
            True if CVD is flattening
        """
        if self.fast_track:
            return True  # Bypass for infrastructure validation

        cvd_slope = footprint_registry.get_cvd_slope(symbol, window_seconds=5)

        # CVD flattening = slope near zero (absorption is stopping the move)
        return abs(cvd_slope) < self.cvd_slope_threshold

    def _check_price_holding(self, current_price: float, level: float, timestamp: float) -> bool:
        """
        Check if price is holding near absorption level.

        Returns:
            True if price is holding
        """
        if self.fast_track:
            return True  # Bypass for infrastructure validation

        # For now, simplified: price within 0.05% of level
        # TODO: Track price history over price_hold_window for more accurate check
        distance_pct = abs(current_price - level) / level * 100
        return distance_pct < 0.05

    def _calculate_tp(
        self, symbol: str, absorption_level: float, direction: str, current_price: float
    ) -> Optional[float]:
        """
        Calculate TP based on volume profile (first low-volume node).

        For SELL_EXHAUSTION (LONG): Find first LVN above current price (resistance)
        For BUY_EXHAUSTION (SHORT): Find first LVN below current price (support)

        Returns:
            TP price or None
        """
        if self.fast_track:
            # Mock TP at fixed distance (0.20%) for infrastructure validation
            if direction == "SELL_EXHAUSTION":
                return current_price * 1.002  # +0.20% for LONG
            else:
                return current_price * 0.998  # -0.20% for SHORT

        # Get volume profile in search range
        if direction == "SELL_EXHAUSTION":
            # LONG: Search above current price
            price_from = current_price
            price_to = current_price * (1 + self.max_tp_distance_pct / 100)
        else:
            # SHORT: Search below current price
            price_from = current_price * (1 - self.max_tp_distance_pct / 100)
            price_to = current_price

        profile = footprint_registry.get_volume_profile(symbol, price_from, price_to)

        if len(profile) < 5:
            return None  # Insufficient data

        # Find low-volume nodes (LVN)
        # LVN = price level with volume < 50% of average volume
        total_volume = sum(ask_vol + bid_vol for _, ask_vol, bid_vol in profile)
        avg_volume = total_volume / len(profile)
        lvn_threshold = avg_volume * 0.5

        lvns = []
        for price, ask_vol, bid_vol in profile:
            total_vol = ask_vol + bid_vol
            if total_vol < lvn_threshold:
                lvns.append(price)

        if not lvns:
            return None  # No LVN found

        # Return first LVN in direction
        if direction == "SELL_EXHAUSTION":
            # LONG: First LVN above current price
            lvns_above = [p for p in lvns if p > current_price]
            return min(lvns_above) if lvns_above else None
        else:
            # SHORT: First LVN below current price
            lvns_below = [p for p in lvns if p < current_price]
            return max(lvns_below) if lvns_below else None

    def _calculate_sl(self, absorption_level: float, delta: float, direction: str) -> float:
        """
        Calculate SL based on absorption level + buffer.

        Buffer = delta_magnitude * sl_buffer_multiplier

        For SELL_EXHAUSTION (LONG): SL below absorption level
        For BUY_EXHAUSTION (SHORT): SL above absorption level

        Returns:
            SL price
        """
        # Calculate buffer based on delta magnitude
        delta_magnitude = abs(delta)
        buffer = delta_magnitude * self.sl_buffer_multiplier

        # Convert buffer to price distance (simplified: assume 1 delta = 0.01% price move)
        # TODO: Calibrate this conversion based on historical data
        buffer_pct = buffer * 0.01 / 100  # 1 delta = 0.01%

        if direction == "SELL_EXHAUSTION":
            # LONG: SL below absorption level
            sl_price = absorption_level * (1 - buffer_pct)
        else:
            # SHORT: SL above absorption level
            sl_price = absorption_level * (1 + buffer_pct)

        return sl_price
