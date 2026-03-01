"""
Sensor Worker Process.
Run sensors in a long-lived separate process to preserve state (actors).
"""

import logging
import multiprocessing
import traceback
from typing import Any, Dict, List, Type

# We need to import the base sensor class type for type hinting if possible,
# but to avoid circular imports we might skip it or use TYPE_CHECKING
# from sensors.sensor_base import V3SensorBase


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

    def run(self):
        """Main loop of the worker process."""
        # Setup logging for this process
        logging.basicConfig(
            level=logging.INFO, format=f"%(asctime)s [%(levelname)s] [Worker-{self.worker_id}] %(message)s"
        )
        logger = logging.getLogger(f"SensorWorker-{self.worker_id}")

        try:
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

                symbol_sensors.append(sensor)
            except Exception as e:
                logger.error(f"❌ Failed to instantiate {sensor_cls} for {symbol}: {e}")

        self.sensors[symbol] = symbol_sensors

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
                    self.output_queue.put({"sensor": sensor.name, "symbol": symbol, "signals": signals})

            except Exception as e:
                logger.error(f"❌ Error in sensor {sensor.name} ({symbol}) on {event_type}: {e}")
