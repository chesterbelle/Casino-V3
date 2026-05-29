"""
Sensor Worker Process.
Run sensors in a long-lived separate process to preserve state (actors).
"""

import logging
import logging.handlers
import multiprocessing
import os
import queue
import traceback
from typing import Any, Dict, List, Type

# v8.3: Non-blocking logging via QueueHandler + QueueListener
_log_queue: queue.Queue = queue.Queue(-1)  # Unlimited size
_log_qh: logging.handlers.QueueHandler = logging.handlers.QueueHandler(_log_queue)
_listener: logging.handlers.QueueListener = None  # Started after logger is configured


def _setup_async_logging(logger: logging.Logger):
    """Configure logger with QueueHandler for non-blocking file I/O."""
    global _listener
    if _listener is not None:
        return  # Already configured

    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/sensors_worker.log", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))

    _listener = logging.handlers.QueueListener(_log_queue, fh, respect_handler_level=True)
    _listener.start()
    logger.addHandler(_log_qh)


# Configure minimal logging for the worker
logger = logging.getLogger("SensorWorker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | WORKER:%(process)d:%(name)s | %(levelname)s | %(message)s"))
    logger.addHandler(ch)
    _setup_async_logging(logger)


class SensorWorker(multiprocessing.Process):
    """
    A persistent worker process that manages a subset of sensors.

    It listens on an input_queue for new Candle data, updates its internal
    sensors, and pushes any resulting signals to an output_queue.
    """

    def __init__(
        self,
        worker_id: int,
        sensor_classes: List[Type],
        input_queue: multiprocessing.Queue,
        output_queue: multiprocessing.Queue,
    ):
        """
        Initialize the worker.

        Args:
            worker_id: ID for identification
            sensor_classes: List of sensor classes to instantiate and manage
            input_queue: Queue to receive {"event": "candle", "data": ...} or "STOP"
            output_queue: Queue to send {"sensor": name, "signals": ...}
        """
        super().__init__(name=f"SensorWorker-{worker_id}")
        self.worker_id = worker_id
        # We pass classes, not instances, to avoid pickling issues with initialized state
        self.sensor_classes = sensor_classes
        self.input_queue = input_queue
        self.output_queue = output_queue
        # Multi-Asset: Key by symbol -> List[Sensor]
        self.sensors: Dict[str, List[Any]] = {}
        self._running = True
        logger.debug(f"📦 [DEBUG] SensorWorker-{self.worker_id} initialized in parent (PID: {os.getpid()})")

    def run(self):
        """Main loop of the worker process."""
        # Setup logging for this process
        logging.basicConfig(
            level=logging.INFO, format=f"%(asctime)s [%(levelname)s] [Worker-{self.worker_id}] %(message)s"
        )
        logger = logging.getLogger(f"SensorWorker-{self.worker_id}")

        try:
            logger.debug(f"🚀 [DEBUG] SensorWorker-{self.worker_id} starting (PID: {os.getpid()})")
            logger.info(f"🚀 Worker started. Ready to process {len(self.sensor_classes)} sensor types.")

            # Main Loop
            while self._running:
                try:
                    # Blocking get - waits for work
                    message = self.input_queue.get()

                    if message == "STOP":
                        logger.info("🛑 Received STOP signal.")
                        break

                    if isinstance(message, dict):
                        event_type = message.get("event")
                        symbol = message.get("symbol")
                        data = message.get("data")

                        if not symbol:
                            logger.warning("⚠️ Received message without symbol!")
                            continue

                        # Lazy instantiation for new symbols
                        self._ensure_sensors_for_symbol(symbol, logger)

                        if event_type == "candle":
                            context = message.get("context")
                            self._process_sensors(symbol, data, context, logger, "candle")
                        elif event_type == "tick":
                            self._process_sensors(symbol, data, None, logger, "tick")
                        elif event_type == "orderbook":
                            self._process_sensors(symbol, data, None, logger, "orderbook")

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"❌ Worker loop error: {e}")
                    traceback.print_exc()

        except Exception as e:
            logger.critical(f"❌ Worker process crashed: {e}")
        finally:
            logger.info("👋 Worker shutting down.")

    def _ensure_sensors_for_symbol(self, symbol: str, logger: logging.Logger):
        """Ensure sensors are instantiated for the given symbol."""
        if symbol in self.sensors:
            return

        logger.info(f"✨ Instantiating {len(self.sensor_classes)} sensors for {symbol}...")
        from config.sensors import ACTIVE_SENSORS, get_sensor_timeframes
        from decision.engine.profile_manager import profile_manager

        symbol_sensors = []
        for sensor_cls in self.sensor_classes:
            try:
                sensor = sensor_cls()

                # Double check if enabled (redundant but safe)
                if not ACTIVE_SENSORS.get(sensor.name, False):
                    continue

                # Configure timeframes
                sensor.timeframes = get_sensor_timeframes(sensor.name)
                # Assign symbol to sensor if it supports it (useful for logging inside sensor)
                sensor.symbol = symbol
                sensor._optimal_tf = sensor.timeframes[0] if sensor.timeframes else "1m"

                # Apply per-symbol profile params if sensor supports configure()
                if hasattr(sensor, "configure"):
                    sensor_params = profile_manager.get_sensor_params(symbol, sensor.name)
                    if sensor_params:
                        sensor.configure(symbol, sensor_params)

                symbol_sensors.append(sensor)
            except Exception as e:
                logger.error(f"❌ Failed to instantiate {sensor_cls} for {symbol}: {e}")

        self.sensors[symbol] = symbol_sensors

        # Phase 2310: Hot-prime FootprintRegistry for this symbol inside the worker
        from core.footprint_registry import footprint_registry
        from core.tick_registry import tick_registry

        tick_size = tick_registry.get(symbol)
        footprint_registry.register_symbol(symbol, tick_size)

    def _process_sensors(
        self, symbol: str, data: Dict, context: Any, logger: logging.Logger, event_type: str = "candle"
    ):
        """Run calculations for sensors of a specific symbol."""
        # Get sensors only for this symbol to avoid state mixing
        active_sensors = self.sensors.get(symbol, [])

        for sensor in active_sensors:
            try:
                signals = None

                # Phase 410: Route data based on event type
                if event_type == "candle" and hasattr(sensor, "calculate"):
                    signals = sensor.calculate(context if context else data)
                elif event_type == "tick" and hasattr(sensor, "on_tick"):
                    signals = sensor.on_tick(data)
                elif event_type == "orderbook" and hasattr(sensor, "on_orderbook"):
                    signals = sensor.on_orderbook(data)

                if signals:
                    # Phase 700: Include context in output for HTF level extraction
                    output = {"sensor": sensor.name, "symbol": symbol, "signals": signals}
                    if context:
                        output["context"] = context
                    self.output_queue.put(output)

            except Exception as e:
                logger.error(f"❌ Error in sensor {sensor.name} ({symbol}) on {event_type}: {e}")
