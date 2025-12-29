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
from .events import CandleEvent, EventType, SignalEvent

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

        # Load and Distribute Sensors
        self._spawn_workers()

        # Start Async Listener
        asyncio.create_task(self._listen_for_signals())

        # Subscribe to Candles
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        logger.info("✅ SensorManager initialized in Actor Model mode")

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
        for i, cls in enumerate(enabled_classes):
            chunks[i % num_workers].append(cls)

        # 4. Create Processes
        for i in range(num_workers):
            if not chunks[i]:
                continue  # Skip empty workers if few sensors

            q_in = multiprocessing.Queue()
            self.input_queues.append(q_in)

            worker = SensorWorker(
                worker_id=i, sensor_classes=chunks[i], input_queue=q_in, output_queue=self.output_queue
            )
            worker.start()
            self.workers.append(worker)

        logger.info(f"🚀 {len(self.workers)} Workers started.")

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
                while not self.output_queue.empty():
                    msg = self.output_queue.get_nowait()
                    await self._handle_worker_message(msg)

                await asyncio.sleep(0.01)  # 10ms poll interval

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
        # use symbol+sensor key
        cooldown_key = f"{symbol}_{sensor_name}" if symbol else sensor_name

        if not self._can_fire(cooldown_key):
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

        metadata = signal_data.get("metadata", {})
        signal_tf = signal_data.get("timeframe", self.timeframe)

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
        )
        logger.info(f"📡 Signal Detected: {sensor_name}@{signal_tf} -> {signal_data['side']} [{target_symbol}]")
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
        # Import all V3 sensors
        from sensors.absorption_block import AbsorptionBlockV3
        from sensors.adaptive_rsi import AdaptiveRSIV3
        from sensors.adx_filter import ADXFilterV3
        from sensors.bollinger_rejection import BollingerRejectionV3
        from sensors.bollinger_squeeze import BollingerSqueezeV3
        from sensors.bollinger_touch import BollingerTouchV3
        from sensors.cci_reversion import CCIReversionV3
        from sensors.consecutive_candles import ConsecutiveCandlesV3
        from sensors.debug_heartbeat import DebugHeartbeatV3
        from sensors.deceleration_candles import DecelerationCandlesV3
        from sensors.doji_indecision import DojiIndecisionV3
        from sensors.double_bottom import DoubleBottomV3
        from sensors.double_top import DoubleTopV3
        from sensors.ema50_support import EMA50SupportV3
        from sensors.ema_crossover import EMACrossoverV3
        from sensors.engulfing_pattern import EngulfingPatternV3
        from sensors.extreme_candle_ratio import ExtremeCandleRatioV3
        from sensors.fakeout import FakeoutV3
        from sensors.footprint.absorption import FootprintAbsorptionV3
        from sensors.footprint.advanced import (
            FootprintDeltaDivergence,
            FootprintPOCRejection,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
        )
        from sensors.footprint.exhaustion import FootprintVolumeExhaustion
        from sensors.footprint.flow_shift import FootprintDeltaPoCShift
        from sensors.footprint.imbalance import FootprintImbalanceV3
        from sensors.fvg_retest import FVGRetestV3
        from sensors.higher_highs_lower_lows import HigherHighsLowerLowsV3
        from sensors.higher_tf_trend import HigherTFTrendV3
        from sensors.hurst_regime import HurstRegimeV3
        from sensors.inside_bar_breakout import InsideBarBreakoutV3
        from sensors.island_reversal import IslandReversalV3
        from sensors.keltner_breakout import KeltnerBreakoutV3
        from sensors.keltner_reversion import KeltnerReversionV3
        from sensors.liquidity_void import LiquidityVoidV3
        from sensors.long_tail import LongTailV3
        from sensors.macd_crossover import MACDCrossoverV3
        from sensors.marubozu_momentum import MarubozuMomentumV3
        from sensors.micro_trend import MicroTrendV3
        from sensors.momentum_burst import MomentumBurstV3
        from sensors.morning_star import MorningStarV3
        from sensors.mtf_impulse import MTFImpulseV3
        from sensors.narrow_range7 import NarrowRange7V3
        from sensors.order_block import OrderBlockV3
        from sensors.parabolic_sar import ParabolicSARV3
        from sensors.pinbar_reversal import PinBarReversalV3
        from sensors.rails_pattern import RailsPatternV3
        from sensors.range_expansion import RangeExpansionV3
        from sensors.rsi_reversion import RSIReversionV3
        from sensors.smart_range import SmartRangeV3
        from sensors.stochastic_reversion import StochasticReversionV3
        from sensors.supertrend import SupertrendV3
        from sensors.support_resistance import SupportResistanceV3
        from sensors.three_bar import ThreeBarV3
        from sensors.three_black_crows import ThreeBlackCrowsV3
        from sensors.three_white_soldiers import ThreeWhiteSoldiersV3
        from sensors.tweezer_pattern import TweezerPatternV3
        from sensors.vcp_pattern import VCPPatternV3
        from sensors.volatility_wakeup import VolatilityWakeupV3
        from sensors.volume_imbalance import VolumeImbalanceV3
        from sensors.volume_spike import VolumeSpikeV3
        from sensors.vsa_reversal import VSAReversalV3
        from sensors.vwap_breakout import VWAPBreakoutV3
        from sensors.vwap_deviation import VWAPDeviationV3
        from sensors.vwap_momentum import VWAPMomentumV3
        from sensors.wick_rejection import WickRejectionV3
        from sensors.wide_range_bar import WideRangeBarV3
        from sensors.williams_r_reversion import WilliamsRReversionV3
        from sensors.wyckoff_spring import WyckoffSpringV3
        from sensors.zscore_reversion import ZScoreReversionV3

        return [
            DebugHeartbeatV3,
            EMACrossoverV3,
            PinBarReversalV3,
            RailsPatternV3,
            EMA50SupportV3,
            MarubozuMomentumV3,
            FootprintImbalanceV3,
            FootprintAbsorptionV3,
            FootprintPOCRejection,
            FootprintDeltaDivergence,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
            FootprintVolumeExhaustion,
            FootprintDeltaPoCShift,
            VWAPBreakoutV3,
            ExtremeCandleRatioV3,
            InsideBarBreakoutV3,
            DecelerationCandlesV3,
            VWAPDeviationV3,
            VCPPatternV3,
            EngulfingPatternV3,
            RSIReversionV3,
            BollingerTouchV3,
            KeltnerReversionV3,
            MACDCrossoverV3,
            SupertrendV3,
            StochasticReversionV3,
            CCIReversionV3,
            WilliamsRReversionV3,
            ZScoreReversionV3,
            ADXFilterV3,
            BollingerSqueezeV3,
            ParabolicSARV3,
            MomentumBurstV3,
            VolumeImbalanceV3,
            OrderBlockV3,
            FVGRetestV3,
            DojiIndecisionV3,
            MorningStarV3,
            LongTailV3,
            AbsorptionBlockV3,
            LiquidityVoidV3,
            FakeoutV3,
            HigherTFTrendV3,
            MTFImpulseV3,
            AdaptiveRSIV3,
            BollingerRejectionV3,
            HurstRegimeV3,
            KeltnerBreakoutV3,
            MicroTrendV3,
            SmartRangeV3,
            VolatilityWakeupV3,
            VSAReversalV3,
            VWAPMomentumV3,
            WickRejectionV3,
            WyckoffSpringV3,
            VolumeSpikeV3,
            TweezerPatternV3,
            ThreeBarV3,
            SupportResistanceV3,
            NarrowRange7V3,
            ConsecutiveCandlesV3,
            RangeExpansionV3,
            ThreeWhiteSoldiersV3,
            ThreeBlackCrowsV3,
            WideRangeBarV3,
            DoubleBottomV3,
            DoubleTopV3,
            HigherHighsLowerLowsV3,
            IslandReversalV3,
        ]
