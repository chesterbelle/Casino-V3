"""
SignalArbitrator — Orchestrator V10.

Centralizes confirmation scenarios (AMT) and arbitrates signals by priority × score.
TacticalAbsorption bypasses this (instant signal). Other 3 scenarios (FB/LE/TA) flow through here.

Architecture:
    SetupEngine -> SignalArbitrator.on_tick() -> Signal or None
    SetupEngine.on_signal() -> Signal or None

NOTA: Antes se llamaba "ScenarioManager". El nombre era engañoso — esto no "gestiona" scenarios,
arbitra señales por prioridad y aplica filtros (VA_GATE).
"""

import logging
from collections import defaultdict
from typing import Optional

from decision.engine.profile_manager import profile_manager
from decision.scenarios.confirmation import (
    FailedBreakoutDetector,
    LiquidityExhaustionDetector,
    TrendAcceptanceDetector,
)

logger = logging.getLogger("SignalArbitrator")


class SignalArbitrator:
    def __init__(self, pressure_engine, context_registry=None):
        self.pressure = pressure_engine
        self.context_registry = context_registry

        # Solo 3 escenarios de confirmación (FB/LE/TA). TacticalAbsorption es
        # instant signal y bypasea SignalArbitrator intencionalmente (ver ADR-1).
        self.scenarios = [
            LiquidityExhaustionDetector(self.pressure),
            FailedBreakoutDetector(self.pressure),
            TrendAcceptanceDetector(self.pressure),
        ]

        # PRIORITY_MAP: Define precedence if multiple scenarios trigger in the same tick.
        # Higher number = Higher Priority.
        self.PRIORITY_MAP = {
            "liquidity_exhaustion": 100,
            "failed_breakout": 50,
            "trend_acceptance": 30,
        }

        # Telemetry
        self.signal_stats = defaultdict(int)

        logger.info("🏗️ SignalArbitrator initialized (AMT V10 Architecture - UDT Enabled)")

    def _apply_va_gate(self, symbol: str, candidates: list) -> list:
        """
        Apply selective VA_GATE based on profile config — AMT PURE LOGIC.
        Uses RegimeClassifier V1 to detect TRENDING or RANGE regime.
        """
        profile_name = profile_manager.get_profile_name(symbol)
        if not profile_name:
            return candidates  # No profile, allow all (backward compat)

        profile = profile_manager.get_profile(profile_name)
        if not profile:
            return candidates

        va_gate = profile.get("va_gate")
        if not va_gate:
            return candidates  # No va_gate config, allow all

        # Get block lists from profile config (with safe defaults)
        block_in_trending = set(
            va_gate.get("block_in_trending", ["failed_breakout", "liquidity_exhaustion", "tactical_absorption"])
        )
        block_in_range = set(va_gate.get("block_in_range", ["trend_acceptance"]))

        if not self.context_registry:
            return candidates

        from decision.regime_classifier import regime_classifier

        regime, metrics = regime_classifier.classify(symbol, self.context_registry, va_gate)

        if regime == "RANGE":
            # RANGE regime (VA intact) — borders respected)
            filtered = [sig for sig in candidates if sig.get("scenario") not in block_in_range]
            if len(filtered) != len(candidates):
                blocked = [s.get("scenario") for s in candidates if s.get("scenario") in block_in_range]
                logger.debug(f"🛡️ [VA_GATE RANGE] {symbol} votes={metrics.get('trend_votes')} — blocked: {blocked}")
        else:
            # TRENDING regime (VA — value migrating)
            filtered = [sig for sig in candidates if sig.get("scenario") not in block_in_trending]
            if len(filtered) != len(candidates):
                blocked = [s.get("scenario") for s in candidates if s.get("scenario") in block_in_trending]
                logger.debug(f"🛡️ [VA_GATE TREND] {symbol} votes={metrics.get('trend_votes')} — blocked: {blocked}")

        # Inject metrics into remaining candidates
        for sig in filtered:
            sig["regime_vote"] = regime
            sig["regime_metrics"] = metrics

        return filtered

    def on_tick(self, symbol: str, price: float, timestamp: float, structural_levels: dict) -> Optional[dict]:
        """
        Main orchestration logic (The Arbitrator).
        Fuses multiple signals in the same direction and resolves conflicts.
        """
        # 0. Structural setup done by Core/ContextRegistry
        # 1. Collect all candidate signals from Fast Lane
        candidates = []

        for scenario in self.scenarios:
            sig = scenario.on_tick(symbol, price, timestamp, structural_levels)
            if sig:
                scenario_key = sig.get("scenario", "unknown")
                sig["_priority"] = self.PRIORITY_MAP.get(scenario_key, 0)
                sig["_score"] = sig.get("score", 1.0)
                candidates.append(sig)

        if not candidates:
            return None

        # 2. Apply selective VA_GATE filter
        candidates = self._apply_va_gate(symbol, candidates)
        if not candidates:
            return None

        # 3. Arbitrate: Group by side — conviction = priority × score
        longs = [s for s in candidates if s["side"] == "LONG"]
        shorts = [s for s in candidates if s["side"] == "SHORT"]

        long_conviction = sum(s["_priority"] * s["_score"] for s in longs)
        short_conviction = sum(s["_priority"] * s["_score"] for s in shorts)

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
        self.signal_stats[scenario_name] += 1

        return best_signal

    def get_stats(self) -> dict:
        """Return signal distribution statistics."""
        return {"scenario_distribution": self.signal_stats, "total_signals": sum(self.signal_stats.values())}

    def on_candle(self, symbol: str, close: float, timestamp: float, structural_levels: dict):
        """Called on candle close to update scenario state (e.g. TrendAcceptance)."""
        for scenario in self.scenarios:
            if hasattr(scenario, "on_candle"):
                scenario.on_candle(symbol, close, timestamp, structural_levels)

    def on_signal(self, signal: dict, trace=None) -> Optional[dict]:
        """
        Routes external signals with UDT support.
        Passthrough: external signals are forwarded directly to SetupEngine.
        """
        tactical_type = signal.get("tactical_type")

        # UDT: Trace tactical signal arrival
        if trace:
            trace.add_step("SignalArbitrator", True, f"Routing {tactical_type} signal", {"side": signal.get("side")})

        return signal

    def reset(self):
        """Reset all scenario states."""
        for scenario in self.scenarios:
            if hasattr(scenario, "pending_breaks"):
                scenario.pending_breaks.clear()
            if hasattr(scenario, "level_tests"):
                scenario.level_tests.clear()
            if hasattr(scenario, "active_breakouts"):
                scenario.active_breakouts.clear()
