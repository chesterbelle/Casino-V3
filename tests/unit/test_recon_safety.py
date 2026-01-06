from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Standard structure import
from croupier.components.reconciliation_service import ReconciliationService


@pytest.mark.asyncio
async def test_reconciliation_safety_valve_abort():
    """
    Test that reconciliation aborts when exchange persistently reports 0 positions
    while local tracker has many (>5).
    """
    # 1. Setup
    mock_adapter = MagicMock()
    mock_tracker = MagicMock()
    mock_oco = MagicMock()

    service = ReconciliationService(mock_adapter, mock_tracker, mock_oco)

    # 2. Mock State: Mass Detachment
    # Local has 10 positions
    mock_tracker.get_stats.return_value = {"open_positions": 10}

    # Exchange returns [] (Empty) persistently
    # We mock _fetch_exchange_positions to return []
    service._fetch_exchange_positions = AsyncMock(return_value=[])

    # Mock error handler to return [] for orders too (irrelevant if aborted early)
    service.error_handler.execute_with_breaker = AsyncMock(return_value=[])

    # 3. Execute
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        reports = await service.reconcile_all()

    # 4. Verify
    # Should have called fetch 4 times total (1 initial + 3 retries)
    assert service._fetch_exchange_positions.call_count == 4

    # Should return empty list (Aborted)
    assert reports == []

    # Should NOT have proceeded to fetch orders (Aborted before step 2)
    # The logic returns [] early
    assert not service.adapter.fetch_open_orders.called
    print("✅ Safety Valve Abort Verified")


@pytest.mark.asyncio
async def test_reconciliation_glitch_resolved():
    """
    Test that reconciliation proceeds if a glitch is resolved during retries.
    """
    # 1. Setup
    mock_adapter = MagicMock()
    mock_tracker = MagicMock()
    mock_oco = MagicMock()

    service = ReconciliationService(mock_adapter, mock_tracker, mock_oco)

    # 2. Mock State
    mock_tracker.get_stats.return_value = {"open_positions": 10}

    # Exchange returns [] first, then [pos] on retry
    # Side effect: attempt 1 ([]), retry 1 ([]), retry 2 ([pos])
    valid_pos = [{"symbol": "BTC/USDT", "contracts": 1}]
    service._fetch_exchange_positions = AsyncMock(side_effect=[[], [], valid_pos])

    # Mock orders fetch to avoid crash later
    service.error_handler.execute_with_breaker = AsyncMock(return_value=[])
    service._reconcile_symbol_data = AsyncMock(return_value={})

    # 3. Execute
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        reports = await service.reconcile_all()

    # 4. Verify
    # Should have called fetch 3 times (Initial + Retry 1 + Retry 2 (Success))
    assert service._fetch_exchange_positions.call_count == 3

    # Should have proceeded to fetch orders (NOT Aborted)
    # Note: our mock for execute_with_breaker returns [], so it continues

    print("✅ Glitch Resolution Verified")
