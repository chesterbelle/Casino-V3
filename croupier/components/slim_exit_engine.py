"""
SlimExitEngine (V10.3) — Universal Tactical Execution
======================================================

A minimalist, high-performance exit engine that replaces the layered
theory with 4 professional universal pillars:
1. Break Even (Risk Neutralization)
2. Delta Invalidation (Toxic Flow Protection via Micro-Z Reversal)
3. Time Decay (Max Stagnation Time Protection)
4. Maker-Join LIMIT Exit Execution (Slippage and Fee Optimization)

No asset-specific profiles or curve-fitting.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from config import trading as config
from core.events import CandleEvent, TickEvent
from core.portfolio.position_tracker import OpenPosition
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


class SlimExitEngine:
    """
    Universal Exit Engine.
    Executes standard, non-profile-specific tactical exits using Limit orders.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logging.getLogger("SlimExitEngine")
        self._pending_terminations: set = set()

        # Pillar state tracking: trade_id -> {breakeven_price, breakeven_activated}
        self._pillar_state: Dict[str, Dict[str, Any]] = {}

        # Load universal exit rules from config
        self.rules = getattr(config, "UNIVERSAL_EXIT_RULES", {})

        self.logger.info("🚀 SlimExitEngine initialized with universal exit rules.")

    async def on_tick(self, event: TickEvent):
        """Main tactical loop: Process all active universal pillars for active positions."""
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions:
            if position.status != "OPEN" or position.trade_id in self._pending_terminations:
                continue

            current_price = event.price
            elapsed = event.timestamp - position.timestamp

            # Skip if within patience lock grace period
            if elapsed < getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0):
                continue

            # ---------------------------------------------------------
            # PILAR 1: TIME DECAY (Max Holding Time)
            # ---------------------------------------------------------
            time_decay_rules = self.rules.get("time_decay", {})
            if time_decay_rules.get("enabled", False):
                if self._check_time_decay(position, elapsed):
                    continue

            # ---------------------------------------------------------
            # PILAR 2: BREAK EVEN (Risk Neutralization)
            # ---------------------------------------------------------
            be_rules = self.rules.get("break_even", {})
            if be_rules.get("enabled", False):
                if self._check_break_even(position, current_price):
                    continue

            # ---------------------------------------------------------
            # PILAR 3: MICRO-Z REVERSAL (Flow Invalidation)
            # ---------------------------------------------------------
            mz_rules = self.rules.get("micro_z_reversal", {})
            if mz_rules.get("enabled", False):
                if self._check_micro_z_reversal(position):
                    continue

    def _check_micro_z_reversal(self, position: OpenPosition) -> bool:
        entry_z = getattr(position, "entry_z", None)
        if entry_z is None or entry_z == 0.0:
            return False

        _, _, current_z = self.croupier.context_registry.get_micro_state(position.symbol)
        threshold = self.rules.get("micro_z_reversal", {}).get("threshold", 4.0)

        delta_z = current_z - entry_z

        if abs(delta_z) > threshold:
            self.logger.warning(
                f"🚨 [SLIM-MZ] Micro-Z Reversal (entry_z={entry_z:.1f}, now={current_z:.1f}, "
                f"Δ={delta_z:+.1f}, thresh={threshold}) for {position.trade_id} | Closing (LIMIT)"
            )
            self._pending_terminations.add(position.trade_id)
            asyncio.create_task(self._execute_limit_close(position, "MZ_REVERSAL"))
            return True
        return False

    def _check_time_decay(self, position: OpenPosition, elapsed: float) -> bool:
        """Time Decay — close if max holding time exceeded."""
        max_hold = self.rules.get("time_decay", {}).get("max_hold_seconds", 360)
        if elapsed > max_hold:
            self.logger.info(
                f"⏳ [SLIM-TIME] Max hold reached ({elapsed:.0f}s > {max_hold}s) for {position.trade_id}. Closing."
            )
            self._pending_terminations.add(position.trade_id)
            asyncio.create_task(self._execute_limit_close(position, "TIME_DECAY"))
            return True
        return False

    def _check_break_even(self, position: OpenPosition, price: float) -> bool:
        """Break Even — move SL to entry + fees when a percentage of TP reached."""
        trade_id = position.trade_id
        state = self._pillar_state.get(trade_id, {})

        price_above_entry = price > position.entry_price if position.side == "LONG" else price < position.entry_price

        if not state.get("breakeven_activated", False):
            # Calculate current PnL as fraction of entry price
            if position.entry_price <= 0:
                return False
            pnl_pct = abs(price - position.entry_price) / position.entry_price
            # Estimate TP target from position tp_level vs entry_price (fallback: 1%)
            tp_pct = 0.01
            if position.entry_price > 0 and getattr(position, "tp_level", 0.0) > 0.0:
                tp_pct = abs(position.tp_level - position.entry_price) / position.entry_price
            trigger_pct = self.rules.get("break_even", {}).get("trigger_pct", 0.5)
            threshold = tp_pct * trigger_pct

            if price_above_entry and pnl_pct >= threshold:
                fee_friction = self.rules.get("break_even", {}).get("fee_friction", 0.0009)
                if position.side == "LONG":
                    breakeven_price = position.entry_price * (1 + fee_friction)
                else:
                    breakeven_price = position.entry_price * (1 - fee_friction)

                self._pillar_state[trade_id] = {
                    "breakeven_activated": True,
                    "breakeven_price": breakeven_price,
                }
                state = self._pillar_state[trade_id]
                self.logger.info(
                    f"⚖️ [SLIM-BE] Break-even activated for {trade_id} @ {breakeven_price:.2f} "
                    f"(pnl={pnl_pct:.3%} >= {threshold:.3%})"
                )

        if state.get("breakeven_activated", False):
            be_price = state["breakeven_price"]
            hit_be = (position.side == "LONG" and price <= be_price) or (position.side == "SHORT" and price >= be_price)
            if hit_be:
                self.logger.info(f"⚖️ [SLIM-BE] Price hit breakeven ({be_price:.2f}) for {trade_id}. Closing.")
                self._pending_terminations.add(trade_id)
                asyncio.create_task(self._execute_limit_close(position, "BREAK_EVEN"))
                return True

        return False

    async def _execute_limit_close(self, position: OpenPosition, reason: str):
        """
        Executes a closure using a LIMIT order to capture Maker rebates
        and eliminate slippage.
        """
        try:
            self.logger.info(f"🎯 [MAKER-EXIT] Sniping exit for {position.trade_id} | Reason: {reason}")
            await self.croupier.close_position(position.trade_id, exit_reason=reason, prefer_maker=True)

        except Exception as e:
            self.logger.error(f"❌ SlimExitEngine closure failed: {e}")
        finally:
            self._pillar_state.pop(position.trade_id, None)
            if position.trade_id in self._pending_terminations:
                self._pending_terminations.remove(position.trade_id)

    async def on_candle(self, event: CandleEvent):
        """Time-based maintenance (optional)."""
        pass
