"""
Test para validar que normalize_trade() funciona correctamente en cada conector.
"""


def test_binance_normalize_trade_with_close():
    """Test que BinanceNativeConnector detecta correctamente un trade de cierre."""
    from exchanges.connectors.binance.binance_native_connector import (
        BinanceNativeConnector,
    )

    # Simular un trade de cierre de Binance
    raw_trade = {
        "id": "12345",
        "symbol": "LTC/USDT:USDT",
        "side": "buy",
        "price": 104.50,
        "amount": 2.5,
        "info": {
            "realizedPnl": "15.50",  # Binance retorna string
            "type": "MARKET",
        },
    }

    # Crear conector (sin conectar)
    connector = BinanceNativeConnector(api_key="test", secret="test", mode="demo")

    # Normalizar trade
    normalized = connector.normalize_trade(raw_trade)

    # Verificar que se detectó como cierre
    assert normalized["is_close"] is True
    assert normalized["realized_pnl"] == 15.50
    assert normalized["close_reason"] == "MANUAL"


def test_binance_normalize_trade_without_close():
    """Test que BinanceNativeConnector NO detecta un trade de apertura como cierre."""
    from exchanges.connectors.binance.binance_native_connector import (
        BinanceNativeConnector,
    )

    # Simular un trade de apertura de Binance
    raw_trade = {
        "id": "12345",
        "symbol": "LTC/USDT:USDT",
        "side": "buy",
        "price": 104.50,
        "amount": 2.5,
        "info": {
            "realizedPnl": "0",  # Sin PnL = apertura
            "type": "MARKET",
        },
    }

    connector = BinanceNativeConnector(api_key="test", secret="test", mode="demo")

    normalized = connector.normalize_trade(raw_trade)

    # Verificar que NO se detectó como cierre
    assert normalized["is_close"] is False
    assert normalized["realized_pnl"] == 0.0
    assert normalized["close_reason"] is None
