from .base import SensorV3


class DebugHeartbeatV3(SensorV3):
    """
    Debug sensor that always fires a signal every 2 bars.
    Used to verify pipeline integrity.
    """

    name = "DebugHeartbeat"

    def calculate(self, context):
        # Handle context dict from SensorManager
        candle_data = context.get("1m") if isinstance(context, dict) else context

        # Determine current candle index based on context list length (simulated)
        # Context structure: {"1m": {...}, "5m": ...}
        # We can't easily count global candles here without internal state.
        # But we can use timestamp modulo.

        ts = candle_data.get("timestamp", 0)
        # Fire if timestamp is even minute (just random toggle)
        if (int(ts) // 60) % 2 == 0:
            return {"side": "buy", "score": 0.5, "metadata": {"reason": "debug_heartbeat"}, "timeframe": "1m"}
        return None
