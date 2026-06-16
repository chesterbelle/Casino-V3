"""
SlimExitEngine (V10.2) — Asset-Specific Tactical Execution
==========================================================

A minimalist, high-performance exit engine that replaces the layered
theory with 4 professional pillars:
1. Scale Out (Partial Profit)
2. Break Even (Risk Neutralization)
3. Trailing Stop (Trend Capture)
4. Delta Invalidation (Toxic Flow Protection)

Key Feature: 100% Maker-Join execution strategy using LIMIT orders.
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
    Asset-Specific Exit Engine.
    Matches symbols to profiles (BLUE_CHIP, LIQUID_ALT, HIGH_BETA)
    and executes tactical exits using Limit orders.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logging.getLogger("SlimExitEngine")
        self._pending_terminations: set = set()
        self._profile_cache: Dict[str, Dict[str, Any]] = {}

        # Pillar 2 & 3 tracking: trade_id -> {breakeven_price, trailing_high, trailing_activated}
        self._pillar_state: Dict[str, Dict[str, float]] = {}

        # Load asset profiles from config
        self.profiles = getattr(config, "ASSET_EXIT_PROFILES", {})

        # Pre-normalize asset lists for robust matching
        for name, profile in self.profiles.items():
            if "assets" in profile:
                profile["normalized_assets"] = [normalize_symbol(a) for a in profile["assets"]]
                for asset_norm in profile["normalized_assets"]:
                    self._profile_cache[asset_norm] = profile

        self.logger.info(f"🚀 SlimExitEngine initialized with {len(self.profiles)} asset profiles.")

    def _get_profile(self, symbol: str) -> Dict[str, Any]:
        """Matches a symbol to its market personality profile. O(1) via pre-built cache."""
        symbol_norm = normalize_symbol(symbol)
        profile = self._profile_cache.get(symbol_norm)
        if profile:
            return profile

        self.logger.error(
            f"⚠️ [CONFIG-ERROR] Symbol {symbol} ({symbol_norm}) has no matching Exit Profile! Using DISABLED DEFAULT."
        )
        default = self.profiles.get("DEFAULT", {})
        self._profile_cache[symbol_norm] = default
        return default

    async def on_tick(self, event: TickEvent):
        """Main tactical loop: Process all 4 pillars for active positions."""
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions:
            if position.status != "OPEN" or position.trade_id in self._pending_terminations:
                continue

            profile = self._get_profile(position.symbol)
            current_price = event.price
            elapsed = event.timestamp - position.timestamp

            # Skip if within patience lock grace period
            if elapsed < getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0):
                continue

            # ---------------------------------------------------------
            # PILAR 2: TIME DECAY (Max Holding Time)
            # ---------------------------------------------------------
            if profile["time_decay"]["enabled"]:
                if self._check_time_decay(position, profile, elapsed):
                    continue

            # ---------------------------------------------------------
            # PILAR 3: BREAK EVEN (Risk Neutralization)
            # ---------------------------------------------------------
            if profile["break_even"]["enabled"]:
                if self._check_break_even(position, current_price, profile):
                    continue

            # ---------------------------------------------------------
            # PILAR 4: TRAILING STOP (Trend Capture)
            # ---------------------------------------------------------
            if profile["trailing"]["enabled"]:
                if self._check_trailing(position, current_price, profile, event):
                    continue

            # ---------------------------------------------------------
            # PILAR 5: MICRO-Z REVERSAL (Flow Invalidation)
            # ---------------------------------------------------------
            if profile["micro_z_reversal"]["enabled"]:
                if self._check_micro_z_reversal(position, profile):
                    continue

            # ---------------------------------------------------------
            # PILAR 1: SCALE OUT (Partial Profit)
            # ---------------------------------------------------------
            if profile["scale_out"]["enabled"] and not getattr(position, "scaled_out", False):
                if await self._check_scale_out(position, current_price, profile):
                    continue

    def _check_micro_z_reversal(self, position: OpenPosition, profile: Dict) -> bool:
        entry_z = getattr(position, "entry_z", None)
        if entry_z is None or entry_z == 0.0:
            return False

        _, _, current_z = self.croupier.context_registry.get_micro_state(position.symbol)
        threshold = profile["micro_z_reversal"]["threshold"]

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

    def _check_time_decay(self, position: OpenPosition, profile: Dict, elapsed: float) -> bool:
        """Pillar 5: Time Decay — close if max holding time exceeded."""
        max_hold = profile["time_decay"]["max_hold_seconds"]
        if elapsed > max_hold:
            self.logger.info(
                f"⏳ [SLIM-TIME] Max hold reached ({elapsed:.0f}s > {max_hold}s) for {position.trade_id}. Closing."
            )
            self._pending_terminations.add(position.trade_id)
            asyncio.create_task(self._execute_limit_close(position, "TIME_DECAY"))
            return True
        return False

    def _check_break_even(self, position: OpenPosition, price: float, profile: Dict) -> bool:
        """Pillar 2: Break Even — move SL to entry + fees when 50% of TP reached."""
        trade_id = position.trade_id
        state = self._pillar_state.get(trade_id, {})

        price_above_entry = price > position.entry_price if position.side == "LONG" else price < position.entry_price

        if not state.get("breakeven_activated", False):
            # Calculate current PnL as fraction of entry price
            if position.entry_price <= 0:
                return False
            pnl_pct = abs(price - position.entry_price) / position.entry_price
            # Estimate TP target from position metadata (fallback: 1%)
            tp_pct = getattr(position, "tp_pct", 0.01)
            trigger_pct = profile["break_even"]["trigger_pct"]
            threshold = tp_pct * trigger_pct

            if price_above_entry and pnl_pct >= threshold:
                fee_friction = profile["break_even"]["fee_friction"]
                if position.side == "LONG":
                    breakeven_price = position.entry_price * (1 + fee_friction)
                else:
                    breakeven_price = position.entry_price * (1 - fee_friction)

                self._pillar_state[trade_id] = {
                    "breakeven_activated": True,
                    "breakeven_price": breakeven_price,
                    "trailing_high": float(position.entry_price),
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

    def _check_trailing(self, position: OpenPosition, price: float, profile: Dict, event: TickEvent) -> bool:
        """Pillar 3: Trailing Stop — trail behind price after break-even."""
        trade_id = position.trade_id
        state = self._pillar_state.get(trade_id)
        if not state or not state.get("breakeven_activated", False):
            return False

        # Update trailing high/low
        if position.side == "LONG":
            if price > state.get("trailing_high", 0.0):
                state["trailing_high"] = price
        else:
            if price < state.get("trailing_low", float("inf")):
                state["trailing_low"] = price

        # Compute trailing stop distance
        atr = position.entry_atr if position.entry_atr and position.entry_atr > 0 else 0.0
        if atr <= 0:
            ctx_atr = self.croupier.context_registry.atrs.get(position.symbol, {})
            atr = ctx_atr.get("short", 0.0) if ctx_atr else 0.0
        if atr <= 0:
            return False

        atr_mult = profile["trailing"]["atr_multiplier"]
        trail_distance = atr * atr_mult
        be_price = state.get("breakeven_price", position.entry_price)

        if position.side == "LONG":
            trail_stop = max(state["trailing_high"] - trail_distance, be_price)
            if price <= trail_stop:
                self.logger.info(f"🎯 [SLIM-TS] Trailing stop hit ({trail_stop:.2f}) for {trade_id}. Closing.")
                self._pending_terminations.add(trade_id)
                asyncio.create_task(self._execute_limit_close(position, "TRAILING_STOP"))
                return True
        else:
            trail_stop = min(state["trailing_low"] + trail_distance, be_price)
            if price >= trail_stop:
                self.logger.info(f"🎯 [SLIM-TS] Trailing stop hit ({trail_stop:.2f}) for {trade_id}. Closing.")
                self._pending_terminations.add(trade_id)
                asyncio.create_task(self._execute_limit_close(position, "TRAILING_STOP"))
                return True

        return False

    async def _check_scale_out(self, position: OpenPosition, price: float, profile: Dict) -> bool:
        """Partial exit at ATR-based target."""
        if not position.entry_atr or position.entry_atr <= 0:
            return False

        dist = abs(price - position.entry_price)
        target_dist = position.entry_atr * profile["scale_out"]["at_atr"]

        if dist >= target_dist:
            fraction = profile["scale_out"]["fraction"]
            self.logger.info(f"⚖️ [SLIM-SO] Scaling out {fraction:.0%} for {position.trade_id}")
            # Mark as scaled out to prevent repeat
            position.scaled_out = True
            asyncio.create_task(
                self.croupier.scale_out_structural(position.trade_id, fraction=fraction, reason="SO_TARGET_REACHED")
            )
            return True
        return False

    async def _execute_limit_close(self, position: OpenPosition, reason: str):
        """
        Executes a closure using a LIMIT order to capture Maker rebates
        and eliminate slippage.
        """
        # Phase 1202: Maker-Join Logic
        # We don't use Croupier.close_position because it defaults to Market.
        # We use a custom flow to the OrderExecutor.
        try:
            self.logger.info(f"🎯 [MAKER-EXIT] Sniping exit for {position.trade_id} | Reason: {reason}")

            # This will eventually use the ExecutionFunnel,
            # for now we call croupier with a specific flag or a new method.
            # Rationale: Direct use of Croupier.close_position(exit_reason=reason)
            # but we need to ensure OrderManager treats it as LIMIT.
            # For Phase 2, we use Croupier.close_position but tag it.
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
