"""
Volatility Spike Sensor - Liquidation & Panic Detector.

Detects sudden expansions in volume/volatility that often precede
liquidation cascades. Used to block 'Fade' (reversion) setups during
the first few seconds of a momentum burst.
"""

import logging
from collections import deque
from typing import Dict, List, Optional, Union

from sensors.base import SensorV3

logger = logging.getLogger("VolatilitySensor")


class VolatilitySpikeSensor(SensorV3):
    """
    Detects extreme volume expansions as a proxy for liquidations.
    """

    def __init__(self):
        super().__init__()
        # Store last 20 1m candle volumes
        self.volume_history = deque(maxlen=20)
        self.last_spike_ts = 0.0

    @property
    def name(self) -> str:
        return "VolatilitySpike"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Union[Optional[dict], List[dict]]:
        """
        Analyzes 1m candles for volume spikes.
        """
        candle_1m = context.get("1m")
        if not candle_1m:
            return None

        vol = candle_1m.get("volume", 0.0)
        ts = candle_1m.get("timestamp", 0.0)

        if vol <= 0:
            return None

        signal = None

        # 1. Check for spike BEFORE adding current to baseline
        if len(self.volume_history) >= 5:
            avg_vol = sum(self.volume_history) / len(self.volume_history)

            # Spike Threshold: 4x Average Volume
            if vol > avg_vol * 4.0:
                self.last_spike_ts = ts
                logger.warning(f"🚨 [VOLATILITY] Spike detected | Vol: {vol:.2f} (Avg: {avg_vol:.2f})")

                signal = {
                    "side": "TACTICAL",
                    "score": 1.0,
                    "metadata": {"type": "VOLATILITY_SPIKE", "ratio": vol / avg_vol, "timestamp": ts},
                    "timeframe": "1m",
                }

        # 2. Update history
        self.volume_history.append(vol)

        return signal
