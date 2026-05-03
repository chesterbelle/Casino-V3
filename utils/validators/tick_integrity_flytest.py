import logging
import sqlite3

from core.symbol_manager import symbol_mapper
from core.tick_registry import tick_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Flytest")


def run_integrity_flytest():
    """
    FLYTEST: Tick Integrity Auditor.
    Compares Inferred Resolution (Silicon Eye) vs Exchange Spec.
    Ensures structural universality.
    """
    logger.info("🦅 Launching Tick Integrity Flytest...")

    # In a real scenario, this would query live state or a persistence layer.
    # For this audit, we will check the current in-memory cache of the registry.

    results = []
    for symbol, cached_tick in tick_registry._cache.items():
        observed_min = tick_registry._observed_min_diff.get(symbol)

        if observed_min:
            drift = abs(cached_tick - observed_min) / cached_tick
            status = "MATCH" if drift < 0.01 else "DRIFT_DETECTED"

            results.append(
                {
                    "symbol": symbol,
                    "cached": cached_tick,
                    "observed": observed_min,
                    "drift_pct": drift * 100,
                    "status": status,
                }
            )
        else:
            results.append(
                {
                    "symbol": symbol,
                    "cached": cached_tick,
                    "observed": "NO_DATA",
                    "drift_pct": 0,
                    "status": "WAITING_SAMPLES",
                }
            )

    print("\n📊 TICK INTEGRITY FLYTEST REPORT")
    print(f"{'Symbol':15s} {'Cached':>10} {'Observed':>10} {'Drift %':>10} {'Status':>15}")
    print("-" * 65)

    for r in results:
        color = "✅" if r["status"] == "MATCH" else "❌" if r["status"] == "DRIFT_DETECTED" else "⏳"
        print(
            f"{r['symbol']:15s} {r['cached']:10.6f} {str(r['observed']):>10} {r['drift_pct']:10.2f}% {color} {r['status']:15s}"
        )


if __name__ == "__main__":
    run_integrity_flytest()
