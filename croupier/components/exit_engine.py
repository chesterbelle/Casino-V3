"""
ExitEngine — Unified 5-Layer Exit Management (Phase 1200)

Replaces both ExitManager and HFTExitManager with a single, layered engine
that combines winner protection + thesis invalidation + SCE scale-out.

Layer Stack (Priority Order):
  5. CATASTROPHIC STOP — Liquidation prevention (always active)
  4. THESIS INVALIDATION — Setup-specific structural invalidation
  3. SCE — Flow-aware conviction scale-out (MEX/CFI)
  2. SHADOW PROTECTION — Breakeven + Trailing + Winner Catcher
  1. SESSION DRAIN — Progressive exit during session shutdown

Design Principles:
  - Every layer adds unique value; no overlapping checks
  - Profit-aware invalidation: never stagnate a winning trade
  - Grace period (Patience Lock) before tactical evaluation
  - 48-symbol concurrency: O(1) per-symbol, semaphore-gated API calls
  - Audit mode compliance: zero interference with signal quality
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

import config.trading as config
from core.context_registry import ContextRegistry
from core.events import (
    AggregatedSignalEvent,
    CandleEvent,
    MicrostructureEvent,
    TickEvent,
)
from core.portfolio.position_tracker import OpenPosition
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


class ExitEngine:
    """
    Unified Exit Engine — 5-Layer Stack.

    Processes each tick through layers 5→1 in priority order.
    A position that hits a higher layer is immediately closed
    and skipped for lower layers.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logging.getLogger("ExitEngine")
        self.context_registry = ContextRegistry()
        self._position_locks = defaultdict(asyncio.Lock)

        # Termination guard: prevents double-close from concurrent layers
        self._pending_terminations: set = set()

        # Configuration
        self.catastrophic_drawdown_pct = getattr(config, "CATASTROPHIC_STOP_PCT", 0.50)
        self.patience_lock_grace_period = getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0)

        self.logger.info(
            "🎯 ExitEngine initialized | "
            f"Catastrophic: {self.catastrophic_drawdown_pct:.1%} | "
            f"Thesis: {getattr(config, 'EXIT_LAYER_THESIS_INVALIDATION', True)} | "
            f"SCE: {getattr(config, 'EXIT_LAYER_SCE', True)} | "
            f"Shadow: {getattr(config, 'EXIT_LAYER_SHADOW_PROTECTION', True)} | "
            f"Drain: {getattr(config, 'EXIT_LAYER_SESSION_DRAIN', True)}"
        )

    # =========================================================
    # EVENT HANDLERS (Same interface as ExitManager/HFTExitManager)
    # =========================================================

    async def on_tick(self, event: TickEvent):
        """
        Main high-frequency monitoring loop.
        Processes layers 5→1 for each position matching the tick's symbol.
        """
        current_price = event.price
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions[:]:
            # Skip positions already closing or terminated
            if (
                position.status == "CLOSING"
                or position.trade_id in self._pending_terminations
                or self.croupier.error_handler.shutdown_mode
                or getattr(position, "shadow_sl_triggered", False)
            ):
                continue

            # --- LAYER 5: CATASTROPHIC STOP (No grace period) ---
            if getattr(config, "EXIT_LAYER_CATASTROPHIC", True):
                if self._check_catastrophic(position, event):
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(
                        self.croupier.close_position(position.trade_id, exit_reason="CATASTROPHIC_STOP")
                    )
                    continue

            # --- PATIENCE LOCK (Grace Period) ---
            elapsed = event.timestamp - position.timestamp
            if elapsed < self.patience_lock_grace_period:
                continue

            # Audit mode: log only, no execution for layers 4-2
            if config.AUDIT_MODE:
                await self._audit_log_layers(position, event, current_price, elapsed)
                continue

            # --- LAYER 4: THESIS INVALIDATION ---
            if getattr(config, "EXIT_LAYER_THESIS_INVALIDATION", True):
                invalidation_reason = self._check_thesis_invalidation(position, event, current_price, elapsed)
                if invalidation_reason:
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(
                        self.croupier.close_position(position.trade_id, exit_reason=invalidation_reason)
                    )
                    continue

            # --- LAYER 3: STRUCTURAL CONVICTION ENGINE (SCE) ---
            if getattr(config, "EXIT_LAYER_SCE", True):
                await self._check_structural_conviction(position, event, current_price)

            # --- LAYER 2: SHADOW PROTECTION ---
            if getattr(config, "EXIT_LAYER_SHADOW_PROTECTION", True):
                # 2a. Shadow SL Trigger Check (Market Close)
                if position.shadow_sl_level is not None and position.shadow_sl_level > 0:
                    triggered = False
                    if position.side == "LONG" and current_price <= position.shadow_sl_level:
                        triggered = True
                    elif position.side == "SHORT" and current_price >= position.shadow_sl_level:
                        triggered = True

                    if triggered:
                        self.logger.warning(
                            f"🚨 Shadow SL Triggered for {position.trade_id} @ {current_price:.6f} "
                            f"(Threshold: {position.shadow_sl_level:.6f})"
                        )
                        position.shadow_sl_triggered = True
                        self._pending_terminations.add(position.trade_id)
                        asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason="SHADOW_SL"))
                        position.shadow_sl_level = None
                        continue

                # 2b. Shadow Breakeven Update
                if config.BREAKEVEN_ENABLED:
                    await self._check_shadow_breakeven(position, current_price)

                # 2c. Shadow Trailing Stop Update
                if config.TRAILING_STOP_ENABLED:
                    await self._check_shadow_trailing_stop(position, current_price)

    async def on_candle(self, event: CandleEvent):
        """
        Handle candle for time-based exits and POC migration.
        """
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions[:]:
            if (
                position.status == "CLOSING"
                or position.trade_id in self._pending_terminations
                or self.croupier.error_handler.shutdown_mode
                or getattr(position, "shadow_sl_triggered", False)
            ):
                continue

            # --- LAYER 1: SESSION DRAIN (Time-Based) ---
            if getattr(config, "EXIT_LAYER_SESSION_DRAIN", True):
                await self._check_time_exit(position, event)

            # --- LAYER 3: SCE (Structural Check) ---
            if getattr(config, "EXIT_LAYER_SCE", True):
                await self._check_structural_conviction(position, event, event.close)

            # POC Migration (always active, not layer-gated)
            await self._check_poc_migration(position)

    async def on_signal(self, event: AggregatedSignalEvent):
        """
        Signal handler — thesis invalidation subsumes signal reversal.
        Kept for interface compatibility but logic is in Layer 4.
        """
        pass

    async def on_microstructure(self, event: MicrostructureEvent):
        """
        Microstructure handler — processes Layer 4 (Thesis Invalidation) checks
        using event-embedded flow data (skewness, z_score, cvd).

        This allows micro-exit triggers from microstructure events directly,
        without requiring context_registry to be updated first.
        """
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions[:]:
            if (
                position.status == "CLOSING"
                or position.trade_id in self._pending_terminations
                or self.croupier.error_handler.shutdown_mode
            ):
                continue

            # --- PATIENCE LOCK ---
            elapsed = event.timestamp - position.timestamp
            if elapsed < self.patience_lock_grace_period:
                continue

            # --- LAYER 4: Flow + Wall Collapse (from event data) ---
            if getattr(config, "EXIT_LAYER_THESIS_INVALIDATION", True):
                # Flow Invalidation (two-tier Z-score from event)
                z = getattr(event, "z_score", 0.0)
                skew = getattr(event, "skewness", 0.5)

                emergency_z = getattr(config, "HFT_TOXIC_FLOW_THRESHOLD", 5.5)
                early_z = 3.0

                flow_reason = None
                # Emergency tier
                if position.side == "LONG" and z < -emergency_z:
                    flow_reason = "FLOW_EMERGENCY"
                elif position.side == "SHORT" and z > emergency_z:
                    flow_reason = "FLOW_EMERGENCY"
                # Early warning tier
                elif position.side == "LONG" and z < -early_z:
                    flow_reason = "FLOW_INVALIDATION"
                elif position.side == "SHORT" and z > early_z:
                    flow_reason = "FLOW_INVALIDATION"

                if flow_reason:
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason=flow_reason))
                    continue

                # Wall Collapse (from event skewness)
                wall_threshold = getattr(config, "HFT_WALL_COLLAPSE_THRESHOLD", 0.15)
                wall_reason = None
                if position.side == "LONG" and skew < wall_threshold:
                    wall_reason = "WALL_COLLAPSE_BID"
                elif position.side == "SHORT" and skew > (1 - wall_threshold):
                    wall_reason = "WALL_COLLAPSE_ASK"

                if wall_reason:
                    self._pending_terminations.add(position.trade_id)
                    asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason=wall_reason))
                    continue

    # =========================================================
    # LAYER 5: CATASTROPHIC STOP
    # =========================================================

    def _check_catastrophic(self, position: OpenPosition, event: TickEvent) -> bool:
        """Determines if position is in terminal death-spiral (>50% loss)."""
        if position.entry_price <= 0:
            return False

        if position.side == "LONG":
            drawdown = (position.entry_price - event.price) / position.entry_price
        else:
            drawdown = (event.price - position.entry_price) / position.entry_price

        return drawdown > self.catastrophic_drawdown_pct

    # =========================================================
    # LAYER 4: THESIS INVALIDATION (Unified)
    # =========================================================

    def _check_thesis_invalidation(
        self, position: OpenPosition, event: TickEvent, current_price: float, elapsed: float
    ) -> Optional[str]:
        """
        Unified thesis invalidation — combines flow, setup-specific, and stagnation checks.

        Two-tier Z-score:
          - Z > 3.0: Early warning (flow against position)
          - Z > 5.5: Emergency (toxic flow burst)

        Stagnation is profit-aware: ONLY closes if unrealized PnL < 0.
        """
        setup = position.setup_type

        # --- 4a. FLOW INVALIDATION (Always active, setup-agnostic) ---
        flow_reason = self._check_flow_invalidation(position)
        if flow_reason:
            return flow_reason

        # --- 4b. SETUP-SPECIFIC INVALIDATION ---
        if setup != "unknown":
            setup_reason = self._check_setup_invalidation(position, current_price)
            if setup_reason:
                return setup_reason

        # --- 4c. STAGNATION (Profit-Aware) — DISABLED as hard close ---
        # Stagnation competes with bracket SL and erodes edge.
        # The bracket SL handles losses better (avg -0.14% vs stagnation -0.19%).
        # Kept as diagnostic only; can be re-enabled as soft gate (SL tightening).
        # stagnation_reason = self._check_stagnation(position, current_price, elapsed)
        # if stagnation_reason:
        #     return stagnation_reason

        # --- 4d. WALL COLLAPSE ---
        wall_reason = self._check_wall_collapse(position)
        if wall_reason:
            return wall_reason

        return None

    def _check_flow_invalidation(self, position: OpenPosition) -> Optional[str]:
        """
        Two-tier Z-score flow invalidation.
        Z > 3.0 (early) or Z > 5.5 (emergency) against position → close.
        """
        if not self.croupier.context_registry:
            return None

        cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)

        # Emergency tier (Z > 5.5)
        emergency_z = getattr(config, "HFT_TOXIC_FLOW_THRESHOLD", 5.5)
        if position.side == "LONG" and z < -emergency_z:
            self.logger.warning(f"🚨 [FLOW-EMERGENCY] {position.symbol} LONG: Toxic sell (Z={z:.1f} < -{emergency_z})")
            return "FLOW_EMERGENCY"
        if position.side == "SHORT" and z > emergency_z:
            self.logger.warning(f"🚨 [FLOW-EMERGENCY] {position.symbol} SHORT: Toxic buy (Z={z:.1f} > +{emergency_z})")
            return "FLOW_EMERGENCY"

        # Early warning tier (Z > 3.0)
        early_z = 3.0
        if position.side == "LONG" and z < -early_z:
            self.logger.warning(f"⚠️ [FLOW-EARLY] {position.symbol} LONG: Strong sell (Z={z:.1f} < -{early_z})")
            return "FLOW_INVALIDATION"
        if position.side == "SHORT" and z > early_z:
            self.logger.warning(f"⚠️ [FLOW-EARLY] {position.symbol} SHORT: Strong buy (Z={z:.1f} > +{early_z})")
            return "FLOW_INVALIDATION"

        return None

    def _check_setup_invalidation(self, position: OpenPosition, current_price: float) -> Optional[str]:
        """Setup-specific structural invalidation."""
        setup = position.setup_type

        if "reversion" in setup:
            # LTA-V4 Structural Reversion Invalidation
            # Toxic flow continues violently against us
            if self.croupier.context_registry:
                cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)
                toxic_threshold = getattr(config, "HFT_TOXIC_FLOW_THRESHOLD", 5.5)
                if position.side == "LONG" and z < -toxic_threshold:
                    self.logger.warning(f"📉 [THESIS] Invalidation: Toxic Sell Flow (Z={z:.1f}) | Reversion Failed")
                    return "THESIS_TOXIC_FLOW"
                if position.side == "SHORT" and z > toxic_threshold:
                    self.logger.warning(f"📈 [THESIS] Invalidation: Toxic Buy Flow (Z={z:.1f}) | Reversion Failed")
                    return "THESIS_TOXIC_FLOW"

        if "Trapped_Traders" in setup or "TrappedTraders" in setup:
            # Trap Released: price escapes the trap zone
            if position.trigger_level and position.trigger_level > 0:
                if position.side == "LONG" and current_price < position.trigger_level * 0.9985:
                    self.logger.warning(
                        f"📉 [THESIS] Bears released at {current_price:.4f} (Trap: {position.trigger_level:.4f})"
                    )
                    return "THESIS_TRAP_RELEASED"
                if position.side == "SHORT" and current_price > position.trigger_level * 1.0015:
                    self.logger.warning(
                        f"📈 [THESIS] Bulls released at {current_price:.4f} (Trap: {position.trigger_level:.4f})"
                    )
                    return "THESIS_TRAP_RELEASED"

        if "Delta_Divergence" in setup or "DeltaDivergence" in setup:
            # Absorption Failed: price moved through the extreme
            if position.side == "LONG" and current_price < position.entry_price * 0.9975:
                return "THESIS_ABSORPTION_FAILED"
            if position.side == "SHORT" and current_price > position.entry_price * 1.0025:
                return "THESIS_ABSORPTION_FAILED"

        # Phase 5: Absorption V1 - Counter-Absorption Detection
        if "Absorption" in setup or setup == "AbsorptionScalpingV1":
            counter_reason = self._check_counter_absorption(position, current_price)
            if counter_reason:
                return counter_reason

        return None

    def _check_stagnation(self, position: OpenPosition, current_price: float, elapsed: float) -> Optional[str]:
        """
        ATR-Dynamic Stagnation — ONLY if unrealized PnL < 0.

        The critical fix: profitable trades are NEVER stagnated.
        A slow winner is still a winner.

        Volatility scaling: In HIGH vol, reversion needs MORE time (price swings wider
        before reverting), so we MULTIPLY by vol_ratio instead of dividing.
        """
        base_timeout = getattr(config, "STAGNATION_BASE_TIMEOUT", 900.0)
        vol_ratio = 1.0
        if self.croupier.context_registry:
            vol_ratio = self.croupier.context_registry.get_volatility_ratio(position.symbol)

        # Edge-aligned: base 900s (15min) matches edge audit window.
        # High vol = wider swings = slightly more time, but cap at 2x.
        effective_timeout = base_timeout * min(vol_ratio, 2.0)

        if elapsed > effective_timeout:
            # PROFIT-AWARE CHECK: Only stagnate if losing
            pnl_pct = self._calc_pnl_pct(position, current_price)
            if pnl_pct < 0:
                self.logger.info(
                    f"⌛ [STAGNATION] Price unresolved after {elapsed:.0f}s "
                    f"(Max: {effective_timeout:.0f}s, VolRatio: {vol_ratio:.2f}, PnL: {pnl_pct:.2%})"
                )
                return "THESIS_STAGNATION"
            else:
                self.logger.debug(f"⌛ Stagnation timeout reached but position profitable ({pnl_pct:.2%}) — holding")

        return None

    def _check_wall_collapse(self, position: OpenPosition) -> Optional[str]:
        """Wall Collapse: institutional support disappears (skew extreme)."""
        if not self.croupier.context_registry:
            return None

        cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)
        wall_threshold = getattr(config, "HFT_WALL_COLLAPSE_THRESHOLD", 0.15)

        if position.side == "LONG" and skew < wall_threshold:
            self.logger.warning(f"🚨 [WALL] Bid wall collapsed (Skew: {skew:.2f}) | Closing LONG")
            return "WALL_COLLAPSE_BID"
        if position.side == "SHORT" and skew > (1 - wall_threshold):
            self.logger.warning(f"🚨 [WALL] Ask wall collapsed (Skew: {skew:.2f}) | Closing SHORT")
            return "WALL_COLLAPSE_ASK"

        return None

    def _check_counter_absorption(self, position: OpenPosition, current_price: float) -> Optional[str]:
        """
        Phase 5: Counter-Absorption Detection for Absorption V1.

        Detects when absorption appears in the opposite direction,
        invalidating the original thesis.

        For LONG (from SELL_EXHAUSTION):
          - Counter-absorption = BUY_EXHAUSTION detected
          - Indicates bulls are now exhausted, bears taking control

        For SHORT (from BUY_EXHAUSTION):
          - Counter-absorption = SELL_EXHAUSTION detected
          - Indicates bears are now exhausted, bulls taking control
        """
        try:
            from core.footprint_registry import footprint_registry
            from sensors.absorption.absorption_detector import AbsorptionDetector

            # Get fresh footprint data
            footprint = footprint_registry.get_footprint(position.symbol)
            if not footprint or len(footprint.levels) < 10:
                return None  # Insufficient data

            # Create detector instance for analysis
            detector = AbsorptionDetector()

            # Find extreme deltas (potential counter-absorption)
            candidates = detector._find_extreme_deltas(footprint, current_price)

            if not candidates:
                return None

            # Check each candidate for counter-absorption
            for level, delta, ask_vol, bid_vol in candidates:
                # Calculate quality metrics
                z_score = detector._calculate_z_score(position.symbol, delta, current_price)
                concentration = detector._calculate_concentration(footprint, level, current_price)
                noise = detector._calculate_noise(ask_vol, bid_vol, delta)

                # Check if it passes quality filters
                if abs(z_score) < detector.z_score_min:
                    continue
                if concentration < detector.concentration_min:
                    continue
                if noise > detector.noise_max:
                    continue

                # Determine direction
                direction = "SELL_EXHAUSTION" if delta < 0 else "BUY_EXHAUSTION"

                # Check for counter-absorption
                if position.side == "LONG" and direction == "BUY_EXHAUSTION":
                    # LONG position, but now seeing BUY exhaustion (counter-absorption)
                    self.logger.warning(
                        f"🔄 [COUNTER-ABSORPTION] LONG invalidated: BUY_EXHAUSTION detected "
                        f"(level={level:.2f}, delta={delta:.1f}, z={z_score:.1f})"
                    )
                    return "COUNTER_ABSORPTION_BUY"

                if position.side == "SHORT" and direction == "SELL_EXHAUSTION":
                    # SHORT position, but now seeing SELL exhaustion (counter-absorption)
                    self.logger.warning(
                        f"🔄 [COUNTER-ABSORPTION] SHORT invalidated: SELL_EXHAUSTION detected "
                        f"(level={level:.2f}, delta={delta:.1f}, z={z_score:.1f})"
                    )
                    return "COUNTER_ABSORPTION_SELL"

            return None

        except Exception as e:
            self.logger.error(f"❌ [COUNTER-ABSORPTION] Detection failed: {e}", exc_info=True)
            return None

    # =========================================================
    # LAYER 3: STRUCTURAL CONVICTION ENGINE (SCE)
    # =========================================================

    async def _check_structural_conviction(self, position: OpenPosition, event: TickEvent, current_price: float):
        """
        Structural Conviction Engine (SCE):
        Monitors order flow conviction to scale out or trail aggressively.
        1. CFI (Counter-Flow Invalidation): Absorption against the trade.
        2. MEX (Micro-Exhaustion): Delta momentum decay.
        3. STS (Structural Trailing Stop): Trailing behind volume nodes.
        """
        if position.status != "ACTIVE" or position.scaled_out:
            return

        # Phase 1300: Only activate SCE when in sufficient profit
        profit_pct = self._calc_pnl_pct(position, current_price)

        # Phase 1300: SCE activation gate
        self.logger.debug(
            f"🔍 [SCE] {position.trade_id} PnL: {profit_pct:.4%} | Gate: {getattr(config, 'SCE_MIN_PROFIT_PCT', 0.0008):.4%}"
        )

        if profit_pct < getattr(config, "SCE_MIN_PROFIT_PCT", 0.0008):
            return

        # 1. CFI: Counter-Flow Invalidation (Absorption at target)
        if getattr(config, "SCE_CFI_ENABLED", True):
            cfi_reason = await self._check_counter_flow_invalidation(position, current_price)
            if cfi_reason:
                self.logger.warning(f"🔄 [SCE-CFI] Conviction Lost: {cfi_reason} | Scaling out.")
                asyncio.create_task(
                    self.croupier.scale_out_structural(
                        position.trade_id, fraction=config.SCE_SCALE_FRACTION, reason="SCE_CFI"
                    )
                )
                return

        # 2. MEX: Micro-Exhaustion (Delta Momentum Decay)
        mex_triggered = self._check_micro_exhaustion(position)
        if mex_triggered:
            self.logger.warning("📉 [SCE-MEX] Momentum Exhausted (Delta decay) | Scaling out.")
            asyncio.create_task(
                self.croupier.scale_out_structural(
                    position.trade_id, fraction=config.SCE_SCALE_FRACTION, reason="SCE_MEX"
                )
            )
            return

        # 3. STS: Structural Trailing Stop
        if getattr(config, "SCE_STS_ENABLED", True):
            await self._check_structural_trailing(position, current_price)

    async def _check_counter_flow_invalidation(self, position: OpenPosition, current_price: float) -> Optional[str]:
        """
        CFI: Detects if passive participants are absorbing our move at a target.
        """
        # We reuse the counter-absorption logic but specifically for scaling out
        return self._check_counter_absorption(position, current_price)

    def _check_micro_exhaustion(self, position: OpenPosition) -> bool:
        """
        MEX: Detects if the aggressive flow in our direction is 'running out of gas'.
        """
        if not self.croupier.context_registry:
            self.logger.warning(f"⚠️ [SCE] ContextRegistry MISSING for {position.symbol}. Conviction check skipped.")
            return False

        cvd, skew, z = self.croupier.context_registry.get_micro_state(position.symbol)
        threshold = getattr(config, "SCE_MEX_THRESHOLD", 0.70)

        # Phase 1300: Z-score tracking
        self.logger.debug(
            f"📊 [SCE-Z] {position.trade_id} Z={z:.2f} | Threshold={threshold:.2f} | Side={position.side}"
        )

        # If long, we want positive Z. If Z drops or becomes neutral while in profit -> Exhaustion.
        if position.side == "LONG":
            if z < threshold:  # Delta strength faded
                return True
        elif position.side == "SHORT":
            if z > -threshold:  # Delta strength faded (less negative)
                return True

        return False

    async def _check_structural_trailing(self, position: OpenPosition, current_price: float):
        """
        STS: Move SL behind High Volume Nodes (HVN) as they form.
        """
        # Logic to find the nearest HVN behind the price
        pass

    # =========================================================
    # LAYER 2: SHADOW PROTECTION (BE + Trailing + Winner Catcher)
    # =========================================================

    async def _check_shadow_breakeven(self, position: OpenPosition, current_price: float):
        """Move Shadow SL to entry if profit threshold reached."""
        if position.entry_price <= 0:
            return

        if position.shadow_sl_level is None and position.sl_level > 0:
            position.shadow_sl_level = position.sl_level

        if position.side == "LONG":
            if position.shadow_sl_level is not None and position.shadow_sl_level >= position.entry_price:
                return
            profit_pct = (current_price - position.entry_price) / position.entry_price

            activation_threshold = config.BREAKEVEN_ACTIVATION_PCT
            if getattr(position, "entry_atr", 0) > 0:
                atr_profit_dist = position.entry_atr * config.EXIT_ATR_MULT_BE
                activation_threshold = atr_profit_dist / position.entry_price

            if profit_pct >= activation_threshold:
                new_sl = position.entry_price * 1.001
                if position.shadow_sl_level is None or new_sl > position.shadow_sl_level:
                    position.shadow_sl_level = new_sl
                    self.logger.info(f"🛡️ Breakeven ACTIVATED for {position.trade_id} @ {new_sl:.6f}")

        elif position.side == "SHORT":
            if (
                position.shadow_sl_level is not None
                and position.shadow_sl_level <= position.entry_price
                and position.shadow_sl_level > 0
            ):
                return
            profit_pct = (position.entry_price - current_price) / position.entry_price

            activation_threshold = config.BREAKEVEN_ACTIVATION_PCT
            if getattr(position, "entry_atr", 0) > 0:
                atr_profit_dist = position.entry_atr * config.EXIT_ATR_MULT_BE
                activation_threshold = atr_profit_dist / position.entry_price

            if profit_pct >= activation_threshold:
                new_sl = position.entry_price * 0.999
                if (
                    position.shadow_sl_level is None
                    or new_sl < position.shadow_sl_level
                    or position.shadow_sl_level == 0
                ):
                    position.shadow_sl_level = new_sl
                    self.logger.info(f"🛡️ Breakeven ACTIVATED for {position.trade_id} @ {new_sl:.6f}")

    async def _check_shadow_trailing_stop(self, position: OpenPosition, current_price: float):
        """Phase 241/800: Update Shadow SL with Phase-Aware Multipliers."""
        if position.entry_price <= 0:
            return
        if position.shadow_sl_level is None and position.sl_level > 0:
            position.shadow_sl_level = position.sl_level

        # 1. Calculate Core Profit Metrics
        profit_pct = self._calc_pnl_pct(position, current_price)

        # 2. Winner Catcher: Phase 0 → Phase 1
        if position.trailing_phase == 0 and profit_pct >= config.TRAILING_STOP_EXPANSION_THRESHOLD_PCT:
            self.logger.warning(
                f"🚀 [WINNER-CATCHER] ACTIVATED for {position.trade_id} @ {profit_pct:.2%} profit | Expanding TP..."
            )
            position.trailing_phase = 1
            asyncio.create_task(self._expand_tp_limit(position))

        # 3. Determine Multiplier based on Phase
        if position.trailing_phase == 1:
            atr_mult = config.TRAILING_STOP_EXPANSION_MULT
        else:
            atr_mult = config.EXIT_ATR_MULT_TS

        # 4. Flow-Aware Inertia
        inertia = 1.0
        if hasattr(self, "context_registry") and self.context_registry:
            inertia = self.context_registry.get_flow_inertia(position.symbol, position.side, profit_pct)

        # 5. Activation Gate
        activation_threshold = getattr(position, "shadow_sl_activation", config.TRAILING_STOP_ACTIVATION_PCT)
        if profit_pct < activation_threshold:
            return

        # 6. Calculate Trailing Level
        if getattr(position, "entry_atr", 0) > 0:
            trailing_dist = position.entry_atr * atr_mult
        else:
            trailing_dist = current_price * config.TRAILING_STOP_DISTANCE_PCT

        if position.side == "LONG":
            new_sl = current_price - (trailing_dist * inertia)
            if position.shadow_sl_level is None or new_sl > position.shadow_sl_level:
                position.shadow_sl_level = new_sl
                if inertia != 1.0 or position.trailing_phase == 1:
                    mode = "EXPANSION" if position.trailing_phase == 1 else "DEFENSIVE"
                    self.logger.debug(f"🧠 [DYNAMIC SL] {mode} Mode (Mult: {atr_mult}x) for {position.trade_id}")
        else:
            new_sl = current_price + (trailing_dist * inertia)
            if position.shadow_sl_level is None or new_sl < position.shadow_sl_level or position.shadow_sl_level == 0:
                position.shadow_sl_level = new_sl
                if inertia != 1.0 or position.trailing_phase == 1:
                    mode = "EXPANSION" if position.trailing_phase == 1 else "DEFENSIVE"
                    self.logger.debug(f"🧠 [DYNAMIC SL] {mode} Mode (Mult: {atr_mult}x) for {position.trade_id}")

    async def _expand_tp_limit(self, position: OpenPosition):
        """Winner Catcher: Move exchange TP to distant target (6:1 RR)."""
        if not position.tp_order_id:
            return

        try:
            risk_dist = abs(position.entry_price - position.sl_level)
            if risk_dist <= 0:
                risk_dist = position.entry_atr * 1.5 if position.entry_atr > 0 else position.entry_price * 0.002

            if position.side == "LONG":
                expanded_tp = position.entry_price + (risk_dist * config.EXPANSION_TP_RR)
            else:
                expanded_tp = position.entry_price - (risk_dist * config.EXPANSION_TP_RR)

            self.logger.info(
                f"🌌 [EXPANSION] Moving TP for {position.trade_id} to {expanded_tp:.6f} "
                f"(Target: {config.EXPANSION_TP_RR}x RR)"
            )

            await self.croupier.modify_tp(
                trade_id=position.trade_id,
                new_tp_price=expanded_tp,
                symbol=position.symbol,
                old_tp_order_id=position.tp_order_id,
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to expand TP for {position.trade_id}: {e}")

    # =========================================================
    # LAYER 1: SESSION DRAIN (Time-Based)
    # =========================================================

    async def _check_time_exit(self, position: OpenPosition, candle: CandleEvent):
        """Apply soft/hard exit based on MAX_HOLD_BARS."""
        if position.bars_held >= config.MAX_HOLD_BARS:
            if getattr(self.croupier, "is_drain_mode", False):
                if not getattr(position, "soft_exit_triggered", False):
                    await self._execute_soft_exit(position, "Max Time")

            if position.bars_held >= config.MAX_HOLD_BARS * 2:
                self.logger.critical(f"🚨 Double Max Hold Reached for {position.trade_id}. Force closing.")
                try:
                    await self.croupier.close_position(position.trade_id, exit_reason="HARD_TIME_EXIT")
                except Exception as e:
                    self.logger.error(f"❌ Failed to execute hard time exit: {e}")

    async def _check_poc_migration(self, position: OpenPosition):
        """Dynamic Value Migration: Adjust TP if POC shifts significantly."""
        if not hasattr(self.context_registry, "get_structural") or not position.tp_order_id:
            return

        now = time.time()
        last_update = getattr(position, "last_poc_migration", 0)
        if now - last_update < 300:
            return

        poc, _, _ = self.context_registry.get_structural(position.symbol)
        if not poc or poc <= 0:
            return

        current_tp = position.tp_level
        if not current_tp or current_tp <= 0:
            return

        migration_pct = abs(poc - current_tp) / current_tp
        if migration_pct >= 0.0020:
            self.logger.info(
                f"🧲 [VALUE MIGRATION] POC shifted for {position.symbol}. "
                f"Old TP: {current_tp:.4f} -> New POC: {poc:.4f} (Shift: {migration_pct:.2%})"
            )
            try:
                await asyncio.sleep(0.05)
                await self.croupier.modify_tp(
                    trade_id=position.trade_id,
                    new_tp_price=poc,
                    symbol=position.symbol,
                    old_tp_order_id=position.tp_order_id,
                )
                position.last_poc_migration = now
                position.tp_level = poc
            except Exception as e:
                self.logger.error(f"❌ Failed to migrate POC for {position.trade_id}: {e}")

    # =========================================================
    # DRAIN PHASE METHODS (Interface compatibility)
    # =========================================================

    async def trigger_soft_exits(self):
        """Immediately narrow TPs for all open positions (Optimistic Stage)."""
        for position in self.croupier.get_open_positions():
            await self._execute_soft_exit(position, "Session Drain (Optimistic)")

    async def trigger_defensive_exits(self):
        """Phase 2: Move TPs to Breakeven and tighten SLs."""
        for position in self.croupier.get_open_positions():
            await self._execute_defensive_exit(position)

    async def trigger_aggressive_exits(self, fraction: float = 0.2):
        """Phase 3: Force close weakest positions."""
        positions = self.croupier.get_open_positions()
        positions.sort(key=lambda p: p.bars_held, reverse=True)
        target_count = max(1, int(len(positions) * fraction)) if positions else 0

        self.logger.warning(f"🔥 Aggressive Drain: Targeting {target_count} stale/weak positions.")

        for i, position in enumerate(positions):
            if i < target_count:
                try:
                    await self.croupier.close_position(position.trade_id, exit_reason="DRAIN_AGGRESSIVE")
                except Exception as e:
                    self.logger.error(f"❌ Failed aggressive close for {position.symbol}: {e}")
            else:
                if not getattr(position, "defensive_exit_triggered", False):
                    await self._execute_defensive_exit(position)

    async def apply_dynamic_exit(self, position: OpenPosition, phase: str):
        """
        Apply dynamic exit strategy based on drain phase.
        Phases: OPTIMISTIC → DEFENSIVE → AGGRESSIVE → PANIC
        """
        async with self._position_locks[position.trade_id]:
            if getattr(position, "drain_phase", None) == phase:
                return

            self.logger.info(f"📉 Applying Dynamic Exit ({phase}) for {position.trade_id}")
            position.drain_phase = phase

            try:
                new_tp = None
                min_profit_dist = position.entry_price * 0.0009

                if phase == "OPTIMISTIC":
                    current_diff = abs(position.tp_level - position.entry_price)
                    narrowed_diff = max(current_diff * config.SOFT_EXIT_TP_MULT, min_profit_dist)
                    if position.side == "LONG":
                        new_tp = position.entry_price + narrowed_diff
                    else:
                        new_tp = position.entry_price - narrowed_diff

                elif phase == "DEFENSIVE":
                    if position.side == "LONG":
                        new_tp = position.entry_price + min_profit_dist
                    else:
                        new_tp = position.entry_price - min_profit_dist

                elif phase == "AGGRESSIVE":
                    if position.side == "LONG":
                        new_tp = position.entry_price + (min_profit_dist * 0.5)
                    else:
                        new_tp = position.entry_price - (min_profit_dist * 0.5)

                elif phase == "PANIC":
                    self.logger.warning(f"🚨 PANIC Exit for {position.trade_id} | Force Closing")
                    await self.croupier.close_position(position.trade_id, exit_reason="DRAIN_PANIC")
                    return

                if new_tp:
                    await self.croupier.modify_tp(
                        trade_id=position.trade_id,
                        new_tp_price=new_tp,
                        symbol=position.symbol,
                        old_tp_order_id=position.tp_order_id,
                    )

            except Exception as e:
                if "-2021" in str(e) or "immediately trigger" in str(e):
                    self.logger.warning(
                        f"⚡ {phase} TP would immediately trigger for {position.trade_id} | Escalating to market close"
                    )
                    try:
                        await self.croupier.close_position(position.trade_id, exit_reason=f"DRAIN_{phase}_ESCALATION")
                    except Exception as close_err:
                        self.logger.error(f"❌ Escalation close failed for {position.trade_id}: {close_err!r}")
                else:
                    self.logger.error(f"❌ Failed to apply {phase} exit: {e!r}")

    # =========================================================
    # HELPER METHODS
    # =========================================================

    def _calc_pnl_pct(self, position: OpenPosition, current_price: float) -> float:
        """Calculate unrealized PnL percentage."""
        if position.side == "LONG":
            return (current_price - position.entry_price) / position.entry_price
        else:
            return (position.entry_price - current_price) / position.entry_price

    async def _audit_log_layers(self, position: OpenPosition, event: TickEvent, current_price: float, elapsed: float):
        """In audit mode, log what each layer WOULD have done without executing."""
        # Layer 4: Thesis Invalidation
        invalidation_reason = self._check_thesis_invalidation(position, event, current_price, elapsed)
        if invalidation_reason:
            self.logger.warning(f"🔍 [AUDIT] Would close {position.trade_id} via {invalidation_reason}")

        # Layer 3: SCE (Shadow Analysis)
        if not position.scaled_out:
            mex = self._check_micro_exhaustion(position)
            if mex:
                self.logger.debug(f"🔍 [AUDIT] SCE: MEX would trigger for {position.trade_id}")

            cfi = await self._check_counter_flow_invalidation(position, current_price)
            if cfi:
                self.logger.debug(f"🔍 [AUDIT] SCE: CFI would trigger for {position.trade_id} ({cfi})")

        # Layer 2: Shadow Protection
        profit_pct = self._calc_pnl_pct(position, current_price)
        if profit_pct >= config.BREAKEVEN_ACTIVATION_PCT:
            self.logger.debug(f"🔍 [AUDIT] Would activate breakeven for {position.trade_id} @ {profit_pct:.2%}")
        if profit_pct >= config.TRAILING_STOP_EXPANSION_THRESHOLD_PCT:
            self.logger.debug(f"🔍 [AUDIT] Would activate Winner Catcher for {position.trade_id} @ {profit_pct:.2%}")

    async def _execute_soft_exit(self, position: OpenPosition, reason: str):
        """Legacy wrapper: apply OPTIMISTIC drain phase."""
        await self.apply_dynamic_exit(position, "OPTIMISTIC")

    async def _execute_defensive_exit(self, position: OpenPosition):
        """Move TP to Breakeven, SL to -0.5%."""
        if getattr(position, "defensive_exit_triggered", False):
            return

        self.logger.info(f"🛡️ Defensive Exit for {position.trade_id} | Targeting Breakeven")
        position.defensive_exit_triggered = True

        try:
            if position.side == "LONG":
                new_tp = position.entry_price * 1.002
                max_loss_price = position.entry_price * 0.995
                current_sl = position.sl_level
                new_sl = max(max_loss_price, current_sl) if current_sl < max_loss_price else current_sl
                if position.entry_price < (position.last_price or 0):
                    new_sl = max(new_sl, position.entry_price * 1.001)
            else:
                new_tp = position.entry_price * 0.998
                max_loss_price = position.entry_price * 1.005
                current_sl = position.sl_level
                new_sl = min(max_loss_price, current_sl) if current_sl > max_loss_price else current_sl
                if position.entry_price > (position.last_price or 0) and (position.last_price or 0) > 0:
                    new_sl = min(new_sl, position.entry_price * 0.999)

            await self.croupier.modify_tp(
                trade_id=position.trade_id,
                new_tp_price=new_tp,
                symbol=position.symbol,
                old_tp_order_id=position.tp_order_id,
            )

            update_sl = False
            if position.side == "LONG" and new_sl > position.sl_level:
                update_sl = True
            elif position.side == "SHORT" and new_sl < position.sl_level:
                update_sl = True

            if update_sl:
                await self._update_sl(position, new_sl, "Defensive Drain (Active)")

        except Exception as e:
            self.logger.error(f"❌ Failed to apply defensive exit: {e}")

    async def _update_sl(self, position: OpenPosition, new_sl: float, reason: str):
        """Helper to physically update SL order on exchange."""
        self.logger.info(f"🔄 Updating Physical SL for {position.trade_id} -> {new_sl:.6f} ({reason})")
        try:
            await self.croupier.modify_sl(
                trade_id=position.trade_id,
                new_sl_price=new_sl,
                symbol=position.symbol,
                old_sl_order_id=position.sl_order_id,
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to update physical SL: {e}")
