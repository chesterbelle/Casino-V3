from collections import defaultdict
from typing import Any, Dict, Optional


class AbsorptionDetector:
    """
    Absorption Detector v10: Profile-Calibrated + Multi-Factor Filter.
    Consumes PressureEngine centralized state.
    Only fires ONCE per absorption event (not every tick during absorption).
    """

    def __init__(self, pressure_engine) -> None:
        self.pressure = pressure_engine
        self.name = "tactical_absorption"
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 180.0
        self.level_tolerance_pct = 0.003
        self.z_score_min = 2.0
        self.volatility_z_max = 2.5
        self.displacement_z_max = 3.0
        self.absorption_score_min = 0.5

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if timestamp - self.last_fire_ts.get(symbol, 0) < self.cooldown:
            return None

        from decision.engine.profile_manager import profile_manager

        sensor_params = profile_manager.get_sensor_params(symbol, "absorption_detector")
        if sensor_params:
            self.z_score_min = sensor_params.get("z_score_min", self.z_score_min)
            self.cooldown = sensor_params.get("cooldown", self.cooldown)
            self.level_tolerance_pct = sensor_params.get("level_tolerance_pct", self.level_tolerance_pct)
            self.volatility_z_max = sensor_params.get("volatility_z_max", self.volatility_z_max)
            self.displacement_z_max = sensor_params.get("displacement_z_max", self.displacement_z_max)
            self.absorption_score_min = sensor_params.get("absorption_score_min", self.absorption_score_min)

        state = self.pressure.get_state(symbol)

        # 1. Absorption score check
        if state.absorption_score < self.absorption_score_min:
            return None

        # 2. CVD velocity z-score filter (avoid low-confidence absorption)
        if abs(state.cvd_velocity) < self.z_score_min:
            return None

        # 3. Volatility filter (avoid extreme chop/chaos)
        if abs(state.volatility_z) > self.volatility_z_max:
            return None

        # 4. Price displacement filter (avoid fading extreme moves)
        if abs(state.price_displacement_z) > self.displacement_z_max:
            return None

        # 5. Block signals from PressureEngine (anti-fade protection)
        if state.block_long and state.cvd_delta < 0:
            return None
        if state.block_short and state.cvd_delta > 0:
            return None

        # 6. Structural level proximity
        poc = structural_levels.get("poc", 0.0)
        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)

        if poc <= 0:
            return None

        near_poc = abs(price - poc) <= (poc * self.level_tolerance_pct)
        near_vah = vah > 0 and abs(price - vah) <= (vah * self.level_tolerance_pct)
        near_val = val > 0 and abs(price - val) <= (val * self.level_tolerance_pct)

        if not (near_poc or near_vah or near_val):
            return None

        side = "LONG" if state.cvd_delta < 0 else "SHORT"

        self.last_fire_ts[symbol] = timestamp

        return {
            "symbol": symbol,
            "side": side,
            "score": state.absorption_score,
            "price": price,
            "timestamp": timestamp,
            "scenario": "tactical_absorption",
            "tactical_type": self.name,
        }
