from unittest.mock import AsyncMock, patch

import pytest

from core.portfolio.position_tracker import PositionTracker


def _open_position(tracker, trade_id="p1", symbol="AVAXUSDT", entry_price=6.426, side="LONG"):
    order = {
        "trade_id": trade_id,
        "symbol": f"{symbol}/USDT" if not symbol.endswith("USDT") else symbol,
        "side": side,
        "size": 4.49,
        "leverage": 10,
        "tp_price": entry_price * 1.05,
        "sl_price": entry_price * 0.95,
    }
    return tracker.open_position(
        order=order,
        entry_price=entry_price,
        entry_timestamp="2026-08-14T11:15:00Z",
        available_equity=10000.0,
    )


@pytest.mark.asyncio
async def test_sheriff_skips_position_being_closed_by_bot():
    """Phase 268: ACCOUNT_UPDATE (pa=0) para una posición que el propio bot ya
    está cerrando (CLOSING) NO debe generar EXTERNAL_CLOSE (falsa detección)."""
    tracker = PositionTracker()
    _open_position(tracker, trade_id="p1", symbol="AVAXUSDT")
    pos = tracker.get_position("p1")
    pos.status = "CLOSING"

    with patch.object(tracker, "confirm_close", new=AsyncMock()) as mock_close:
        await tracker.handle_account_update({"a": {"P": [{"s": "AVAXUSDT", "pa": "0"}]}})

    mock_close.assert_not_awaited()


@pytest.mark.asyncio
async def test_sheriff_skips_off_boarding_position():
    """Phase 268: posición OFF_BOARDING (ya registrada) tampoco debe re-clasificarse."""
    tracker = PositionTracker()
    _open_position(tracker, trade_id="p2", symbol="SOLUSDT")
    pos = tracker.get_position("p2")
    pos.status = "OFF_BOARDING"

    with patch.object(tracker, "confirm_close", new=AsyncMock()) as mock_close:
        await tracker.handle_account_update({"a": {"P": [{"s": "SOLUSDT", "pa": "0"}]}})

    mock_close.assert_not_awaited()


@pytest.mark.asyncio
async def test_sheriff_closes_orphan_open_position():
    """Phase 268 (control): posición OPEN con ACCOUNT_UPDATE externo (pa=0) SÍ
    debe cerrarse con EXTERNAL_CLOSE (caso real de silent death)."""
    tracker = PositionTracker()
    _open_position(tracker, trade_id="p3", symbol="LTCUSDT", entry_price=43.0)
    pos = tracker.get_position("p3")
    assert pos.status == "OPEN"

    with patch.object(tracker, "confirm_close", new=AsyncMock()) as mock_close:
        # Precio sin relación con TP (45.15) ni SL (40.85) -> EXTERNAL_CLOSE
        with patch.object(tracker, "adapter", new=type("A", (), {"get_current_price": AsyncMock(return_value=43.5)})()):
            await tracker.handle_account_update({"a": {"P": [{"s": "LTCUSDT", "pa": "0"}]}})

    mock_close.assert_awaited_once()
    call_kwargs = mock_close.call_args.kwargs
    assert call_kwargs["trade_id"] == "p3"
    assert call_kwargs["exit_reason"] == "EXTERNAL_CLOSE"
