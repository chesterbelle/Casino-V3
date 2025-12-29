"""
Signal Aggregator for Casino-V3.
Collects signals from multiple sensors and applies Weighted Consensus scoring.

Weighted Consensus: ΣL vs ΣS
- Sum all LONG sensor scores → ΣL
- Sum all SHORT sensor scores → ΣS
- The side with higher total wins
- Captures both quality (individual score) and quantity (consensus)
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, List

from config.strategies import get_sensor_type, get_strategy_for_sensor
from core.events import AggregatedSignalEvent, EventType, SignalEvent

from .sensor_tracker import SensorTracker

logger = logging.getLogger(__name__)

# Configuration
SIGNAL_TIMEOUT_MS = 100  # Wait 100ms for all sensors to fire
MIN_SCORE_THRESHOLD = 0.5  # Only sensors with proven/neutral performance participate
MIN_MARGIN_RATIO = 0.10  # Winner must have 10% higher Σ than loser for conviction


class SignalAggregatorV3:
    """
    Aggregates signals from multiple sensors using intelligent scoring.

    Instead of simple voting, scores each signal based on sensor's historical
    performance (expectancy, win rate, profit factor, etc).
    """

    def __init__(self, engine):
        self.engine = engine
        # Multi-Asset: Symbol -> Timestamp -> List[Signal]
        self.signal_buffer: Dict[str, Dict[float, List[SignalEvent]]] = defaultdict(lambda: defaultdict(list))
        # Track latest candle timestamp per symbol
        self.latest_candle_ts: Dict[str, float] = {}
        self.timeout_tasks: Dict[str, asyncio.Task] = {}

        # Initialize sensor tracker
        self.tracker = SensorTracker()

        # Subscribe to SIGNAL events
        self.engine.subscribe(EventType.SIGNAL, self.on_signal)

        # Subscribe to CANDLE events to track candle changes
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        logger.info("✅ SignalAggregator initialized with intelligent scoring")

    async def on_candle(self, event):
        """Track new candles to reset signal buffer."""
        symbol = event.symbol
        new_ts = event.timestamp

        last_ts = self.latest_candle_ts.get(symbol)

        # If we moved to a new candle for this symbol, process any leftovers from previous
        if last_ts and last_ts != new_ts:
            if self.signal_buffer[symbol].get(last_ts):
                await self._process_signals(symbol, last_ts)

        # Update to new candle
        self.latest_candle_ts[symbol] = new_ts

        # Clean old buffers (keep last 5 candles only)
        # Access buffer for this symbol
        symbol_buffer = self.signal_buffer[symbol]
        if len(symbol_buffer) > 5:
            sorted_keys = sorted(symbol_buffer.keys())
            # Remove oldest keys until only 5 remain
            while len(symbol_buffer) > 5:
                del symbol_buffer[sorted_keys.pop(0)]

    async def on_signal(self, event: SignalEvent):
        """Collect signal and start timeout if first signal for this candle."""
        symbol = event.symbol

        # Use the latest updated candle timestamp for this symbol
        candle_ts = self.latest_candle_ts.get(symbol)

        if candle_ts is None:
            logger.warning(f"⚠️ Received signal for {symbol} but no candle timestamp set")
            return

        # Add signal to buffer
        self.signal_buffer[symbol][candle_ts].append(event)

        current_count = len(self.signal_buffer[symbol][candle_ts])

        # If this is the first signal for this candle, start timeout
        if current_count == 1:
            # We don't store task reference to cancel it, basically fire-and-forget timeout
            # But maybe good to track context?
            asyncio.create_task(self._timeout_handler(symbol, candle_ts))
            logger.debug(f"🕐 Started {SIGNAL_TIMEOUT_MS}ms timeout for {symbol} candle {candle_ts}")

    async def _timeout_handler(self, symbol: str, candle_ts: float):
        """Wait for timeout, then process signals."""
        await asyncio.sleep(SIGNAL_TIMEOUT_MS / 1000.0)
        await self._process_signals(symbol, candle_ts)

    async def _process_signals(self, symbol: str, candle_ts: float):
        """
        Process buffered signals using Weighted Consensus.

        Weighted Consensus Algorithm:
        1. Filter signals by minimum score threshold
        2. Extract HTF context (optional trend filter)
        3. Calculate ΣL (sum of LONG scores) and ΣS (sum of SHORT scores)
        4. Winner = side with higher Σ
        5. Confidence = winner_sum / total_sum
        """
        signals = self.signal_buffer[symbol].get(candle_ts, [])

        if not signals:
            return

        # 1. Filter by Score (Quality Gate)
        valid_signals = [s for s in signals if self.tracker.get_sensor_score(s.sensor_id) >= MIN_SCORE_THRESHOLD]

        if not valid_signals:
            logger.debug(
                f"   All signals filtered out for candle {candle_ts} due to low score (< {MIN_SCORE_THRESHOLD})"
            )
            aggregated = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=time.time(),
                symbol=signals[0].symbol,
                candle_timestamp=candle_ts,
                selected_sensor="None",
                sensor_score=0.0,
                side="SKIP",
                confidence=0.0,
                total_signals=len(signals),
            )
            await self.engine.dispatch(aggregated)
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # 2. Extract HTF context from ALL context sensors (weighted by count)
        context_sensors = {"HigherTFTrend", "HurstRegime", "MTFImpulse"}
        htf_long_count = 0
        htf_short_count = 0

        for signal in valid_signals:
            if signal.sensor_id in context_sensors:
                if signal.side == "LONG":
                    htf_long_count += 1
                elif signal.side == "SHORT":
                    htf_short_count += 1
                logger.debug(f"📊 HTF Context: {signal.sensor_id} = {signal.side}")

        # Determine HTF consensus (majority of context sensors)
        if htf_long_count > htf_short_count:
            htf_context = "LONG"
        elif htf_short_count > htf_long_count:
            htf_context = "SHORT"
        else:
            htf_context = None  # No clear HTF direction or no context sensors

        if htf_context:
            logger.debug(f"📊 HTF Consensus: {htf_context} ({htf_long_count}L/{htf_short_count}S)")

        # 3. WEIGHTED CONSENSUS - Calculate ΣL and ΣS
        trading_signals = [s for s in valid_signals if s.sensor_id not in context_sensors]

        if not trading_signals:
            logger.debug("   No trading signals after filtering context sensors")
            aggregated = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=time.time(),
                symbol=signals[0].symbol,
                candle_timestamp=candle_ts,
                selected_sensor="None",
                sensor_score=0.0,
                side="SKIP",
                confidence=0.0,
                total_signals=len(signals),
            )
            await self.engine.dispatch(aggregated)
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # Calculate weighted sums
        # Weight = historical_score * signal_strength
        sigma_long = 0.0
        sigma_short = 0.0
        long_signals = []
        short_signals = []

        for signal in trading_signals:
            historical_score = self.tracker.get_sensor_score(signal.sensor_id)
            # Signal strength: 0-1, default 1.0 if not provided
            signal_strength = getattr(signal, "score", 1.0)
            # Combined weight: historical performance * current signal strength
            combined_score = historical_score * signal_strength

            if signal.side == "LONG":
                sigma_long += combined_score
                long_signals.append(
                    {
                        "signal": signal,
                        "sensor_id": signal.sensor_id,
                        "score": combined_score,
                        "strength": signal_strength,
                    }
                )
            elif signal.side == "SHORT":
                sigma_short += combined_score
                short_signals.append(
                    {
                        "signal": signal,
                        "sensor_id": signal.sensor_id,
                        "score": combined_score,
                        "strength": signal_strength,
                    }
                )

        total_weight = sigma_long + sigma_short

        # Log weighted consensus
        logger.debug(
            f"📊 Weighted Consensus: ΣL={sigma_long:.2f} ({len(long_signals)} sensors) | "
            f"ΣS={sigma_short:.2f} ({len(short_signals)} sensors)"
        )

        # 4. Determine winner by weighted sum
        if sigma_long == sigma_short:
            # Exact tie (very rare) - SKIP
            logger.info(f"⚖️ Exact tie: ΣL={sigma_long:.2f} = ΣS={sigma_short:.2f} → SKIP")
            aggregated = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=time.time(),
                symbol=signals[0].symbol,
                candle_timestamp=candle_ts,
                selected_sensor="None",
                sensor_score=0.0,
                side="SKIP",
                confidence=0.0,
                total_signals=len(signals),
            )
            await self.engine.dispatch(aggregated)
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # Winner is side with higher Σ
        if sigma_long > sigma_short:
            consensus_side = "LONG"
            winner_sum = sigma_long
            winner_signals = long_signals
            loser_sum = sigma_short
        else:
            consensus_side = "SHORT"
            winner_sum = sigma_short
            winner_signals = short_signals
            loser_sum = sigma_long

        # 5. Minimum Margin Check (conviction filter)
        # If both sides are close, skip - not enough conviction
        margin_ratio = (winner_sum - loser_sum) / total_weight if total_weight > 0 else 0

        # FAST TRACK: OrderFlow sensors bypass consensus margin (they are high conviction)
        has_order_flow = any(get_sensor_type(s["sensor_id"]) == "OrderFlow" for s in winner_signals)

        if not has_order_flow and margin_ratio < MIN_MARGIN_RATIO and loser_sum > 0:
            logger.info(
                f"⚖️ Low conviction: margin {margin_ratio:.1%} < {MIN_MARGIN_RATIO:.0%} | "
                f"ΣL={sigma_long:.2f} ΣS={sigma_short:.2f} → SKIP"
            )
            aggregated = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=time.time(),
                symbol=signals[0].symbol,
                candle_timestamp=candle_ts,
                selected_sensor="None",
                sensor_score=0.0,
                side="SKIP",
                confidence=0.0,
                total_signals=len(signals),
            )
            await self.engine.dispatch(aggregated)
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # 6. HTF Alignment Check (optional filter)
        if htf_context and consensus_side != htf_context:
            logger.info(
                f"🚫 Rejecting {consensus_side}: Against HTF trend ({htf_context}) | "
                f"ΣL={sigma_long:.2f} ΣS={sigma_short:.2f}"
            )
            aggregated = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=time.time(),
                symbol=signals[0].symbol,
                candle_timestamp=candle_ts,
                selected_sensor="None",
                sensor_score=0.0,
                side="SKIP",
                confidence=0.0,
                total_signals=len(signals),
            )
            await self.engine.dispatch(aggregated)
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # 7. STRATEGY TRIGGER FILTER
        # All sensors vote, but trade only if a sensor from active strategy participated
        from config.strategies import get_active_sensors

        strategy_sensors = get_active_sensors()

        if strategy_sensors:
            # Filter winner signals to only those from active strategy
            strategy_signals_on_winning_side = [s for s in winner_signals if s["sensor_id"] in strategy_sensors]

            if not strategy_signals_on_winning_side:
                # Consensus reached but no strategy sensor participated → SKIP
                logger.info(
                    f"⏭️ Consensus {consensus_side} but no strategy sensor participated | "
                    f"ΣL={sigma_long:.2f} ΣS={sigma_short:.2f} → SKIP"
                )
                aggregated = AggregatedSignalEvent(
                    type=EventType.AGGREGATED_SIGNAL,
                    timestamp=time.time(),
                    symbol=signals[0].symbol,
                    candle_timestamp=candle_ts,
                    selected_sensor="None",
                    sensor_score=0.0,
                    side="SKIP",
                    confidence=0.0,
                    total_signals=len(signals),
                )
                await self.engine.dispatch(aggregated)
                if candle_ts in self.signal_buffer:
                    del self.signal_buffer[candle_ts]
                return

            # Select BEST sensor from strategy signals (not overall best)
            selected = max(strategy_signals_on_winning_side, key=lambda s: s["score"])
            logger.debug(
                f"📊 Strategy trigger: {selected['sensor_id']} from "
                f"{len(strategy_signals_on_winning_side)} strategy sensors"
            )
        else:
            # No strategy defined - use overall best (DebugAll mode)
            selected = max(winner_signals, key=lambda s: s["score"])

        # Get strategy context for the selected sensor
        strategies = get_strategy_for_sensor(selected["sensor_id"])
        strategy_name = strategies[0] if strategies else "Unknown"

        # Calculate confidence: margin of victory
        margin = (winner_sum - loser_sum) / total_weight if total_weight > 0 else 0
        confidence = margin * selected["score"]  # Scale by best sensor's quality

        logger.info(
            f"✅ WEIGHTED CONSENSUS {consensus_side}: "
            f"Σ={winner_sum:.2f} vs {loser_sum:.2f} (Δ={winner_sum - loser_sum:.2f}) | "
            f"Trigger: {selected['sensor_id']} ({selected['score']:.3f}) | "
            f"Voters: {len(winner_signals)} | "
            f"HTF: {'✓' if htf_context == consensus_side else 'N/A'}"
        )

        aggregated = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=time.time(),
            symbol=selected["signal"].symbol,
            candle_timestamp=candle_ts,
            selected_sensor=selected["sensor_id"],
            sensor_score=selected["score"],
            side=consensus_side,
            confidence=confidence,
            total_signals=len(signals),
            metadata={
                "sigma_long": sigma_long,
                "sigma_short": sigma_short,
                "long_count": len(long_signals),
                "short_count": len(short_signals),
                "margin": winner_sum - loser_sum,
                "total_voters": len(winner_signals),
                **(selected["signal"].metadata or {}),
            },
            strategy_name=strategy_name,
        )

        await self.engine.dispatch(aggregated)

        # Clear processed signals
        if candle_ts in self.signal_buffer[symbol]:
            del self.signal_buffer[symbol][candle_ts]
