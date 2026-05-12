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

logger = logging.getLogger("ScenarioManager")


class ScenarioManager:
    def __init__(self, footprint_registry, context_registry):
        self.footprint = footprint_registry
        self.context = context_registry

        # Scenario Detectors
        self.scenarios = [FailedBreakoutDetector(), LiquidityExhaustionDetector(), TrendAcceptanceDetector()]

        # Confirmation Middleware (Confirmation Lane)
        self.guardian = AbsorptionReversalGuardian()

        logger.info("🏗️ ScenarioManager initialized (AMT V10 Architecture)")

    def on_tick(self, symbol: str, price: float, timestamp: float) -> Optional[dict]:
        """
        Main orchestration logic called on every tick.

        1. Check Confirmation Lane (Guardian) for pending signals.
        2. Check Fast Lane (AMT Scenarios) for new structural signals.
        """
        # --- CARRIL DE CONFIRMACIÓN (Micro-Flow) ---
        # Si el Guardian confirma una señal pendiente (ej. Absorción), sale de inmediato.
        confirmed_signal = self.guardian.on_tick(symbol, price, timestamp)
        if confirmed_signal:
            return confirmed_signal

        # --- CARRIL RÁPIDO (Estructural AMT) ---
        # Evaluamos escenarios que no requieren confirmación de micro-flujo (FailedBreakout, etc.)
        for scenario in self.scenarios:
            signal = scenario.on_tick(symbol, price, timestamp, self.context, self.footprint)
            if signal:
                # Estos escenarios disparan instantáneamente al detectar el patrón estructural
                signal["needs_micro_confirmation"] = False
                return signal

        return None

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
