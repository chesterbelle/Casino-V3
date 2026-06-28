import logging
from collections import defaultdict
from typing import Any, Dict, Optional


class AbsorptionDetector:
    """
    Absorption Detector v10: Profile-Calibrated + Multi-Factor Filter.
    Consumes OrderFlowEngine centralized state.
    Only fires ONCE per absorption event (not every tick during absorption).

    Consumes OrderFlowEngine centralized state.
    Only fires ONCE per absorption event (not every tick during absorption).

    Resolves cluster-specific params at runtime via profile_manager.
    """

    def __init__(self, pressure_engine, params=None) -> None:
        self.pressure = pressure_engine
        self.name = "tactical_absorption"
        self.last_fire_ts: Dict[str, float] = defaultdict(float)
        self._cluster_cache: Dict[str, dict] = {}

        # Fallback defaults (used only if profile_manager lookup fails)
        self.cooldown = 180.0
        self.level_tolerance_pct = 0.003
        self.z_score_min = 2.0
        self.volatility_z_max = 2.5
        self.displacement_z_max = 3.0
        self.absorption_score_min = 0.5

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.param_validation import validate_params
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "absorption_detector")
            params = validate_params(params or {}, "absorption")
        except ImportError:
            params = {}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Error loading params for %s: %s", symbol, e)
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if price <= 0:
            return None

        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        level_tolerance_pct = params.get("level_tolerance_pct", self.level_tolerance_pct)
        z_score_min = params.get("z_score_min", self.z_score_min)
        volatility_z_max = params.get("volatility_z_max", self.volatility_z_max)
        displacement_z_max = params.get("displacement_z_max", self.displacement_z_max)
        absorption_score_min = params.get("absorption_score_min", self.absorption_score_min)

        if timestamp - self.last_fire_ts.get(symbol, 0) < cooldown:
            return None

        state = self.pressure.get_state(symbol)
        if state is None:
            return None

        # 1. Minimum absolute volume guard (avoid signals in illiquid windows)
        total_window_vol = state.window_buy_vol + state.window_sell_vol
        min_vol = params.get("min_window_volume", 100.0)
        if total_window_vol < min_vol:
            return None

        # 2. Absorption score check (z-score auto-calibrado)
        if state.absorption_score_v2 < absorption_score_min:
            return None

        # 3. CVD velocity z-score filter (avoid low-confidence absorption)
        if abs(state.cvd_velocity) < z_score_min:
            return None

        # 4. Volatility filter (avoid extreme chop/chaos)
        if abs(state.volatility_z) > volatility_z_max:
            return None

        # 5. Price displacement filter (avoid fading extreme moves)
        if abs(state.price_displacement_z) > displacement_z_max:
            return None

        # 6. Block signals from OrderFlowEngine (anti-fade protection)
        if state.block_long and state.cvd_delta < 0:
            return None
        if state.block_short and state.cvd_delta > 0:
            return None

        # 7. Structural level proximity
        poc = structural_levels.get("poc", 0.0)
        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)

        if poc <= 0:
            return None

        near_poc = abs(price - poc) <= (poc * level_tolerance_pct)
        near_vah = vah > 0 and abs(price - vah) <= (vah * level_tolerance_pct)
        near_val = val > 0 and abs(price - val) <= (val * level_tolerance_pct)

        if not (near_poc or near_vah or near_val):
            return None

        side = "LONG" if state.cvd_session_delta < 0 else "SHORT"

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
