from collections import defaultdict
from typing import Any, Dict, Optional


class AbsorptionDetector:
    """
    Absorption Detector v9+: Cooldown + Structural Level Filter.
    Consumes PressureEngine centralized state.
    Only fires ONCE per absorption event (not every tick during absorption).
    """

    def __init__(self, pressure_engine) -> None:
        self.pressure = pressure_engine
        self.name = "TacticalAbsorptionV2"
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self.cooldown = 120.0
        self.level_tolerance_pct = 0.003

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if timestamp - self.last_fire_ts[symbol] < self.cooldown:
            return None

        state = self.pressure.get_state()

        if state.absorption_score < 0.5:
            return None

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

        if abs(state.cvd_velocity) < 0.5:
            return None

        if state.cvd_delta == 0:
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
