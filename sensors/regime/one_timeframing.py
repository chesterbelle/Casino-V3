import logging
from typing import Dict, Optional

from sensors.base import SensorV3

logger = logging.getLogger(__name__)


class OneTimeframingSensor(SensorV3):
    """
    James Dalton's One-Timeframing (OTF) Sensor.
    Detects directional conviction in the market auction process.

    Logic:
    - Bullish OTF: Current Low > Previous Low.
    - Bearish OTF: Current High < Previous High.
    - Strategy: Fading is prohibited when the market is one-timeframing with conviction (e.g. 2+ bars).
    """

    def __init__(self, lookback: int = 5):
        super().__init__()
        self.lookback = lookback
        self.history = []  # List of candles for OTF analysis
        self.symbol = "Unknown"

    @property
    def name(self) -> str:
        return "OneTimeframing"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        """
        Detect OTF regime from candle context.
        Uses any available timeframe (defaults to '1m' for scalping safety).
        """
        # We focus on the most granular TF for immediate regime detection
        tf = "1m"
        candle = context.get(tf)
        if not candle:
            return None

        # Add to history and maintain lookback
        if not self.history or self.history[-1]["timestamp"] != candle["timestamp"]:
            self.history.append(candle)
            logger.info(f"📈 [OTF] History updated for {self.symbol}: {len(self.history)} candles")
        else:
            self.history[-1] = candle

        if len(self.history) < self.lookback + 1:
            return None

        self.history = self.history[-(self.lookback + 2) :]

        # Analyze OTF
        # We compare [i] with [i-1] for the last `lookback` candles
        bull_otf_count = 0
        bear_otf_count = 0

        for i in range(len(self.history) - 1, len(self.history) - self.lookback - 1, -1):
            curr = self.history[i]
            prev = self.history[i - 1]

            if curr["low"] > prev["low"]:
                bull_otf_count += 1
            if curr["high"] < prev["high"]:
                bear_otf_count += 1

        regime = "NEUTRAL"
        score = 0.5

        # Conviction threshold: at least `lookback` consecutive bars
        if bull_otf_count >= self.lookback:
            regime = "BULL_OTF"
            score = 1.0
        elif bear_otf_count >= self.lookback:
            regime = "BEAR_OTF"
            score = 1.0

        if regime != "NEUTRAL":
            logger.info(
                f"🔥 [OTF] Conviction detected for {self.symbol}: {regime} ({bull_otf_count}U/{bear_otf_count}D)"
            )

        return {
            "side": "LONG" if regime == "BULL_OTF" else ("SHORT" if regime == "BEAR_OTF" else "NEUTRAL"),
            "score": score,
            "metadata": {
                "type": "MarketRegime_OTF",
                "regime": regime,
                "bull_count": bull_otf_count,
                "bear_count": bear_otf_count,
                "lookback": self.lookback,
            },
            "timeframe": tf,
        }
