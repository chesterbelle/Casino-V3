"""
Regression tests for Binance order routing (Hallazgo #8).

Validates the Phase 248 Revision 2 design rule:
  - Conditional orders (TP/SL/OCO family) -> ALWAYS Algo API.
  - closePosition=True -> converted to reduceOnly + real quantity for
    conditional orders (Main API rejects them with -4120).
  - closePosition=True -> ONLY kept for plain MARKET/LIMIT (dust cleanup).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


def _build_connector():
    """Construct a connector instance bypassing __init__ (no credentials/HTTP)."""
    connector = BinanceNativeConnector.__new__(BinanceNativeConnector)
    connector.logger = MagicMock()
    connector._normalize_symbol = MagicMock(side_effect=lambda s: s.replace("/", ""))
    connector.amount_to_precision = MagicMock(side_effect=lambda s, v: str(v))
    connector.price_to_precision = MagicMock(side_effect=lambda s, v: str(v))
    connector._get_position_size_for_algo_fallback = AsyncMock(return_value=0.0)
    connector._create_algo_order = AsyncMock(
        return_value={"id": "algo123", "status": "new", "amount": 0.0, "price": 0.0}
    )
    connector._request = AsyncMock(return_value={})
    return connector


class TestConditionalRouting:
    """Conditional orders must route to Algo API, never Main API with closePosition."""

    @pytest.mark.asyncio
    async def test_conditional_close_position_converts_to_reduce_only(self):
        """TAKE_PROFIT_MARKET + closePosition + amount=0 -> Algo API with resolved quantity."""
        connector = _build_connector()
        connector._get_position_size_for_algo_fallback.return_value = 0.1928

        result = await connector.create_order(
            symbol="SOLUSDT",
            side="SELL",
            amount=0,
            order_type="TAKE_PROFIT_MARKET",
            params={"closePosition": True, "stopPrice": 75.03},
        )

        assert connector._create_algo_order.await_count == 1
        connector._request.assert_not_awaited()
        sent_args = connector._create_algo_order.await_args.args[0]
        assert "closePosition" not in sent_args
        assert sent_args["reduceOnly"] == "true"
        assert sent_args["quantity"] == "0.1928"
        assert sent_args["type"] == "TAKE_PROFIT_MARKET"

    @pytest.mark.asyncio
    async def test_conditional_close_position_unresolvable_size_last_resort_main_api(self):
        """If position size cannot be resolved, fall back to Main API (safety net)."""
        connector = _build_connector()
        connector._get_position_size_for_algo_fallback.return_value = 0.0

        await connector.create_order(
            symbol="SOLUSDT",
            side="BUY",
            amount=0,
            order_type="STOP_MARKET",
            params={"closePosition": True, "stopPrice": 76.0},
        )

        connector._request.assert_awaited_once()
        call_kwargs = connector._request.await_args.args
        assert call_kwargs[1] == "/fapi/v1/order"
        sent_args = call_kwargs[2]
        assert sent_args["closePosition"] == "true"
        assert "quantity" not in sent_args

    @pytest.mark.asyncio
    async def test_conditional_reduce_only_goes_straight_to_algo_api(self):
        """Normal bracket (reduceOnly + quantity) routes to Algo API unchanged."""
        connector = _build_connector()

        await connector.create_order(
            symbol="SOLUSDT",
            side="SELL",
            amount=0.1928,
            order_type="TAKE_PROFIT_MARKET",
            params={"reduceOnly": True, "stopPrice": 75.03},
        )

        assert connector._create_algo_order.await_count == 1
        connector._request.assert_not_awaited()
        sent_args = connector._create_algo_order.await_args.args[0]
        assert sent_args["reduceOnly"] == "true"
        assert sent_args["quantity"] == "0.1928"
        assert "closePosition" not in sent_args


class TestMainApiRouting:
    """Plain MARKET/LIMIT keep closePosition=True (dust cleanup / emergency close)."""

    @pytest.mark.asyncio
    async def test_market_close_position_stays_on_main_api(self):
        """MARKET + closePosition (emergency close) -> Main API, no quantity."""
        connector = _build_connector()

        await connector.create_order(
            symbol="SOLUSDT",
            side="BUY",
            amount=0,
            order_type="market",
            params={"closePosition": True},
        )

        connector._request.assert_awaited_once()
        connector._create_algo_order.assert_not_awaited()
        sent_args = connector._request.await_args.args[2]
        assert sent_args["closePosition"] == "true"
        assert "quantity" not in sent_args

    @pytest.mark.asyncio
    async def test_market_reduce_only_stays_on_main_api(self):
        """Normal MARKET reduceOnly close -> Main API with quantity."""
        connector = _build_connector()

        await connector.create_order(
            symbol="SOLUSDT",
            side="SELL",
            amount=0.1928,
            order_type="market",
            params={"reduceOnly": True},
        )

        connector._request.assert_awaited_once()
        connector._create_algo_order.assert_not_awaited()
        sent_args = connector._request.await_args.args[2]
        assert sent_args["reduceOnly"] == "true"
        assert sent_args["quantity"] == "0.1928"
