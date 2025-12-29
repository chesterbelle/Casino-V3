"""
Unit tests for symbol normalization utility.
"""

import pytest

from utils.symbol_norm import normalize_symbol


class TestSymbolNormalization:
    """Test suite for normalize_symbol function."""

    def test_uppercase_conversion(self):
        """Should convert lowercase symbols to uppercase."""
        assert normalize_symbol("xrp/usdt") == "XRP/USDT"
        assert normalize_symbol("btc/usdt") == "BTC/USDT"
        assert normalize_symbol("eth/usdt") == "ETH/USDT"

    def test_futures_suffix_removal(self):
        """Should remove :USDT futures contract suffix."""
        assert normalize_symbol("XRP/USDT:USDT") == "XRP/USDT"
        assert normalize_symbol("BTC/USDT:USDT") == "BTC/USDT"
        assert normalize_symbol("eth/usdt:usdt") == "ETH/USDT"

    def test_already_normalized(self):
        """Should handle already-normalized symbols."""
        assert normalize_symbol("XRP/USDT") == "XRP/USDT"
        assert normalize_symbol("BTC/USDT") == "BTC/USDT"

    def test_empty_string(self):
        """Should return empty string for empty input."""
        assert normalize_symbol("") == ""

    def test_mixed_case_with_suffix(self):
        """Should handle mixed case with suffix."""
        assert normalize_symbol("xRp/UsDt:uSdT") == "XRP/USDT"

    def test_different_quote_currencies(self):
        """Should preserve non-USDT quote currencies."""
        assert normalize_symbol("BTC/BUSD") == "BTC/BUSD"
        assert normalize_symbol("ETH/BTC") == "ETH/BTC"

    @pytest.mark.parametrize(
        "input_symbol,expected",
        [
            ("XRP/USDT", "XRP/USDT"),
            ("xrp/usdt", "XRP/USDT"),
            ("XRP/USDT:USDT", "XRP/USDT"),
            ("xrp/usdt:usdt", "XRP/USDT"),
            ("", ""),
            ("BTC/BUSD:BUSD", "BTC/BUSD"),
        ],
    )
    def test_parametrized_normalization(self, input_symbol, expected):
        """Parametrized test for various symbol formats."""
        assert normalize_symbol(input_symbol) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
