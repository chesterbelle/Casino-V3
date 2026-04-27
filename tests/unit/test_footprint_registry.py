"""
Unit tests for FootprintRegistry.

Tests:
1. Singleton pattern
2. Trade updates (bid/ask volume)
3. CVD calculation
4. Delta calculation
5. Volume profile
6. CVD slope
7. Pruning old levels
8. Latency telemetry
"""

import time
import unittest

from core.footprint_registry import FootprintRegistry


class TestFootprintRegistry(unittest.TestCase):
    def setUp(self):
        """Reset registry before each test."""
        self.registry = FootprintRegistry()
        self.registry.reset()
        self.symbol = "BTC/USDT:USDT"
        self.tick_size = 0.5
        self.registry.register_symbol(self.symbol, self.tick_size)

    def test_singleton(self):
        """Test that FootprintRegistry is a singleton."""
        registry1 = FootprintRegistry()
        registry2 = FootprintRegistry()
        self.assertIs(registry1, registry2)

    def test_register_symbol(self):
        """Test symbol registration."""
        symbol = "ETH/USDT:USDT"
        self.registry.register_symbol(symbol, tick_size=0.1)
        self.assertIn(symbol, self.registry.footprints)
        self.assertEqual(self.registry.tick_sizes[symbol], 0.1)

    def test_add_trade_buy(self):
        """Test adding a BUY trade (aggressive buy)."""
        price = 65432.5
        volume = 1.5
        timestamp = time.time()

        self.registry.on_trade(self.symbol, price, volume, "BUY", timestamp)

        footprint = self.registry.get_footprint(self.symbol)
        self.assertIsNotNone(footprint)

        # Check ask volume (aggressive buys)
        ask_vol, bid_vol = footprint.get_volume_at_level(price)
        self.assertEqual(ask_vol, 1.5)
        self.assertEqual(bid_vol, 0.0)

        # Check delta
        delta = footprint.get_delta_at_level(price)
        self.assertEqual(delta, 1.5)

        # Check CVD
        self.assertEqual(footprint.cvd, 1.5)

    def test_add_trade_sell(self):
        """Test adding a SELL trade (aggressive sell)."""
        price = 65432.5
        volume = 2.0
        timestamp = time.time()

        self.registry.on_trade(self.symbol, price, volume, "SELL", timestamp)

        footprint = self.registry.get_footprint(self.symbol)

        # Check bid volume (aggressive sells)
        ask_vol, bid_vol = footprint.get_volume_at_level(price)
        self.assertEqual(ask_vol, 0.0)
        self.assertEqual(bid_vol, 2.0)

        # Check delta (negative for sells)
        delta = footprint.get_delta_at_level(price)
        self.assertEqual(delta, -2.0)

        # Check CVD (negative)
        self.assertEqual(footprint.cvd, -2.0)

    def test_mixed_trades(self):
        """Test mixed BUY and SELL trades at same level."""
        price = 65432.5
        timestamp = time.time()

        # Add BUY
        self.registry.on_trade(self.symbol, price, 1.5, "BUY", timestamp)
        # Add SELL
        self.registry.on_trade(self.symbol, price, 1.0, "SELL", timestamp + 0.1)

        footprint = self.registry.get_footprint(self.symbol)

        # Check volumes
        ask_vol, bid_vol = footprint.get_volume_at_level(price)
        self.assertEqual(ask_vol, 1.5)
        self.assertEqual(bid_vol, 1.0)

        # Check delta
        delta = footprint.get_delta_at_level(price)
        self.assertEqual(delta, 0.5)  # 1.5 - 1.0

        # Check CVD
        self.assertEqual(footprint.cvd, 0.5)  # 1.5 - 1.0

    def test_multiple_levels(self):
        """Test trades at multiple price levels."""
        timestamp = time.time()

        # Level 1: 65432.5
        self.registry.on_trade(self.symbol, 65432.5, 1.0, "BUY", timestamp)
        # Level 2: 65433.0
        self.registry.on_trade(self.symbol, 65433.0, 2.0, "SELL", timestamp + 0.1)
        # Level 3: 65433.5
        self.registry.on_trade(self.symbol, 65433.5, 1.5, "BUY", timestamp + 0.2)

        footprint = self.registry.get_footprint(self.symbol)

        # Check CVD (1.0 - 2.0 + 1.5 = 0.5)
        self.assertEqual(footprint.cvd, 0.5)

        # Check number of levels
        self.assertEqual(len(footprint.levels), 3)

    def test_volume_profile(self):
        """Test volume profile extraction."""
        timestamp = time.time()

        # Add trades at different levels
        self.registry.on_trade(self.symbol, 65432.0, 1.0, "BUY", timestamp)
        self.registry.on_trade(self.symbol, 65432.5, 2.0, "SELL", timestamp + 0.1)
        self.registry.on_trade(self.symbol, 65433.0, 1.5, "BUY", timestamp + 0.2)
        self.registry.on_trade(self.symbol, 65433.5, 0.5, "SELL", timestamp + 0.3)

        # Get profile in range
        profile = self.registry.get_volume_profile(self.symbol, 65432.0, 65433.5)

        # Should have 4 levels, sorted by price
        self.assertEqual(len(profile), 4)
        self.assertEqual(profile[0][0], 65432.0)  # First level
        self.assertEqual(profile[3][0], 65433.5)  # Last level

        # Check volumes at first level (1.0 BUY, 0.0 SELL)
        self.assertEqual(profile[0][1], 1.0)  # ask_vol
        self.assertEqual(profile[0][2], 0.0)  # bid_vol

    def test_cvd_slope(self):
        """Test CVD slope calculation."""
        timestamp = time.time()
        footprint = self.registry.get_footprint(self.symbol)

        # Add trades over time to create CVD history
        for i in range(10):
            self.registry.on_trade(self.symbol, 65432.5, 1.0, "BUY", timestamp + i)
            # Update CVD history manually (normally done by on_trade)
            footprint.cvd_history.append((timestamp + i, footprint.cvd))

        # CVD should be increasing (10 BUYs = +10 CVD)
        slope = footprint.get_cvd_slope(window_seconds=5)

        # Slope should be positive (CVD increasing)
        self.assertGreater(slope, 0)

    def test_prune_old_levels(self):
        """Test pruning of old levels."""
        timestamp = time.time()

        # Add old trade
        self.registry.on_trade(self.symbol, 65432.0, 1.0, "BUY", timestamp - 7200)  # 2 hours ago

        # Add recent trade
        self.registry.on_trade(self.symbol, 65433.0, 2.0, "BUY", timestamp)

        footprint = self.registry.get_footprint(self.symbol)

        # Before pruning: 2 levels
        self.assertEqual(len(footprint.levels), 2)

        # Prune (window = 3600s = 1 hour)
        footprint.prune_old_levels(timestamp)

        # After pruning: 1 level (old one removed)
        self.assertEqual(len(footprint.levels), 1)
        self.assertIn(65433.0, footprint.levels)
        self.assertNotIn(65432.0, footprint.levels)

    def test_latency_telemetry(self):
        """Test latency telemetry."""
        timestamp = time.time()

        # Get initial count
        initial_telemetry = self.registry.get_telemetry()
        initial_count = initial_telemetry["update_count"]

        # Add some trades
        for i in range(100):
            self.registry.on_trade(self.symbol, 65432.5 + i * 0.5, 1.0, "BUY", timestamp + i * 0.01)

        telemetry = self.registry.get_telemetry()

        # Check telemetry fields (count should have increased by 100)
        self.assertEqual(telemetry["update_count"], initial_count + 100)
        self.assertGreater(telemetry["avg_latency_ms"], 0)
        self.assertGreater(telemetry["max_latency_ms"], 0)
        self.assertEqual(telemetry["symbols_tracked"], 1)
        self.assertGreater(telemetry["total_levels"], 0)

    def test_price_rounding(self):
        """Test price rounding to tick size."""
        footprint = self.registry.get_footprint(self.symbol)

        # Tick size = 0.5
        self.assertEqual(footprint.round_price(65432.3), 65432.5)
        self.assertEqual(footprint.round_price(65432.7), 65432.5)
        self.assertEqual(footprint.round_price(65432.8), 65433.0)

    def test_reset(self):
        """Test registry reset."""
        timestamp = time.time()

        # Add some trades
        self.registry.on_trade(self.symbol, 65432.5, 1.0, "BUY", timestamp)
        self.registry.on_trade(self.symbol, 65433.0, 2.0, "SELL", timestamp + 0.1)

        footprint = self.registry.get_footprint(self.symbol)
        self.assertEqual(len(footprint.levels), 2)
        self.assertNotEqual(footprint.cvd, 0.0)

        # Reset
        self.registry.reset()

        # After reset: empty
        footprint = self.registry.get_footprint(self.symbol)
        self.assertEqual(len(footprint.levels), 0)
        self.assertEqual(footprint.cvd, 0.0)


if __name__ == "__main__":
    unittest.main()
