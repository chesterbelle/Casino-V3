import logging
from collections import deque


class LatencyMonitor:
    """
    Active Latency Telemetry (Phase 102).

    Tracks API response times (RTT) and determines if the network
    or exchange is congested.
    """

    def __init__(self, window_size: int = 50, critical_threshold_ms: float = 800.0):
        self.logger = logging.getLogger("LatencyMonitor")
        self.window_size = window_size
        self.critical_threshold_ms = critical_threshold_ms

        # Ring buffer for recent latencies
        self._latencies = deque(maxlen=window_size)

        self._avg_latency = 0.0
        self._is_congested = False

    def record_latency(self, latency_ms: float):
        """Records a new latency sample and updates metrics."""
        self._latencies.append(latency_ms)
        self._avg_latency = sum(self._latencies) / len(self._latencies)

        # Update congestion state
        new_congestion = self._avg_latency >= self.critical_threshold_ms
        if new_congestion != self._is_congested:
            self._is_congested = new_congestion
            if self._is_congested:
                self.logger.warning(
                    f"🚨 CONGESTION DETECTED: Avg Latency={self._avg_latency:.2f}ms. Entering Safe Mode."
                )
            else:
                self.logger.info(
                    f"✅ Congestion cleared: Avg Latency={self._avg_latency:.2f}ms. Resuming normal operations."
                )

    @property
    def avg_latency(self) -> float:
        return self._avg_latency

    @property
    def is_congested(self) -> bool:
        """Returns True if the system is in Safe Mode due to latency."""
        return self._is_congested

    def get_stats(self) -> dict:
        return {
            "avg_latency": round(self._avg_latency, 2),
            "is_congested": self._is_congested,
            "samples": len(self._latencies),
            "max_recent": round(max(self._latencies) if self._latencies else 0, 2),
        }
