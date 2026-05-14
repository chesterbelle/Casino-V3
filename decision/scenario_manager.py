"""
Scenario Manager — Orchestrator V10.

Centralizes all tactical scenarios (AMT, Absorption) and manages the dispatch pipeline.
Distinguishes between Fast Lane (Instant) and Confirmation Lane (Guardian) signals.

Architecture:
    SetupEngine -> ScenarioManager.on_tick() -> Signal or None
    SetupEngine -> ScenarioManager.on_signal() -> Signal or None
"""

import logging
from typing import Optional

from decision.absorption_reversal_guardian import AbsorptionReversalGuardian
from decision.amt_scenarios import (
    FailedBreakoutDetector,
    LiquidityExhaustionDetector,
    TrendAcceptanceDetector,
)
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger("ScenarioManager")


class ScenarioManager(TraceBulletMixin):
    def __init__(self, footprint_registry, context_registry):
        super().__init__()
        self.footprint = footprint_registry
        self.context = context_registry

        # Scenario Detectors - Reordered by statistical precedence (Best edge first)
        self.scenarios = [
            LiquidityExhaustionDetector(),  # Highest Edge (~0.32%)
            FailedBreakoutDetector(),  # Tactical Mean Reversion (~0.09%)
            TrendAcceptanceDetector(),  # Momentum/Trend
        ]

        # PRIORITY_MAP: Define precedence if multiple scenarios trigger in the same tick.
        # Higher number = Higher Priority.
        self.PRIORITY_MAP = {
            "liquidity_exhaustion": 100,
            "failed_breakout": 50,
            "trend_acceptance": 30,
            "absorption_reversal": 80,  # Guarded signal priority
        }

        # Telemetry
        self.signal_stats = {}

        # Confirmation Middleware (Confirmation Lane)
        self.guardian = AbsorptionReversalGuardian()

        logger.info("🏗️ ScenarioManager initialized (AMT V10 Architecture - Priority Scrutiny enabled)")

    def on_tick(self, symbol: str, price: float, timestamp: float) -> Optional[dict]:
        """
        Main orchestration logic (The Arbitrator).
        Fuses multiple signals in the same direction and resolves conflicts.
        """
        # 1. Collect all candidate signals
        candidates = []

        # Confirmation Lane (Guarded signals)
        confirmed = self.guardian.on_tick(symbol, price, timestamp)
        if confirmed:
            confirmed["_priority"] = self.PRIORITY_MAP.get("absorption_reversal", 80)
            candidates.append(confirmed)

        # Fast Lane (Instant AMT scenarios)
        for scenario in self.scenarios:
            sig = scenario.on_tick(symbol, price, timestamp, self.context, self.footprint)
            if sig:
                scenario_key = sig.get("scenario", "unknown")
                sig["_priority"] = self.PRIORITY_MAP.get(scenario_key, 0)
                candidates.append(sig)

                # Trace Phase 1: Scenario Triggered
                self.trace(
                    sig,
                    "PHASE1_TRIGGERED",
                    {"scenario": scenario_key, "priority": sig["_priority"]},
                )

        if not candidates:
            return None

        # 2. Arbitrate: Group by side
        longs = [s for s in candidates if s["side"] == "LONG"]
        shorts = [s for s in candidates if s["side"] == "SHORT"]

        long_conviction = sum(s["_priority"] for s in longs)
        short_conviction = sum(s["_priority"] for s in shorts)

        # 3. Resolve Conflicts (High-Stakes Decision)
        if long_conviction > 0 and short_conviction > 0:
            # Conflict! Calculate delta
            diff = abs(long_conviction - short_conviction)
            if diff < 30:
                logger.warning(
                    f"⚔️ [CONFLICT] LONG({long_conviction}) vs SHORT({short_conviction}) | Diff {diff} too small. Neutralizing."
                )
                return None

            # Winner takes it all
            if long_conviction > short_conviction:
                winning_group = longs
                total_conviction = long_conviction
                logger.info(f"⚔️ [CONFLICT_RESOLVED] LONG wins ({long_conviction} vs {short_conviction})")
            else:
                winning_group = shorts
                total_conviction = short_conviction
                logger.info(f"⚔️ [CONFLICT_RESOLVED] SHORT wins ({short_conviction} vs {long_conviction})")
        else:
            # Single direction dominance
            winning_group = longs if long_conviction > 0 else shorts
            total_conviction = long_conviction if long_conviction > 0 else short_conviction

        if not winning_group:
            return None

        # 4. Fuse & Ranking
        # Pick the highest priority signal from the winning group as the template
        winning_group.sort(key=lambda x: x["_priority"], reverse=True)
        best_signal = winning_group[0]

        # Enrich with composite data
        best_signal["conviction_score"] = total_conviction
        best_signal["is_composite"] = len(winning_group) > 1
        best_signal["contributing_scenarios"] = [s.get("scenario") or s.get("tactical_type") for s in winning_group]

        # Telemetry: Track which scenario won
        scenario_name = best_signal.get("scenario", best_signal.get("tactical_type", "unknown"))
        self.signal_stats[scenario_name] = self.signal_stats.get(scenario_name, 0) + 1

        return best_signal

    def get_stats(self) -> dict:
        """Return signal distribution statistics."""
        return {"scenario_distribution": self.signal_stats, "total_signals": sum(self.signal_stats.values())}

    def on_candle(self, symbol: str, close: float, timestamp: float):
        """Called on candle close to update scenario state (e.g. TrendAcceptance)."""
        for scenario in self.scenarios:
            if hasattr(scenario, "on_candle"):
                scenario.on_candle(symbol, close, timestamp, self.context, self.footprint)

    def on_signal(self, signal: dict) -> Optional[dict]:
        """
        Handle signals from external sensors (e.g. AbsorptionDetector worker).
        Routes signals to the appropriate lane.
        """
        tactical_type = signal.get("tactical_type")

        # Lógica de Ruteo:
        # La Absorción REQUIERE confirmación de micro-flujo (Guardian)
        ABS_IDS = ("Absorption", "TacticalAbsorptionV2", "TacticalAbsorption", "AbsorptionDetector")
        if tactical_type in ABS_IDS:
            logger.debug(f"📥 [ROUTING] {tactical_type} signal sent to Confirmation Lane (Guardian)")
            self.guardian.register_candidate(signal, timestamp=signal.get("timestamp", 0.0))
            return None  # No se despacha aún

        # El Agotamiento (si viene de sensor externo) también podría requerir confirmación
        if tactical_type == "LiquidityExhaustion" and signal.get("needs_micro_confirmation", True):
            self.guardian.register_candidate(signal)
            return None

        # El resto son instantáneos
        return signal

    def reset(self):
        """Reset all scenario states."""
        self.guardian.candidates.clear()
        for scenario in self.scenarios:
            if hasattr(scenario, "pending_breaks"):
                scenario.pending_breaks.clear()
            if hasattr(scenario, "level_tests"):
                scenario.level_tests.clear()
            if hasattr(scenario, "active_breakouts"):
                scenario.active_breakouts.clear()
