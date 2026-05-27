import logging
import time
from typing import Any, Dict

from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger("Telemetry")


class TelemetryMixin(TraceBulletMixin):
    """
    Handles all internal telemetry, trace propagation (UDT), and Historian metrics
    for the SetupEngine.
    """

    def _trace_decision(
        self,
        symbol: str,
        status: str,
        gate: str,
        reason: str,
        metrics: Dict[str, Any],
        price: float = 0.0,
        side: str = "",
    ):
        """Helper to fire internal decision traces to Historian."""
        import config.trading as trading_config

        if not getattr(trading_config, "ENABLE_DECISION_TRACE", False):
            return

        from core.observability.historian import historian as hist_local

        trace_data = {
            "timestamp": time.time(),
            "symbol": symbol,
            "status": status,
            "gate": gate,
            "reason": reason,
            "metrics": metrics,
            "price": price,
            "side": side,
        }
        # Debug console logging for active troubleshooting (Trace Bullet)
        if status == "REJECTED":
            logger.info(f"🚫 [GATE] {symbol} {side} {gate} REJECTED: {reason}")

        hist_local.record_decision_trace(trace_data)

    def log_scenario_distribution(self, scenario_manager) -> dict:
        """Expose distribution stats from ScenarioManager."""
        stats = scenario_manager.get_stats()
        dist = stats["scenario_distribution"]
        total = stats["total_signals"]

        logger.info("📊 --- SCENARIO DISTRIBUTION REPORT ---")
        for sc, count in dist.items():
            pct = (count / total * 100) if total > 0 else 0
            logger.info(f"🔹 {sc:20}: {count:3} ({pct:5.1f}%)")
        logger.info(f"📈 TOTAL SIGNALS DISPATCHED: {total}")
        return stats
