"""
Absorption Detector for Absorption Scalping V2.

Detects absorption CANDIDATES (Phase 1) — aggressive volume without price displacement.
Runs in the MAIN PROCESS with direct FootprintRegistry access.

V2 Architecture (Two-Phase):
  PHASE 1 — DETECTION (this file):
    FootprintRegistry → AbsorptionDetector.on_candle()
       ↓
    4 Quality Filters (Magnitude, Velocity, Noise, Price Stagnation)
       ↓
    Candidate dict → AbsorptionReversalGuardian (Phase 2)

  PHASE 2 — CONFIRMATION (guardians/absorption_reversal_guardian.py):
    Candidate + 3 Confirmation Sensors (DeltaReversal, PriceBreak, CVDFlip)
       ↓
    ≥2 of 3 confirmed → Entry signal

Key V2 change: Price Stagnation is now a REQUIRED condition.
Delta extreme where price DID move is impulse, not absorption.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

from core.footprint_registry import footprint_registry

logger = logging.getLogger(__name__)


class AbsorptionDetector:
    """
    Detects absorption CANDIDATES from footprint data (Phase 1).

    Absorption = Aggressive volume without price displacement.
    Indicates exhaustion of the aggressor (buyer or seller).

    Quality Filters (4 in V2):
    1. Magnitude:   Cross-sectional z-score of delta > threshold
    2. Velocity:    Concentration of delta at level > threshold
    3. Noise:       Opposite-side volume ratio < threshold
    4. Stagnation:  Price did NOT move in direction of attack (NEW in V2)

    Returns a CANDIDATE dict (not an entry signal).
    The AbsorptionReversalGuardian handles Phase 2 confirmation.
    """

    def __init__(self):
        self.name = "AbsorptionDetector"

        # Filter thresholds (tuned for LTC/USDT backtests)
        self.z_score_min = 2.5  # Minimum |z-score| for magnitude
        self.concentration_min = 0.60  # Minimum concentration for velocity
        self.noise_max = 0.20  # Maximum noise ratio
        self.stagnation_max_pct = 0.05  # Max price move in attack direction (0.05%)

        # Candle history for stagnation check
        self._prev_candles: Dict[str, dict] = {}  # symbol → {open, high, low, close, ts}

        # Throttle: only analyze once per candle (not per tick)
        self._last_candle_ts: Dict[str, float] = {}

        logger.info(f"✅ {self.name} initialized (main-process mode)")

    def on_candle(
        self,
        symbol: str,
        timestamp: float,
        close_price: float,
        open_price: float = 0,
        high_price: float = 0,
        low_price: float = 0,
    ) -> Optional[dict]:
        """
        Analyze footprint for absorption on each candle close (Phase 1).

        Called directly from SetupEngine.on_candle_absorption (main process).
        Returns a CANDIDATE dict (not an entry signal).
        Phase 2 confirmation is handled by AbsorptionReversalGuardian.

        Args:
            symbol: Trading symbol
            timestamp: Candle close timestamp
            close_price: Candle close price
            open_price: Candle open price (for stagnation check)
            high_price: Candle high price (for stagnation check)
            low_price: Candle low price (for stagnation check)

        Returns:
            Candidate dict or None
        """
        # Throttle: one analysis per candle
        if self._last_candle_ts.get(symbol, 0) == timestamp:
            return None
        self._last_candle_ts[symbol] = timestamp

        # Get footprint from registry (lives in main process)
        footprint = footprint_registry.get_footprint(symbol)
        if not footprint or len(footprint.levels) < 5:
            return None

        # Find extreme delta levels (candidates)
        candidates = self._find_extreme_deltas(footprint)
        if not candidates:
            return None

        # Evaluate each candidate through quality filters
        for level, delta, ask_vol, bid_vol in candidates:
            # Filter 1: Magnitude (cross-sectional z-score)
            z_score = self._cross_sectional_zscore(footprint, delta)
            if abs(z_score) < self.z_score_min:
                continue

            # Filter 2: Velocity (concentration)
            concentration = self._concentration(footprint, level, timestamp)
            if concentration < self.concentration_min:
                continue

            # Filter 3: Noise (opposite-side volume)
            noise = self._noise_ratio(ask_vol, bid_vol, delta)
            if noise > self.noise_max:
                continue

            # Filter 4: Price Stagnation (V2 — CRITICAL)
            # Delta extreme where price DID move = impulse, not absorption
            direction = "SELL_EXHAUSTION" if delta < 0 else "BUY_EXHAUSTION"
            if not self._check_price_stagnation(symbol, direction, close_price, open_price, high_price, low_price):
                logger.debug(
                    f"❌ [ABSORPTION] Price moved in attack direction — not stagnation " f"({symbol} {direction})"
                )
                continue

            # All 4 filters passed → absorption CANDIDATE detected
            logger.info(
                f"🔍 [ABSORPTION_CANDIDATE] {symbol} {direction} "
                f"(z={z_score:.2f}, conc={concentration:.2f}, noise={noise:.2f}, stagnation=PASS)"
            )

            # Store candle for future stagnation checks
            self._prev_candles[symbol] = {
                "open": open_price or close_price,
                "high": high_price or close_price,
                "low": low_price or close_price,
                "close": close_price,
                "ts": timestamp,
            }

            return {
                "symbol": symbol,
                "level": level,
                "absorption_level": level,
                "direction": direction,
                "delta": delta,
                "z_score": z_score,
                "concentration": concentration,
                "noise": noise,
                "timestamp": timestamp,
                "ask_volume": ask_vol,
                "bid_volume": bid_vol,
                "price": close_price,
                "side": "LONG" if direction == "SELL_EXHAUSTION" else "SHORT",
                "phase": "candidate",  # V2: not yet confirmed
            }

        return None

    # ── Candidate Selection ──────────────────────────────────────────

    def _find_extreme_deltas(self, footprint) -> List[Tuple[float, float, float, float]]:
        """
        Find price levels with extreme delta (top 10%).

        Returns:
            List of (level, delta, ask_vol, bid_vol) sorted by |delta| desc
        """
        deltas = []
        for level, data in footprint.levels.items():
            delta = data["delta"]
            if abs(delta) > 0:
                deltas.append((level, delta, data["ask_volume"], data["bid_volume"]))

        if len(deltas) < 5:
            return []

        deltas.sort(key=lambda x: abs(x[1]), reverse=True)

        # Top 10% (at least 1, max 5)
        top_n = max(1, min(5, len(deltas) // 10))
        return deltas[:top_n]

    # ── Quality Filters ──────────────────────────────────────────────

    def _cross_sectional_zscore(self, footprint, delta: float) -> float:
        """
        Cross-sectional z-score: how extreme is this delta relative to
        ALL other deltas in the current footprint snapshot.

        This is superior to temporal z-score because:
        - No history accumulation needed (works from first candle)
        - No IPC state sync issues
        - Directly measures "is this level abnormal RIGHT NOW?"
        """
        all_deltas = [data["delta"] for data in footprint.levels.values()]
        if len(all_deltas) < 5:
            return 0.0

        mean = sum(all_deltas) / len(all_deltas)
        variance = sum((d - mean) ** 2 for d in all_deltas) / len(all_deltas)
        std_dev = math.sqrt(variance)

        if std_dev < 1e-9:
            return 0.0

        return (delta - mean) / std_dev

    def _concentration(self, footprint, level: float, timestamp: float) -> float:
        """
        Concentration ratio: how much of the level's volume is recent.

        High concentration = volume arrived in a burst (velocity signal).
        """
        data = footprint.levels.get(level)
        if not data:
            return 0.0

        time_since_update = timestamp - data.get("last_update", timestamp)

        if time_since_update < 30:
            return 0.90
        elif time_since_update < 60:
            return 0.60
        else:
            return 0.30

    def _check_price_stagnation(
        self, symbol: str, direction: str, close_price: float, open_price: float, high_price: float, low_price: float
    ) -> bool:
        """
        V2 Filter 4: Price Stagnation — price did NOT move in attack direction.

        If sellers attacked (SELL_EXHAUSTION) but price didn't drop significantly,
        that's stagnation → absorption is real.
        If sellers attacked AND price dropped → that's impulse, NOT absorption.

        Measures the displacement in the direction of the attack:
        - SELL_EXHAUSTION: how much did price drop from open? (open - low)
        - BUY_EXHAUSTION: how much did price rise from open? (high - open)

        If displacement < stagnation_max_pct → stagnation confirmed (absorption real)
        If displacement >= stagnation_max_pct → impulse (not absorption)
        """
        ref_price = open_price if open_price > 0 else close_price
        if ref_price <= 0:
            return True  # No data, don't block

        if direction == "SELL_EXHAUSTION":
            # Attack was downward. Did price actually drop?
            if low_price <= 0:
                return True
            displacement_pct = (ref_price - low_price) / ref_price * 100
        else:
            # BUY_EXHAUSTION: Attack was upward. Did price actually rise?
            if high_price <= 0:
                return True
            displacement_pct = (high_price - ref_price) / ref_price * 100

        return displacement_pct < self.stagnation_max_pct

    def _noise_ratio(self, ask_vol: float, bid_vol: float, delta: float) -> float:
        """
        Noise ratio: opposite-side volume / total volume.

        Low noise = clean absorption (one-sided aggression).
        """
        total_vol = ask_vol + bid_vol
        if total_vol == 0:
            return 1.0

        if delta < 0:
            # SELL_EXHAUSTION: opposite = buy (ask) volume
            return ask_vol / total_vol
        else:
            # BUY_EXHAUSTION: opposite = sell (bid) volume
            return bid_vol / total_vol


# Sensor registration (for SensorManager — returns None, we don't use workers)
def get_sensor_class():
    """AbsorptionDetector runs in main process, not in workers."""
    return None
