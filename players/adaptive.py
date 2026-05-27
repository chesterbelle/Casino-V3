"""
Fixed Player Strategy
=====================

A simple player that bets a fixed percentage of equity on every signal.
Supports optional Kelly Criterion sizing based on sensor performance.
"""

import logging

from core.events import EventType
from decision.engine.proposal import TradeProposal

logger = logging.getLogger(__name__)


class AdaptivePlayer:
    """
    Adaptive player that sizes bets based on TradeProposal grade.
    """

    def __init__(
        self,
        engine,
        croupier,
        max_positions: int = 1,
        context_registry=None,
    ):
        self.engine = engine
        self.croupier = croupier
        self.max_positions = max_positions
        self.context_registry = context_registry
        self._inflight_symbols = set()

        # Policy: A = 1.0%, B = 0.5%
        self.SIZE_POLICY = {"A": 0.01, "B": 0.005}

        # Subscribe to Proposals
        self.engine.subscribe(EventType.TRADE_PROPOSAL, self.on_trade_proposal)

        logger.info(f"✅ AdaptivePlayer (V8.5 Planar) initialized. Policy: {self.SIZE_POLICY}")

    async def on_trade_proposal(self, proposal: TradeProposal):
        """Execute proposal based on rigid grade policy."""
        target_symbol_norm = proposal.symbol.replace("/", "").replace(":USDT", "")

        # Check inflight
        if target_symbol_norm in self._inflight_symbols:
            logger.warning(f"🚫 REJECTED | {proposal.symbol} | INFLIGHT_LOCK")
            return

        # Check limit
        open_positions = [
            p for p in self.croupier.get_active_positions() if p.symbol.replace("/", "") == target_symbol_norm
        ]
        if len(open_positions) >= self.max_positions:
            logger.warning(f"🚫 REJECTED | {proposal.symbol} | POSITION_LIMIT")
            return

        # Simple Sizing
        bet_size = self.SIZE_POLICY.get(proposal.grade, 0.0025)
        equity = self.croupier.get_equity()

        logger.info(
            f"🎯 Executing {proposal.side} | Grade: {proposal.grade} | "
            f"Size: {bet_size:.2%} of {equity:.2f} | TP: {proposal.tp_price} | SL: {proposal.sl_price}"
        )

        self._inflight_symbols.add(target_symbol_norm)

        try:
            amount = (equity * bet_size) / proposal.entry_price
            # Replicating production place_limit_order logic inside MockCroupier or redirecting
            order_payload = {
                "symbol": proposal.symbol,
                "side": proposal.side,
                "amount": amount,
                "tp_price": proposal.tp_price,
                "sl_price": proposal.sl_price,
                "type": "LIMIT",
                "trace_id": proposal.trace_id,
            }
            await self.croupier.execute_order(order_payload)

        finally:
            self._inflight_symbols.discard(target_symbol_norm)
