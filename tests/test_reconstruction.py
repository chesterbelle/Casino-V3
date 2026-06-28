import unittest

from core.order_flow.engine import OrderFlowEngine
from decision.scenarios.liquidity_exhaustion import LiquidityExhaustionDetector


class TestReconstructedArchitecture(unittest.TestCase):
    def setUp(self):
        self.engine = OrderFlowEngine()
        self.scenario = LiquidityExhaustionDetector(self.engine)
        self.symbol = "TEST/USDT"

    def test_liquidity_exhaustion_reaction(self):
        for i in range(20):
            self.engine.update(self.symbol, qty=10000.0, is_buyer_maker=(i % 2 == 0), ts=100.0 + i, price=100.0)

        state = self.engine.get_state(self.symbol)
        self.assertIsNotNone(state)
        self.assertIsInstance(state.cvd_velocity, float)


if __name__ == "__main__":
    unittest.main()
