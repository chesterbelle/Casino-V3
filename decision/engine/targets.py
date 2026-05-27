from typing import Tuple


class TargetingMixin:
    """
    Handles TP/SL calculations using Auction Market Theory geometry.
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
        Phase 800: AMT Structural Target Calculator.

        Derives TP and SL from Auction Market Theory geometry (POC, VAH, VAL)
        instead of ATR-based multipliers. Each reversion setup has a distinct
        geometric formula based on the expected dynamics within the Value Area.
        """
        if signal is None:
            signal = {}

        atr_pct = 0.20
        if self.context_registry:
            atr_data = self.context_registry.atrs.get(symbol, {})
            if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                atr_pct = atr_data.get("medium") or atr_data.get("short") or atr_pct
            else:
                atr_pct = atr_data.get("short") or atr_data.get("medium") or atr_pct

        applied_dynamic = False
        tp_price = price
        sl_price = price

        poc = vah = val = 0.0
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)

        if poc > 0 and vah > 0 and val > 0 and vah > val:
            va_width = vah - val
            noise_floor_tp = max(atr_pct * 1.5, 0.15) / 100.0
            noise_floor_sl = max(atr_pct * 1.0, 0.10) / 100.0

            AMT_CONFIG = {
                "TacticalAbsorptionV2": ("OPPOSITE", 0.3),
                "absorption_reversal": ("POC", 0.3),
                "failed_breakout": ("OPPOSITE", 0.5),
                "liquidity_exhaustion": ("OPPOSITE", 0.3),
            }

            cfg = AMT_CONFIG.get(scenario)
            if cfg:
                tp_target, sl_buf = cfg
                if side == "LONG":
                    tp_price = vah if tp_target == "OPPOSITE" else poc
                    sl_price = val - (va_width * sl_buf)
                else:
                    tp_price = val if tp_target == "OPPOSITE" else poc
                    sl_price = vah + (va_width * sl_buf)

                if (side == "LONG" and tp_price > price and sl_price < price) or (
                    side == "SHORT" and tp_price < price and sl_price > price
                ):
                    applied_dynamic = True

                    tp_dist = abs(tp_price - price) / price
                    sl_dist = abs(sl_price - price) / price

                    if tp_dist < noise_floor_tp:
                        tp_price = price * (1.0 + noise_floor_tp) if side == "LONG" else price * (1.0 - noise_floor_tp)

                    if sl_dist < noise_floor_sl:
                        sl_price = price * (1.0 - noise_floor_sl) if side == "LONG" else price * (1.0 + noise_floor_sl)

                    setup_name = f"AMT_{scenario.upper()}_{val_pos}"
                    level_ref = "AMT_STRUCTURAL_LEVEL"

        if not applied_dynamic:
            MULTIPLIERS = {
                "TacticalAbsorptionV2": 5.0,
                "absorption_reversal": 5.0,
                "trend_acceptance": 4.5,
                "failed_breakout": 2.5,
                "liquidity_exhaustion": 2.5,
            }
            mult = MULTIPLIERS.get(scenario, 2.5)
            if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                tp_dist_pct = atr_pct * mult
                sl_dist_pct = atr_pct * 3.33
            else:
                tp_dist_pct = atr_pct * mult
                sl_dist_pct = atr_pct * (mult * 0.8)
            tp_dec = tp_dist_pct / 100.0
            sl_dec = sl_dist_pct / 100.0
            if side == "LONG":
                tp_price = price * (1.0 + tp_dec)
                sl_price = price * (1.0 - sl_dec)
            else:
                tp_price = price * (1.0 - tp_dec)
                sl_price = price * (1.0 + sl_dec)
            setup_name = f"AMT_{scenario.upper()}_{val_pos}"
            level_ref = f"VAR_AWARE_{mult}x_ATR"

        return tp_price, sl_price, setup_name, level_ref, atr_pct
