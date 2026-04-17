"""
Cascade Liquidation Detector — "The Tsunami Surfer"

Detects the moment when retail stop-losses begin executing in chain,
creating a self-reinforcing price waterfall (liquidation cascade).

The signal fires AFTER the cascade exhausts itself, entering in the
opposite direction (fade the capitulation).

Phase C1: New complementary strategy for the LTA V4 architecture.

Detection Logic:
1. Volume Spike:  Current bar volume > 5× the 20-bar average.
2. Directional Aggression:  Delta Z-score exceeds ±4.0 (extreme one-sided flow).
3. Price Acceleration:  Price moves > 2× ATR in the same direction within 3 bars.
4. Exhaustion Signature:  After the cascade, the final bar shows volume exhaustion
   (< 50% of cascade peak) and delta reversal — the cascade has burned out.

The signal is a TacticalLiquidationCascade event that feeds into the
existing LTA structural gating pipeline (proximity + guardians).
"""

import logging
from collections import deque
from typing import Dict, Optional

from sensors.base import SensorV3

logger = logging.getLogger(__name__)


class LiquidationCascadeDetector(SensorV3):
    """
    Detects cascade liquidation events and generates fade signals.

    A cascade is identified by:
    - Extreme volume spike (5× average)
    - Extreme Z-score (±4.0)
    - Rapid price displacement (2× ATR)
    - Followed by volume exhaustion and delta reversal

    The trade is a "Tsunami Surf" — enter AFTER the wave crashes and
    ride the bounce back toward the POC.
    """

    def __init__(
        self,
        volume_spike_ratio: float = 5.0,  # Volume must be 5× the 20-bar avg
        z_threshold: float = 4.0,  # Z-score must exceed ±4.0
        atr_displacement: float = 2.0,  # Price must move 2× ATR
        exhaustion_ratio: float = 0.50,  # Post-cascade volume < 50% of peak
        lookback_bars: int = 20,  # Rolling history for averages
        cascade_window: int = 3,  # Bars to measure price acceleration
    ):
        super().__init__()
        self.volume_spike_ratio = volume_spike_ratio
        self.z_threshold = z_threshold
        self.atr_displacement = atr_displacement
        self.exhaustion_ratio = exhaustion_ratio
        self.lookback_bars = lookback_bars
        self.cascade_window = cascade_window

        # Rolling state
        self.volume_history: deque = deque(maxlen=lookback_bars)
        self.delta_history: deque = deque(maxlen=lookback_bars)
        self.price_history: deque = deque(maxlen=lookback_bars)
        self.atr_history: deque = deque(maxlen=lookback_bars)

        # Cascade tracking state machine
        self._cascade_active = False
        self._cascade_direction = None  # "UP" or "DOWN"
        self._cascade_peak_volume = 0.0
        self._cascade_start_price = 0.0
        self._cascade_bars = 0

    @property
    def name(self) -> str:
        return "LiquidationCascade"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        """Process 1m candle and detect cascade liquidation events."""
        candle = context.get("1m")
        if not candle:
            return None

        volume = candle.get("volume", 0)
        delta = candle.get("delta", 0)
        close = candle.get("close", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)
        atr = candle.get("atr", 0)

        if close <= 0 or volume <= 0:
            return None

        # Update rolling history
        self.volume_history.append(volume)
        self.delta_history.append(delta)
        self.price_history.append(close)
        if atr > 0:
            self.atr_history.append(atr)

        # Need enough history
        if len(self.volume_history) < self.lookback_bars:
            return None

        avg_volume = sum(self.volume_history) / len(self.volume_history)
        avg_atr = sum(self.atr_history) / len(self.atr_history) if self.atr_history else 0

        if avg_volume <= 0 or avg_atr <= 0:
            return None

        # Calculate delta Z-score (simplified using delta history)
        delta_mean = sum(self.delta_history) / len(self.delta_history)
        delta_variance = sum((d - delta_mean) ** 2 for d in self.delta_history) / len(self.delta_history)
        delta_std = delta_variance**0.5 if delta_variance > 0 else 1.0
        delta_z = (delta - delta_mean) / delta_std if delta_std > 0 else 0.0

        # ======================================================
        # STATE MACHINE: Cascade Detection
        # ======================================================

        if not self._cascade_active:
            # ---- Phase 1: Detect cascade INITIATION ----
            volume_spike = volume > avg_volume * self.volume_spike_ratio
            extreme_delta = abs(delta_z) > self.z_threshold

            if volume_spike and extreme_delta:
                # Cascade has begun
                self._cascade_active = True
                self._cascade_direction = "DOWN" if delta_z < 0 else "UP"
                self._cascade_peak_volume = volume
                self._cascade_start_price = close
                self._cascade_bars = 1

                logger.info(
                    f"⚡ [CASCADE] Detected initiation: {self._cascade_direction} | "
                    f"Vol: {volume:.0f} ({volume/avg_volume:.1f}×avg) | "
                    f"ΔZ: {delta_z:.1f}"
                )
                return None  # Don't signal yet — wait for exhaustion

        else:
            # ---- Phase 2: Track cascade and detect EXHAUSTION ----
            self._cascade_bars += 1
            self._cascade_peak_volume = max(self._cascade_peak_volume, volume)

            # Check price displacement
            price_displacement = abs(close - self._cascade_start_price)
            displacement_atr = price_displacement / avg_atr if avg_atr > 0 else 0

            # Check exhaustion conditions
            volume_exhausted = volume < self._cascade_peak_volume * self.exhaustion_ratio
            delta_reversed = (self._cascade_direction == "DOWN" and delta > 0) or (
                self._cascade_direction == "UP" and delta < 0
            )
            sufficient_displacement = displacement_atr >= self.atr_displacement

            # Timeout: if cascade runs > 5 bars without exhausting, abort
            if self._cascade_bars > 5:
                logger.debug(f"⚡ [CASCADE] Timeout after {self._cascade_bars} bars. Resetting.")
                self._reset_cascade()
                return None

            # Check for exhaustion signature
            if volume_exhausted and delta_reversed and sufficient_displacement:
                # CASCADE EXHAUSTION CONFIRMED — generate fade signal
                fade_direction = "LONG" if self._cascade_direction == "DOWN" else "SHORT"

                logger.info(
                    f"🌊 [CASCADE] Exhaustion confirmed! Fade {fade_direction} | "
                    f"Displacement: {displacement_atr:.1f}×ATR | "
                    f"Vol decay: {volume/self._cascade_peak_volume:.1%} of peak | "
                    f"Bars: {self._cascade_bars}"
                )

                signal = {
                    "side": "TACTICAL",
                    "metadata": {
                        "tactical_type": "TacticalLiquidationCascade",
                        "direction": fade_direction,
                        "subtype": f"Cascade_Fade_{self._cascade_direction}",
                        "cascade_direction": self._cascade_direction,
                        "cascade_bars": self._cascade_bars,
                        "peak_volume": round(self._cascade_peak_volume, 2),
                        "volume_decay_pct": round(volume / self._cascade_peak_volume, 3),
                        "displacement_atr": round(displacement_atr, 2),
                        "delta_z_peak": round(delta_z, 2),
                        "price": close,
                        "high": high,
                        "low": low,
                        "open": candle.get("open", close),
                        "close": close,
                    },
                }

                self._reset_cascade()
                return signal

        return None

    def _reset_cascade(self):
        """Reset cascade tracking state."""
        self._cascade_active = False
        self._cascade_direction = None
        self._cascade_peak_volume = 0.0
        self._cascade_start_price = 0.0
        self._cascade_bars = 0
