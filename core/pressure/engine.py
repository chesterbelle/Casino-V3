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


class CoinPressureEngine:
    """
    Estado de presión para UN símbolo.
    CVD, price history y parámetros de perfil aislados por moneda.
    Los parámetros se obtienen de profile_manager en creación.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.last_state = PressureState()

        self.current_cvd = 0.0
        self.cvd_history = deque(maxlen=200)
        self.velocity_zscore = RollingZScore(window_size=200)

        self._load_params()

        self.absorption_snapshots = 0
        self.last_price = 0.0

        self.price_history = deque(maxlen=200)
        self.price_returns = deque(maxlen=200)

    def _load_params(self):
        try:
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(self.symbol, "absorption_detector")
            self.concentration_min = params.get("concentration_min", 0.50) if params else 0.50
            self.noise_max = params.get("noise_max", 0.35) if params else 0.35
            self.stagnation_floor_pct = params.get("stagnation_floor_pct", 0.0008) if params else 0.0008

            # Load z_block from pressure_thresholds in profile
            pressure_params = profile_manager.get_pressure_thresholds(self.symbol)
            self.z_block = pressure_params.get("z_block", 2.0) if pressure_params else 2.0
        except Exception:
            self.concentration_min = 0.50
            self.noise_max = 0.35
            self.stagnation_floor_pct = 0.0008
            self.z_block = 2.0

    def update(
        self, qty: float, is_buyer_maker: bool, ts: float, price: float, footprint_levels: Optional[Dict] = None
    ):
        if qty > 0:
            if is_buyer_maker:
                self.current_cvd -= qty
            else:
                self.current_cvd += qty

            self.cvd_history.append((ts, self.current_cvd))
            self.last_state.cvd_delta = self.current_cvd

            if len(self.cvd_history) > 2:
                dt = ts - self.cvd_history[-2][0]
                if dt > 0:
                    raw_velocity = abs(self.current_cvd - self.cvd_history[-2][1]) / dt
                    self.velocity_zscore.update(raw_velocity)
                    self.last_state.cvd_velocity = self.velocity_zscore.get_zscore(raw_velocity)

        price_diff_pct = abs(price - self.last_price) / self.last_price if self.last_price > 0 else 0.0
        is_high_delta = abs(self.last_state.cvd_velocity) > 0.1
        is_price_stagnant = price_diff_pct < self.stagnation_floor_pct

        tick_absorption = 0.3 if (is_high_delta and is_price_stagnant) else 0.0

        if footprint_levels:
            sorted_levels = sorted(footprint_levels.items(), key=lambda x: abs(x[1].get("delta", 0)), reverse=True)
            if sorted_levels:
                best_level, data = sorted_levels[0]
                ask_vol, bid_vol = data.get("ask_volume", 0), data.get("bid_volume", 0)
                total_vol = ask_vol + bid_vol

                if total_vol > 0:
                    concentration = max(ask_vol, bid_vol) / total_vol
                    noise = min(ask_vol, bid_vol) / total_vol

                    conc_norm = max(
                        0, (concentration - self.concentration_min) / max(1 - self.concentration_min, 0.001)
                    )
                    noise_norm = max(0, (self.noise_max - noise) / max(self.noise_max, 0.001))
                    self.last_state.absorption_score = min(1.0, (conc_norm * noise_norm) ** 0.5)
                else:
                    self.last_state.absorption_score = tick_absorption
        else:
            self.last_state.absorption_score = tick_absorption

        if self.last_price > 0:
            ret = price / self.last_price - 1
            self.price_returns.append(ret)
            if len(self.price_returns) >= 10:
                mu = sum(self.price_returns) / len(self.price_returns)
                var = sum((r - mu) ** 2 for r in self.price_returns) / len(self.price_returns)
                sigma = var**0.5
                self.last_state.volatility_z = (abs(ret) - mu) / sigma if sigma > 0 else 0.0

        self.price_history.append(price)
        if len(self.price_history) >= 20:
            mu_p = sum(self.price_history) / len(self.price_history)
            var_p = sum((p - mu_p) ** 2 for p in self.price_history) / len(self.price_history)
            sigma_p = var_p**0.5
            if sigma_p > 0:
                self.last_state.price_displacement_z = (price - mu_p) / sigma_p

        cvd_sell = self.last_state.cvd_delta < 0
        cvd_buy = self.last_state.cvd_delta > 0
        displaced_high = self.last_state.price_displacement_z > self.z_block
        displaced_low = self.last_state.price_displacement_z < -self.z_block
        self.last_state.block_long = cvd_sell and displaced_high
        self.last_state.block_short = cvd_buy and displaced_low

        self.last_price = price
        self.last_state.timestamp = ts

    def update_from_orderbook(self, bids: list, asks: list, ts: float) -> None:
        bids = [
            (float(p) if not isinstance(p, float) else p, float(q) if not isinstance(q, float) else q) for p, q in bids
        ]
        asks = [
            (float(p) if not isinstance(p, float) else p, float(q) if not isinstance(q, float) else q) for p, q in asks
        ]
        mid = (bids[0][0] + asks[0][0]) / 2 if bids and asks else 0.0
        levels = {}
        for price, qty in asks[:15]:
            levels[price] = {"ask_volume": qty, "bid_volume": 0, "delta": qty}
        for price, qty in bids[:15]:
            if price in levels:
                levels[price]["bid_volume"] = qty
                levels[price]["delta"] = levels[price]["ask_volume"] - qty
            else:
                levels[price] = {"ask_volume": 0, "bid_volume": qty, "delta": -qty}
        self.update(0, True, ts, mid, levels)

    def get_state(self) -> PressureState:
        return self.last_state


class PressureEngine:
    """
    Facade — mantiene un CoinPressureEngine por símbolo.
    Los escenarios reciben esta instancia y llaman get_state(symbol).
    Una sola instancia compartida entre SensorManager y SetupEngine.
    """

    def __init__(self):
        self._engines: Dict[str, CoinPressureEngine] = {}

    def _get(self, symbol: str) -> CoinPressureEngine:
        if symbol not in self._engines:
            self._engines[symbol] = CoinPressureEngine(symbol)
        return self._engines[symbol]

    def update(
        self,
        symbol: str,
        qty: float,
        is_buyer_maker: bool,
        ts: float,
        price: float,
        footprint_levels: Optional[Dict] = None,
    ):
        self._get(symbol).update(qty, is_buyer_maker, ts, price, footprint_levels)

    def get_state(self, symbol: str) -> PressureState:
        return self._get(symbol).get_state()

    def update_from_orderbook(self, symbol: str, bids: list, asks: list, ts: float) -> None:
        self._get(symbol).update_from_orderbook(bids, asks, ts)
