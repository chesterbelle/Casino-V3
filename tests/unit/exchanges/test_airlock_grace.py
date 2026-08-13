"""
Regression tests for Hallazgo #10 (Airlock grace period + open-order scan).

Validates the Phase 262 design rule:
  - When the Airlock RPC times out, the worker may have ALREADY created the
    order (response in transit). Blindly re-sending duplicates the order on
    Binance (-4116) and leaves orphan/ghost brackets.
  - A late worker response (success or error) must be honoured, NEVER
    re-submitted locally.
  - -2013 recovery must fall back to an open-order scan before declaring loss.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from exchanges.connectors.binance.binance_native_connector import (
    AirlockWorkerError,
    BinanceNativeConnector,
)


def _build_connector():
    """Construct a connector instance bypassing __init__ (no credentials/HTTP).

    The Airlock block lives inside `_execute_raw_request` (the REAL method),
    so we stub the underlying HTTP layer instead of that method itself.
    """
    connector = BinanceNativeConnector.__new__(BinanceNativeConnector)
    connector.logger = MagicMock()
    connector._exec_cmd_queue = object()
    connector._exec_cmd_pipe = MagicMock()
    connector._exec_res_queue = MagicMock()
    connector._exec_futures = {}
    connector._airlock_grace_timeout = 0.3
    connector._base_url = "https://testnet.binancefuture.com"
    connector._api_key = None
    connector._http_session = MagicMock()
    connector._http_session.closed = False
    connector._rate_limiter = MagicMock()
    connector._rate_limiter.acquire = AsyncMock(return_value=None)
    connector._latency_monitor = MagicMock()
    connector._normalize_symbol = MagicMock(side_effect=lambda s: s.replace("/", ""))
    connector._handle_response = AsyncMock(return_value={"LOCAL": True})

    class _FakeCM:
        async def __aenter__(self):
            return MagicMock(status=200)

        async def __aexit__(self, *args):
            return False

    connector._http_session.post = MagicMock(return_value=_FakeCM())
    connector._http_session.get = MagicMock(return_value=_FakeCM())
    return connector


async def _call_execute_raw_request(connector, method="POST", url="/fapi/v1/algoOrder", payload=None, timeout=0.01):
    """Invoke the real Airlock owner with minimal args."""
    return await connector._execute_raw_request(
        method,
        f"{connector._base_url}{url}",
        payload or {"symbol": "AVAXUSDT"},
        {},
        "orders",
        signed=False,
        timeout=timeout,
    )


class TestAirlockGracePeriod:
    """A late worker response must be honoured, never re-submitted."""

    @pytest.mark.asyncio
    async def test_late_success_response_is_used_without_resend(self):
        """Worker succeeds after the RPC timeout: use result, no resend."""
        connector = _build_connector()
        connector._exec_cmd_pipe.send = MagicMock()

        async def _wait_for_future_then_resolve():
            # Wait until the future is registered, then resolve it late
            # (after the initial timeout, inside the grace window).
            for _ in range(100):
                if connector._exec_futures:
                    break
                await asyncio.sleep(0.001)
            assert connector._exec_futures, "Future was never registered"
            future = next(iter(connector._exec_futures.values()))
            await asyncio.sleep(0.05)
            future.set_result({"id": "1000000165000000", "status": "new"})

        resolve_task = asyncio.ensure_future(_wait_for_future_then_resolve())
        result = await asyncio.wait_for(_call_execute_raw_request(connector), timeout=1.0)
        resolve_task.cancel()

        assert result["id"] == "1000000165000000"
        # Grace result consumed the future; local fallback must NOT have run.
        assert not connector._exec_futures, "Future should have been consumed"
        connector._handle_response.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_late_error_response_raises_airlock_worker_error(self):
        """Worker reports an error during grace: honour it, do NOT resend."""
        connector = _build_connector()
        connector._exec_cmd_pipe.send = MagicMock()

        async def _resolve_with_error():
            for _ in range(100):
                if connector._exec_futures:
                    break
                await asyncio.sleep(0.001)
            future = next(iter(connector._exec_futures.values()))
            await asyncio.sleep(0.05)
            future.set_exception(Exception("invalid_order: (-4024) price band"))

        resolve_task = asyncio.ensure_future(_resolve_with_error())
        try:
            with pytest.raises(AirlockWorkerError):
                await asyncio.wait_for(_call_execute_raw_request(connector), timeout=1.0)
        finally:
            resolve_task.cancel()
        # Worker error is authoritative: local fallback must NOT have run.
        connector._handle_response.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_genuine_timeout_still_falls_back_locally(self):
        """Worker never answers: pop future and proceed to local fallback."""
        connector = _build_connector()
        connector._exec_cmd_pipe.send = MagicMock()
        result = await asyncio.wait_for(_call_execute_raw_request(connector), timeout=2.0)

        assert result == {"LOCAL": True}
        assert any("Retrying locally" in str(c) for c in connector.logger.warning.call_args_list)


class TestOpenOrderScanRecovery:
    """-2013 recovery must scan open orders before declaring loss."""

    @pytest.mark.asyncio
    async def test_fetch_order_falls_back_to_open_order_scan(self):
        """Regular + algo fetch miss, but open-order scan recovers the order."""
        connector = _build_connector()

        async def fake_request(method, url, params, **kwargs):
            if "/fapi/v1/order" == url:
                raise Exception("invalid_order: (-2013) Order does not exist.")
            if "/fapi/v1/algoOrder" == url:
                raise Exception("invalid_order: (-2013) Order does not exist.")
            raise AssertionError(f"Unexpected request: {method} {url}")

        connector._request = AsyncMock(side_effect=fake_request)
        connector._normalize_order = MagicMock(side_effect=lambda o: {**o, "clientOrderId": o["origClientOrderId"]})
        connector._normalize_algo_order = MagicMock(side_effect=lambda o: o)
        connector.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    "id": "1000000165126806",
                    "clientOrderId": "CASINO_TP_AVAXUSDT_eb82f9dabfcb",
                    "status": "open",
                    "info": {"clientAlgoId": "CASINO_TP_AVAXUSDT_eb82f9dabfcb"},
                }
            ]
        )

        result = await connector.fetch_order("CASINO_TP_AVAXUSDT_eb82f9dabfcb", "AVAXUSDT")

        assert result["id"] == "1000000165126806"
        connector.fetch_open_orders.assert_awaited_once()
