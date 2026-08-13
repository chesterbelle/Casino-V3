"""
Regression tests for Hallazgo #10 (single client_order_id identity).

Validates the Phase 262 design rule:
  - ResilientConnector must INHERIT the caller's client_order_id (passed via
    params by OCOManager/OrderExecutor) instead of generating its own.
  - Dual identity (tracked id != id sent to Binance) broke -4116 recovery,
    which looked up the wrong id and failed with -2013 (orphan brackets).
  - When no caller id is provided, generate locally AND inject it into params
    so the tracked id == the id the connector sends to the exchange.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from exchanges.connectors.resilient_connector import ResilientConnector


def _build_connector():
    connector = ResilientConnector.__new__(ResilientConnector)
    connector.logger = MagicMock()
    connector._connector = MagicMock()
    connector._connector.create_order = AsyncMock(return_value={"id": "1000000165000000", "status": "new"})
    connector._order_tracker = MagicMock()
    connector._order_tracker.start_tracking = MagicMock(return_value=None)
    connector._order_tracker.update_order_submitted = MagicMock(return_value=True)
    connector._session_state = None
    connector._generate_client_order_id = MagicMock(return_value="CASINO_LOCALGEN_abc123")
    return connector


class TestSingleIdentity:
    """The caller's client_order_id must be inherited, never overwritten."""

    @pytest.mark.asyncio
    async def test_inherits_caller_client_order_id(self):
        """OCOManager id must be the id tracked and the id sent to Binance."""
        connector = _build_connector()
        caller_id = "CASINO_TP_AVAXUSDT_eb82f9dabfcb"

        await connector.create_order(
            symbol="AVAXUSDT",
            side="buy",
            amount=4.0,
            order_type="market",
            params={"client_order_id": caller_id},
        )

        # Tracking used the caller's id, not a locally generated one.
        track_kwargs = connector._order_tracker.start_tracking.call_args.kwargs
        assert track_kwargs["client_order_id"] == caller_id
        # No local generation happened.
        connector._generate_client_order_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_when_absent_but_injects_into_params(self):
        """Without a caller id: generate once AND unify it into params."""
        connector = _build_connector()

        await connector.create_order(
            symbol="SOLUSDT",
            side="sell",
            amount=0.1928,
            order_type="TAKE_PROFIT_MARKET",
            params={"stopPrice": 75.03},
        )

        # The generated id was tracked...
        track_kwargs = connector._order_tracker.start_tracking.call_args.kwargs
        assert track_kwargs["client_order_id"] == "CASINO_LOCALGEN_abc123"
        # ...and injected into params so the underlying connector sends it.
        sent_params = connector._connector.create_order.await_args.args[-1]
        assert sent_params["client_order_id"] == "CASINO_LOCALGEN_abc123"
        assert sent_params["clientOrderId"] == "CASINO_LOCALGEN_abc123"

    @pytest.mark.asyncio
    async def test_tracking_submitted_uses_same_id(self):
        """update_order_submitted maps the same id to the exchange order id."""
        connector = _build_connector()
        caller_id = "CASINO_FC_401c27453fe4"

        await connector.create_order(
            symbol="AVAXUSDT",
            side="buy",
            amount=4.0,
            order_type="market",
            params={"client_order_id": caller_id},
        )

        connector._order_tracker.update_order_submitted.assert_called_once_with(caller_id, "1000000165000000")
