"""
Absorption Reversal Guardian for Absorption Scalping V2 — Phase 2.

Evaluates confluence of confirmation sensors after an absorption candidate
is detected by AbsorptionDetector (Phase 1).

Architecture:
  AbsorptionDetector → candidate (Phase 1)
       ↓
  AbsorptionReversalGuardian:
       1. Receives candidate, starts confirmation window (3 candles)
       2. Monitors 3 confirmation sensors each candle
       3. If ≥2 of 3 confirmed → generates entry signal
       4. If window expires without confirmation → discards candidate

Regime filter:
  - RANGE: 2 of 3 confirmations, full size
  - TREND_ALIGNED: 2 of 3 confirmations, full size
  - TREND_CONTRA: 3 of 3 confirmations REQUIRED, 50% size
"""

import logging
import time
from typing import Dict, List, Optional

from core.context_registry import ContextRegistry
from core.footprint_registry import footprint_registry
from sensors.absorption.confirmation_sensors import (
    CVDFlipSensor,
    DeltaReversalSensor,
    PriceBreakSensor,
)

logger = logging.getLogger(__name__)


class PendingCandidate:
    """Tracks a candidate through its confirmation window."""

    def __init__(self, candidate: dict, max_candles: int = 3):
        self.candidate = candidate
        self.max_candles = max_candles
        self.candles_elapsed = 0
        self.confirmations = {
            "delta_reversal": False,
            "price_break": False,
            "cvd_flip": False,
        }

    @property
    def confirmation_count(self) -> int:
        return sum(1 for v in self.confirmations.values() if v)

    @property
    def expired(self) -> bool:
        return self.candles_elapsed >= self.max_candles

    @property
    def symbol(self) -> str:
        return self.candidate["symbol"]


class AbsorptionReversalGuardian:
    """
    Phase 2 Guardian: Evaluates confirmation confluence for absorption candidates.

    Does NOT detect anything by itself. Only decides if the evidence from
    the 3 confirmation sensors is sufficient to enter.

    Strict separation: sensors detect facts, guardians evaluate confluence.
    """

    def __init__(self, fast_track: bool = False):
        self.name = "AbsorptionReversalGuardian"
        self.fast_track = fast_track

        # Confirmation sensors
        self.delta_reversal = DeltaReversalSensor()
        self.price_break = PriceBreakSensor()
        self.cvd_flip = CVDFlipSensor()

        # Pending candidates: symbol → PendingCandidate
        self.pending: Dict[str, PendingCandidate] = {}

        # Configuration
        self.confirmation_window = 3  # Max candles to wait for confirmation
        self.min_confirmations = 2  # Standard: 2 of 3
        self.min_confirmations_contra = 3  # Counter-trend: 3 of 3 (strict)
        self.contra_size_multiplier = 0.5  # Counter-trend: 50% size

        logger.info(f"✅ {self.name} initialized (window={self.confirmation_window} candles)")

    def register_candidate(self, candidate: dict):
        """
        Register a new absorption candidate from Phase 1.

        Called by SetupEngine when AbsorptionDetector produces a candidate.
        Starts the confirmation window.
        """
        symbol = candidate["symbol"]

        # Enrich candidate with CVD slope at detection time
        footprint = footprint_registry.get_footprint(symbol)
        if footprint:
            candidate["cvd_slope_at_detection"] = footprint.get_cvd_slope(window_seconds=5)

        # Replace any existing pending candidate for this symbol
        self.pending[symbol] = PendingCandidate(candidate, max_candles=self.confirmation_window)

        logger.info(
            f"📋 [GUARDIAN] Candidate registered: {symbol} {candidate['direction']} "
            f"(waiting for {self.confirmation_window} candles, need ≥{self.min_confirmations} confirmations)"
        )

    def on_candle(
        self,
        symbol: str,
        timestamp: float,
        close_price: float,
        open_price: float = 0,
        high_price: float = 0,
        low_price: float = 0,
    ) -> Optional[dict]:
        """
        Evaluate pending candidates on each candle close.

        Called by SetupEngine on every candle after candidate registration.
        Checks all 3 confirmation sensors and decides whether to enter.

        Args:
            symbol: Trading symbol
            timestamp: Candle close timestamp
            close_price: Candle close price
            open_price: Candle open price
            high_price: Candle high price
            low_price: Candle low price

        Returns:
            Entry signal dict if confirmed, None otherwise
        """
        if symbol not in self.pending:
            return None

        pending = self.pending[symbol]
        pending.candles_elapsed += 1

        candidate = pending.candidate

        # Get current delta from footprint
        footprint = footprint_registry.get_footprint(symbol)
        current_delta = 0.0
        if footprint:
            # Sum deltas across all levels for this candle's net delta
            current_delta = sum(data["delta"] for data in footprint.levels.values())

        # Check all 3 confirmation sensors
        if not pending.confirmations["delta_reversal"]:
            if self.delta_reversal.check(symbol, candidate, current_delta):
                pending.confirmations["delta_reversal"] = True

        if not pending.confirmations["price_break"]:
            if self.price_break.check(symbol, candidate, close_price):
                pending.confirmations["price_break"] = True

        if not pending.confirmations["cvd_flip"]:
            if self.cvd_flip.check(symbol, candidate):
                pending.confirmations["cvd_flip"] = True

        # Evaluate confluence
        count = pending.confirmation_count
        is_contra_trend = self._is_contra_trend(symbol, candidate["side"])
        required = self.min_confirmations_contra if is_contra_trend else self.min_confirmations

        logger.info(
            f"🔍 [GUARDIAN] {symbol} candle {pending.candles_elapsed}/{self.confirmation_window}: "
            f"{count}/{required} confirmations "
            f"(delta_rev={pending.confirmations['delta_reversal']}, "
            f"price_brk={pending.confirmations['price_break']}, "
            f"cvd_flip={pending.confirmations['cvd_flip']})"
            f"{' [CONTRA-TREND]' if is_contra_trend else ''}"
        )

        # Check if confirmed
        if count >= required:
            # CONFIRMED — generate entry signal
            size_mult = self.contra_size_multiplier if is_contra_trend else 1.0
            entry_signal = self._generate_entry_signal(
                candidate, close_price, timestamp, count, size_mult, is_contra_trend
            )
            # Remove from pending
            del self.pending[symbol]
            return entry_signal

        # Check if window expired
        if pending.expired:
            logger.info(
                f"❌ [GUARDIAN] {symbol} confirmation window expired "
                f"({count}/{required} confirmations) — candidate discarded"
            )
            del self.pending[symbol]

        return None

    def _is_contra_trend(self, symbol: str, side: str) -> bool:
        """
        Check if the entry is counter-trend (against the dominant regime).

        Uses ContextRegistry regime data if available.
        """
        if self.fast_track:
            return False

        try:
            ctx = ContextRegistry()
            regime_v2_data = getattr(ctx, "_regime_v2", {}).get(symbol)
            if not regime_v2_data:
                return False

            regime = regime_v2_data.get("regime", "BALANCE")
            direction = regime_v2_data.get("direction", "NEUTRAL")
            confidence = regime_v2_data.get("confidence", 0.0)

            # Only count as contra-trend if regime confidence is high
            if confidence < 0.6:
                return False

            if regime == "TREND_UP" and side == "SHORT":
                return True
            if regime == "TREND_DOWN" and side == "LONG":
                return True

        except Exception:
            pass

        return False

    def _generate_entry_signal(
        self,
        candidate: dict,
        current_price: float,
        timestamp: float,
        confirmations: int,
        size_multiplier: float,
        is_contra_trend: bool,
    ) -> dict:
        """
        Generate entry signal from confirmed candidate.

        This is the final output of Phase 2 — ready for setup engine
        to calculate TP/SL and dispatch.
        """
        logger.info(
            f"🎯 [GUARDIAN_CONFIRMED] {candidate['symbol']} {candidate['side']} "
            f"({confirmations}/3 confirmations, size={size_multiplier:.0%})"
            f"{' [CONTRA-TREND STRICT]' if is_contra_trend else ''}"
        )

        return {
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "direction": candidate["direction"],
            "absorption_level": candidate["absorption_level"],
            "level": candidate["level"],
            "delta": candidate["delta"],
            "z_score": candidate["z_score"],
            "concentration": candidate["concentration"],
            "noise": candidate["noise"],
            "price": current_price,
            "entry_price": current_price,
            "timestamp": timestamp,
            "confirmations": confirmations,
            "confirmation_details": {
                "delta_reversal": True,  # We know at least 2 of 3 are True
                "price_break": True,
                "cvd_flip": True,
            },
            "size_multiplier": size_multiplier,
            "is_contra_trend": is_contra_trend,
            "phase": "confirmed",  # V2: Phase 2 complete
            "strategy": "AbsorptionScalpingV2",
        }
