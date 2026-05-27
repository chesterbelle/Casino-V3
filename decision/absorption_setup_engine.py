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
from decision.engine.proposal import TradeProposal
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger(__name__)


class AbsorptionSetupEngine(TraceBulletMixin):
    """
    Converts confirmed entry signals into executable setups (V2).

    In V2, this engine only handles TP/SL calculation, validation, and Grade assignment.
    Confirmation is handled by AbsorptionReversalGuardian (Phase 2).

    Dynamic TP/SL:
    - TP: First low-volume node (LVN) in trade direction
    - SL: Absorption level ± buffer
    """

    def __init__(self):
        super().__init__()
        self.name = "AbsorptionSetupEngine"
        self.min_tp_distance_pct = 0.25
        self.max_tp_distance_pct = 0.50
        self.sl_buffer_pct = 0.15

        logger.info(f"✅ {self.name} V2 (Planar Architecture) initialized")

    def _update_dynamic_bounds(self, symbol: str):
        from core.context_registry import ContextRegistry

        reg = ContextRegistry()
        atr_data = reg.atrs.get(symbol, {})
        atr_pct = atr_data.get("long") or atr_data.get("short") or 0.20

        self.min_tp_distance_pct = atr_pct * 3.0
        self.max_tp_distance_pct = atr_pct * 6.5
        self.sl_buffer_pct = atr_pct * 3.33

    def process_confirmed_signal(self, signal: dict) -> Optional[TradeProposal]:
        """
        Process a CONFIRMED entry signal and return a TradeProposal.
        """
        symbol = signal["symbol"]
        direction = signal["direction"]
        level = signal["absorption_level"]
        current_price = signal["entry_price"]
        timestamp = signal["timestamp"]

        self._update_dynamic_bounds(symbol)
        self.trace(signal, "SETUP_GEN_START")

        tp_price = self._calculate_tp(symbol, level, direction, current_price)
        if tp_price is None:
            return None

        tp_distance_pct = abs(tp_price - current_price) / current_price * 100
        if tp_distance_pct < self.min_tp_distance_pct or tp_distance_pct > self.max_tp_distance_pct:
            return None

        sl_price = self._calculate_sl(level, direction)

        # Grade logic: High conviction if multiple confirmations exist
        confirmations = signal.get("confirmations", 0)
        grade = "A" if confirmations >= 2 else "B"

        proposal = TradeProposal(
            symbol=symbol,
            side=signal["side"],
            entry_price=current_price,
            tp_price=tp_price,
            sl_price=sl_price,
            grade=grade,
            narrative=f"Absorption-{grade}-Conf:{confirmations}",
            trace_id=signal.get("trace_id", "unknown"),
            timestamp=timestamp,
        )

        logger.info(f"🎯 [V8.5] TradeProposal generated: {proposal}")
        self.trace(proposal, "SETUP_GEN_COMPLETE")
        return proposal

    # ── TP/SL Calculation ────────────────────────────────────────────

    def _calculate_tp(
        self, symbol: str, absorption_level: float, direction: str, current_price: float
    ) -> Optional[float]:
        """
        Calculate TP based on volume profile (first low-volume node).
        """
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
