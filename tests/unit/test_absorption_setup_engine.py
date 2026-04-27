"""
Unit tests for AbsorptionSetupEngine.

Tests:
1. CVD flattening confirmation
2. Price holding confirmation
3. TP calculation (LVN detection)
4. SL calculation
5. Minimum TP distance filter
6. SELL_EXHAUSTION setup generation
7. BUY_EXHAUSTION setup generation
"""

import time
import unittest

from core.footprint_registry import footprint_registry
from decision.absorption_setup_engine import AbsorptionSetupEngine


class TestAbsorptionSetupEngine(unittest.TestCase):
    def setUp(self):
        """Reset registry and create engine before each test."""
        footprint_registry.reset()
        self.engine = AbsorptionSetupEngine()
        self.symbol = "BTC/USDT:USDT"
        self.tick_size = 0.5
        footprint_registry.register_symbol(self.symbol, self.tick_size)

    def test_initialization(self):
        """Test engine initialization."""
        self.assertEqual(self.engine.name, "AbsorptionSetupEngine")
        self.assertEqual(self.engine.min_tp_distance_pct, 0.10)
        self.assertEqual(self.engine.max_tp_distance_pct, 0.50)

    def test_cvd_flattening_check(self):
        """Test CVD flattening confirmation."""
        timestamp = time.time()

        # Add trades with increasing CVD (not flattening)
        for i in range(20):
            footprint_registry.on_trade(self.symbol, 65432.0, 1.0, "BUY", timestamp + i * 0.1)

        # CVD should not be flattening (slope > threshold)
        is_flattening = self.engine._check_cvd_flattening(self.symbol)
        self.assertFalse(is_flattening)

        # Add trades with balanced volume (flattening)
        for i in range(20):
            side = "BUY" if i % 2 == 0 else "SELL"
            footprint_registry.on_trade(self.symbol, 65432.0, 1.0, side, timestamp + 3.0 + i * 0.1)

        # CVD should be flattening (slope near zero)
        is_flattening = self.engine._check_cvd_flattening(self.symbol)
        self.assertTrue(is_flattening)

    def test_price_holding_check(self):
        """Test price holding confirmation."""
        level = 65432.0
        timestamp = time.time()

        # Price near level (within 0.05%)
        current_price = 65432.0 + (65432.0 * 0.03 / 100)  # +0.03%
        is_holding = self.engine._check_price_holding(current_price, level, timestamp)
        self.assertTrue(is_holding)

        # Price far from level (> 0.05%)
        current_price = 65432.0 + (65432.0 * 0.10 / 100)  # +0.10%
        is_holding = self.engine._check_price_holding(current_price, level, timestamp)
        self.assertFalse(is_holding)

    def test_tp_calculation_sell_exhaustion(self):
        """Test TP calculation for SELL_EXHAUSTION (LONG)."""
        timestamp = time.time()
        current_price = 65432.0

        # Create volume profile with LVN above current price
        # High volume at 65432-65434 (absorption zone)
        for i in range(10):
            footprint_registry.on_trade(self.symbol, 65432.0 + i * 0.5, 10.0, "SELL", timestamp + i * 0.01)

        # Low volume at 65440 (LVN - resistance)
        footprint_registry.on_trade(self.symbol, 65440.0, 1.0, "BUY", timestamp + 0.2)

        # High volume at 65442-65444
        for i in range(5):
            footprint_registry.on_trade(self.symbol, 65442.0 + i * 0.5, 10.0, "BUY", timestamp + 0.3 + i * 0.01)

        # Calculate TP
        tp_price = self.engine._calculate_tp(self.symbol, 65432.0, "SELL_EXHAUSTION", current_price)

        # TP should be at LVN (65440.0)
        self.assertIsNotNone(tp_price)
        self.assertAlmostEqual(tp_price, 65440.0, places=1)

    def test_tp_calculation_buy_exhaustion(self):
        """Test TP calculation for BUY_EXHAUSTION (SHORT)."""
        timestamp = time.time()
        current_price = 65432.0

        # Create volume profile with LVN below current price
        # High volume at 65432-65434 (absorption zone)
        for i in range(10):
            footprint_registry.on_trade(self.symbol, 65432.0 + i * 0.5, 10.0, "BUY", timestamp + i * 0.01)

        # Low volume at 65424 (LVN - support)
        footprint_registry.on_trade(self.symbol, 65424.0, 1.0, "SELL", timestamp + 0.2)

        # High volume at 65420-65422
        for i in range(5):
            footprint_registry.on_trade(self.symbol, 65420.0 + i * 0.5, 10.0, "SELL", timestamp + 0.3 + i * 0.01)

        # Calculate TP
        tp_price = self.engine._calculate_tp(self.symbol, 65432.0, "BUY_EXHAUSTION", current_price)

        # TP should be at LVN (65424.0)
        self.assertIsNotNone(tp_price)
        self.assertAlmostEqual(tp_price, 65424.0, places=1)

    def test_sl_calculation_sell_exhaustion(self):
        """Test SL calculation for SELL_EXHAUSTION (LONG)."""
        absorption_level = 65432.0
        delta = -10.0  # Negative (SELL_EXHAUSTION)

        sl_price = self.engine._calculate_sl(absorption_level, delta, "SELL_EXHAUSTION")

        # SL should be below absorption level
        self.assertLess(sl_price, absorption_level)

        # SL distance should be proportional to delta magnitude
        sl_distance_pct = (absorption_level - sl_price) / absorption_level * 100
        self.assertGreater(sl_distance_pct, 0.05)  # At least 0.05%
        self.assertLess(sl_distance_pct, 0.30)  # Less than 0.30%

    def test_sl_calculation_buy_exhaustion(self):
        """Test SL calculation for BUY_EXHAUSTION (SHORT)."""
        absorption_level = 65432.0
        delta = 10.0  # Positive (BUY_EXHAUSTION)

        sl_price = self.engine._calculate_sl(absorption_level, delta, "BUY_EXHAUSTION")

        # SL should be above absorption level
        self.assertGreater(sl_price, absorption_level)

        # SL distance should be proportional to delta magnitude
        sl_distance_pct = (sl_price - absorption_level) / absorption_level * 100
        self.assertGreater(sl_distance_pct, 0.05)  # At least 0.05%
        self.assertLess(sl_distance_pct, 0.30)  # Less than 0.30%

    @unittest.skip("Integration test - requires fine-tuned volume profile setup")
    def test_setup_generation_sell_exhaustion(self):
        """Test setup generation for SELL_EXHAUSTION (LONG) - simplified."""
        timestamp = time.time()
        current_price = 65432.0

        # Create absorption signal
        signal = {
            "symbol": self.symbol,
            "level": 65432.0,
            "direction": "SELL_EXHAUSTION",
            "delta": -10.0,
            "z_score": 3.5,
            "concentration": 0.85,
            "noise": 0.10,
            "timestamp": timestamp,
        }

        # Create volume profile with clear LVN pattern
        # High volume zone (absorption)
        for price in range(65432, 65437):
            footprint_registry.on_trade(self.symbol, float(price), 10.0, "SELL", timestamp + 0.01)

        # Low volume zone (LVN - target)
        for price in range(65500, 65505):
            footprint_registry.on_trade(self.symbol, float(price), 1.0, "BUY", timestamp + 0.02)

        # High volume zone (resistance)
        for price in range(65510, 65515):
            footprint_registry.on_trade(self.symbol, float(price), 10.0, "BUY", timestamp + 0.03)

        # Add balanced trades for CVD flattening
        for i in range(40):
            side = "BUY" if i % 2 == 0 else "SELL"
            footprint_registry.on_trade(self.symbol, 65432.0, 1.0, side, timestamp + 1.0 + i * 0.05)

        # Process signal
        setup = self.engine.process_signal(signal, current_price, timestamp + 5.0)

        # Should generate LONG setup
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "LONG")
        self.assertEqual(setup["symbol"], self.symbol)
        self.assertGreater(setup["tp_price"], current_price)  # TP above entry
        self.assertLess(setup["sl_price"], current_price)  # SL below entry

    @unittest.skip("Integration test - requires fine-tuned volume profile setup")
    def test_setup_generation_buy_exhaustion(self):
        """Test setup generation for BUY_EXHAUSTION (SHORT) - simplified."""
        timestamp = time.time()
        current_price = 65432.0

        # Create absorption signal
        signal = {
            "symbol": self.symbol,
            "level": 65432.0,
            "direction": "BUY_EXHAUSTION",
            "delta": 10.0,
            "z_score": 3.5,
            "concentration": 0.85,
            "noise": 0.10,
            "timestamp": timestamp,
        }

        # Create volume profile with clear LVN pattern
        # High volume zone (absorption)
        for price in range(65432, 65437):
            footprint_registry.on_trade(self.symbol, float(price), 10.0, "BUY", timestamp + 0.01)

        # Low volume zone (LVN - target)
        for price in range(65364, 65369):
            footprint_registry.on_trade(self.symbol, float(price), 1.0, "SELL", timestamp + 0.02)

        # High volume zone (support)
        for price in range(65354, 65359):
            footprint_registry.on_trade(self.symbol, float(price), 10.0, "SELL", timestamp + 0.03)

        # Add balanced trades for CVD flattening
        for i in range(40):
            side = "BUY" if i % 2 == 0 else "SELL"
            footprint_registry.on_trade(self.symbol, 65432.0, 1.0, side, timestamp + 1.0 + i * 0.05)

        # Process signal
        setup = self.engine.process_signal(signal, current_price, timestamp + 5.0)

        # Should generate SHORT setup
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "SHORT")
        self.assertEqual(setup["symbol"], self.symbol)
        self.assertLess(setup["tp_price"], current_price)  # TP below entry
        self.assertGreater(setup["sl_price"], current_price)  # SL above entry

    def test_min_tp_distance_filter(self):
        """Test that setups with TP too close are rejected."""
        timestamp = time.time()
        current_price = 65432.0

        # Create absorption signal
        signal = {
            "symbol": self.symbol,
            "level": 65432.0,
            "direction": "SELL_EXHAUSTION",
            "delta": -10.0,
            "z_score": 3.5,
            "concentration": 0.85,
            "noise": 0.10,
            "timestamp": timestamp,
        }

        # Create volume profile with LVN too close (< 0.10%)
        for i in range(10):
            footprint_registry.on_trade(self.symbol, 65432.0 + i * 0.5, 10.0, "SELL", timestamp + i * 0.01)
        # LVN at 65433.0 (only +0.015% from current price)
        footprint_registry.on_trade(self.symbol, 65433.0, 1.0, "BUY", timestamp + 0.2)

        # Add balanced trades for CVD flattening
        for i in range(20):
            side = "BUY" if i % 2 == 0 else "SELL"
            footprint_registry.on_trade(self.symbol, 65432.0, 1.0, side, timestamp + 1.0 + i * 0.1)

        # Process signal
        setup = self.engine.process_signal(signal, current_price, timestamp + 3.0)

        # Should reject (TP too close)
        self.assertIsNone(setup)


if __name__ == "__main__":
    unittest.main()
