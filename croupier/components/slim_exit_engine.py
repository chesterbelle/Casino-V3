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

        # Load asset profiles from config
        self.profiles = getattr(config, "ASSET_EXIT_PROFILES", {})

        # Pre-normalize asset lists for robust matching
        for name, profile in self.profiles.items():
            if "assets" in profile:
                profile["normalized_assets"] = [normalize_symbol(a) for a in profile["assets"]]

        self.logger.info(f"🚀 SlimExitEngine initialized with {len(self.profiles)} asset profiles.")

    def _get_profile(self, symbol: str) -> Dict[str, Any]:
        """Matches a symbol to its market personality profile."""
        symbol_norm = normalize_symbol(symbol)
        for name, profile in self.profiles.items():
            if name == "DEFAULT":
                continue
            if symbol_norm in profile.get("normalized_assets", []):
                return profile

        # Fallback to DEFAULT with Error Logging
        self.logger.error(
            f"⚠️ [CONFIG-ERROR] Symbol {symbol} ({symbol_norm}) has no matching Exit Profile! Using DISABLED DEFAULT."
        )
        return self.profiles.get("DEFAULT", {})

    async def on_tick(self, event: TickEvent):
        """Main tactical loop: Process pillars for active positions."""
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions[:]:
            if position.status != "OPEN" or position.trade_id in self._pending_terminations:
                continue

            profile = self._get_profile(position.symbol)
            current_price = event.price
            elapsed = event.timestamp - position.timestamp

            # Skip if within patience lock grace period
            if elapsed < getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0):
                continue

            # ---------------------------------------------------------
            # PILAR 4: DELTA INVALIDATION (Toxic Flow)
            # ---------------------------------------------------------
            if profile["delta_invalidation"]["enabled"]:
                if await self._check_delta_invalidation(position, profile):
                    continue

            # ---------------------------------------------------------
            # PILAR 1: SCALE OUT (Partial Profit)
            # ---------------------------------------------------------
            if profile["scale_out"]["enabled"] and not getattr(position, "scaled_out", False):
                if await self._check_scale_out(position, current_price, profile):
                    continue

            # ---------------------------------------------------------
            # PILAR 2: BREAK EVEN (Risk Neutralization)
            # ---------------------------------------------------------
            if profile["break_even"]["enabled"]:
                await self._check_break_even(position, current_price, profile)

            # ---------------------------------------------------------
            # PILAR 3: TRAILING STOP (Trend Capture)
            # ---------------------------------------------------------
            if profile["trailing"]["enabled"]:
                await self._check_trailing(position, current_price, profile)

    async def _check_delta_invalidation(self, position: OpenPosition, profile: Dict) -> bool:
        """Exit if toxic flow REVERSAL detected post-entry (Relative Delta Z).

        Design rationale:
        - Absorption LONG enters when Z is very negative (sellers being absorbed).
        - Absolute Z check would fire immediately against the entry signal.
        - Instead, we measure how much Z has CHANGED since entry:
          - LONG: If Z rises far above entry_z → buyers exhausted, flow reversed to selling.
          - SHORT: If Z drops far below entry_z → sellers exhausted, flow reversed to buying.
        """
        if not self.croupier.context_registry:
            return False

        entry_z = getattr(position, "entry_z", None)
        if entry_z is None or entry_z == 0.0:
            return False  # No baseline → can't measure delta

        _, _, current_z = self.croupier.context_registry.get_micro_state(position.symbol)
        threshold = profile["delta_invalidation"]["z_score_threshold"]

        # Delta Z = how much the flow state changed since we entered
        delta_z = current_z - entry_z

        triggered = False
        if position.side == "LONG" and delta_z > threshold:
            # Flow was bearish at entry (Z negative), now shifted bullish (Z rising).
            # Counter-intuitive but correct: absorption LONG profits when selling pressure
            # continues then exhausts. If Z jumps positive, the absorption thesis is broken.
            triggered = True
        elif position.side == "SHORT" and delta_z < -threshold:
            # Flow was bullish at entry (Z positive), now shifted bearish.
            triggered = True

        if triggered:
            self.logger.warning(
                f"🚨 [SLIM-DI] Flow Reversal (entry_z={entry_z:.1f}, now={current_z:.1f}, "
                f"Δ={delta_z:+.1f}, thresh={threshold}) for {position.trade_id} | Closing (LIMIT)"
            )
            self._pending_terminations.add(position.trade_id)
            asyncio.create_task(self._execute_limit_close(position, "DI_TOXIC_FLOW"))
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

    async def _check_break_even(self, position: OpenPosition, price: float, profile: Dict):
        """Move SL to entry after reaching target."""
        if getattr(position, "be_activated", False) or not getattr(position, "entry_atr", 0):
            return

        dist = abs(price - position.entry_price)
        activation_dist = position.entry_atr * profile["break_even"]["at_atr"]

        if dist >= activation_dist:
            self.logger.info(f"🛡️ [SLIM-BE] Activating Break-Even for {position.trade_id}")
            position.be_activated = True
            # New SL is entry price (fees covered by being Maker on exit)
            new_sl = position.entry_price
            asyncio.create_task(
                self.croupier.modify_sl(trade_id=position.trade_id, new_sl_price=new_sl, symbol=position.symbol)
            )

    async def _check_trailing(self, position: OpenPosition, price: float, profile: Dict):
        """Dynamic ATR-based trailing stop."""
        if not getattr(position, "entry_atr", 0):
            return

        # Phase 1301: Directional profit check (Fix: abs() was causing activation on losses)
        if position.side == "LONG":
            profit_dist = price - position.entry_price
        else:
            profit_dist = position.entry_price - price

        activation_dist = position.entry_atr * profile["trailing"]["activation_atr"]

        if profit_dist < activation_dist:
            return

        trail_dist = position.entry_atr * profile["trailing"]["distance_atr"]
        shadow_sl = getattr(position, "shadow_sl_level", None)

        if position.side == "LONG":
            new_sl = price - trail_dist
            # Guard: Never trail backward, and never below entry if risk is off
            if shadow_sl is not None:
                new_sl = max(new_sl, shadow_sl)
            if getattr(position, "be_activated", False) or getattr(position, "scaled_out", False):
                new_sl = max(new_sl, position.entry_price)

            if shadow_sl is None or new_sl > shadow_sl:
                position.shadow_sl_level = new_sl
        else:
            new_sl = price + trail_dist
            # Guard: Never trail backward, and never above entry if risk is off
            if shadow_sl is not None and shadow_sl != 0:
                new_sl = min(new_sl, shadow_sl)
            if getattr(position, "be_activated", False) or getattr(position, "scaled_out", False):
                new_sl = min(new_sl, position.entry_price)

            if shadow_sl is None or new_sl < shadow_sl or shadow_sl == 0:
                position.shadow_sl_level = new_sl

        # If shadow level hit, close with LIMIT
        shadow_sl = getattr(position, "shadow_sl_level", None)
        if shadow_sl:
            hit = False
            if position.side == "LONG" and price <= shadow_sl:
                hit = True
            elif position.side == "SHORT" and price >= shadow_sl:
                hit = True

            if hit:
                self.logger.warning(f"📉 [SLIM-TS] Trailing Stop triggered for {position.trade_id} @ {price}")
                self._pending_terminations.add(position.trade_id)
                asyncio.create_task(self._execute_limit_close(position, "TS_DYNAMIC_FOLLOW"))

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
            if position.trade_id in self._pending_terminations:
                self._pending_terminations.remove(position.trade_id)

    async def on_candle(self, event: CandleEvent):
        """Time-based maintenance (optional)."""
        pass
