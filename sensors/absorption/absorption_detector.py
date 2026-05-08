import logging
import math
import uuid
from typing import Dict, List, Optional, Tuple

from core.footprint_registry import footprint_registry
from sensors.base import SensorV3
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger(__name__)


class AbsorptionDetector(SensorV3, TraceBulletMixin):
    """
    Absorption Detector V3 - High-Precision Tactical Sensor.

    Detects aggressive volume without price displacement (Absorption).
    Now runs as an asynchronous worker sensor to minimize execution latency.
    """

    def __init__(self):
        SensorV3.__init__(self)
        TraceBulletMixin.__init__(self)
        self._name = "TacticalAbsorptionV2"
        self.timeframes = ["1m"]

        # Filter thresholds
        self.z_score_min = 1.5
        self.concentration_min = 0.15
        self.noise_max = 0.85
        self.stagnation_max_pct = 0.15

        # State tracking
        self._last_candle_ts: Dict[str, float] = {}
        self.last_candle = None
        self.symbol = None

    @property
    def name(self) -> str:
        return self._name

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        """
        Main calculation loop triggered by SensorManager on each candle.
        """
        # 1. Extract context
        candle_1m = context.get("1m")
        if not candle_1m:
            return None

        self.last_candle = candle_1m
        self.symbol = candle_1m["symbol"]
        timestamp = candle_1m["timestamp"]

        # 2. Throttle check
        if self._last_candle_ts.get(self.symbol, 0) == timestamp:
            return None
        self._last_candle_ts[self.symbol] = timestamp

        # 3. Get footprint from registry (updated by SensorWorker in this process)
        footprint = footprint_registry.get_footprint(self.symbol)
        if not footprint or len(footprint.levels) < 2:
            return None

        # 4. Find candidates and filter
        candidates = self._find_extreme_deltas(footprint)

        for level, delta, ask_vol, bid_vol in candidates:
            # Filter 1: Magnitude
            z_score = self._cross_sectional_zscore(footprint, delta)
            if abs(z_score) < self.z_score_min:
                logger.debug(f"❌ [ABS] Rejected {level}: Z-score {z_score:.2f} < {self.z_score_min}")
                continue

            # Filter 2: Velocity
            concentration = self._concentration(footprint, level, timestamp)
            if concentration < self.concentration_min:
                logger.debug(f"❌ [ABS] Rejected {level}: Concentration {concentration:.2f} < {self.concentration_min}")
                continue

            # Filter 3: Noise
            noise = self._noise_ratio(ask_vol, bid_vol, delta)
            if noise > self.noise_max:
                logger.debug(f"❌ [ABS] Rejected {level}: Noise {noise:.2f} > {self.noise_max}")
                continue

            # Filter 4: Stagnation
            direction = "SELL_EXHAUSTION" if delta < 0 else "BUY_EXHAUSTION"
            if not self._check_price_stagnation(direction, candle_1m):
                logger.debug(f"❌ [ABS] Rejected {level}: Stagnation check failed")
                continue

            # SUCCESS: Tactical Absorption V2 Detected
            side = "LONG" if direction == "SELL_EXHAUSTION" else "SHORT"
            trace_id = f"TRB-{self.symbol.split('/')[0]}-{uuid.uuid4().hex[:8]}"

            logger.info(
                f"🎯 [TACTICAL_ABS] {self.symbol} {side} Detected | "
                f"Z={z_score:.2f} | Conc={concentration:.2f} | Price={candle_1m['close']:.2f}"
            )

            # Return signal dict for SensorManager to emit
            signal = {
                "side": side,
                "score": abs(z_score) / 5.0,  # Normalized score
                "price": candle_1m["close"],
                "trace_id": trace_id,
                "metadata": {
                    "tactical_type": self.name,
                    "z_score": z_score,
                    "footprint_z_score": z_score,
                    "concentration": concentration,
                    "noise": noise,
                    "absorption_level": level,
                    "direction": direction,
                    "trace_id": trace_id,
                },
            }

            self.trace(signal, "SENSOR_INGEST")
            return signal

        return None

    def on_tick(self, tick_data: dict) -> None:
        """
        Phase 2300: Real-time footprint update inside worker process.
        This ensures the local registry is hot when calculate() is called on candle close.
        """
        sym = tick_data.get("symbol")
        if not sym:
            return

        # Inject into local worker process registry
        from core.footprint_registry import footprint_registry

        footprint_registry.on_trade(
            sym,
            float(tick_data["price"]),
            float(tick_data["volume"]),
            tick_data["side"],
            float(tick_data["timestamp"]),
        )

    def _find_extreme_deltas(self, footprint) -> List[Tuple[float, float, float, float]]:
        deltas = []
        for level, data in footprint.levels.items():
            delta = data["delta"]
            if abs(delta) > 0:
                deltas.append((level, delta, data["ask_volume"], data["bid_volume"]))
        if len(deltas) < 10:
            return []
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        top_n = max(1, min(5, len(deltas) // 10))
        return deltas[:top_n]

    def _cross_sectional_zscore(self, footprint, delta: float) -> float:
        all_deltas = [data["delta"] for data in footprint.levels.values()]
        if len(all_deltas) < 2:
            return 0.0
        mean = sum(all_deltas) / len(all_deltas)
        variance = sum((d - mean) ** 2 for d in all_deltas) / len(all_deltas)
        std_dev = math.sqrt(variance)
        return (delta - mean) / std_dev if std_dev > 1e-9 else 0.0

    def _concentration(self, footprint, level: float, timestamp: float) -> float:
        data = footprint.levels.get(level)
        if not data:
            return 0.0
        time_since_update = timestamp - data.get("last_update", timestamp)
        if time_since_update < 30:
            return 0.90
        elif time_since_update < 60:
            return 0.60
        return 0.30

    def _check_price_stagnation(self, direction: str, candle: dict) -> bool:
        open_p = candle.get("open", 0)
        close_p = candle.get("close", 0)
        high_p = candle.get("high", 0)
        low_p = candle.get("low", 0)
        ref_price = open_p if open_p > 0 else close_p
        if ref_price <= 0:
            return True
        if direction == "SELL_EXHAUSTION":
            displacement_pct = (ref_price - low_p) / ref_price * 100
        else:
            displacement_pct = (high_p - ref_price) / ref_price * 100
        return displacement_pct < self.stagnation_max_pct

    def _noise_ratio(self, ask_vol: float, bid_vol: float, delta: float) -> float:
        total_vol = ask_vol + bid_vol
        if total_vol == 0:
            return 1.0
        return (ask_vol if delta < 0 else bid_vol) / total_vol


def get_sensor_class():
    return AbsorptionDetector
