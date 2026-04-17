"""
Sensor Manager for Casino-V3.
Orchestrates sensors, manages cooldowns, and emits SignalEvents.

Optimized with ProcessPoolExecutor for parallel sensor execution.
"""

import asyncio
import logging
import multiprocessing
import os
from collections import defaultdict, deque
from typing import Any, Dict, Tuple

from .bar_aggregator import BarAggregator
from .events import (
    CandleEvent,
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    OrderBookEvent,
    SignalEvent,
    TickEvent,
)

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

        # Phase 1: Real-time Microstructural Tracking
        self.tick_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.cvd_state: Dict[str, float] = defaultdict(float)
        self.ob_skewness: Dict[str, float] = defaultdict(float)
        self._last_micro_dispatch: Dict[str, float] = {}
        self.last_price: Dict[str, float] = defaultdict(float)

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
        from sensors.quant.volatility_regime import RollingZScore

        self.micro_zscores: Dict[str, RollingZScore] = defaultdict(lambda: RollingZScore(window_size=120))
        self._last_z_update: Dict[str, float] = {}

        # Load and Distribute Sensors
        self._spawn_workers()

        # Phase 7: Micro-Event Batching to prevent Main Loop stalls
        self._micro_buffer = []
        self._last_market_time = 0.0  # Phase 50: Parity - Track latest market time (MarketTime over RealTime)
        self.throttle_ms = 100.0  # Throttled microstructure events
        self._last_tick_dispatch = {}
        self._last_ob_dispatch = {}
        self._tick_count = 0
        self._stopped = False
        self._batch_flush_task = asyncio.create_task(self._flush_micro_events_loop())

        # Start Async Listener
        self._signal_listener_task = asyncio.create_task(self._listen_for_signals())

        # Subscribe to Events (Phase 410: The Ingestion Pivot)
        self.engine.subscribe(EventType.CANDLE, self.on_candle)
        self.engine.subscribe(EventType.TICK, self.on_tick)
        self.engine.subscribe(EventType.ORDER_BOOK, self.on_orderbook)

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
            worker.daemon = True  # Phase 1201: Daemon flag — prevents main process from blocking on exit
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
        self._last_market_time = event.timestamp
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
            "atr": getattr(event, "atr", 0.0),
            "poc": getattr(event, "poc", 0.0),
            "vah": getattr(event, "vah", 0.0),
            "val": getattr(event, "val", 0.0),
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
        }

        # Dispatch to all queues
        for q in self.input_queues:
            asyncio.get_running_loop().run_in_executor(None, q.put, msg)

    async def on_tick(self, event: TickEvent):
        """
        Phase 410: Broadcast new trades (ticks) to workers.
        Phase 1: Track CVD and emit Microstructure.
        Throttled to prevent IPC explosion.
        """
        self._last_market_time = event.timestamp
        if self._tick_count % 1000 == 0:
            logger.info(f"📥 [SENSOR] Tick received: {event.symbol} at {event.timestamp}")

        now = event.timestamp
        sym = event.symbol
        self.last_price[sym] = event.price

        # Phase 1: CVD Tracking (Incremental Add only - pruning moved to throttled micro_dispatch)
        delta = 0.0
        if event.side == "BUY":
            delta = event.volume
        elif event.side == "SELL":
            delta = -event.volume
        else:
            if int(now) % 60 == 0:
                logger.warning(f"⚠️ [SENSOR] Unexpected side: {event.side} for {sym}")
        self.tick_history[sym].append((now, delta))
        self.cvd_state[sym] += delta

        await self._dispatch_micro_state(sym, now, event_data=event)

        last_dispatch = self._last_tick_dispatch.get(event.symbol, 0)

        # Throttle to max 1 update per 100ms (Using Market Time)
        if (now - last_dispatch) < (self.throttle_ms / 1000.0):
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
        Phase 1: Track Skewness.
        Throttled to prevent IPC explosion.
        """
        now = event.timestamp
        self._last_market_time = now
        sym = event.symbol

        # Phase 1: Skewness tracking moved to throttled micro_dispatch
        await self._dispatch_micro_state(sym, now, event_data=event)

        last_dispatch = self._last_ob_dispatch.get(event.symbol, 0)

        # Throttle to max 1 update per 100ms (Using Market Time)
        if (now - last_dispatch) < (self.throttle_ms / 1000.0):
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

    async def _dispatch_micro_state(self, sym: str, now: float, event_data: Any = None):
        """
        Emit internal MicrostructureEvent for SetupEngineV4, throttled.
        Phase 500: Performance - Heavy pruning and skewness calculations happen here (gated).
        """
        last_micro = self._last_micro_dispatch.get(sym, 0)
        # Throttle using market time (now)
        if (now - last_micro) < (self.throttle_ms / 1000.0):
            return

        self._last_micro_dispatch[sym] = now

        # 1. Throttled CVD Pruning (Lazy Pruning)
        cutoff = now - 5.0
        history = self.tick_history[sym]
        while history and history[0][0] < cutoff:
            old_ts, old_delta = history.popleft()
            self.cvd_state[sym] -= old_delta

        # 2. Throttled L2 Depth & Skewness Calculation (Phase 1300)
        if not hasattr(self, "bid_depth_5"):
            self.bid_depth_5: Dict[str, float] = defaultdict(float)
            self.ask_depth_5: Dict[str, float] = defaultdict(float)
            self.current_spread: Dict[str, float] = defaultdict(float)

        if isinstance(event_data, OrderBookEvent) and event_data.bids and event_data.asks:
            # Update internal depth state
            self.bid_depth_5[sym] = sum(float(b[1]) for b in event_data.bids[:5])
            self.ask_depth_5[sym] = sum(float(a[1]) for a in event_data.asks[:5])
            self.current_spread[sym] = float(event_data.asks[0][0]) - float(event_data.bids[0][0])

            # Calculate Skewness (Volume Ratio)
            total_vol = self.bid_depth_5[sym] + self.ask_depth_5[sym]
            if total_vol > 0:
                self.ob_skewness[sym] = self.bid_depth_5[sym] / total_vol

        # 3. Phase 1000: De-correlated Z-Score (P0)
        # Use separate 60s history to measure the "Toxic" nature of the last 5 seconds.
        # We update the Z-Score distribution only every 1s (to reduce autocorrelation)
        # but we measure every throttle interval.
        z_engine = self.micro_zscores[sym]
        last_z_upd = self._last_z_update.get(sym, 0)
        if now - last_z_upd >= 1.0:  # Add to statistical history every 1 second
            z_engine.update(self.cvd_state[sym])
            self._last_z_update[sym] = now

        z = z_engine.get_zscore(self.cvd_state[sym]) if z_engine.is_ready else 0.0

        evt = MicrostructureEvent(
            type=EventType.MICROSTRUCTURE,
            timestamp=now,
            symbol=sym,
            cvd=self.cvd_state[sym],
            skewness=self.ob_skewness.get(sym, 0.5),
            bid_depth_5=self.bid_depth_5[sym],
            ask_depth_5=self.ask_depth_5[sym],
            spread=self.current_spread[sym],
            z_score=z,
            price=self.last_price[sym],
        )

        # BACKTEST FIDELITY: Dispatch immediately as a batch of 1 to bypass async lag
        batch_evt = MicrostructureBatchEvent(type=EventType.MICROSTRUCTURE_BATCH, timestamp=now, events=[evt])

        # Throttled TRACE (Every 100 ticks)
        if hasattr(self, "_tick_count"):
            self._tick_count += 1
        else:
            self._tick_count = 1

        if self._tick_count % 1000 == 0:
            logger.info(
                f"📡 [SENSOR] Dispatching micro batch {self._tick_count} | CVD: {self.cvd_state[sym]:.2f} | Z: {z:.2f}"
            )

        await self.engine.dispatch(batch_evt)

    async def _flush_micro_buffer(self):
        """Internal helper to flush the micro buffer."""
        if not self._micro_buffer:
            return

        batch_events = self._micro_buffer
        self._micro_buffer = []

        batch_evt = MicrostructureBatchEvent(
            type=EventType.MICROSTRUCTURE_BATCH, timestamp=self._last_market_time, events=batch_events
        )
        await self.engine.dispatch(batch_evt)

    async def _flush_micro_events_loop(self):
        """Background task to flush buffered micro events as a batch."""
        while not self._stopped:
            try:
                await asyncio.sleep(0.1)  # Flush every 100ms
                await self._flush_micro_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in micro flush loop: {e}")

    async def _listen_for_signals(self):
        """Async loop to consume signals from workers."""
        logger.info("👂 Listening for signals from workers...")

        while not self._stopped:
            try:
                # Non-blocking polling of the output queue
                processed = 0
                while not self.output_queue.empty() and processed < 1000:
                    msg = self.output_queue.get_nowait()
                    await self._handle_worker_message(msg)
                    processed += 1

                if processed == 0:
                    await asyncio.sleep(0.01)  # 10ms poll interval
                else:
                    await asyncio.sleep(0)  # Yield for other tasks if busy

            except asyncio.CancelledError:
                # Phase 1201: Critical fix — must break cleanly on shutdown.
                # Previously caught by `except Exception` and re-awaited,
                # creating an infinite retry loop that blocked asyncio.run() from returning.
                logger.info("🛑 SensorManager signal listener stopped.")
                break
            except Exception as e:
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
        context = msg.get("context")  # Phase 700: Get context from worker
        if isinstance(signals, dict):
            await self._emit_signal(signals, sensor_name, symbol, context)
        elif isinstance(signals, list):
            for s in signals:
                if s:
                    await self._emit_signal(s, sensor_name, symbol, context)

        # Update cooldown
        self._last_trigger[cooldown_key] = self._candle_index

    def _can_fire(self, key: str) -> bool:
        """Check cooldown."""
        last_index = self._last_trigger.get(key)
        if last_index is None:
            return True
        return (self._candle_index - last_index) >= self.cooldown_bars

    async def _emit_signal(self, signal_data: dict, sensor_name: str, symbol: str = None, context: dict = None):
        """Emit SignalEvent."""
        from config.sensors import get_sensor_params

        metadata = dict(signal_data.get("metadata") or {})
        signal_tf = signal_data.get("timeframe", self.timeframe)

        # Globally inject OHLC data for the structural guardians
        if isinstance(context, dict):
            candle_1m = context.get(self.timeframe) if self.timeframe in context else context.get("1m")
            if isinstance(candle_1m, dict):
                for k in ["open", "high", "low", "close"]:
                    if metadata.get(k) is None and candle_1m.get(k) is not None:
                        metadata[k] = candle_1m.get(k)

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
        if isinstance(context, dict):
            for tf in ("15m", "1h", "4h"):
                tf_candle = context.get(tf)
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

            # Phase 710: ATR-based Breathing Room (Volatility Awareness)
            candle_1m = context.get("1m")
            if isinstance(candle_1m, dict) and candle_1m.get("atr"):
                metadata["atr_1m"] = candle_1m["atr"]

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
            timestamp=(
                getattr(signal_data, "timestamp", self._last_market_time)
                if isinstance(signal_data, dict)
                else self._last_market_time
            ),
            symbol=target_symbol,
            side=signal_data["side"],
            sensor_id=sensor_name,
            score=signal_data.get("score", 1.0),
            metadata=metadata,
            fast_track=bool(metadata.get("fast_track", False)),
            price=metadata.get("price", 0.0),
        )
        # Phase 180: Silent Sensors (Switch to DEBUG to reduce minute-boundary log burst)
        logger.debug(f"📡 Signal Detected: {sensor_name}@{signal_tf} -> {signal_data['side']} [{target_symbol}]")
        await self.engine.dispatch(event)

    def stop(self):
        """Shutdown workers and cancel async tasks. Drains queues to prevent pipe deadlock."""
        logger.info("🛑 Stopping Sensor Workers...")
        self._stopped = True

        # 1. Cancel async tasks (they'll see _stopped=True on next iteration)
        for task_name in ("_batch_flush_task", "_signal_listener_task"):
            task = getattr(self, task_name, None)
            if task and not task.done():
                task.cancel()

        # 2. Send STOP to all workers
        for q in self.input_queues:
            try:
                q.put_nowait("STOP")
            except Exception:
                pass

        # 3. Drain the output queue to prevent feeder thread deadlock
        # (workers may have written data that nobody reads after shutdown)
        try:
            while not self.output_queue.empty():
                self.output_queue.get_nowait()
        except Exception:
            pass

        # 4. Join/terminate workers
        for w in self.workers:
            w.join(timeout=1.0)
            if w.is_alive():
                w.terminate()

        # 5. Close queues to release pipe file descriptors
        try:
            self.output_queue.close()
            self.output_queue.join_thread()
        except Exception:
            pass
        for q in self.input_queues:
            try:
                q.close()
                q.join_thread()
            except Exception:
                pass

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
        from sensors.footprint.delta_velocity import DeltaVelocitySensorV3
        from sensors.footprint.exhaustion import FootprintVolumeExhaustion
        from sensors.footprint.flow_shift import FootprintDeltaPoCShift
        from sensors.footprint.imbalance import FootprintImbalanceV3
        from sensors.footprint.liquidation_cascade import LiquidationCascadeDetector
        from sensors.footprint.session import SessionValueArea
        from sensors.footprint.volatility import VolatilitySpikeSensor
        from sensors.regime.one_timeframing import OneTimeframingSensor

        return [
            OneTimeframingSensor,
            SessionValueArea,
            DebugHeartbeatV3,
            FootprintImbalanceV3,
            VolatilitySpikeSensor,
            FootprintAbsorptionV3,
            FootprintPOCRejection,
            FootprintDeltaDivergence,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
            FootprintVolumeExhaustion,
            FootprintDeltaPoCShift,
            CumulativeDeltaSensorV3,
            BigOrderSensor,
            DeltaVelocitySensorV3,
            LiquidationCascadeDetector,
        ]
