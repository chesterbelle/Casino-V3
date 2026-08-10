"""
Unit tests for symbol normalization utility.
"""

import pytest

from utils.symbol_norm import normalize_symbol


class TestSymbolNormalization:
    """Test suite for normalize_symbol function."""

    def test_uppercase_conversion(self):
        """Should convert lowercase symbols to uppercase and remove slashes."""
        assert normalize_symbol("xrp/usdt") == "XRPUSDT"
        assert normalize_symbol("btc/usdt") == "BTCUSDT"
        assert normalize_symbol("eth/usdt") == "ETHUSDT"

    def test_futures_suffix_removal(self):
        """Should remove :USDT futures contract suffix."""
        assert normalize_symbol("XRP/USDT:USDT") == "XRPUSDT"
        assert normalize_symbol("BTC/USDT:USDT") == "BTCUSDT"
        assert normalize_symbol("eth/usdt:usdt") == "ETHUSDT"

    def test_already_normalized(self):
        """Should handle already-normalized symbols."""
        assert normalize_symbol("XRPUSDT") == "XRPUSDT"
        assert normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_empty_string(self):
        """Should return empty string for empty input."""
        assert normalize_symbol("") == ""

    def test_mixed_case_with_suffix(self):
        """Should handle mixed case with suffix."""
        assert normalize_symbol("xRp/UsDt:uSdT") == "XRPUSDT"

    def test_different_quote_currencies(self):
        """Should preserve non-USDT quote currencies (and remove slashes)."""
        assert normalize_symbol("BTC/BUSD") == "BTCBUSD"
        assert normalize_symbol("ETH/BTC") == "ETHBTC"

    @pytest.mark.parametrize(
        "input_symbol,expected",
        [
            ("XRP/USDT", "XRPUSDT"),
            ("xrp/usdt", "XRPUSDT"),
            ("XRP/USDT:USDT", "XRPUSDT"),
            ("xrp/usdt:usdt", "XRPUSDT"),
            ("", ""),
            ("BTC/BUSD:BUSD", "BTCBUSD"),
        ],
    )
    def test_parametrized_normalization(self, input_symbol, expected):
        """Parametrized test for various symbol formats."""
        assert normalize_symbol(input_symbol) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
