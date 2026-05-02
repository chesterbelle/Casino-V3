import logging

import config.strategies as strat_config

from .guardian_result import GuardianResult

logger = logging.getLogger("POCMigrationGuardian")


def check_poc_migration(symbol: str, side: str, context_registry, fast_track: bool) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="POC_MIGRATION")

    migration = context_registry.get_poc_migration(symbol, lookback_ticks=300)
    threshold = strat_config.LTA_POC_MIGRATION_THRESHOLD
    metrics = {"migration": migration, "threshold": threshold}

    if side == "LONG" and migration < -threshold:
        if migration < -(threshold * 1.5):
            logger.info(f"🛡️ [POC_MIGRATION] {symbol} LONG blocked: POC migrated {migration:.4%} (hard discovery)")
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Hard migration against side",
                metrics=metrics,
                gate_name="POC_MIGRATION",
            )

        logger.info(f"🛡️ [POC_MIGRATION] {symbol} LONG soft-gate: POC migrated {migration:.4%} (soft discovery)")
        return GuardianResult(
            passed=True,
            multiplier=strat_config.LTA_SOFT_GATE_REDUCTION,
            reason="Soft migration against side",
            metrics=metrics,
            gate_name="POC_MIGRATION",
        )

    if side == "SHORT" and migration > threshold:
        if migration > (threshold * 1.5):
            logger.info(f"🛡️ [POC_MIGRATION] {symbol} SHORT blocked: POC migrated {migration:.4%} (hard discovery)")
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Hard migration against side",
                metrics=metrics,
                gate_name="POC_MIGRATION",
            )

        logger.info(f"🛡️ [POC_MIGRATION] {symbol} SHORT soft-gate: POC migrated {migration:.4%} (soft discovery)")
        return GuardianResult(
            passed=True,
            multiplier=strat_config.LTA_SOFT_GATE_REDUCTION,
            reason="Soft migration against side",
            metrics=metrics,
            gate_name="POC_MIGRATION",
        )

    return GuardianResult(
        passed=True, multiplier=1.0, reason="Healthy migration", metrics=metrics, gate_name="POC_MIGRATION"
    )
