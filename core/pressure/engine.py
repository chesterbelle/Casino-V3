from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from sensors.quant.volatility_regime import RollingZScore


@dataclass
class PressureState:
    cvd_delta: float = 0.0
    cvd_velocity: float = 0.0
    imbalance_ratio: float = 0.0
    volatility_z: float = 0.0
    absorption_score: float = 0.0
    timestamp: float = 0.0
    price_displacement_z: float = 0.0
    block_long: bool = False
    block_short: bool = False


class PressureEngine:
    """
    Motor centralizado de medición de presión.
    Calcula métricas de microestructura de forma agnóstica.
    """

    def __init__(self, profile_params: Optional[Dict] = None):
        self.last_state = PressureState()
        # CVD variables
        self.current_cvd = 0.0
        self.cvd_history = deque(maxlen=200)

        # Z-Score normalizer
        self.velocity_zscore = RollingZScore(window_size=200)

        # Absorption parameters
        self.z_score_min = profile_params.get("z_score_min", 3.0) if profile_params else 3.0
        self.concentration_min = profile_params.get("concentration_min", 0.50) if profile_params else 0.50
        self.noise_max = profile_params.get("noise_max", 0.35) if profile_params else 0.35

        # Absorption tracking
        self.absorption_snapshots = 0
        self.last_price = 0.0

        # Volatility and displacement tracking
        self.price_history = deque(maxlen=200)
        self.price_returns = deque(maxlen=200)

    def update(
        self, qty: float, is_buyer_maker: bool, ts: float, price: float, footprint_levels: Optional[Dict] = None
    ):
        """
        Engine centralizado: Presión normalizada + Detección de anomalías.
        """
        # 1. CVD Calculation (Raw)
        if is_buyer_maker:
            self.current_cvd -= qty
        else:
            self.current_cvd += qty

        self.cvd_history.append((ts, self.current_cvd))
        self.last_state.cvd_delta = self.current_cvd

        # 2. Velocity with Z-Score Normalization
        if len(self.cvd_history) > 2:
            dt = ts - self.cvd_history[-2][0]
            if dt > 0:
                raw_velocity = abs(self.current_cvd - self.cvd_history[-2][1]) / dt
                self.velocity_zscore.update(raw_velocity)
                self.last_state.cvd_velocity = self.velocity_zscore.get_zscore(raw_velocity)

        # 3. Absorption Mechanics
        price_diff = abs(price - self.last_price) if self.last_price > 0 else 0.0
        is_high_delta = abs(self.last_state.cvd_velocity) > 0.1
        is_price_stagnant = price_diff < 0.10

        tick_absorption = 1.0 if (is_high_delta and is_price_stagnant) else 0.0

        # 4. Footprint Refinement (Contexto)
        if footprint_levels:
            # Concentración y Ruido
            sorted_levels = sorted(footprint_levels.items(), key=lambda x: abs(x[1].get("delta", 0)), reverse=True)
            if sorted_levels:
                best_level, data = sorted_levels[0]
                ask_vol, bid_vol = data.get("ask_volume", 0), data.get("bid_volume", 0)
                delta = data.get("delta", 0)
                total_vol = ask_vol + bid_vol

                if total_vol > 0:
                    concentration = (ask_vol if delta > 0 else bid_vol) / total_vol
                    noise = (ask_vol if delta < 0 else bid_vol) / total_vol

                    if concentration >= self.concentration_min and noise <= self.noise_max:
                        self.last_state.absorption_score = 1.0
                    else:
                        self.last_state.absorption_score = 0.0
        else:
            self.last_state.absorption_score = tick_absorption

        self.last_price = price
        self.last_state.timestamp = ts

    def get_state(self) -> PressureState:
        return self.last_state
