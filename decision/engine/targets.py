from typing import Tuple


class TargetingMixin:
    """
    v8.4 Crystal Reforge — Dynamic Target Calculator.

    Targets adapt to market conditions using ATR + POC + Grid minimums.
    Grid-calibrated floors ensure minimum profitability.
    """

    # Grid-optimal floors per scenario (from Uniform Grid analysis)
    GRID_FLOORS = {
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

        if is_reversion:
            # REVERSION: Dynamic TP/SL with 0.90% floor
            grid_floor = self.GRID_FLOORS["reversion"]

            # TP: max(POC_distance, ATR×1.5, grid_floor)
            atr_tp = atr_pct * 1.5 / 100.0
            if poc > 0:
                poc_dist = abs(poc - price) / price
                tp_pct = max(atr_tp, poc_dist, grid_floor["tp"])
            else:
                tp_pct = max(atr_tp, grid_floor["tp"])

            # SL: max(ATR×1.5, grid_floor)
            sl_pct = max(atr_pct * 1.5 / 100.0, grid_floor["sl"])

            if side == "LONG":
                tp_price = price * (1.0 + tp_pct)
                sl_price = price * (1.0 - sl_pct)
            else:
                tp_price = price * (1.0 - tp_pct)
                sl_price = price * (1.0 + sl_pct)

            level_ref = "REVERSION_DYNAMIC"
            setup_name = f"AMT_{scenario.upper()}_REVERSION_{val_pos}"

        else:
            # CONTINUATION: Dynamic TP/SL with 1.0% floor
            grid_floor = self.GRID_FLOORS["continuation"]

            # TP: max(ATR×1.5, grid_floor)
            tp_pct = max(atr_pct * 1.5 / 100.0, grid_floor["tp"])

            # SL: max(ATR×1.0, grid_floor)
            sl_pct = max(atr_pct * 1.0 / 100.0, grid_floor["sl"])

            if side == "LONG":
                tp_price = price * (1.0 + tp_pct)
                sl_price = price * (1.0 - sl_pct)
            else:
                tp_price = price * (1.0 - tp_pct)
                sl_price = price * (1.0 + sl_pct)

            level_ref = "CONTINUATION_DYNAMIC"
            setup_name = f"AMT_{scenario.upper()}_CONTINUATION_{val_pos}"

        return tp_price, sl_price, setup_name, level_ref, atr_pct
