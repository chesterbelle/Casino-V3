"""
Utilidades Matemáticas Estructurales (LTA V7)
---------------------------------------------
Módulo de cálculo puro extraído de SetupEngine para determinar:
- Proximidad a niveles estructurales (Location Gates).
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


def check_level_proximity(symbol: str, price: float, context_registry, fast_track: bool = False) -> Optional[dict]:
    """
    Phase 700: Check if price is within proximity of a structural level.
    Returns the nearest level reference dict or None if price is in open space.
    Levels checked: POC, VAH, VAL, IBH, IBL.
    """
    if not context_registry or price <= 0:
        return None

    poc, vah, val = context_registry.get_structural(symbol)
    ib_high, ib_low = context_registry.get_ib(symbol)

    levels = []
    if poc > 0:
        levels.append(("POC", poc))
    if vah > 0:
        levels.append(("VAH", vah))
    if val > 0:
        levels.append(("VAL", val))
    if ib_high and ib_high > 0:
        levels.append(("IBH", ib_high))
    if ib_low and ib_low > 0:
        levels.append(("IBL", ib_low))

    PROX_THRESHOLD = 1.0 if fast_track else 0.0035  # Synchronized with LTA_PROXIMITY_THRESHOLD (0.35%)

    nearest = None
    min_dist = float("inf")
    for name, level_price in levels:
        dist = abs(price - level_price) / price
        if dist < PROX_THRESHOLD and dist < min_dist:
            min_dist = dist
            nearest = {"level_ref": name, "level_price": level_price, "dist_pct": round(dist * 100, 4)}

    return nearest
