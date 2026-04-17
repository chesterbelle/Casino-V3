"""
HFT Exit Manager - Phase 1100 Axia-Style Professional Invalidation

Provides setup-aware exit management for high-frequency institutional scalping.
Professional Patience: Hold for structural targets while the thesis is alive.
Structural Invalidation: Exit immediately if the entry thesis is invalidated.

Replaces the 'Dumb' mode with high-resolution invalidation logic to prevent
edge erosion by avoiding full SL hits on dead trades.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

import config.trading as config
from core.events import TickEvent
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


logger = logging.getLogger("HFTExitManager")


class HFTExitManager:
    """
    Phase 1100: Axia-Style Professional Patience.

    Monitors the 'Thesis Integrity' of each open position based on the
    Footprint setup that triggered it.

    Key Principles:
    - Patience: Do not exit on noise; let the trade breathe (Sniper Lock).
    - Invalidation: If the setup (Trapped Traders, Delta Divergence)
      is structurally broken, trigger immediate exit to preserve capital.
    - Airbag: Secondary safety net for toxic order flow bursts.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logger

        # Minimal configuration
        self.catastrophic_drawdown_pct = getattr(config, "CATASTROPHIC_STOP_PCT", 0.50)
        self.patience_lock_grace_period = getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 3.0)

        # Phase 1100: Pending termination guard for HFT high-frequency loops
        self._pending_terminations = set()

        self.logger.info(
            "🎯 HFTExitManager initialized | "
            f"Catastrophic stop: {self.catastrophic_drawdown_pct:.1%} | "
            f"Axia Invalidation: {getattr(config, 'AXIA_INVALIDATION_ENABLED', False)} | "
            "Mode: PROFESSIONAL (Axia-Style)"
        )

    async def on_tick(self, event: TickEvent):
        """
        Main High-Frequency monitoring loop.
        Evaluates Catastrophe (Liquidation) AND Invalidation (Dead Thesis).

        Args:
            event: TickEvent containing real-time price data for the symbol.
        """
        if not getattr(config, "HFT_EXIT_MODE", False) or getattr(config, "AUDIT_MODE", False):
            return

        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions:
            # Skip positions already closing or already triggered for exit by this manager
            if position.status == "CLOSING" or position.trade_id in self._pending_terminations:
                continue

            now = event.timestamp
            elapsed = now - position.timestamp

            # --- 1. CATASTROPHIC STOP (Liquidation Sheriff) ---
            if self._check_catastrophe(position, event):
                self._pending_terminations.add(position.trade_id)
                asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason="THESIS_CATASTROPHE"))
                continue

            # --- 2. PATIENCE LOCK (Airlock Period) ---
            # Phase 1100: Trades MUST breathe for X seconds before any tactical exit.
            # Prevents 'Noise Exit' which erodes the edge in institutional scalping.
            if elapsed < self.patience_lock_grace_period:
                continue

            # --- 3. FLOW INVALIDATION (Institutional Panic Button) ---
            # Phase B2: If massive order flow reverses against the position (Z ±3.0),
            # close immediately regardless of SL proximity. This is the theory's
            # "Regla de Invalidación Prematura" — always active, not behind a flag.
            flow_reason = self._check_flow_invalidation(position, event)
            if flow_reason:
                self._pending_terminations.add(position.trade_id)
                asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason=flow_reason))
                continue

            # --- 4. AXIA PROFESSIONAL EXIT (Thesis Invalidation) ---
            if getattr(config, "AXIA_INVALIDATION_ENABLED", False):
                invalidation_reason = self._check_thesis_invalidation(position, event)
                if invalidation_reason:
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(
                        self.croupier.close_position(position.trade_id, exit_reason=invalidation_reason)
                    )
                    continue

            # --- 5. TACTICAL SILENCE (Order Flow Airbag) ---
            if getattr(config, "HFT_AIRBAG_ENABLED", False):
                # Close if flow becomes toxic or structural walls collapse
                airbag_reason = self._check_tactical_airbag(position, event)
                if airbag_reason:
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason=airbag_reason))
                    continue

    def _check_flow_invalidation(self, position, event: TickEvent) -> Optional[str]:
        """
        Phase B2: Institutional Panic Button (Flow Invalidation).
        If the real-time Z-score shows massive order flow against the position
        (|Z| > 3.0), the entry thesis is narratively dead regardless of price.
        This is always active — it's the theory's 'Regla de Invalidación Prematura'.
        """
        if not self.croupier.context_registry:
            return None

        cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)

        FLOW_INVALIDATION_Z = 3.0

        if position.side == "LONG" and z < -FLOW_INVALIDATION_Z:
            self.logger.warning(
                f"🚨 [FLOW_INVALIDATION] {position.symbol} LONG closed: "
                f"Massive selling (Z={z:.1f} < -{FLOW_INVALIDATION_Z})"
            )
            return "FLOW_INVALIDATION"

        if position.side == "SHORT" and z > FLOW_INVALIDATION_Z:
            self.logger.warning(
                f"🚨 [FLOW_INVALIDATION] {position.symbol} SHORT closed: "
                f"Massive buying (Z={z:.1f} > +{FLOW_INVALIDATION_Z})"
            )
            return "FLOW_INVALIDATION"

        return None

    def _check_catastrophe(self, position, event: TickEvent) -> bool:
        """Determines if the position is in a terminal death-spiral (>50% loss)."""
        if position.entry_price <= 0:
            return False

        if position.side == "LONG":
            drawdown = (position.entry_price - event.price) / position.entry_price
        else:
            drawdown = (event.price - position.entry_price) / position.entry_price

        return drawdown > self.catastrophic_drawdown_pct

    def _check_thesis_invalidation(self, position, event: TickEvent) -> Optional[str]:
        """
        Institutional Invalidation Logic.

        Evaluates if the 'Physics' of the Footprint setup that triggered
        the trade is still valid. If the thesis is dead, exit immediately.
        Returns the specific exit reason or None.
        """
        setup = position.setup_type
        if setup == "unknown":
            return None

        price = event.price

        # Setup-Specific Invalidation Logic
        if "reversion" in setup:
            # Phase 650: LTA-V4 Structural Reversion Invalidation
            # 1. PRICE-DELTA DIVERGENCE FAILURE
            # If we entered on absorption but aggression (Z-Score) continues violently against us
            cvd, skew, z = (0, 0.5, 0)
            if self.croupier.context_registry:
                cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)

            if position.side == "LONG" and z < -config.HFT_TOXIC_FLOW_THRESHOLD:
                self.logger.warning(f"📉 [AXIA] Invalidation: Toxic Sell Flow (Z={z:.1f}) | Reversion Failed")
                return "THESIS_TOXIC_FLOW"
            if position.side == "SHORT" and z > config.HFT_TOXIC_FLOW_THRESHOLD:
                self.logger.warning(f"📈 [AXIA] Invalidation: Toxic Buy Flow (Z={z:.1f}) | Reversion Failed")
                return "THESIS_TOXIC_FLOW"

            # 2. DYNAMIC STAGNATION (ATR-BASED)
            # If price fails to rotate within a volatility-adjusted window
            base_timeout = 3600.0  # Phase 650.3: 1 hour base (Institutional Patience)
            vol_ratio = 1.0
            if self.croupier.context_registry:
                vol_ratio = self.croupier.context_registry.get_volatility_ratio(position.symbol)

            # High vol = less patience (Timeout / 2.0 = 5 min)
            # Low vol = more patience (Timeout / 0.5 = 20 min)
            effective_timeout = base_timeout / vol_ratio
            elapsed = event.timestamp - position.timestamp

            if elapsed > effective_timeout:
                self.logger.info(
                    f"⌛ [AXIA] Stagnation: Price unresolved after {elapsed:.0f}s (Max: {effective_timeout:.0f}s, VolRatio: {vol_ratio:.2f})"
                )
                return "THESIS_STAGNATION"

        if "Trapped_Traders" in setup or "TrappedTraders" in setup:
            # LONG (Bears Trapped): Invalidation if price goes BELOW the trap zone.
            # SHORT (Bulls Trapped): Invalidation if price goes ABOVE the trap zone.
            # Phase 650 Fix: We widen the micro-wick buffer from 0.05% to 0.15%
            if position.trigger_level and position.trigger_level > 0:
                if position.side == "LONG" and price < position.trigger_level * 0.9985:
                    self.logger.warning(
                        f"📉 [AXIA] Invalidation: Bears released at {price:.4f} (Trap: {position.trigger_level:.4f})"
                    )
                    return "THESIS_TRAP_RELEASED"
                if position.side == "SHORT" and price > position.trigger_level * 1.0015:
                    self.logger.warning(
                        f"📈 [AXIA] Invalidation: Bulls released at {price:.4f} (Trap: {position.trigger_level:.4f})"
                    )
                    return "THESIS_TRAP_RELEASED"

        if "Delta_Divergence" in setup or "DeltaDivergence" in setup:
            # Invalidation: If price moves significantly through the extreme (price in metadata)
            # showing that absorption failed and aggressive expansion won.
            # Phase 650 Fix: Widened to 0.25% (just inside the 0.3% hard SL)
            if position.side == "LONG" and price < position.entry_price * 0.9975:
                return "THESIS_ABSORPTION_FAILED"
            if position.side == "SHORT" and price > position.entry_price * 1.0025:
                return "THESIS_ABSORPTION_FAILED"

        return None

    def _check_tactical_airbag(self, position, event: TickEvent) -> Optional[str]:
        """
        'Tactical Silence' Airbag for HFT.

        Uses ContextRegistry micro-state (Z-Score/Skewness) to detect radioactive
        order flow or the sudden disappearance of institutional support (Walls).
        """
        if not self.croupier.context_registry:
            return None

        cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)

        # 1. Toxic Flow Burst (Extreme Z-Score)
        if position.side == "LONG" and z < -config.HFT_TOXIC_FLOW_THRESHOLD:
            self.logger.warning(f"🚨 [AIRBAG] Toxic Flow Detected (Z={z:.1f}) | Closing LONG")
            return "AIRBAG_TOXIC_FLOW"
        if position.side == "SHORT" and z > config.HFT_TOXIC_FLOW_THRESHOLD:
            self.logger.warning(f"🚨 [AIRBAG] Toxic Flow Detected (Z={z:.1f}) | Closing SHORT")
            return "AIRBAG_TOXIC_FLOW"

        # 2. Wall Collapse (Liquidity Pull)
        if position.side == "LONG" and skew < config.HFT_WALL_COLLAPSE_THRESHOLD:
            self.logger.warning(f"🚨 [AIRBAG] Wall Collapse (Skew: {skew:.2f}) | Closing LONG")
            return "AIRBAG_WALL_COLLAPSE"
        if position.side == "SHORT" and skew > (1 - config.HFT_WALL_COLLAPSE_THRESHOLD):
            self.logger.warning(f"🚨 [AIRBAG] Wall Collapse (Skew: {skew:.2f}) | Closing SHORT")
            return "AIRBAG_WALL_COLLAPSE"

        return None

    async def on_signal(self, event):
        """NO-OP: Thesis Invalidation handles this in real-time."""
        pass

    async def on_candle(self, event):
        """NO-OP: All monitoring migrated to Tick-by-Tick."""
        pass

    async def on_microstructure(self, event):
        """NO-OP: Integrated into on_tick via ContextRegistry."""
        pass

    async def trigger_soft_exits(self):
        """Standard Session Drain - delegates to Croupier logic."""
        pass

    async def trigger_defensive_exits(self):
        pass

    async def trigger_aggressive_exits(self, fraction: float = 0.2):
        pass

    async def apply_dynamic_exit(self, position, phase: str):
        pass
