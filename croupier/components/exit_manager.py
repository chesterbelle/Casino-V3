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

import logging
from typing import TYPE_CHECKING

import config.trading as config
from core.events import AggregatedSignalEvent, CandleEvent
from core.portfolio.position_tracker import OpenPosition

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
        self.logger.info("✅ ExitManager initialized")

    async def on_signal(self, event: AggregatedSignalEvent):
        """
        Handle aggregated signal for potential reversals.
        """
        if not config.SIGNAL_REVERSAL_ENABLED:
            return

        # Check for reversals on all open positions
        for position in self.croupier.get_open_positions():
            await self._check_signal_reversal(position, event)

    async def on_candle(self, event: CandleEvent):
        """
        Handle candle update for trailing stops, breakeven, and time exits.
        """
        # We need current price. Candle close is a good approximation.
        current_price = event.close

        # Iterate over copy to allow modification during iteration
        for position in self.croupier.get_open_positions()[:]:
            # DEBUG: Log every check to catch contamination
            # self.logger.info(
            #    f"🔍 Checking {position.symbol} vs Event {event.symbol} | Price: {current_price}"
            # )

            # Fix: Ensure we only process logic for the symbol that just updated
            # Normalize strings to be safe (remove / and :)
            pos_sym_clean = position.symbol.replace("/", "").replace(":", "").split("USDT")[0]
            evt_sym_clean = event.symbol.replace("/", "").replace(":", "").split("USDT")[0]

            if pos_sym_clean != evt_sym_clean:
                # self.logger.debug(f"⏭️ Skipping {position.symbol} (Event: {event.symbol})")
                continue

            self.logger.info(f"⚡ Processing Exit Logic for {position.symbol} | Price: {current_price}")

            # 1. Check Time-Based Exit
            await self._check_time_exit(position, event)

            # 2. Check Breakeven
            if config.BREAKEVEN_ENABLED:
                await self._check_breakeven(position, current_price)

            # 3. Check Trailing Stop
            if config.TRAILING_STOP_ENABLED:
                await self._check_trailing_stop(position, current_price)

    async def _check_signal_reversal(self, position: OpenPosition, signal: AggregatedSignalEvent):
        """
        Close position if strong opposite signal detected.
        """
        # Ignore signals for other symbols
        if signal.symbol != position.symbol:
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
            # 1.002 to cover fee + slight profit
            if position.side == "LONG":
                new_tp = position.entry_price * 1.002
                new_sl = position.entry_price * 0.995  # -0.5% stop
            else:
                new_tp = position.entry_price * 0.998
                new_sl = position.entry_price * 1.005  # -0.5% stop

            # Update TP
            await self.croupier.modify_tp(
                trade_id=position.trade_id,
                new_tp_price=new_tp,
                symbol=position.symbol,
                old_tp_order_id=position.tp_order_id,
            )

            # Update SL (Only if tighter than current)
            update_sl = False
            if position.side == "LONG" and new_sl > position.sl_level:
                update_sl = True
            elif position.side == "SHORT" and new_sl < position.sl_level:
                update_sl = True

            if update_sl:
                await self._update_sl(position, new_sl, "Defensive Drain")

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

    async def _execute_soft_exit(self, position: OpenPosition, reason: str):
        """
        Narrow the Take Profit to target a quick exit.
        """
        if getattr(position, "soft_exit_triggered", False) and reason != "Session Drain (Optimistic)":
            return

        self.logger.info(f"⏳ {reason} Soft Exit for {position.trade_id} | Narrowing TP")
        position.soft_exit_triggered = True

        try:
            # Narrow TP by the multiplier (e.g., target 50% of original profit)
            current_diff = abs(position.tp_level - position.entry_price)
            narrowed_diff = current_diff * config.SOFT_EXIT_TP_MULT

            if position.side == "LONG":
                new_tp = position.entry_price + narrowed_diff
            else:
                new_tp = position.entry_price - narrowed_diff

            await self.croupier.modify_tp(
                trade_id=position.trade_id,
                new_tp_price=new_tp,
                symbol=position.symbol,
                old_tp_order_id=position.tp_order_id,
            )
            self.logger.info(f"✅ Soft Exit applied: New TP @ {new_tp:.4f}")
        except Exception as e:
            self.logger.error(f"❌ Failed to apply soft exit: {e}")

    async def _check_breakeven(self, position: OpenPosition, current_price: float):
        """
        Move SL to entry if profit threshold reached.
        """
        # Skip if already at or better than breakeven
        if position.side == "LONG":
            if position.sl_level >= position.entry_price:
                return

            # Calculate profit pct
            profit_pct = (current_price - position.entry_price) / position.entry_price

            if profit_pct >= config.BREAKEVEN_ACTIVATION_PCT:
                new_sl = position.entry_price * 1.001  # Slightly above entry to cover fees
                await self._update_sl(position, new_sl, "Breakeven")

        elif position.side == "SHORT":
            if position.sl_level <= position.entry_price:
                return

            # Calculate profit pct (entry - current) / entry
            profit_pct = (position.entry_price - current_price) / position.entry_price

            if profit_pct >= config.BREAKEVEN_ACTIVATION_PCT:
                new_sl = position.entry_price * 0.999  # Slightly below entry
                await self._update_sl(position, new_sl, "Breakeven")

    async def _check_trailing_stop(self, position: OpenPosition, current_price: float):
        """
        Update SL to follow price if activation threshold reached.
        """
        # Guard against zero division (if entry price missing/corrupt)
        if position.entry_price <= 0:
            return

        if position.side == "LONG":
            # Calculate profit
            profit_pct = (current_price - position.entry_price) / position.entry_price

            # Check activation
            if profit_pct < config.TRAILING_STOP_ACTIVATION_PCT:
                return

            # Calculate potential new SL
            # Distance from CURRENT price
            trailing_dist = current_price * config.TRAILING_STOP_DISTANCE_PCT
            new_sl = current_price - trailing_dist

            # Only move UP
            if new_sl > position.sl_level:
                # Ensure we don't move SL too close (min tick size check handled by Croupier/Adapter)
                await self._update_sl(position, new_sl, "Trailing Stop")

        elif position.side == "SHORT":
            # Calculate profit
            profit_pct = (position.entry_price - current_price) / position.entry_price

            # Check activation
            if profit_pct < config.TRAILING_STOP_ACTIVATION_PCT:
                return

            # Calculate potential new SL
            # Distance from CURRENT price
            trailing_dist = current_price * config.TRAILING_STOP_DISTANCE_PCT
            new_sl = current_price + trailing_dist

            # Only move DOWN
            if new_sl < position.sl_level:
                await self._update_sl(position, new_sl, "Trailing Stop")

    async def _update_sl(self, position: OpenPosition, new_sl: float, reason: str):
        """
        Execute SL update via Croupier.
        """
        self.logger.info(
            f"🔄 {reason} triggered for {position.trade_id} | "
            f"Current SL: {position.sl_level:.2f} -> New SL: {new_sl:.2f}"
        )

        try:
            result = await self.croupier.modify_sl(
                trade_id=position.trade_id,
                new_sl_price=new_sl,
                symbol=position.symbol,
                old_sl_order_id=position.sl_order_id,
            )

            # Update position state locally
            position.sl_level = result["new_sl_price"]
            position.sl_order_id = result["new_order_id"]

        except Exception as e:
            self.logger.error(f"❌ Failed to update SL ({reason}): {e}")
