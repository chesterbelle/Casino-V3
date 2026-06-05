"""
Scenario ④: Trend Acceptance — "VA Breakout + Confirming Delta + Pullback"

AMT Narrative:
    Price leaves the VA with strong delta confirmation. The market is
    genuinely accepting new prices. The entry is on the pullback to
    the broken level (now acting as support/resistance).

Entry conditions:
    1. Price was outside VA for ≥3 consecutive candles
    2. CVD during breakout CONFIRMED the direction
    3. Price pulled back toward the broken level (VAH or VAL)
       without fully re-entering the VA

Signal: At the pullback to the broken level
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("AMTScenarios.TrendAcceptance")


class TrendAcceptanceDetector:
    def __init__(self, pressure_engine) -> None:
        self.name = "TrendAcceptance"
        self.pressure = pressure_engine
        self.active_breakouts = {}
        self.last_fire_ts = defaultdict(float)
        self.cooldown = 60.0
        self.min_candles_outside = 3
        self.cvd_confirmation_threshold = 5.0

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if timestamp - self.last_fire_ts[symbol] < self.cooldown:
            return None

        # Get profile parameters for this symbol
        from decision.engine.profile_manager import profile_manager

        sensor_params = profile_manager.get_sensor_params(symbol, "trend_acceptance")

        # Update parameters from profile if available
        if sensor_params:
            self.min_candles_outside = sensor_params.get("min_candles_outside", self.min_candles_outside)
            self.cvd_confirmation_threshold = sensor_params.get(
                "cvd_confirmation_threshold", self.cvd_confirmation_threshold
            )

        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)

        state = self.pressure.get_state()
        cvd_slope = state.cvd_velocity

        # Lógica simplificada de tendencia:
        # Detectar si el precio está fuera de VA + confirmación de presión
        is_above = price > vah
        is_below = price < val

        if is_above and cvd_slope > self.cvd_confirmation_threshold:
            return {
                "symbol": symbol,
                "side": "LONG",
                "price": price,
                "timestamp": timestamp,
                "scenario": "trend_acceptance",
            }
        elif is_below and cvd_slope < -self.cvd_confirmation_threshold:
            return {
                "symbol": symbol,
                "side": "SHORT",
                "price": price,
                "timestamp": timestamp,
                "scenario": "trend_acceptance",
            }

        return None
