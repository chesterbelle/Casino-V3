import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


@pytest.mark.asyncio
async def test_auto_resync_on_1021_error():
    """
    Test that BinanceNativeConnector automatically triggers _sync_time() and retries
    when a -1021 error (Timestamp outside recvWindow) is encountered.
    """
    # 1. Setup
    connector = BinanceNativeConnector(mode="demo", enable_websocket=False)
    # _http_session must be MagicMock because .get() is not awaitable itself, it returns a context manager
    connector._http_session = MagicMock()
    connector._http_session.close = AsyncMock()  # close() is awaited
    connector._base_url = "https://testnet.binancefuture.com"
    connector._time_offset = 0

    # Mock _sync_time to avoid real network call and just update offset
    connector._sync_time = AsyncMock(side_effect=lambda: setattr(connector, "_time_offset", -1000))

    # 2. Mock Requests
    # First request: Fails with -1021
    # Second request: Succeeds (Retry by ErrorHandler)

    # Mock response object
    mock_fail_resp = AsyncMock()
    mock_fail_resp.status = 400
    mock_fail_resp.text.return_value = (
        '{"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}'
    )

    mock_success_resp = AsyncMock()
    mock_success_resp.status = 200
    mock_success_resp.text.return_value = '{"status": "FILLED"}'

    # Setup session.get to return fail then success
    # NOTE: _execute_raw_request uses session.get/post context managers
    # We need to mock the context manager return

    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.side_effect = [mock_fail_resp, mock_success_resp]
    connector._http_session.get.return_value = mock_get_ctx

    # 3. Execute
    # We call _request directly. ErrorHandler should catch exception from first attempt,
    # see it is retriable (TEMPORARY in classifier), and retry.
    # Inside _execute_raw_request -> _handle_response, we expect _sync_time to be called.

    try:
        result = await connector._request("GET", "/fapi/v1/order")
        assert result == {"status": "FILLED"}
    except Exception as e:
        pytest.fail(f"Should have retried and succeeded, but raised: {e}")

    # 4. Verify
    # Check that _sync_time was called
    assert connector._sync_time.called
    assert connector._sync_time.call_count == 1

    # Check that offset was updated (by our side effect)
    assert connector._time_offset == -1000
    print("✅ Auto-Resync Logic Verified")


if __name__ == "__main__":
    asyncio.run(test_auto_resync_on_1021_error())
