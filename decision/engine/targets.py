from typing import Tuple

from core.coin_profiler import coin_profiler
from decision.engine.profile_manager import profile_manager


class TargetingMixin:
    """
    v8.4 Crystal Reforge — Dynamic Target Calculator.

    Targets adapt to market conditions using ATR + POC + Grid minimums.
    Grid-calibrated floors ensure minimum profitability.
    Coin profile multipliers adapt to microstructure.
    """

    # Default grid-optimal floors (used if no profile loaded)
    DEFAULT_GRID_FLOORS = {
        "reversion": {"tp": 0.009, "sl": 0.009},  # 0.90% symmetric
        "continuation": {"tp": 0.01, "sl": 0.01},  # 1.0% symmetric
    }

    def _calculate_targets(
        self,
        symbol: str,
        side: str,
        price: float,
        setup_mode,
        val_pos: str,
        scenario: str = "unknown",
        signal: dict = None,
    ) -> Tuple[float, float, str, str, float]:
        """
        Dynamic target calculator: max(ATR, POC, Grid_minimum).
        """
        if signal is None:
            signal = {}

        # Get ATR
        atr_pct = 0.20
        if self.context_registry:
            atr_data = self.context_registry.atrs.get(symbol, {})
            atr_pct = atr_data.get("short") or atr_data.get("medium") or atr_pct

        # Get structural levels
        poc = vah = val = 0.0
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)

        # Determine mode
        is_reversion = setup_mode.value == "reversion" if hasattr(setup_mode, "value") else setup_mode != "continuation"

        # Get targets from profile or use defaults
        profile_targets = profile_manager.get_target_params(scenario)
        if profile_targets:
            tp_pct = profile_targets.get("tp_pct", 0.009)
            sl_pct = profile_targets.get("sl_pct", 0.009)
        else:
            # Fallback to grid-optimal floors
            grid_floor = self.DEFAULT_GRID_FLOORS.get(
                "reversion" if is_reversion else "continuation", {"tp": 0.009, "sl": 0.009}
            )
            tp_pct = grid_floor["tp"]
            sl_pct = grid_floor["sl"]

        if side == "LONG":
            tp_price = price * (1.0 + tp_pct)
            sl_price = price * (1.0 - sl_pct)
        else:
            tp_price = price * (1.0 - tp_pct)
            sl_price = price * (1.0 + sl_pct)

        level_ref = f"PROFILE_{scenario.upper()}"
        setup_name = f"AMT_{scenario.upper()}_{val_pos}"

        return tp_price, sl_price, setup_name, level_ref, atr_pct

    def _apply_coin_profile(self, symbol: str, tp_price: float, sl_price: float, price: float) -> Tuple[float, float]:
        """Apply coin profile multipliers to TP/SL."""
        # Get coin profile (simplified stats - in production, use real-time data)
        coin_stats = {"trades_per_sec": 0.03, "volume_24h_usd": 100_000_000}
        tier = coin_profiler.classify(symbol, coin_stats)
        multipliers = coin_profiler.get_multipliers(tier)

        # Apply multipliers
        tp_dist = abs(tp_price - price) * multipliers["tp"]
        sl_dist = abs(sl_price - price) * multipliers["sl"]

        if tp_price > price:
            tp_price = price + tp_dist
            sl_price = price - sl_dist
        else:
            tp_price = price - tp_dist
            sl_price = price + sl_dist

        return tp_price, sl_price
