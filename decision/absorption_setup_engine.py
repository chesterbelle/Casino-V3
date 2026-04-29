"""
Absorption Setup Engine for Absorption Scalping V2.

Converts CONFIRMED entry signals (from AbsorptionReversalGuardian, Phase 2)
into executable setups with TP/SL.
Runs in the MAIN PROCESS with direct FootprintRegistry access.

V2 Architecture:
  AbsorptionReversalGuardian → confirmed entry signal (Phase 2)
       ↓
  AbsorptionSetupEngine:
       1. Calculate TP (LVN-based, dynamic)
       2. Calculate SL (absorption level ± buffer)
       3. Validate TP distance
       4. Apply size multiplier (contra-trend reduction)
       ↓
  Setup dict → SetupEngine dispatch

Note: CVD flattening and price holding checks are NO LONGER done here.
Those are now handled by the confirmation sensors in Phase 2.
"""

import logging
from typing import Optional

from core.footprint_registry import footprint_registry

logger = logging.getLogger(__name__)


class AbsorptionSetupEngine:
    """
    Converts confirmed entry signals into executable setups (V2).

    In V2, this engine only handles TP/SL calculation and validation.
    Confirmation is handled by AbsorptionReversalGuardian (Phase 2).

    Dynamic TP/SL:
    - TP: First low-volume node (LVN) in trade direction
    - SL: Absorption level ± buffer
    """

    def __init__(self, fast_track: bool = False):
        self.name = "AbsorptionSetupEngine"
        self.fast_track = fast_track

        # Configuration
        self.min_tp_distance_pct = 0.05  # Minimum TP distance (0.05%)
        self.max_tp_distance_pct = 0.50  # Maximum TP distance (0.50%)
        self.sl_buffer_pct = 0.15  # SL buffer as % of price

        logger.info(f"✅ {self.name} V2 initialized{' (FAST-TRACK MODE)' if fast_track else ''}")

    def process_confirmed_signal(self, signal: dict) -> Optional[dict]:
        """
        Process a CONFIRMED entry signal from AbsorptionReversalGuardian.

        In V2, the signal is already confirmed (Phase 2 complete).
        This method only calculates TP/SL and validates distances.

        Args:
            signal: Confirmed entry signal dict from guardian

        Returns:
            Setup dict or None
        """
        symbol = signal["symbol"]
        direction = signal["direction"]
        level = signal["absorption_level"]
        current_price = signal["entry_price"]
        timestamp = signal["timestamp"]

        # Calculate TP
        tp_price = self._calculate_tp(symbol, level, direction, current_price)
        if tp_price is None:
            logger.debug(f"❌ [ABSORPTION_V2] No valid TP found for {symbol}")
            return None

        # Validate TP distance
        tp_distance_pct = abs(tp_price - current_price) / current_price * 100
        if tp_distance_pct < self.min_tp_distance_pct:
            logger.debug(f"❌ [ABSORPTION_V2] TP too close: {tp_distance_pct:.2f}% < {self.min_tp_distance_pct}%")
            return None
        if tp_distance_pct > self.max_tp_distance_pct:
            logger.debug(f"❌ [ABSORPTION_V2] TP too far: {tp_distance_pct:.2f}% > {self.max_tp_distance_pct}%")
            return None

        # Calculate SL
        sl_price = self._calculate_sl(level, direction)

        # Generate setup
        side = signal["side"]
        size_multiplier = signal.get("size_multiplier", 1.0)

        setup = {
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "absorption_level": level,
            "delta": signal["delta"],
            "z_score": signal["z_score"],
            "concentration": signal["concentration"],
            "noise": signal["noise"],
            "timestamp": timestamp,
            "strategy": "AbsorptionScalpingV2",
            "size_multiplier": size_multiplier,
            "confirmations": signal.get("confirmations", 0),
            "is_contra_trend": signal.get("is_contra_trend", False),
        }

        logger.info(
            f"🎯 [ABSORPTION_V2] Setup generated: {symbol} {side} @ {current_price:.2f} "
            f"(TP={tp_price:.2f} +{tp_distance_pct:.2f}%, SL={sl_price:.2f}, "
            f"conf={signal.get('confirmations', 0)}/3, size={size_multiplier:.0%})"
        )

        return setup

    # ── TP/SL Calculation ────────────────────────────────────────────

    def _calculate_tp(
        self, symbol: str, absorption_level: float, direction: str, current_price: float
    ) -> Optional[float]:
        """
        Calculate TP based on volume profile (first low-volume node).
        """
        if self.fast_track:
            if direction == "SELL_EXHAUSTION":
                return current_price * 1.002
            else:
                return current_price * 0.998

        # Search range
        if direction == "SELL_EXHAUSTION":
            price_from = current_price
            price_to = current_price * (1 + self.max_tp_distance_pct / 100)
        else:
            price_from = current_price * (1 - self.max_tp_distance_pct / 100)
            price_to = current_price

        profile = footprint_registry.get_volume_profile(symbol, price_from, price_to)

        if len(profile) < 5:
            return None

        # Find low-volume nodes (LVN): volume < 50% of average
        total_volume = sum(ask_vol + bid_vol for _, ask_vol, bid_vol in profile)
        avg_volume = total_volume / len(profile)
        lvn_threshold = avg_volume * 0.5

        lvns = [price for price, ask_vol, bid_vol in profile if (ask_vol + bid_vol) < lvn_threshold]

        if not lvns:
            return None

        if direction == "SELL_EXHAUSTION":
            lvns_above = [p for p in lvns if p > current_price]
            return min(lvns_above) if lvns_above else None
        else:
            lvns_below = [p for p in lvns if p < current_price]
            return max(lvns_below) if lvns_below else None

    def _calculate_sl(self, absorption_level: float, direction: str) -> float:
        """
        Calculate SL: absorption level ± fixed buffer.
        """
        if direction == "SELL_EXHAUSTION":
            # LONG: SL below absorption level
            return absorption_level * (1 - self.sl_buffer_pct / 100)
        else:
            # SHORT: SL above absorption level
            return absorption_level * (1 + self.sl_buffer_pct / 100)
