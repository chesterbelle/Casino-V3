import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("FailedAuctionGuardian")


def check_failed_auction(
    symbol: str, side: str, reversal_signal: dict, context_registry, recent_extremes: dict, fast_track: bool
) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="FAILED_AUCTION")

    poc, vah, val = context_registry.get_structural(symbol)
    price = reversal_signal.get("close", 0.0)
    high = reversal_signal.get("high", 0.0)
    low = reversal_signal.get("low", 0.0)

    recent = recent_extremes.get(symbol)
    if recent and len(recent) > 0:
        lookback_high = max(c["high"] for c in recent)
        lookback_low = min(c["low"] for c in recent)
        high = max(high, lookback_high) if high > 0 else lookback_high
        low = min(low, lookback_low) if low > 0 else lookback_low

    metrics = {
        "price": price,
        "high": high,
        "low": low,
        "val": val,
        "vah": vah,
        "lookback_candles": len(recent) if recent else 0,
    }

    if side == "LONG":
        if low > val:
            logger.info(f"🛡️ [FAILED_AUCTION] {symbol} LONG blocked: No probe below VAL ({low:.4f} > {val:.4f})")
            return GuardianResult(
                passed=False, multiplier=0.0, reason="No probe below edge", metrics=metrics, gate_name="FAILED_AUCTION"
            )

        if price > 0 and price < val:
            logger.info(
                f"🛡️ [FAILED_AUCTION] {symbol} LONG blocked: Price closed below VAL ({price:.4f} < {val:.4f}) — continuation, not rejection"
            )
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Close below edge — continuation",
                metrics=metrics,
                gate_name="FAILED_AUCTION",
            )

    if side == "SHORT":
        if high < vah:
            logger.info(f"🛡️ [FAILED_AUCTION] {symbol} SHORT blocked: No probe above VAH ({high:.4f} < {vah:.4f})")
            return GuardianResult(
                passed=False, multiplier=0.0, reason="No probe above edge", metrics=metrics, gate_name="FAILED_AUCTION"
            )

        if price > 0 and price > vah:
            logger.info(
                f"🛡️ [FAILED_AUCTION] {symbol} SHORT blocked: Price closed above VAH ({price:.4f} > {vah:.4f}) — continuation, not rejection"
            )
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Close above edge — continuation",
                metrics=metrics,
                gate_name="FAILED_AUCTION",
            )

    return GuardianResult(
        passed=True,
        multiplier=1.0,
        reason="Valid probe with close inside VA",
        metrics=metrics,
        gate_name="FAILED_AUCTION",
    )
