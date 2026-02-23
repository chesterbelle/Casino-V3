"""
Exit Manager - Advanced Exit Strategies.

Handles dynamic exit logic beyond simple TP/SL:
- Signal Reversal: Close if strong opposite signal detected
- Trailing Stop: Dynamic SL tracking price
- Breakeven: Move SL to entry after profit threshold
- Time-Based: Enforce max hold time

Author: Casino V3 Team
Version: 1.0.0
"""

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

import config.trading as config
from core.events import AggregatedSignalEvent, CandleEvent, TickEvent
from core.portfolio.position_tracker import OpenPosition
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


class ExitManager:
    """
    Manages dynamic exit strategies for open positions.
    """

    def __init__(self, croupier: "Croupier"):
        """
        Initialize ExitManager.

        Args:
            croupier: Croupier instance for executing exits/modifications
        """
        self.croupier = croupier
        self.logger = logging.getLogger("ExitManager")
        self._position_locks = defaultdict(asyncio.Lock)
        self.logger.info("✅ ExitManager initialized")

    async def on_signal(self, event: AggregatedSignalEvent):
        """
        Handle aggregated signal for potential reversals.
        """
        if not config.SIGNAL_REVERSAL_ENABLED:
            return

        # Check for reversals on all open positions
        for position in self.croupier.get_open_positions():
            # Phase 243: Skip if closing or shutdown
            if position.status == "CLOSING" or self.croupier.error_handler.shutdown_mode:
                continue
            await self._check_signal_reversal(position, event)

    async def on_candle(self, event: CandleEvent):
        """
        Handle candle update for time exits.
        Phase 241: Breakeven and trailing migrated to on_tick for zero-lag shadow tracking.
        """
        current_price = event.close
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions[:]:
            # Phase 243: Skip positions already in closure or if reactor is shutting down
            if position.status == "CLOSING" or self.croupier.error_handler.shutdown_mode:
                continue

            self.logger.debug(f"⚡ Processing Candle Exit Logic for {position.symbol} | Price: {current_price}")
            await self._check_time_exit(position, event)

    async def on_tick(self, event: TickEvent):
        """
        Phase 241: High-Frequency Shadow Trailing Stops and Breakeven evaluation.
        Evaluates current price against in-memory SL without updating physical exchange order.
        """
        current_price = event.price
        symbol_norm = normalize_symbol(event.symbol)

        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)
        for position in positions[:]:
            # Phase 243: Skip positions already in closure or if reactor is shutting down
            if position.status == "CLOSING" or self.croupier.error_handler.shutdown_mode:
                continue
            # 1. Trigger Shadow SL Market Close (Airlock Bypass)
            if position.shadow_sl_level is not None:
                if position.side == "LONG" and current_price <= position.shadow_sl_level:
                    self.logger.warning(
                        f"🚨 Shadow SL Triggered for {position.trade_id} @ {current_price:.6f} (Threshold: {position.shadow_sl_level:.6f})"
                    )
                    asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason="SHADOW_SL"))
                    position.shadow_sl_level = None  # Prevent multi-triggers
                    continue
                elif position.side == "SHORT" and current_price >= position.shadow_sl_level:
                    self.logger.warning(
                        f"🚨 Shadow SL Triggered for {position.trade_id} @ {current_price:.6f} (Threshold: {position.shadow_sl_level:.6f})"
                    )
                    asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason="SHADOW_SL"))
                    position.shadow_sl_level = None  # Prevent multi-triggers
                    continue

            # 2. Update Shadow Breakeven
            if config.BREAKEVEN_ENABLED:
                await self._check_shadow_breakeven(position, current_price)

            # 3. Update Shadow Trailing Stop
            if config.TRAILING_STOP_ENABLED:
                await self._check_shadow_trailing_stop(position, current_price)

    async def _check_signal_reversal(self, position: OpenPosition, signal: AggregatedSignalEvent):
        """
        Close position if strong opposite signal detected.
        """
        # Ignore signals for other symbols
        if normalize_symbol(signal.symbol) != normalize_symbol(position.symbol):
            return

        # Ignore weak signals
        if signal.confidence < config.SIGNAL_REVERSAL_THRESHOLD:
            return

        # Check for opposition
        is_reversal = False
        if position.side == "LONG" and signal.side == "SHORT":
            is_reversal = True
        elif position.side == "SHORT" and signal.side == "LONG":
            is_reversal = True

        if is_reversal:
            self.logger.info(
                f"🔄 Signal Reversal Detected for {position.trade_id} | "
                f"Position: {position.side} | Signal: {signal.side} ({signal.confidence:.2f})"
            )
            try:
                await self.croupier.close_position(position.trade_id)
                self.logger.info(f"✅ Position {position.trade_id} closed due to signal reversal")
            except Exception as e:
                self.logger.error(f"❌ Failed to close position on reversal: {e}")

    async def trigger_soft_exits(self):
        """Immediately narrow TPs for all open positions (Optimistic Stage)."""
        for position in self.croupier.get_open_positions():
            await self._execute_soft_exit(position, "Session Drain (Optimistic)")

    async def trigger_defensive_exits(self):
        """Phase 2: Move TPs to Breakeven and tighten SLs."""
        for position in self.croupier.get_open_positions():
            await self._execute_defensive_exit(position)

    async def trigger_aggressive_exits(self, fraction: float = 0.2):
        """Phase 3: Force close weakest positions or tighten SL to market."""
        positions = self.croupier.get_open_positions()
        # Sort by PnL (worst first) to dump bags first
        # Note: We need current price which isn't readily available in position obj without lookup.
        # We'll use bars_held as a proxy for "stale" positions if PnL is unknown.
        positions.sort(key=lambda p: p.bars_held, reverse=True)

        target_count = max(1, int(len(positions) * fraction)) if positions else 0

        self.logger.warning(f"🔥 Aggressive Drain: Targeting {target_count} stale/weak positions.")

        for i, position in enumerate(positions):
            if i < target_count:
                # Force close
                try:
                    self.logger.info(f"💀 Force Closing {position.symbol} (Aggressive Drain)")
                    await self.croupier.close_position(position.trade_id, exit_reason="DRAIN_AGGRESSIVE")
                except Exception as e:
                    self.logger.error(f"❌ Failed aggressive close for {position.symbol}: {e}")
            else:
                # For the rest, apply SUPER tight trailing logic or market SL?
                # For now, just ensure defensive exit is applied
                if not getattr(position, "defensive_exit_triggered", False):
                    await self._execute_defensive_exit(position)

    async def _execute_defensive_exit(self, position: OpenPosition):
        """Move TP to Breakeven, SL to -0.5% (or 50% risk)."""
        if getattr(position, "defensive_exit_triggered", False):
            return

        self.logger.info(f"🛡️ Defensive Exit for {position.trade_id} | Targeting Breakeven")
        position.defensive_exit_triggered = True

        try:
            # 1. Move TP to Entry (Breakeven + Fees cover)
            if position.side == "LONG":
                new_tp = position.entry_price * 1.002
                # Phase 210: Active Defense - Tighten SL to -0.5% MAX
                max_loss_price = position.entry_price * 0.995
                current_sl = position.sl_level
                # If current SL is lower (worse) than max loss, tighten it.
                if current_sl < max_loss_price:
                    new_sl = max_loss_price
                else:
                    new_sl = current_sl

                # If position is profitable, move SL to Breakeven
                # (We rely on _check_breakeven to handle this normally, but force it here for drain)
                if position.entry_price < (position.last_price or 0):
                    new_sl = max(new_sl, position.entry_price * 1.001)

            else:
                new_tp = position.entry_price * 0.998
                # Phase 210: Active Defense - Tighten SL to -0.5% MAX
                max_loss_price = position.entry_price * 1.005
                current_sl = position.sl_level
                # If current SL is higher (worse) than max loss, tighten it.
                if current_sl > max_loss_price:
                    new_sl = max_loss_price
                else:
                    new_sl = current_sl

                # If profitable (Entry > Current), move SL to Breakeven
                if position.entry_price > (position.last_price or 0) and (position.last_price or 0) > 0:
                    new_sl = min(new_sl, position.entry_price * 0.999)

            # Update TP
            await self.croupier.modify_tp(
                trade_id=position.trade_id,
                new_tp_price=new_tp,
                symbol=position.symbol,
                old_tp_order_id=position.tp_order_id,
            )

            # Update SL (Only if tighter)
            update_sl = False
            if position.side == "LONG" and new_sl > position.sl_level:
                update_sl = True
            elif position.side == "SHORT" and new_sl < position.sl_level:
                update_sl = True

            if update_sl:
                await self._update_sl(position, new_sl, "Defensive Drain (Active)")

        except Exception as e:
            self.logger.error(f"❌ Failed to apply defensive exit: {e}")

    async def _check_time_exit(self, position: OpenPosition, candle: CandleEvent):
        """
        Apply soft exit (narrow TP) if max hold time reached.
        """
        if position.bars_held >= config.MAX_HOLD_BARS:
            if not getattr(position, "soft_exit_triggered", False):
                await self._execute_soft_exit(position, "Max Time")

            # HARD LIMIT: If it reaches 2x MAX_HOLD_BARS, then close at market for absolute safety
            if position.bars_held >= config.MAX_HOLD_BARS * 2:
                self.logger.critical(f"🚨 Double Max Hold Reached for {position.trade_id}. Force closing.")
                try:
                    await self.croupier.close_position(position.trade_id, exit_reason="HARD_TIME_EXIT")
                except Exception as e:
                    self.logger.error(f"❌ Failed to execute hard time exit: {e}")

    async def apply_dynamic_exit(self, position: OpenPosition, phase: str):
        """
        Apply dynamic exit strategy based on drain phase.

        Phases:
        - OPTIMISTIC (T-30m): TP = 50% of target (Gain)
        - DEFENSIVE (T-20m): TP = Entry Price (Break Even)
        - AGGRESSIVE (T-10m): TP = -0.1% (Small Loss)
        - PANIC (T-5m): Market Close (Immediate Exit)
        """
        async with self._position_locks[position.trade_id]:
            # Avoid redundant updates if already in this phase
            if getattr(position, "drain_phase", None) == phase:
                return

            self.logger.info(f"📉 Applying Dynamic Exit ({phase}) for {position.trade_id}")
            position.drain_phase = phase

            try:
                new_tp = None

                if phase == "OPTIMISTIC":
                    # Original Soft Exit Logic: 50% of target
                    current_diff = abs(position.tp_level - position.entry_price)
                    narrowed_diff = current_diff * config.SOFT_EXIT_TP_MULT
                    if position.side == "LONG":
                        new_tp = position.entry_price + narrowed_diff
                    else:
                        new_tp = position.entry_price - narrowed_diff

                elif phase == "DEFENSIVE":
                    # Breakeven
                    new_tp = position.entry_price

                elif phase == "AGGRESSIVE":
                    # Accept small loss (-0.1%)
                    loss_dist = position.entry_price * 0.001
                    if position.side == "LONG":
                        new_tp = position.entry_price - loss_dist
                    else:
                        new_tp = position.entry_price + loss_dist

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
                    self.logger.info(f"✅ {phase} TP applied: {new_tp:.4f}")

            except Exception as e:
                # Phase 233: If TP "would immediately trigger", price already passed the exit target.
                # This means the position should be closed NOW instead of placing a limit order.
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

    async def _execute_soft_exit(self, position: OpenPosition, reason: str):
        """Legacy wrapper for compatibility."""
        await self.apply_dynamic_exit(position, "OPTIMISTIC")

    async def _check_shadow_breakeven(self, position: OpenPosition, current_price: float):
        """Phase 241: Move Shadow SL to entry if profit threshold reached."""
        if position.shadow_sl_level is None:
            position.shadow_sl_level = position.sl_level  # Initialize to hard SL

        if position.side == "LONG":
            if position.shadow_sl_level >= position.entry_price:
                return
            profit_pct = (current_price - position.entry_price) / position.entry_price
            if profit_pct >= config.BREAKEVEN_ACTIVATION_PCT:
                new_sl = position.entry_price * 1.001
                if new_sl > position.shadow_sl_level:
                    position.shadow_sl_level = new_sl
                    self.logger.info(f"🛡️ High-Frequency Breakeven ACTIVATED for {position.trade_id} @ {new_sl:.6f}")
        elif position.side == "SHORT":
            if position.shadow_sl_level <= position.entry_price and position.shadow_sl_level > 0:
                return
            profit_pct = (position.entry_price - current_price) / position.entry_price
            if profit_pct >= config.BREAKEVEN_ACTIVATION_PCT:
                new_sl = position.entry_price * 0.999
                if new_sl < position.shadow_sl_level or position.shadow_sl_level == 0:
                    position.shadow_sl_level = new_sl
                    self.logger.info(f"🛡️ High-Frequency Breakeven ACTIVATED for {position.trade_id} @ {new_sl:.6f}")

    async def _check_shadow_trailing_stop(self, position: OpenPosition, current_price: float):
        """Phase 241: Update Shadow SL to follow price if activation threshold reached."""
        if position.entry_price <= 0:
            return
        if position.shadow_sl_level is None:
            position.shadow_sl_level = position.sl_level

        if position.side == "LONG":
            profit_pct = (current_price - position.entry_price) / position.entry_price
            if profit_pct < config.TRAILING_STOP_ACTIVATION_PCT:
                return
            trailing_dist = current_price * config.TRAILING_STOP_DISTANCE_PCT
            new_sl = current_price - trailing_dist
            if new_sl > position.shadow_sl_level:
                position.shadow_sl_level = new_sl
        elif position.side == "SHORT":
            profit_pct = (position.entry_price - current_price) / position.entry_price
            if profit_pct < config.TRAILING_STOP_ACTIVATION_PCT:
                return
            trailing_dist = current_price * config.TRAILING_STOP_DISTANCE_PCT
            new_sl = current_price + trailing_dist
            if new_sl < position.shadow_sl_level or position.shadow_sl_level == 0:
                position.shadow_sl_level = new_sl
