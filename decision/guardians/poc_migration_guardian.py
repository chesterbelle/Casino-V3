import logging

import config.strategies as strat_config

from .guardian_result import GuardianResult

logger = logging.getLogger("POCMigrationGuardian")


def check_poc_migration(symbol: str, side: str, context_registry, fast_track: bool) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="POC_MIGRATION")

    migration = context_registry.get_poc_migration(symbol, lookback_ticks=300)
    threshold = strat_config.LTA_POC_MIGRATION_THRESHOLD
    metrics = {"migration": round(migration, 6), "threshold": threshold}
    
    passed = True
    score = 1.0

    # Normalization: migration is positive for UP, negative for DOWN
    # For LONG: migration > 0 is good (score 1.0), migration < 0 is bad (decay)
    # For SHORT: migration < 0 is good (score 1.0), migration > 0 is bad (decay)

    if side == "LONG":
        if migration < -(threshold * 1.5):
            passed = False
            score = 0.0
        elif migration < 0:
            # Linear decay from 1.0 (at 0) to 0.1 (at -1.5*threshold)
            score = max(0.1, 1.0 + (migration / (threshold * 1.5)) * 0.9)
        else:
            score = 1.0
            
    elif side == "SHORT":
        if migration > (threshold * 1.5):
            passed = False
            score = 0.0
        elif migration > 0:
            # Linear decay from 1.0 (at 0) to 0.1 (at 1.5*threshold)
            score = max(0.1, 1.0 - (migration / (threshold * 1.5)) * 0.9)
        else:
            score = 1.0

    reason = "Hard migration against side" if not passed else "POC migration analyzed"
    
    return GuardianResult(
        passed=passed,
        score=round(score, 3),
        multiplier=1.0,
        reason=reason,
        metrics=metrics,
        gate_name="POC_MIGRATION",
    )
