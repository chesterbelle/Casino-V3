import unittest

from core.pressure.engine import PressureEngine
from decision.scenarios.liquidity_exhaustion import LiquidityExhaustionDetector


class TestReconstructedArchitecture(unittest.TestCase):
    def setUp(self):
        self.engine = PressureEngine()
        self.scenario = LiquidityExhaustionDetector(self.engine)

    def test_liquidity_exhaustion_reaction(self):
        # Simular ticks para generar presión
        # El engine requiere al menos 11 ticks para calcular velocidad (cvd_history window=200, len>10)
        # La lógica actual:
        # is_high_delta = abs(self.last_state.cvd_velocity) > self.z_score_min (default 3.0)
        # Necesitamos un delta de velocidad (Z-Score) > 3.0

        # Vamos a inyectar valores que generen alta velocidad de CVD
        for i in range(20):
            # Aumentamos el volumen drásticamente para superar el Z-Score
            self.engine.update(qty=10000.0, is_buyer_maker=(i % 2 == 0), ts=100.0 + i, price=100.0)

        state = self.engine.get_state()
        print(f"\nScore de absorción: {state.absorption_score}, CVD Velocity: {state.cvd_velocity}")
        self.assertEqual(state.absorption_score, 1.0)


if __name__ == "__main__":
    unittest.main()
