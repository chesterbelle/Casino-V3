"""
Execution Pressure Benchmark (isolated)
----------------------------------------
Identifies event-loop bottlenecks by bombarding the core engine with
synthetic high-velocity events and concurrent IO pressure.

Objective: Fail if lag > 100ms or stalls detected.
"""

import asyncio
import logging
import os
import sys
import time
from typing import List

# Add root to sys.path
sys.path.append(os.getcwd())

from core.clock import Clock
from core.engine import Engine
from core.events import EventType, MicrostructureEvent
from core.observability.loop_monitor import LoopMonitor
from core.observability.watchdog import watchdog
from core.state.persistent_state import PersistentState

# Configure logging to console only for benchmark clarity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("PressureBench")


class ExecutionPressureBenchmark:
    def __init__(self, duration: int = 15, event_freq: int = 1000):
        self.duration = duration
        self.event_freq = event_freq  # events per second
        self.engine = Engine()
        self.clock = Clock(tick_size_seconds=1.0)
        self.loop_monitor = LoopMonitor(interval=0.5, warning_threshold=0.05, critical_threshold=0.2)
        self.state_mgr = PersistentState(state_dir="./temp_bench_state", save_interval=1)
        self.max_lag = 0.0
        self.stalls_detected = 0

    async def setup(self):
        logger.info("🔧 Setting up Pressure Benchmark...")
        if not os.path.exists("./temp_bench_state"):
            os.makedirs("./temp_bench_state")

        # Register watchdog to clock so it doesn't report False Positives
        self.clock.add_iterator(watchdog)

        await self.engine.start(blocking=False)
        await self.clock.start()
        await self.state_mgr.start()
        self.loop_monitor.start()
        await watchdog.start()

        # Subscribe a heavy dummy listener to simulate processing overhead
        self.engine.subscribe(EventType.MICROSTRUCTURE, self._heavy_listener)
        logger.info("✅ Setup complete.")

    async def _heavy_listener(self, event):
        """Simulate some light CPU work per event."""
        _ = [x * x for x in range(50)]

    async def producer_task(self):
        """Generates a high-frequency burst of events."""
        logger.info(f"🔥 Starting Event Burst: {self.event_freq} events/sec")
        interval = 1.0 / self.event_freq
        end_time = time.time() + self.duration

        count = 0
        while time.time() < end_time:
            t_start = time.perf_counter()

            evt = MicrostructureEvent(
                type=EventType.MICROSTRUCTURE,
                timestamp=time.time(),
                symbol="BENCH",
                cvd=100.0,
                skewness=0.5,
                z_score=1.2,
                price=50000.0,
            )
            await self.engine.dispatch(evt)
            count += 1

            # Precise sleep to maintain frequency
            t_end = time.perf_counter()
            sleep_time = interval - (t_end - t_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            if count % 1000 == 0:
                logger.debug(f"📤 Sent {count} events...")

        logger.info(f"✅ Produced {count} events.")

    async def persistence_stress_task(self):
        """Forces frequent state saves to stress IO/serialization."""
        logger.info("💾 Starting Persistence Stress Task...")
        end_time = time.time() + self.duration

        while time.time() < end_time:
            # Update state with dummy data
            await self.state_mgr.update_balance(random_val := 10000 + time.time() % 100, random_val)
            # Force immediate save
            await self.state_mgr.save()
            await asyncio.sleep(0.5)  # Force a save every 500ms

    async def run(self):
        try:
            await self.setup()

            logger.info(f"🚀 Running benchmark for {self.duration}s...")

            # Start monitoring lag in background
            monitor_task = asyncio.create_task(self._track_max_lag())

            # Run stress tasks
            await asyncio.gather(self.producer_task(), self.persistence_stress_task())

            logger.info("🏁 Stress phase complete. Analyzing results...")

            # Stop and cleanup
            self.loop_monitor.stop()
            monitor_task.cancel()
            await self.state_mgr.stop()
            await self.clock.stop()
            await self.engine.stop()
            await watchdog.stop()

            # Final Report
            status = watchdog.get_status()
            for name, info in status.items():
                if not info["healthy"]:
                    logger.error(f"❌ STALL DETECTED in watchdog: {name} (Lag: {info['elapsed']:.2f}s)")
                    self.stalls_detected += 1

            passed = self.max_lag < 0.1 and self.stalls_detected == 0

            print("\n" + "=" * 50)
            print(" REACTOR PRESSURE BENCHMARK RESULTS")
            print("=" * 50)
            print(f"  Duration:         {self.duration}s")
            print(f"  Event Frequency:  {self.event_freq}/s")
            print(f"  Max Loop Lag:     {self.max_lag*1000:.2f}ms (Limit: 100ms)")
            print(f"  Stalls Detected:  {self.stalls_detected}")
            print(f"  Status:           {'✅ PASS' if passed else '❌ FAIL'}")
            print("=" * 50 + "\n")

            return passed

        except Exception as e:
            logger.error(f"💥 Benchmark Error: {e}", exc_info=True)
            return False

    async def _track_max_lag(self):
        """Active lag tracker using LoopMonitor logic."""
        interval = 0.5
        while True:
            t0 = time.time()
            await asyncio.sleep(interval)
            t1 = time.time()
            lag = (t1 - t0) - interval
            if lag > self.max_lag:
                self.max_lag = lag
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    bench = ExecutionPressureBenchmark(duration=15, event_freq=2000)
    success = asyncio.run(bench.run())
    sys.exit(0 if success else 1)
