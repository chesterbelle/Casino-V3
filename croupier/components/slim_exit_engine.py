"""
SlimExitEngine (V11) — Compression-Only Exit Engine
====================================================

A single-pillar exit engine: gradual bracket compression.
The bracket is left intact for max_hold_seconds, then linearly
compressed toward entry + fee_friction over compression_window seconds.

No close_position() calls. No break even. No micro-z reversal.
The OCO bracket is the sole exit mechanism.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Tuple

from config import trading as config
from core.events import CandleEvent, TickEvent
from core.portfolio.position_tracker import OpenPosition
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


class SlimExitEngine:
    """
    Compression-Only Exit Engine.

    Single pillar: bracket compression over time.
    - 0 to max_hold: bracket intact, thesis runs free.
    - max_hold to total_expiry: TP/SL linearly converge on entry +/- fee_friction.
    - Beyond total_expiry: bracket fully converged, fills naturally as market touches entry.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logging.getLogger("SlimExitEngine")

        self.rules = getattr(config, "UNIVERSAL_EXIT_RULES", {})
        td = self.rules.get("time_decay", {})

        self.max_hold = td.get("max_hold_seconds", 21600)
        self.compression_window = td.get("compression_window", 21600)
        self.fee_friction = td.get("fee_friction", 0.0009)
        self.total_expiry = self.max_hold + self.compression_window

        # Throttle: trade_id -> (last_tp, last_sl) to avoid redundant modify calls
        self._last_compress: Dict[str, Tuple[float, float]] = {}
        self._min_delta_pct = 0.0001  # 0.01% minimum change to trigger modify

        self.logger.info(
            f"🚀 SlimExitEngine V11 initialized | max_hold={self.max_hold}s "
            f"compression_window={self.compression_window}s total_expiry={self.total_expiry}s"
        )

    async def on_tick(self, event: TickEvent):
        """Main loop: apply bracket compression for active positions."""
        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions:
            if position.status not in ("OPEN", "ACTIVE"):
                continue

            elapsed = event.timestamp - position.timestamp
            if elapsed < getattr(config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0):
                continue

            await self._apply_compression(position, elapsed)

    async def _apply_compression(self, position: OpenPosition, elapsed: float):
        """Compress bracket toward entry +/- fee_friction based on elapsed time."""
        if elapsed < self.max_hold:
            return

        entry = position.entry_price
        if entry <= 0:
            return

        fee_offset = entry * self.fee_friction

        if position.side == "LONG":
            tp_target = entry + fee_offset
            sl_target = entry - fee_offset
        else:
            tp_target = entry - fee_offset
            sl_target = entry + fee_offset

        if elapsed >= self.total_expiry:
            new_tp = tp_target
            new_sl = sl_target
        else:
            progress = (elapsed - self.max_hold) / self.compression_window
            new_tp = self._lerp(position.tp_level, tp_target, progress)
            new_sl = self._lerp(position.sl_level, sl_target, progress)

        if not self._should_modify(position.trade_id, new_tp, new_sl):
            return

        self._last_compress[position.trade_id] = (new_tp, new_sl)

        self.logger.info(
            f"🔄 [COMPRESS] {position.trade_id} | elapsed={elapsed:.0f}s "
            f"TP: {position.tp_level:.2f}->{new_tp:.2f} "
            f"SL: {position.sl_level:.2f}->{new_sl:.2f}"
        )

        try:
            tasks = []
            if abs(new_tp - position.tp_level) > 1e-8:
                tasks.append(self.croupier.modify_tp(position.trade_id, new_tp, position.symbol))
            if abs(new_sl - position.sl_level) > 1e-8:
                tasks.append(self.croupier.modify_sl(position.trade_id, new_sl, position.symbol))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"❌ [COMPRESS] Modify failed for {position.trade_id}: {e}")

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """Linear interpolation: a at t=0, b at t=1."""
        return a + (b - a) * t

    def _should_modify(self, trade_id: str, new_tp: float, new_sl: float) -> bool:
        """Throttle: skip if prices haven't changed meaningfully since last modification."""
        last = self._last_compress.get(trade_id)
        if last is None:
            return True
        last_tp, last_sl = last
        if abs(new_tp - last_tp) > self._min_delta_pct * max(abs(last_tp), 1.0):
            return True
        if abs(new_sl - last_sl) > self._min_delta_pct * max(abs(last_sl), 1.0):
            return True
        return False

    async def on_candle(self, event: CandleEvent):
        """Time-based maintenance (optional)."""
        pass
