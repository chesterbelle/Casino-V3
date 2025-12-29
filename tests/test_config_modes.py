import importlib
import sys

import pytest

CONFIG_MODULE = "core.config"
ENV_VARS = [
    "CASINO_MODE",
    "CASINO_EXCHANGE",
    "CASINO_LIVE_TRADING_ENABLED",
    "CASINO_LIVE_TRADING_ENABLED_CONFIG",
]


def _reload_config(monkeypatch, **env_overrides):
    for key, value in env_overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    # Remove the core.config and any submodules from sys.modules so they are reimported
    monkeypatch.delitem(sys.modules, CONFIG_MODULE, raising=False)
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.delitem(sys.modules, "config.system", raising=False)
    monkeypatch.delitem(sys.modules, "config.exchange", raising=False)
    monkeypatch.delitem(sys.modules, "config.trading", raising=False)
    monkeypatch.delitem(sys.modules, "core.config", raising=False)
    return importlib.import_module(CONFIG_MODULE)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_default_mode_is_testing(monkeypatch):
    config = _reload_config(monkeypatch)
    # Default mode changed to 'demo' in v2 config/system.py
    assert config.MODE == "demo"
    # Default exchange changed to BYBIT in v2
    assert config.EXCHANGE == "BYBIT"


def test_mode_override_via_env(monkeypatch):
    config = _reload_config(monkeypatch, CASINO_MODE="backtest")
    assert config.MODE == "backtest"


def test_invalid_mode_raises(monkeypatch):
    with pytest.raises(ValueError):
        _reload_config(monkeypatch, CASINO_MODE="invalid")


def test_live_mode_requires_confirmations(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "YES")

    config = _reload_config(
        monkeypatch,
        CASINO_MODE="live",
        CASINO_EXCHANGE="KRAKEN",
        CASINO_LIVE_TRADING_ENABLED="true",
        CASINO_LIVE_TRADING_ENABLED_CONFIG="true",
    )
    assert config.MODE == "live"
    assert config.EXCHANGE == "KRAKEN"
    assert config.LIVE_TRADING_ENABLED is True
