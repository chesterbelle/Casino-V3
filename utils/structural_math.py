"""
Utilidades Matemáticas Estructurales (LTA V7)
---------------------------------------------
Módulo de cálculo puro extraído de SetupEngine para determinar:
- Nodos de Bajo Volumen (LVN) para targets dinámicos.
"""

import logging
from typing import Optional

logger = logging.getLogger("StructuralMath")


def calculate_lvn_target(symbol: str, entry_price: float, side: str) -> Optional[float]:
    """
    LTA V7: LVN-based dynamic Take Profit.
    Identifies the first liquidity gap (LVN) in the trade direction.
    """
    try:
        from core.footprint_registry import footprint_registry

        # Look up to 0.60% for a target
        range_pct = 0.0060
        if side == "LONG":
            p_from, p_to = entry_price, entry_price * (1 + range_pct)
        else:
            p_from, p_to = entry_price * (1 - range_pct), entry_price

        profile = footprint_registry.get_volume_profile(symbol, p_from, p_to)
        if len(profile) < 5:
            return None

        # LVN = volume < 50% of average in the range
        avg_vol = sum(ask + bid for _, ask, bid in profile) / len(profile)
        lvn_threshold = avg_vol * 0.5

        lvns = [p for p, ask, bid in profile if (ask + bid) < lvn_threshold]
        if not lvns:
            return None

        if side == "LONG":
            # First LVN ABOVE entry
            targets = [p for p in lvns if p > entry_price * 1.0010]
            return min(targets) if targets else None
        else:
            # First LVN BELOW entry
            targets = [p for p in lvns if p < entry_price * 0.9990]
            return max(targets) if targets else None
    except Exception as e:
        logger.error(f"❌ Error calculating LVN target: {e}")
        return None
