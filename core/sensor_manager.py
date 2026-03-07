"""
Sensor Manager for Casino-V3.
Orchestrates sensors, manages cooldowns, and emits SignalEvents.

Optimized with ProcessPoolExecutor for parallel sensor execution.
"""

import asyncio
import logging
import multiprocessing
import os
import time
from typing import Dict, Tuple

from .bar_aggregator import BarAggregator
from .events import CandleEvent, EventType, OrderBookEvent, SignalEvent, TickEvent

logger = logging.getLogger(__name__)

# Number of worker processes for parallel sensor execution
# Use half of CPU cores to leave room for other tasks
SENSOR_WORKERS = max(2, (os.cpu_count() or 4) // 2)


def _calculate_sensor(sensor_data: Tuple) -> Tuple[str, dict]:
    """
    Worker function for parallel sensor calculation.

    This runs in a separate process to bypass GIL for CPU-bound numpy operations.

    Args:
        sensor_data: Tuple of (sensor_instance, candle_data)

    Returns:
        Tuple of (sensor_name, signal_or_none)
    """
    sensor, candle_data = sensor_data
    try:
        signal = sensor.calculate(candle_data)
        return (sensor.name, signal)
    except Exception as e:
        return (sensor.name, {"error": str(e)})


class SensorManager:
    """
    Orchestrates V3 Sensors using an Actor Model (Parallel Persistent Processes).

    Responsibilities:
    1. Distributes sensors across worker processes.
    2. Broadcasts candle data to workers.
    3. Aggregates signals from workers via async listener.
    """

    def __init__(self, engine, timeframe: str = "1m"):
        self.engine = engine
        self.timeframe = timeframe
        self.cooldown_bars = 5
        self._candle_index = -1
        self._last_trigger: Dict[str, int] = {}

        # Bar aggregator for reference (Workers maintain their own state,
        # but we might need this for context injection if we pass it)
        # Multi-Asset: One aggregator per symbol
        self.aggregators: Dict[str, BarAggregator] = {}

        # IPC Config
        self.workers = []
        self.input_queues = []  # One per worker to avoid contention/ordering issues
        self.output_queue = multiprocessing.Queue()  # Shared output queue for all workers

        # Capability Mapping (Phase 660 Optimization)
        self.tick_queues = []
        self.ob_queues = []

        # Load and Distribute Sensors
        self._spawn_workers()

        # Start Async Listener
        asyncio.create_task(self._listen_for_signals())

        # Subscribe to Events (Phase 410: The Ingestion Pivot)
        self.engine.subscribe(EventType.CANDLE, self.on_candle)
        self.engine.subscribe(EventType.TICK, self.on_tick)
        self.engine.subscribe(EventType.ORDER_BOOK, self.on_orderbook)

        # Throttler for High-Frequency events (Phase 420 Prep)
        self._last_tick_dispatch: Dict[str, float] = {}
        self._last_ob_dispatch: Dict[str, float] = {}
        self.throttle_ms = 100  # 100ms max update rate per symbol to workers

        logger.info("✅ SensorManager initialized in Actor Model mode (Tick-Aware)")

    def _spawn_workers(self):
        """Load sensors and distribute them among worker processes."""
        # 1. Gather all sensor classes
        from config.sensors import ACTIVE_SENSORS

        # Lazy import of all sensors to get their classes
        # (Using the block from original file to gather classes)
        sensor_classes = self._get_all_sensor_classes()

        # Filter enabled sensors
        enabled_classes = []
        for cls in sensor_classes:
            # Temporary instantiation to check name usually needed
            # Or assume class name map. Let's instantiate briefly to check name
            try:
                # Optimization: if strict naming convention, we could guess name.
                # But safer to instantiate once here.
                tmp = cls()
                if ACTIVE_SENSORS.get(tmp.name, False):
                    enabled_classes.append(cls)
            except Exception:
                pass

        if not enabled_classes:
            logger.warning("⚠️ No sensors enabled!")
            return

        # 2. Determine worker count
        cpu_count = os.cpu_count() or 4
        # Use roughly 50-75% of cores, min 2
        num_workers = max(2, int(cpu_count * 0.75))

        logger.info(f"🏭 Spawning {num_workers} SensorWorkers for {len(enabled_classes)} sensors...")

        # 3. Distribute sensors (Round Robin)
        from .sensor_worker import SensorWorker

        chunks = [[] for _ in range(num_workers)]
        capabilities = [{"tick": False, "ob": False} for _ in range(num_workers)]

        for i, cls in enumerate(enabled_classes):
            worker_idx = i % num_workers
            chunks[worker_idx].append(cls)

            # Detect capabilities
            try:
                tmp = cls()
                if hasattr(tmp, "on_tick"):
                    capabilities[worker_idx]["tick"] = True
                if hasattr(tmp, "on_orderbook"):
                    capabilities[worker_idx]["ob"] = True
            except Exception:
                pass

        # 4. Create Processes
        for i in range(num_workers):
            if not chunks[i]:
                continue  # Skip empty workers if few sensors

            q_in = multiprocessing.Queue(maxsize=10000)  # Phase 660: Add cap to prevent OOM if main process stalls
            self.input_queues.append(q_in)

            # Register for targeted broadcast
            if capabilities[i]["tick"]:
                self.tick_queues.append(q_in)
            if capabilities[i]["ob"]:
                self.ob_queues.append(q_in)

            worker = SensorWorker(
                worker_id=i, sensor_classes=chunks[i], input_queue=q_in, output_queue=self.output_queue
            )
            worker.start()
            self.workers.append(worker)

        logger.info(
            f"🚀 {len(self.workers)} Workers started | "
            f"Tick-Aware: {len(self.tick_queues)} | OB-Aware: {len(self.ob_queues)}"
        )

    async def on_candle(self, event: CandleEvent):
        """
        Broadcast new candle to all workers.
        Non-blocking, fire-and-forget.
        """
        self._candle_index += 1
        logger.info(f"📨 SensorManager: Processing candle for {event.symbol} (Index: {self._candle_index})")

        # Standardize candle data for serialization
        candle_data = {
            "timestamp": event.timestamp,
            "open": event.open,
            "high": event.high,
            "low": event.low,
            "close": event.close,
            "volume": event.volume,
            "profile": getattr(event, "profile", None),
            "delta": getattr(event, "delta", 0.0),
        }

        # Update local aggregator (per symbol)
        if event.symbol not in self.aggregators:
            self.aggregators[event.symbol] = BarAggregator()

        # Capture the aggregated context (Fix for Silent Sensors)
        context = self.aggregators[event.symbol].on_candle(candle_data)

        # Message for workers
        msg = {
            "event": "candle",
            "symbol": event.symbol,
            "data": candle_data,
            "context": context,  # Pass the full context to sensors
            # Most V3 sensors calc their own indicators.
            # If we pass context, it must be picklable.
        }

        # Dispatch to all queues
        # Use executor to avoid blocking main loop with Queue.put (can block if full)
        loop = asyncio.get_running_loop()
        for q in self.input_queues:
            # We don't await this inside the loop to avoid sequential blocking,
            # but we use run_in_executor to ensure it happens in a thread.
            loop.run_in_executor(None, q.put, msg)

    async def on_tick(self, event: TickEvent):
        """
        Phase 410: Broadcast new trades (ticks) to workers.
        Throttled to prevent IPC explosion.
        """
        now = time.time()
        last_dispatch = self._last_tick_dispatch.get(event.symbol, 0)

        # Throttle to max 1 update per 100ms
        if (now - last_dispatch) * 1000 < self.throttle_ms:
            return

        self._last_tick_dispatch[event.symbol] = now

        msg = {
            "event": "tick",
            "symbol": event.symbol,
            "data": {"price": event.price, "volume": event.volume, "side": event.side, "timestamp": event.timestamp},
        }

        loop = asyncio.get_running_loop()
        # Phase 660: Targeted broadcast (Only to workers that have tick-aware sensors)
        for q in self.tick_queues:
            loop.run_in_executor(None, q.put, msg)

    async def on_orderbook(self, event: OrderBookEvent):
        """
        Phase 410: Broadcast OrderBook snapshots to workers.
        Throttled to prevent IPC explosion.
        """
        now = time.time()
        last_dispatch = self._last_ob_dispatch.get(event.symbol, 0)

        # Throttle to max 1 update per 100ms
        if (now - last_dispatch) * 1000 < self.throttle_ms:
            return

        self._last_ob_dispatch[event.symbol] = now

        msg = {
            "event": "orderbook",
            "symbol": event.symbol,
            "data": {"bids": event.bids, "asks": event.asks, "timestamp": event.timestamp},
        }

        loop = asyncio.get_running_loop()
        # Phase 660: Targeted broadcast (Only to workers that have OB-aware sensors)
        for q in self.ob_queues:
            loop.run_in_executor(None, q.put, msg)

    async def _listen_for_signals(self):
        """Async loop to consume signals from workers."""
        logger.info("👂 Listening for signals from workers...")
        # loop = asyncio.get_event_loop() # Unused

        while True:
            try:
                # Non-blocking check of the queue
                # Queue.get is blocking. We should use run_in_executor
                # wrapper or a non-blocking get loop with sleep

                # Option A: Polling with sleep (simplest, low overhead if sleep is small)
                processed = 0
                while not self.output_queue.empty() and processed < 1000:
                    msg = self.output_queue.get_nowait()
                    await self._handle_worker_message(msg)
                    processed += 1

                if processed == 0:
                    await asyncio.sleep(0.01)  # 10ms poll interval
                else:
                    await asyncio.sleep(0)  # Yield for other tasks if busy

            except Exception as e:
                if not isinstance(e, asyncio.CancelledError):
                    logger.error(f"❌ Error in signal listener: {e}")
                await asyncio.sleep(0.1)

    async def _handle_worker_message(self, msg: dict):
        """Process a message from a worker."""
        sensor_name = msg.get("sensor")
        symbol = msg.get("symbol")
        signals = msg.get("signals")

        if not sensor_name or not signals:
            return

        # Check cooldown (Centralized cooldown management)
        # Context/Regime sensors are exempt from cooldown to provide fresh bias
        from config.strategies import get_sensor_type

        stype = get_sensor_type(sensor_name)
        is_context = stype in ("Context", "RegimeFilter", "TrendIndicator")

        cooldown_key = f"{symbol}_{sensor_name}" if symbol else sensor_name

        if not is_context and not self._can_fire(cooldown_key):
            return

        # Emit Signal(s)
        if isinstance(signals, dict):
            await self._emit_signal(signals, sensor_name, symbol)
        elif isinstance(signals, list):
            for s in signals:
                if s:
                    await self._emit_signal(s, sensor_name, symbol)

        # Update cooldown
        self._last_trigger[cooldown_key] = self._candle_index

    def _can_fire(self, key: str) -> bool:
        """Check cooldown."""
        last_index = self._last_trigger.get(key)
        if last_index is None:
            return True
        return (self._candle_index - last_index) >= self.cooldown_bars

    async def _emit_signal(self, signal_data: dict, sensor_name: str, symbol: str = None):
        """Emit SignalEvent."""
        from config.sensors import get_sensor_params

        metadata = dict(signal_data.get("metadata") or {})
        signal_tf = signal_data.get("timeframe", self.timeframe)

        # Strategy contract: always attach a reliable trigger price for level confirmation.
        # Priority:
        # 1) Explicit metadata price (sensor-provided)
        # 2) Top-level signal_data price
        # 3) Candle close from context (if available)
        if metadata.get("price") is None and metadata.get("at_price") is None:
            if signal_data.get("price") is not None:
                metadata["price"] = signal_data.get("price")
            else:
                ctx = signal_data.get("context")
                if isinstance(ctx, dict):
                    candle_1m = ctx.get("1m") if "1m" in ctx else None
                    if isinstance(candle_1m, dict) and candle_1m.get("close") is not None:
                        metadata["price"] = candle_1m.get("close")

        # Phase 700: Extract HTF structural levels for Trader Dale context
        ctx = signal_data.get("context")
        if isinstance(ctx, dict):
            for tf in ("15m", "1h", "4h"):
                tf_candle = ctx.get(tf)
                if isinstance(tf_candle, dict):
                    poc = tf_candle.get("poc")
                    vah = tf_candle.get("vah")
                    val = tf_candle.get("val")
                    if poc and poc > 0:
                        metadata[f"{tf}_poc"] = poc
                    if vah and vah > 0:
                        metadata[f"{tf}_vah"] = vah
                    if val and val > 0:
                        metadata[f"{tf}_val"] = val

        sensor_config = get_sensor_params(sensor_name, signal_tf)
        if "tp_pct" in sensor_config:
            metadata["tp_pct"] = sensor_config["tp_pct"]
        if "sl_pct" in sensor_config:
            metadata["sl_pct"] = sensor_config["sl_pct"]

        metadata["signal_timeframe"] = signal_tf

        # Use symbol from message, fallback to adapter (legacy/single-mode safe,
        # but really we should depend on symbol being present)
        target_symbol = symbol or self.engine.data_feed.adapter.symbol

        event = SignalEvent(
            type=EventType.SIGNAL,
            timestamp=time.time(),
            symbol=target_symbol,
            side=signal_data["side"],
            sensor_id=sensor_name,
            score=signal_data.get("score", 1.0),
            metadata=metadata,
            fast_track=bool(metadata.get("fast_track", False)),
        )
        # Phase 180: Silent Sensors (Switch to DEBUG to reduce minute-boundary log burst)
        logger.debug(f"📡 Signal Detected: {sensor_name}@{signal_tf} -> {signal_data['side']} [{target_symbol}]")
        await self.engine.dispatch(event)

    def stop(self):
        """Shutdown workers."""
        logger.info("🛑 Stopping Sensor Workers...")
        for q in self.input_queues:
            q.put("STOP")

        for w in self.workers:
            w.join(timeout=1.0)
            if w.is_alive():
                w.terminate()

    def _get_all_sensor_classes(self):
        """Helper to return all sensor classes (moved from original _load_sensors)."""
        # ... Import block ...
        # Import only Footprint and Core sensors for Phase 400
        from sensors.debug_heartbeat import DebugHeartbeatV3
        from sensors.footprint.absorption import FootprintAbsorptionV3
        from sensors.footprint.advanced import (
            FootprintDeltaDivergence,
            FootprintPOCRejection,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
        )
        from sensors.footprint.big_orders import BigOrderSensor
        from sensors.footprint.cumulative_delta import CumulativeDeltaSensorV3
        from sensors.footprint.exhaustion import FootprintVolumeExhaustion
        from sensors.footprint.flow_shift import FootprintDeltaPoCShift
        from sensors.footprint.imbalance import FootprintImbalanceV3
        from sensors.footprint.session import SessionValueArea
        from sensors.regime.one_timeframing import OneTimeframingSensor

        return [
            OneTimeframingSensor,
            SessionValueArea,
            DebugHeartbeatV3,
            FootprintImbalanceV3,
            FootprintAbsorptionV3,
            FootprintPOCRejection,
            FootprintDeltaDivergence,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
            FootprintVolumeExhaustion,
            FootprintDeltaPoCShift,
            CumulativeDeltaSensorV3,
            BigOrderSensor,
        ]
