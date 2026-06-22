import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from sensors.quant.volatility_regime import RollingZScore


@dataclass
class PressureState:
    cvd_delta: float = 0.0
    cvd_session_delta: float = 0.0
    cvd_velocity: float = 0.0
    imbalance_ratio: float = 0.0
    volatility_z: float = 0.0
    absorption_score: float = 0.0
    absorption_score_v2: float = 0.0
    timestamp: float = 0.0
    price_displacement_z: float = 0.0
    block_long: bool = False
    block_short: bool = False
    z_concentration: float = 0.0
    z_noise: float = 0.0
    window_buy_vol: float = 0.0
    window_sell_vol: float = 0.0


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
        self.cvd_session = 0.0
        self._last_cvd_session_reset_ts = 0.0
        self._cvd_session_reset_interval = 14400.0  # 4 hours — covers all window transitions
        self.cvd_history = deque(maxlen=200)
        self.velocity_zscore = RollingZScore(window_size=200)
        self.concentration_zscore = RollingZScore(window_size=500)
        self.noise_zscore = RollingZScore(window_size=500)
        self._trade_aggr_window = deque(maxlen=100)
        self._window_buy_vol = 0.0
        self._window_sell_vol = 0.0

        # Legacy params for absorption_score (retained for signal dict backward compat)
        self.concentration_min = 0.50
        self.noise_max = 0.35

        self._load_params()

        self.absorption_snapshots = 0
        self.last_price = 0.0
        self.last_trade_price = 0.0

        self.price_history = deque(maxlen=200)
        self.price_returns = deque(maxlen=200)

    def reset_cvd_session(self):
        """Resets session-scoped CVD and z-scores to eliminate drift across liquidity windows."""
        self.cvd_session = 0.0
        self._last_cvd_session_reset_ts = 0.0
        self.velocity_zscore = RollingZScore(window_size=200)
        self.concentration_zscore = RollingZScore(window_size=500)
        self.noise_zscore = RollingZScore(window_size=500)

    def _check_cvd_session_reset(self, ts: float):
        """Auto-reset CVD session if enough time has passed (window transition)."""
        if self._last_cvd_session_reset_ts == 0.0:
            self._last_cvd_session_reset_ts = ts
        elif ts - self._last_cvd_session_reset_ts > self._cvd_session_reset_interval:
            self.cvd_session = 0.0
            self._last_cvd_session_reset_ts = ts

    def _load_params(self):
        try:
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(self.symbol, "absorption_detector")
            self.stagnation_floor_pct = params.get("stagnation_floor_pct", 0.0008) if params else 0.0008
            self.book_bucket_pct = params.get("book_bucket_pct", 0.0) if params else 0.0
            self.concentration_min = params.get("concentration_min", 0.50) if params else 0.50
            self.noise_max = params.get("noise_max", 0.35) if params else 0.35

            # Load z_block from pressure_thresholds in profile
            pressure_params = profile_manager.get_pressure_thresholds(self.symbol)
            self.z_block = pressure_params.get("z_block", 2.0) if pressure_params else 2.0
        except ImportError:
            # profile_manager no disponible — valores por defecto
            self.stagnation_floor_pct = 0.0008
            self.book_bucket_pct = 0.0
            self.z_block = 2.0
            self.concentration_min = 0.50
            self.noise_max = 0.35
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Error loading params for %s: %s", self.symbol, e)
            self.stagnation_floor_pct = 0.0008
            self.book_bucket_pct = 0.0
            self.z_block = 2.0
            self.concentration_min = 0.50
            self.noise_max = 0.35

    def update(
        self, qty: float, is_buyer_maker: bool, ts: float, price: float, footprint_levels: Optional[Dict] = None
    ):
        self._check_cvd_session_reset(ts)

        if qty > 0:
            if is_buyer_maker:
                self.current_cvd -= qty
                self.cvd_session -= qty
                buy_qty, sell_qty = 0.0, qty
            else:
                self.current_cvd += qty
                self.cvd_session += qty
                buy_qty, sell_qty = qty, 0.0

            self.cvd_history.append((ts, self.current_cvd))
            self.last_state.cvd_delta = self.current_cvd
            self.last_state.cvd_session_delta = self.cvd_session
            self.last_trade_price = price

            if len(self.cvd_history) > 2:
                dt = ts - self.cvd_history[-2][0]
                if dt > 0:
                    raw_velocity = abs(self.current_cvd - self.cvd_history[-2][1]) / dt
                    self.velocity_zscore.update(raw_velocity)
                    self.last_state.cvd_velocity = self.velocity_zscore.get_zscore(raw_velocity)

            # Trade flow window for concentration/noise
            if len(self._trade_aggr_window) == self._trade_aggr_window.maxlen:
                old_buy, old_sell = self._trade_aggr_window[0]
                self._window_buy_vol -= old_buy
                self._window_sell_vol -= old_sell
            self._trade_aggr_window.append((buy_qty, sell_qty))
            self._window_buy_vol += buy_qty
            self._window_sell_vol += sell_qty

        ref_price = self.last_trade_price if self.last_trade_price > 0 else self.last_price
        price_diff_pct = abs(price - ref_price) / ref_price if ref_price > 0 else 0.0
        is_high_delta = abs(self.last_state.cvd_velocity) > 0.1
        is_price_stagnant = price_diff_pct < self.stagnation_floor_pct

        tick_absorption = 0.3 if (is_high_delta and is_price_stagnant) else 0.0

        if footprint_levels:
            sorted_levels = sorted(footprint_levels.items(), key=lambda x: abs(x[1].get("delta", 0)), reverse=True)
            if sorted_levels:
                best_level, data = sorted_levels[0]

                if self.book_bucket_pct > 0.0:
                    best_price = float(best_level)
                    consolidated_ask = 0.0
                    consolidated_bid = 0.0
                    tolerance = best_price * self.book_bucket_pct
                    for price_lvl, lvl_data in footprint_levels.items():
                        if abs(price_lvl - best_price) <= tolerance:
                            consolidated_ask += lvl_data.get("ask_volume", 0)
                            consolidated_bid += lvl_data.get("bid_volume", 0)

                    total_vol = consolidated_ask + consolidated_bid
                    if total_vol > 0:
                        concentration = max(consolidated_ask, consolidated_bid) / total_vol
                        noise = min(consolidated_ask, consolidated_bid) / total_vol
                    else:
                        concentration = 1.0
                        noise = 0.0
                else:
                    ask_vol, bid_vol = data.get("ask_volume", 0), data.get("bid_volume", 0)
                    total_vol = ask_vol + bid_vol
                    if total_vol > 0:
                        concentration = max(ask_vol, bid_vol) / total_vol
                        noise = min(ask_vol, bid_vol) / total_vol
                    else:
                        concentration = 1.0
                        noise = 0.0

                if total_vol > 0:
                    # Legacy score (umbrales fijos)
                    conc_norm = max(
                        0, (concentration - self.concentration_min) / max(1 - self.concentration_min, 0.001)
                    )
                    noise_norm = max(0, (self.noise_max - noise) / max(self.noise_max, 0.001))
                    self.last_state.absorption_score = min(1.0, (conc_norm * noise_norm) ** 0.5)

                    # Z-score auto-calibrado (Fase 1+2)
                    self.concentration_zscore.update(concentration)
                    self.noise_zscore.update(noise)
                    self.last_state.z_concentration = self.concentration_zscore.get_zscore(concentration)
                    self.last_state.z_noise = self.noise_zscore.get_zscore(noise)

                    if self.concentration_zscore.is_ready and self.noise_zscore.is_ready:
                        z_conc = self.last_state.z_concentration
                        z_noise = self.last_state.z_noise
                        z_absorption = max(0.0, z_conc) + max(0.0, -z_noise)
                        self.last_state.absorption_score_v2 = min(1.0, z_absorption / 6.0)
                    else:
                        self.last_state.absorption_score_v2 = tick_absorption

                    self.absorption_snapshots += 1
                else:
                    self.last_state.absorption_score = tick_absorption
                    self.last_state.absorption_score_v2 = tick_absorption
        else:
            total_trade = self._window_buy_vol + self._window_sell_vol
            if total_trade > 0:
                concentration = max(self._window_buy_vol, self._window_sell_vol) / total_trade
                noise = min(self._window_buy_vol, self._window_sell_vol) / total_trade

                conc_norm = max(0, (concentration - self.concentration_min) / max(1 - self.concentration_min, 0.001))
                noise_norm = max(0, (self.noise_max - noise) / max(self.noise_max, 0.001))
                self.last_state.absorption_score = min(1.0, (conc_norm * noise_norm) ** 0.5)

                self.concentration_zscore.update(concentration)
                self.noise_zscore.update(noise)
                self.last_state.z_concentration = self.concentration_zscore.get_zscore(concentration)
                self.last_state.z_noise = self.noise_zscore.get_zscore(noise)

                if self.concentration_zscore.is_ready and self.noise_zscore.is_ready:
                    z_conc = self.last_state.z_concentration
                    z_noise = self.last_state.z_noise
                    z_absorption = max(0.0, z_conc) + max(0.0, -z_noise)
                    self.last_state.absorption_score_v2 = min(1.0, z_absorption / 6.0)
                else:
                    self.last_state.absorption_score_v2 = tick_absorption

                self.absorption_snapshots += 1
            else:
                self.last_state.absorption_score = tick_absorption
                self.last_state.absorption_score_v2 = tick_absorption

        if qty > 0:
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
        self.last_state.block_long = (
            cvd_sell and (displaced_high or self.last_state.block_long) and not (cvd_buy and displaced_low)
        )
        self.last_state.block_short = (
            cvd_buy and (displaced_low or self.last_state.block_short) and not (cvd_sell and displaced_high)
        )

        self.last_state.window_buy_vol = self._window_buy_vol
        self.last_state.window_sell_vol = self._window_sell_vol
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

    def zscore_velocity(self, raw_velocity: float) -> float:
        return self.velocity_zscore.get_zscore(raw_velocity)


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

    def zscore_velocity(self, symbol: str, raw_velocity: float) -> float:
        return self._get(symbol).zscore_velocity(raw_velocity)

    def update_from_orderbook(self, symbol: str, bids: list, asks: list, ts: float) -> None:
        self._get(symbol).update_from_orderbook(bids, asks, ts)

    def reset_cvd_session(self, symbol: str) -> None:
        """Resets session-scoped CVD for a symbol to eliminate drift."""
        self._get(symbol).reset_cvd_session()
