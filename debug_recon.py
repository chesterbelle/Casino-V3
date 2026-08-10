import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from core.state.position import OpenPosition
from croupier.components.reconciliation_service import ReconciliationService


async def main():
    mock_tracker = MagicMock()
    mock_tracker.get_positions_by_symbol.return_value = []
    mock_tracker.remove_position = AsyncMock(return_value=True)
    mock_tracker.has_valid_bracket.return_value = (False, False)

    old_time = (time.time() - 300) * 1000
    ghost_pos = OpenPosition(
        trade_id="ghost_1",
        symbol="BTC/USDT",
        side="LONG",
        entry_price=50000.0,
        amount=1.0,
        entry_timestamp=str(old_time),
        status="OPEN",
        timestamp=old_time / 1000.0,
        margin_used=10.0,
        notional=50000.0,
        leverage=5.0,
        tp_level=55000.0,
        sl_level=45000.0,
        order={"amount": 1.0},
    )
    mock_tracker.get_positions_by_symbol.return_value = [ghost_pos]

    recon = ReconciliationService(
        exchange_adapter=MagicMock(), position_tracker=mock_tracker, error_handler=MagicMock()
    )
    recon._investigate_ghost = AsyncMock(return_value=None)

    report = await recon._reconcile_symbol_data("BTC/USDT", [], [])
    print("GHOSTS REMOVED:", report["ghosts_removed"])
    print("ISSUES:", report["issues_found"])


asyncio.run(main())
