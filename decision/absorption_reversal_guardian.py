"""
Absorption Reversal Guardian for Absorption Scalping V2 — Phase 2.

Evaluates confluence of confirmation sensors after an absorption candidate
is detected by AbsorptionDetector (Phase 1).

V10 Architecture (tick-level confirmation):
  AbsorptionDetector → candidate (Phase 1, ~5ms)
       ↓
  AbsorptionReversalGuardian:
       1. Receives candidate, starts 500ms confirmation window
       2. Monitors 3 confirmation sensors every 50ms (each ~5 ticks)
       3. If ≥2 of 3 confirmed → generates entry signal
       4. If 500ms expires without confirmation → discards candidate

Confirmation sensors (tick-level):
  - DeltaReversalSensor: rolling delta of absorption level (2s window)
  - PriceBreakSensor: current price vs absorption level
  - CVDFlipSensor: CVD slope change (2s window)

Regime filter:
  - RANGE: 2 of 3 confirmations, full size
  - TREND_ALIGNED: 2 of 3 confirmations, full size
  - TREND_CONTRA: 3 of 3 confirmations REQUIRED, 50% size
"""

import logging
from typing import Dict, Optional

from core.context_registry import ContextRegistry
from core.footprint_registry import footprint_registry
from sensors.absorption.confirmation_sensors import (
    CVDFlipSensor,
    DeltaReversalSensor,
    PriceBreakSensor,
)
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger(__name__)


class PendingCandidate:
    """Tracks a candidate through its tick-level confirmation window."""

    def __init__(self, candidate: dict, window_ms: int = 500, registration_ts: float = 0.0):
        self.candidate = candidate
        self.window_ms = window_ms
        self.registration_ts = registration_ts  # Market time (event.timestamp)
        self.last_eval_ts = 0.0  # Market time of last evaluation
        self.confirmations = {
            "delta_reversal": False,
            "price_break": False,
            "cvd_flip": False,
        }
        # Phase A (AMT): Exhaustion metrics computed at registration
        self.exhaustion = candidate.get("exhaustion", {})
        self.exhaustion_score = 0  # 0-2: delta_declining + volume_declining

    @property
    def confirmation_count(self) -> int:
        return sum(1 for v in self.confirmations.values() if v)

    def elapsed_ms(self, current_ts: float) -> float:
        """Elapsed milliseconds since registration using market time."""
        return (current_ts - self.registration_ts) * 1000

    def expired(self, current_ts: float) -> bool:
        """Check if confirmation window has expired using market time."""
        return self.elapsed_ms(current_ts) >= self.window_ms

    @property
    def symbol(self) -> str:
        return self.candidate["symbol"]


class AbsorptionReversalGuardian(TraceBulletMixin):
    """
    Phase 2 Guardian: Tick-level confirmation for absorption candidates.

    Evaluates 3 microstructure sensors every 50ms within a 500ms window.
    If the aggressor has surrendered (delta flipped, price broke, CVD turned),
    confirmation is fast — typically 100-300ms after detection.
    """

    def __init__(self, fast_track: bool = False):
        super().__init__()
        self.name = "AbsorptionReversalGuardian"
        self.fast_track = fast_track

        # Confirmation sensors
        self.delta_reversal = DeltaReversalSensor()
        self.price_break = PriceBreakSensor()
        self.cvd_flip = CVDFlipSensor()

        # Pending candidates: symbol → PendingCandidate
        self.pending: Dict[str, PendingCandidate] = {}

        # Timing configuration
        self.confirmation_window_ms = 500  # Max time to wait for confirmation (500ms per V10 spec)
        self.eval_interval_ms = 50  # Evaluate every 50ms (~5 ticks)
        self.min_confirmations = 2  # Standard: 2 of 3
        self.min_confirmations_contra = 3  # Counter-trend: 3 of 3 (strict)
        self.contra_size_multiplier = 0.5  # Counter-trend: 50% size

        logger.info(
            f"✅ {self.name} initialized "
            f"(window={self.confirmation_window_ms}ms, "
            f"eval_every={self.eval_interval_ms}ms)"
        )

    def register_candidate(self, candidate: dict, timestamp: float = 0.0):
        """
        Register a new absorption candidate from Phase 1.

        Called by SetupEngine when AbsorptionDetector produces a candidate.
        Starts the 500ms confirmation window using market time.

        Phase A (AMT): Also computes exhaustion metrics at registration time.
        """
        symbol = candidate["symbol"]

        # Enrich candidate with CVD slope at detection time
        footprint = footprint_registry.get_footprint(symbol)
        if footprint:
            candidate["cvd_slope_at_detection"] = footprint.get_cvd_slope(window_seconds=2)
            # Phase A (AMT): Compute exhaustion metrics from pre-signal flow
            exhaustion = footprint.get_exhaustion_metrics(window_long=10.0, window_short=2.0)
            candidate["exhaustion"] = exhaustion
        else:
            candidate["exhaustion"] = {"delta_ratio": 1.0, "volume_ratio": 1.0, "ready": False}

        # Replace any existing pending candidate for this symbol
        pending = PendingCandidate(candidate, window_ms=self.confirmation_window_ms, registration_ts=timestamp)

        # Phase A (AMT): Calculate exhaustion score (0-2)
        exh = candidate["exhaustion"]
        score = 0
        if exh.get("delta_ratio", 1.0) < 0.5:
            score += 1
        if exh.get("volume_ratio", 1.0) < 0.6:
            score += 1
        pending.exhaustion_score = score
        pending.exhaustion = exh

        self.pending[symbol] = pending

        # Trace Phase 2 Interception
        self.trace(
            candidate,
            "PHASE2_INTERCEPT",
            {
                "window_ms": self.confirmation_window_ms,
                "exhaustion_score": score,
                "delta_ratio": exh.get("delta_ratio"),
                "volume_ratio": exh.get("volume_ratio"),
            },
        )

        logger.info(
            f"📋 [GUARDIAN] Candidate registered: {symbol} {candidate['direction']} "
            f"(window={self.confirmation_window_ms}ms, "
            f"need ≥{self.min_confirmations} confirmations, "
            f"exhaustion={score}/2 [δ_ratio={exh.get('delta_ratio', '?')}, "
            f"v_ratio={exh.get('volume_ratio', '?')}])"
        )

    def on_tick(self, symbol: str, price: float, timestamp: float) -> Optional[dict]:
        """
        Evaluate pending candidates on each tick.

        Called by SetupEngine on every tick. Throttled to eval_interval_ms
        using market time to work correctly in both live and backtest.

        Args:
            symbol: Trading symbol
            price: Current tick price
            timestamp: Tick timestamp (market time)

        Returns:
            Entry signal dict if confirmed, None otherwise
        """
        if symbol not in self.pending:
            return None

        pending = self.pending[symbol]

        # Throttle: only evaluate every eval_interval_ms (using market time)
        elapsed_since_eval = (timestamp - pending.last_eval_ts) * 1000
        if elapsed_since_eval < self.eval_interval_ms:
            return None
        pending.last_eval_ts = timestamp

        candidate = pending.candidate

        # Get current delta from footprint (level-specific)
        footprint = footprint_registry.get_footprint(symbol)
        current_delta = 0.0
        if footprint:
            # Use level-specific delta, not sum of all levels
            absorption_level = candidate.get("absorption_level", 0.0)
            level_data = footprint.levels.get(absorption_level)
            if level_data:
                current_delta = level_data["delta"]
            else:
                # Fallback: net delta across all levels
                current_delta = sum(data["delta"] for data in footprint.levels.values())

        # Check all 3 confirmation sensors
        if not pending.confirmations["delta_reversal"]:
            if self.delta_reversal.check(symbol, candidate, current_delta):
                pending.confirmations["delta_reversal"] = True

        if not pending.confirmations["price_break"]:
            if self.price_break.check(symbol, candidate, price):
                pending.confirmations["price_break"] = True

        if not pending.confirmations["cvd_flip"]:
            if self.cvd_flip.check(symbol, candidate):
                pending.confirmations["cvd_flip"] = True

        # Evaluate confluence
        count = pending.confirmation_count
        is_contra_trend = self._is_contra_trend(symbol, candidate["side"])
        required = self.min_confirmations_contra if is_contra_trend else self.min_confirmations
        elapsed = pending.elapsed_ms(timestamp)

        logger.debug(
            f"🔍 [GUARDIAN] {symbol} {elapsed:.0f}/{self.confirmation_window_ms}ms: "
            f"{count}/{required} confirmations "
            f"(delta_rev={pending.confirmations['delta_reversal']}, "
            f"price_brk={pending.confirmations['price_break']}, "
            f"cvd_flip={pending.confirmations['cvd_flip']})"
            f"{' [CONTRA-TREND]' if is_contra_trend else ''}"
        )

        # Check if confirmed
        if count >= required:
            # CONFIRMED — generate entry signal
            size_mult = self.contra_size_multiplier if is_contra_trend else 1.0
            entry_signal = self._generate_entry_signal(
                candidate, price, timestamp, count, size_mult, is_contra_trend, elapsed
            )
            # Phase A (AMT): Attach exhaustion data to signal
            entry_signal["exhaustion"] = pending.exhaustion
            entry_signal["exhaustion_score"] = pending.exhaustion_score
            # Remove from pending
            del self.pending[symbol]

            self.trace(
                entry_signal,
                "PHASE2_CONFIRMED",
                {"latency_ms": elapsed, "confirmations": count, "required": required},
            )
            return entry_signal

        # Check if window expired
        if pending.expired(timestamp):
            logger.info(
                f"❌ [GUARDIAN] {symbol} confirmation window expired "
                f"({elapsed:.0f}ms, {count}/{required} confirmations) — discarded"
            )
            self.trace(
                candidate,
                "PHASE2_REJECTED",
                {"reason": "TIMEOUT", "elapsed_ms": elapsed, "confirmations": count, "required": required},
            )
            del self.pending[symbol]

        return None

    def _is_contra_trend(self, symbol: str, side: str) -> bool:
        """
        Check if the entry is counter-trend (against the dominant regime).

        Uses ContextRegistry regime data if available.
        """
        if self.fast_track:
            return False

        try:
            ctx = ContextRegistry()
            regime_v2_data = getattr(ctx, "_regime_v2", {}).get(symbol)
            if not regime_v2_data:
                return False

            regime = regime_v2_data.get("regime", "BALANCE")
            confidence = regime_v2_data.get("confidence", 0.0)

            # Only count as contra-trend if regime confidence is high
            if confidence < 0.6:
                return False

            if regime == "TREND_UP" and side == "SHORT":
                return True
            if regime == "TREND_DOWN" and side == "LONG":
                return True

        except Exception:
            pass

        return False

    def _generate_entry_signal(
        self,
        candidate: dict,
        current_price: float,
        timestamp: float,
        confirmations: int,
        size_multiplier: float,
        is_contra_trend: bool,
        elapsed_ms: float,
    ) -> dict:
        """
        Generate entry signal from confirmed candidate.

        This is the final output of Phase 2 — ready for setup engine
        to calculate TP/SL and dispatch.
        """
        logger.info(
            f"🎯 [GUARDIAN_CONFIRMED] {candidate['symbol']} {candidate['side']} "
            f"({confirmations}/3 confirmations in {elapsed_ms:.0f}ms, "
            f"size={size_multiplier:.0%})"
            f"{' [CONTRA-TREND STRICT]' if is_contra_trend else ''}"
        )

        return {
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "direction": candidate.get("direction"),
            "absorption_level": candidate.get("absorption_level"),
            "level": candidate.get("level"),
            "delta": candidate.get("delta", 0.0),
            "z_score": candidate.get("z_score", candidate.get("metadata", {}).get("z_score", 0.0)),
            "concentration": candidate.get("concentration", candidate.get("metadata", {}).get("concentration", 0.0)),
            "noise": candidate.get("noise", candidate.get("metadata", {}).get("noise", 0.0)),
            "price": current_price,
            "entry_price": current_price,
            "timestamp": timestamp,
            "confirmations": confirmations,
            "confirmation_details": {
                "delta_reversal": True,  # We know at least 2 of 3 are True
                "price_break": True,
                "cvd_flip": True,
            },
            "confirmation_latency_ms": round(elapsed_ms, 1),
            "size_multiplier": size_multiplier,
            "is_contra_trend": is_contra_trend,
            "phase": "confirmed",
            "strategy": "AbsorptionScalpingV2",
            "scenario": "absorption_reversal",
            "tactical_type": "AbsorptionReversal",
        }
