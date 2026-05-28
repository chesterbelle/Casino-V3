from typing import Tuple


class TargetingMixin:
    """
    v8.4 Crystal Reforge — Simplified Target Calculator.

    Two modes:
    1. Reversion (Scenarios 1, 2, 3): TP = POC, SL = 1.5× ATR
    2. Continuation (Scenario 4): TP = 1.5× ATR, SL = 1.0× ATR
    """

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
        Simplified target calculator for v8.4 Crystal Reforge.
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

        # Determine if reversion or continuation
        is_reversion = setup_mode.value == "reversion" if hasattr(setup_mode, "value") else setup_mode != "continuation"

        # v8.4 Simplified Logic
        if is_reversion:
            # REVERSION: TP = POC, SL = 1.5× ATR
            if poc > 0:
                tp_price = poc
            else:
                # Fallback: 1.5× ATR
                tp_dist = price * atr_pct * 1.5 / 100.0
                tp_price = price + tp_dist if side == "LONG" else price - tp_dist

            sl_dist = price * atr_pct * 1.5 / 100.0
            sl_price = price - sl_dist if side == "LONG" else price + sl_dist

            level_ref = "REVERSION_POC" if poc > 0 else "REVERSION_ATR"
            setup_name = f"AMT_{scenario.upper()}_REVERSION_{val_pos}"

        else:
            # CONTINUATION: TP = 1.5× ATR, SL = 1.0× ATR
            tp_dist = price * atr_pct * 1.5 / 100.0
            sl_dist = price * atr_pct * 1.0 / 100.0

            if side == "LONG":
                tp_price = price + tp_dist
                sl_price = price - sl_dist
            else:
                tp_price = price - tp_dist
                sl_price = price + sl_dist

            level_ref = "CONTINUATION_ATR"
            setup_name = f"AMT_{scenario.upper()}_CONTINUATION_{val_pos}"

        # Enforce minimum distances
        min_tp_pct = 0.001  # 0.1%
        min_sl_pct = 0.001  # 0.1%

        tp_dist_pct = abs(tp_price - price) / price
        sl_dist_pct = abs(sl_price - price) / price

        if tp_dist_pct < min_tp_pct:
            tp_price = price * (1.0 + min_tp_pct) if side == "LONG" else price * (1.0 - min_tp_pct)

        if sl_dist_pct < min_sl_pct:
            sl_price = price * (1.0 - min_sl_pct) if side == "LONG" else price * (1.0 + min_sl_pct)

        return tp_price, sl_price, setup_name, level_ref, atr_pct
