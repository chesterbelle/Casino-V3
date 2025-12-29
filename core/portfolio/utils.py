from typing import Any


def get_position_notional(position: Any) -> float:
    """Return notional for a position, handling dicts and objects.

    Notional is amount/contracts * entry_price.
    """
    notional = 0.0
    try:
        if isinstance(position, dict):
            notional = position.get("notional") or (position.get("amount", 0) * position.get("entry_price", 0))
        else:
            notional = getattr(position, "notional", None)
            if notional is None:
                size = getattr(position, "size", 0)
                entry_price = getattr(position, "entry_price", 0)
                notional = size * entry_price
    except Exception:
        notional = 0.0
    return float(notional or 0.0)


def calculate_position_pnl(position: Any, exit_price: float, fee: float) -> float:
    """Calculate PnL for a given position safely.

    This function handles position representations both as dicts and objects
    and extracts notional safely.
    """
    try:
        side = None
        if isinstance(position, dict):
            side = (position.get("side") or "").upper()
            entry_price = float(position.get("entry_price", 0))
        else:
            side = getattr(position, "side", "")
            entry_price = getattr(position, "entry_price", 0)
            side = side.upper() if isinstance(side, str) else side

        if side == "LONG" or str(side).lower() == "buy":
            pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0
        else:  # SHORT
            pnl_pct = (entry_price - exit_price) / entry_price if entry_price else 0.0

        notional = get_position_notional(position)
        pnl = notional * pnl_pct
        pnl -= fee
        return pnl
    except Exception:
        return 0.0
