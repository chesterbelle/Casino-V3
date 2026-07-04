"""
Scenario ④: Trend Acceptance — "VA Breakout + Confirming Delta + Pullback"

AMT Narrative:
    Price leaves the VA with strong delta confirmation. The market is
    genuinely accepting new prices. The entry is on the pullback to
    the broken level (now acting as support/resistance).

Entry conditions:
    1. Price EXITS the VA with CVD confirmation
    2. Price EXTENDS beyond the broken level (minimum breakout distance)
    3. Price PULLS BACK toward the broken level without re-entering VA
    4. Regime filter: VA stable, POC not migrating, vol not expanding

Signal: At the pullback to the broken level
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("AMTScenarios.TrendAcceptance")


class TrendAcceptanceDetector:
    def __init__(self, pressure_engine, params=None, context_registry=None) -> None:
        self.name = "TrendAcceptance"
        self.pressure = pressure_engine
        self.context_registry = context_registry
        self.active_breakouts: Dict[str, dict] = {}
        self.last_fire_ts = defaultdict(float)
        self._cluster_cache: Dict[str, dict] = {}

        # Fallback defaults
        self.cooldown = 600.0
        self.cvd_confirmation_threshold = 5.0
        self.pullback_bps = 12.0
        self.min_breakout_distance_bps = 20.0

        # Regime filter thresholds (can be overridden by profile)
        self.regime_poc_migration_max = 0.005
        self.regime_vol_ratio_max = 1.5
        self.regime_va_expansion_max = 1.1

    def reset_for_symbol(self, symbol: str) -> None:
        """Clear per-symbol state at daily boundary."""
        self.active_breakouts.pop(symbol, None)
        self.last_fire_ts.pop(symbol, None)
        self._cluster_cache.pop(symbol, None)

    def _get_params(self, symbol: str) -> dict:
        if symbol in self._cluster_cache:
            return self._cluster_cache[symbol]
        try:
            from decision.engine.param_validation import validate_params
            from decision.engine.profile_manager import profile_manager

            params = profile_manager.get_sensor_params(symbol, "trend_acceptance")
            params = validate_params(params or {}, "trend_acceptance")

            # Load regime filter thresholds from profile
            if params:
                self.regime_poc_migration_max = params.get("regime_poc_migration_max", self.regime_poc_migration_max)
                self.regime_vol_ratio_max = params.get("regime_vol_ratio_max", self.regime_vol_ratio_max)
                self.regime_va_expansion_max = params.get("regime_va_expansion_max", self.regime_va_expansion_max)
        except ImportError:
            params = {}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception("Error loading params for %s: %s", symbol, e)
            params = {}
        self._cluster_cache[symbol] = params
        return params

    def cleanup(self, symbol: str, now_ts: float, max_age: float = 3600.0) -> None:
        """Remove stale breakout state for a symbol."""
        if symbol in self.active_breakouts:
            if now_ts - self.active_breakouts[symbol]["timestamp"] > max_age:
                del self.active_breakouts[symbol]
        # Clean up old last_fire_ts entries
        if symbol in self.last_fire_ts:
            if now_ts - self.last_fire_ts[symbol] > max_age:
                del self.last_fire_ts[symbol]

    def _is_regime_favorable(self, symbol: str) -> bool:
        """
        Check if market regime is favorable for trend_acceptance.

        Returns False (block signal) if:
        - POC migrating too fast (unstable value area)
        - Volatility ratio too high (chop/expansion, not trend)
        - VA expanding too fast (transition, not acceptance)

        Uses ContextRegistry for real-time regime metrics.
        """
        if not self.context_registry:
            return True  # No registry = allow (backward compat)

        # 1. POC Migration - fast migration = unstable VA
        poc_migration = self.context_registry.get_poc_migration(symbol)
        if abs(poc_migration) > self.regime_poc_migration_max:
            logger.debug(
                f"🛡️ [TA REGIME] {symbol} blocked: POC migration {poc_migration:.4f} > {self.regime_poc_migration_max}"
            )
            return False

        # 2. Volatility Ratio - high ratio = chop/expansion not clean trend
        vol_ratio = self.context_registry.get_volatility_ratio(symbol)
        if vol_ratio > self.regime_vol_ratio_max:
            logger.debug(f"🛡️ [TA REGIME] {symbol} blocked: vol_ratio {vol_ratio:.2f} > {self.regime_vol_ratio_max}")
            return False

        # 3. VA Expansion - rapid expansion = transition not acceptance
        va_integrity = self.context_registry.get_va_integrity(symbol)
        # Low integrity = expanding VA = transition
        if va_integrity > 0 and va_integrity < 0.15:
            logger.debug(f"🛡️ [TA REGIME] {symbol} blocked: va_integrity {va_integrity:.3f} < 0.15 (expanding VA)")
            return False

        return True

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[Dict[str, Any]]:
        if price <= 0:
            return None

        params = self._get_params(symbol)
        cooldown = params.get("cooldown", self.cooldown)
        cvd_confirmation_threshold = params.get("cvd_confirmation_threshold", self.cvd_confirmation_threshold)
        # Bridge profile naming: pullback_tolerance_pct (pct) → pullback_bps
        pullback_bps = params.get("pullback_bps", self.pullback_bps)
        if "pullback_tolerance_pct" in params and "pullback_bps" not in params:
            pullback_bps = params["pullback_tolerance_pct"] * 10000
        min_breakout_distance_bps = params.get("min_breakout_distance_bps", self.min_breakout_distance_bps)
        if "max_pullback_penetration_pct" in params and "min_breakout_distance_bps" not in params:
            min_breakout_distance_bps = params["max_pullback_penetration_pct"] * 10000

        if timestamp - self.last_fire_ts.get(symbol, 0) < cooldown:
            return None

        vah = structural_levels.get("vah", 0.0)
        val = structural_levels.get("val", 0.0)
        # Validate structural levels
        if vah <= 0 or val <= 0 or vah <= val:
            return None

        state = self.pressure.get_state(symbol)
        if state is None:
            return None
        cvd_slope = state.cvd_velocity

        # --- Handle existing breakout state ---
        if symbol in self.active_breakouts:
            bo = self.active_breakouts[symbol]
            signal = self._process_active_breakout(
                bo, symbol, price, vah, val, cvd_slope, timestamp, pullback_bps, min_breakout_distance_bps
            )
            if signal is not None:
                return signal
            if bo.get("cancelled", False):
                del self.active_breakouts[symbol]
            return None

        # --- Initiate new breakout if price exits VA with CVD confirmation ---
        is_above = price > vah
        is_below = price < val

        # Regime filter: block new breakouts in unfavorable regime
        if not self._is_regime_favorable(symbol):
            return None

        if is_above and cvd_slope > cvd_confirmation_threshold:
            self.active_breakouts[symbol] = {
                "direction": "long",
                "breakout_price": price,
                "max_price": price,
                "closest_to_vah": price,
                "timestamp": timestamp,
                "cancelled": False,
            }
        elif is_below and cvd_slope < -cvd_confirmation_threshold:
            self.active_breakouts[symbol] = {
                "direction": "short",
                "breakout_price": price,
                "min_price": price,
                "closest_to_val": price,
                "timestamp": timestamp,
                "cancelled": False,
            }

        return None

    def _process_active_breakout(
        self,
        bo: dict,
        symbol: str,
        price: float,
        vah: float,
        val: float,
        cvd_slope: float,
        timestamp: float,
        pullback_bps: float,
        min_breakout_distance_bps: float,
    ) -> Optional[Dict[str, Any]]:
        if bo["direction"] == "long":
            return self._process_long_breakout(
                bo, symbol, price, vah, cvd_slope, timestamp, pullback_bps, min_breakout_distance_bps
            )
        else:
            return self._process_short_breakout(
                bo, symbol, price, val, cvd_slope, timestamp, pullback_bps, min_breakout_distance_bps
            )

    def _process_long_breakout(
        self,
        bo: dict,
        symbol: str,
        price: float,
        vah: float,
        cvd_slope: float,
        timestamp: float,
        pullback_bps: float,
        min_breakout_distance_bps: float,
    ) -> Optional[Dict[str, Any]]:
        if price > bo["max_price"]:
            bo["max_price"] = price

        if price > vah and price < bo["closest_to_vah"]:
            bo["closest_to_vah"] = price

        # Price re-entered VA → breakout cancelled
        if price <= vah:
            bo["cancelled"] = True
            return None

        pullback_level = vah * (1 + pullback_bps / 10000)
        if price <= pullback_level:
            # Regime filter: confirm regime still favorable at pullback
            if not self._is_regime_favorable(symbol):
                bo["cancelled"] = True
                return None
            breakout_distance_bps = (bo["max_price"] / vah - 1) * 10000
            if breakout_distance_bps >= min_breakout_distance_bps:
                logger.debug(
                    "LONG trend_acceptance %s @ %.2f (breakout %.2f -> max %.2f, %.1fbps)",
                    symbol,
                    price,
                    vah,
                    bo["max_price"],
                    breakout_distance_bps,
                )
                bo["cancelled"] = True
                self.last_fire_ts[symbol] = timestamp
                score = min(1.0, max(0.3, abs(cvd_slope) / 3.0))
                return {
                    "symbol": symbol,
                    "side": "LONG",
                    "score": score,
                    "price": price,
                    "timestamp": timestamp,
                    "scenario": "trend_acceptance",
                }

        return None

    def _process_short_breakout(
        self,
        bo: dict,
        symbol: str,
        price: float,
        val: float,
        cvd_slope: float,
        timestamp: float,
        pullback_bps: float,
        min_breakout_distance_bps: float,
    ) -> Optional[Dict[str, Any]]:
        if price < bo["min_price"]:
            bo["min_price"] = price

        if price < val and price > bo["closest_to_val"]:
            bo["closest_to_val"] = price

        if price >= val:
            bo["cancelled"] = True
            return None

        pullback_level = val * (1 - pullback_bps / 10000)
        if price >= pullback_level:
            # Regime filter: confirm regime still favorable at pullback
            if not self._is_regime_favorable(symbol):
                bo["cancelled"] = True
                return None
            breakout_distance_bps = (1 - bo["min_price"] / val) * 10000
            if breakout_distance_bps >= min_breakout_distance_bps:
                logger.debug(
                    "SHORT trend_acceptance %s @ %.2f (breakout %.2f -> min %.2f, %.1fbps)",
                    symbol,
                    price,
                    val,
                    bo["min_price"],
                    breakout_distance_bps,
                )
                bo["cancelled"] = True
                self.last_fire_ts[symbol] = timestamp
                score = min(1.0, max(0.3, abs(cvd_slope) / 3.0))
                return {
                    "symbol": symbol,
                    "side": "SHORT",
                    "score": score,
                    "price": price,
                    "timestamp": timestamp,
                    "scenario": "trend_acceptance",
                }

        return None
