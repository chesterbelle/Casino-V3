import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("FailedAuctionGuardian")


def check_failed_auction(
    symbol: str, side: str, reversal_signal: dict, context_registry, recent_extremes: dict, fast_track: bool
) -> GuardianResult:
    """
    BYPASSED: Iteration Mode (Absorption Focus)
    Allows all trades to pass through to test Exit Engine quality.
    """
    return GuardianResult(
        passed=True, multiplier=1.0, reason="BYPASSED for EXPRIMIDOR iteration", gate_name="FAILED_AUCTION"
    )
