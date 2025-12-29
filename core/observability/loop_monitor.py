"""
Loop Lag Monitor for Casino V3.

Continuously measures the latency of the asyncio event loop to detect
blocking operations or CPU saturation.
"""

import asyncio
import logging
import time
from typing import Optional

from core.observability.metrics import update_loop_lag

logger = logging.getLogger(__name__)


class LoopMonitor:
    """
    Monitors asyncio event loop lag.

    Lag is defined as the difference between the requested sleep time
    and the actual elapsed time. High lag indicates the loop is blocked
    by CPU-bound tasks or too many IO callbacks.
    """

    def __init__(
        self,
        interval: float = 1.0,
        warning_threshold: float = 0.1,
        critical_threshold: float = 1.0,
    ):
        """
        Initialize LoopMonitor.

        Args:
            interval: How often to measure lag (seconds).
            warning_threshold: Lag duration to log warning (seconds).
            critical_threshold: Lag duration to log critical (seconds).
        """
        self.interval = interval
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Start the monitor task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"❤️ Loop Monitor started (Interval: {self.interval}s)")

    def stop(self):
        """Stop the monitor task."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while self._running:
                t0 = time.time()
                await asyncio.sleep(self.interval)
                t1 = time.time()

                # Calculate lag (Actual Time - Expected Time)
                # If we slept for 1.0s and it took 1.5s, lag is 0.5s.
                lag = (t1 - t0) - self.interval

                # Update Prometheus metric
                update_loop_lag(lag)

                if lag > self.critical_threshold:
                    logger.critical(f"💀 HIGH LOOP LAG DETECTED: {lag:.4f}s (Threshold: {self.critical_threshold}s)")
                elif lag > self.warning_threshold:
                    logger.warning(f"⚠️ Loop Lag High: {lag:.4f}s (Threshold: {self.warning_threshold}s)")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Loop Monitor failed: {e}")
