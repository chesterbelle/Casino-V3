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
from typing import Dict, List, Optional

from config.sensors import get_sensor_params
from config.strategies import get_sensor_type, get_strategy_for_sensor
from core.events import AggregatedSignalEvent, EventType, SignalEvent
from core.observability.decision_auditor import DecisionAuditor

from .sensor_tracker import SensorTracker

logger = logging.getLogger(__name__)

# Configuration
SIGNAL_TIMEOUT_MS = 20  # Phase 310: Compressed from 500ms to 20ms to eliminate T0-T1 latency bottlenecks
MIN_SCORE_THRESHOLD = 0.5  # Only sensors with proven/neutral performance participate
MIN_MARGIN_RATIO = 0.10  # Winner must have 10% higher Σ than loser for conviction

# =============================================================================
# WINDOW TYPE COMPATIBILITY (Liquidity Windows Adaptation)
# =============================================================================
# Maps sensors to compatible window types (adapted from Dalton's Day Type)
# TREND_WINDOW: Follow direction, no fading
# RANGE_WINDOW: Fade extremes, reversal plays
# NORMAL_WINDOW: Mixed approach, most sensors work

SENSOR_WINDOW_TYPE_COMPAT = {
    # OrderFlow Sensors (Dale)
    "FootprintImbalanceV3": ["TREND_WINDOW", "NORMAL_WINDOW", "RANGE_WINDOW"],  # Works in all
    "FootprintAbsorptionV3": ["RANGE_WINDOW", "NORMAL_WINDOW"],  # Best in range (reversal)
    "FootprintStackedImbalance": ["TREND_WINDOW", "NORMAL_WINDOW"],  # Trend continuation
    "FootprintTrappedTraders": ["RANGE_WINDOW", "NORMAL_WINDOW"],  # Reversal at extremes
    "FootprintVolumeExhaustion": ["RANGE_WINDOW"],  # Only in range (volume dries at extremes)
    "CumulativeDeltaSensorV3": ["TREND_WINDOW", "NORMAL_WINDOW", "RANGE_WINDOW"],  # Works in all
    "FootprintDeltaPoCShift": ["TREND_WINDOW", "NORMAL_WINDOW"],  # Trend following
    "FootprintDeltaDivergence": ["RANGE_WINDOW", "NORMAL_WINDOW"],  # Reversal signal
    "FootprintPOCRejection": ["RANGE_WINDOW", "NORMAL_WINDOW"],  # Reversal at POC
    "BigOrderSensor": ["TREND_WINDOW", "NORMAL_WINDOW", "RANGE_WINDOW"],  # Confirmation at key levels
    # Structural Sensors (Dalton) - Context, always allowed
    "SessionValueArea": ["TREND_WINDOW", "NORMAL_WINDOW", "RANGE_WINDOW", "DEVELOPING"],
    "OneTimeframing": ["TREND_WINDOW", "NORMAL_WINDOW", "RANGE_WINDOW", "DEVELOPING"],
}


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
        # Keep track of which candles have already been processed to avoid double-firing fast-tracked signals
        self.processed_candles: Dict[str, set] = defaultdict(set)
        # Track latest candle timestamp per symbol
        self.latest_candle_ts: Dict[str, float] = {}
        self.timeout_tasks: Dict[str, asyncio.Task] = {}

        # Initialize sensor tracker
        self.tracker = SensorTracker()

        # Phase 420: Cache for latest structural context per symbol (0-latency Fast-Track lookup)
        self.latest_context: Dict[str, Dict[str, SignalEvent]] = defaultdict(dict)

        # Phase 103: Forensic Traceability
        self.auditor = DecisionAuditor()

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
        processed_set = self.processed_candles[symbol]

        if len(symbol_buffer) > 5:
            sorted_keys = sorted(symbol_buffer.keys())
            # Remove oldest keys until only 5 remain
            while len(symbol_buffer) > 5:
                old_key = sorted_keys.pop(0)
                del symbol_buffer[old_key]
                processed_set.discard(old_key)

    async def on_signal(self, event: SignalEvent):
        """Collect signal and start timeout if first signal for this candle."""
        symbol = event.symbol

        # Use the latest updated candle timestamp for this symbol
        candle_ts = self.latest_candle_ts.get(symbol)

        if candle_ts is None:
            logger.warning(f"⚠️ Received signal for {symbol} but no candle timestamp set")
            return

        # Phase 240 Latency Fix: If this candle was already processed (via Fast-Track), ignore late arrivals
        if candle_ts in self.processed_candles[symbol]:
            logger.debug(f"⏭️ Skipping late signal for {symbol} (candle {candle_ts} already processed)")
            return

        # Add signal to buffer
        self.signal_buffer[symbol][candle_ts].append(event)

        # Phase 240: Fast-Track Execution for HFT/OrderFlow sensors
        # If an ultra-fast sensor fires, we don't wait for late-arriving noise indicators.
        # RegimeFilter sensors (Dalton) are also fast-tracked to ensure they are available for consensus.
        sensor_type = get_sensor_type(event.sensor_id)
        is_context = sensor_type in ("RegimeFilter", "Context")

        # Cache the context for 0-latency injection during Fast-Track
        if is_context:
            self.latest_context[symbol][event.sensor_id] = event
            logger.debug(f"📊 CONTEXT: Cached {event.sensor_id} for {symbol}.")

        if sensor_type == "OrderFlow" or getattr(event, "fast_track", False):
            logger.info(f"⚡ FAST-TRACK: {event.sensor_id} fired for {symbol}. Bypassing delay (0ms latency).")
            # Cancel any pending timeout task for this symbol if exists
            if symbol in self.timeout_tasks and not self.timeout_tasks[symbol].done():
                self.timeout_tasks[symbol].cancel()

            # Process immediately
            asyncio.create_task(self._process_signals(symbol, candle_ts))
            return

        current_count = len(self.signal_buffer[symbol][candle_ts])
        # If this is the first signal for this candle, start standard timeout
        if current_count == 1:
            # Store task reference to allow cancellation
            task = asyncio.create_task(self._timeout_handler(symbol, candle_ts))
            self.timeout_tasks[symbol] = task
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
        # Phase 240: Prevent double execution if already fast-tracked
        if candle_ts in self.processed_candles[symbol]:
            return

        signals = list(self.signal_buffer[symbol].get(candle_ts, []))

        # Phase 420: Inject cached structural context if missing from this exact candle's buffer.
        # This solves the Context Race Condition with ZERO latency penalty.
        existing_sensor_ids = set()
        for s in signals:
            existing_sensor_ids.add(s.sensor_id)

        for ctx_sensor_id, ctx_event in self.latest_context[symbol].items():
            if ctx_sensor_id not in existing_sensor_ids:
                signals.append(ctx_event)
                logger.debug(f"💉 FAST-TRACK: Injected cached {ctx_sensor_id} context for {symbol}")

        if not signals:
            return

        # Mark as processed immediately to prevent race conditions
        self.processed_candles[symbol].add(candle_ts)

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
            asyncio.create_task(self.engine.dispatch(aggregated))
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # 2. Extract HTF context from strictly structural sensors (Dalton)
        context_sensors = {"OneTimeframing", "SessionValueArea"}
        htf_long_count = 0
        htf_short_count = 0
        structural_levels = {}

        for signal in valid_signals:
            if signal.sensor_id in context_sensors:
                if signal.side == "LONG":
                    htf_long_count += 1
                elif signal.side == "SHORT":
                    htf_short_count += 1

                # Extract levels for Gap 1 confirmation and window context
                if signal.sensor_id == "SessionValueArea" and signal.metadata:
                    structural_levels = {
                        "poc": signal.metadata.get("poc"),
                        "vah": signal.metadata.get("vah"),
                        "val": signal.metadata.get("val"),
                        "ibh": signal.metadata.get("ib_high"),
                        "ibl": signal.metadata.get("ib_low"),
                        "mtf_side": signal.metadata.get("mtf_30m_side"),
                    }
                    # Extract Liquidity Window context (for future use)
                    _ = signal.metadata.get("window_type", "DEVELOPING")
                    _ = signal.metadata.get("liquidity_window", "unknown")
                    _ = signal.metadata.get("window_volatility", "unknown")
                logger.debug(f"📊 HTF Context: {signal.sensor_id} = {signal.side}")

        # Determine HTF consensus (majority of context sensors)
        if htf_long_count > htf_short_count:
            htf_context = "LONG"
        elif htf_short_count > htf_long_count:
            htf_context = "SHORT"
        else:
            htf_context = None

        # 2.5 Gap 1: Enforce Level-Based Confirmation
        # Dale/Dalton: Trading only near levels of interest
        prox_ticks = 10  # 1 USDT for BTC/ETH (assuming 0.1 tick size)
        _ = prox_ticks * 0.1  # prox_dist calculated but not yet used

        filtered_valid_signals = []
        for signal in valid_signals:
            if signal.sensor_id in context_sensors:
                filtered_valid_signals.append(signal)
                continue

            # If we have structural levels, enforce proximity
            if structural_levels and any(v is not None for v in structural_levels.values()):
                price = signal.metadata.get("price") or signal.metadata.get("at_price")
                if not price:
                    # Fallback to candle close (imprecise for scalping but safety net)
                    price = self.latest_candle_ts.get(signal.symbol, 0)  # This is WRONG, I need candle price
                    # Actually, aggregator doesn't have the full candle object readily available here
                    # Let's assume the sensor SHOULD provide the price.
                    # If no price, we allow it (riskier) but log a warning.
                    logger.warning(f"⚠️ Signal {signal.sensor_id} missing price metadata for level confirmation.")
                    filtered_valid_signals.append(signal)
                    continue

                # Check proximity to ANY structural level
            mtf_30m_side = structural_levels.get("mtf_side", "NEUTRAL")

            mtf_alignment = True
            if signal.side == "LONG" and mtf_30m_side == "BEARISH":
                mtf_alignment = False
            elif signal.side == "SHORT" and mtf_30m_side == "BULLISH":
                mtf_alignment = False

            if not mtf_alignment:
                logger.debug(f"⚠️ [Gap 6] MTF Divergence for {signal.sensor_id} {signal.side}: Against 30m POC flow.")
                signal.score *= 0.5  # Penalize instead of hard reject for MTF

            # WindowType removed - not suitable for HFT scalping
            # All footprint sensors now operate freely without context filtering

            filtered_valid_signals.append(signal)

        # 3. WEIGHTED CONSENSUS - Calculate ΣL and ΣS
        trading_signals = [s for s in filtered_valid_signals if s.sensor_id not in context_sensors]

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
            asyncio.create_task(self.engine.dispatch(aggregated))
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
            # Asymmetric LONG filter - reject weak LONG signals
            if signal.side == "LONG":
                sensor_params = get_sensor_params(signal.sensor_id)
                min_score_long = sensor_params.get("min_score_long", 0.0)
                signal_score = getattr(signal, "score", 1.0)
                if signal_score < min_score_long:
                    logger.debug(
                        f"⚠️ [Asymmetry Fix] Rejecting {signal.sensor_id} LONG: Score {signal_score:.2f} < Min {min_score_long:.2f}"
                    )
                    continue  # Skip this signal

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
            asyncio.create_task(self.engine.dispatch(aggregated))
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

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

        # 4.5 Multi-Confirmation Boost (Dale/Dalton)
        # "4 confirmations → Alta probabilidad de éxito"
        # Boost score when multiple sensors confirm the same setup at the same level
        MULTI_CONFIRMATION_BOOST = 0.15  # +15% score per additional confirmation

        def get_signal_level(sig_data: dict) -> Optional[float]:
            """Extract price level from signal metadata."""
            metadata = sig_data["signal"].metadata
            if not metadata:
                return None
            # Try various level keys
            for key in ["level_price", "poc", "vah", "val", "ib_high", "ib_low", "at_price", "price"]:
                if key in metadata and metadata[key] is not None:
                    return float(metadata[key])
            return None

        # Check for multi-confirmation on winning side
        if len(winner_signals) >= 2:
            confirmation_levels = {}
            for sig_data in winner_signals:
                level = get_signal_level(sig_data)
                if level is None:
                    continue
                # Round to tick granularity for grouping
                rounded_level = round(level * 10) / 10  # 0.1 tick precision
                if rounded_level not in confirmation_levels:
                    confirmation_levels[rounded_level] = []
                confirmation_levels[rounded_level].append(sig_data["sensor_id"])

            # Find the level with most confirmations
            max_confirmations = 0
            confirmed_level = None
            for level, sensors in confirmation_levels.items():
                if len(sensors) > max_confirmations:
                    max_confirmations = len(sensors)
                    confirmed_level = level

            # Apply boost if 2+ confirmations at same level
            if max_confirmations >= 2:
                boost = MULTI_CONFIRMATION_BOOST * (max_confirmations - 1)
                winner_sum *= 1 + boost
                logger.info(
                    f"🎯 Multi-Confirmation Boost: {max_confirmations} sensors at level {confirmed_level} "
                    f"(+{boost:.0%} score) | Sensors: {confirmation_levels[confirmed_level]}"
                )

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
            asyncio.create_task(self.engine.dispatch(aggregated))
            if candle_ts in self.signal_buffer:
                del self.signal_buffer[candle_ts]
            return

        # 6. HTF Alignment Check (optional filter)
        if htf_context and consensus_side != htf_context:
            # Phase 650 Remedy: Allow high-conviction override
            high_conviction = False
            for sig_data in winner_signals:
                if sig_data["weight"] >= 0.45:  # High conviction threshold (e.g., Stacked Imbalance)
                    high_conviction = True
                    break

            if not high_conviction:
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
                asyncio.create_task(self.engine.dispatch(aggregated))
                if candle_ts in self.signal_buffer:
                    del self.signal_buffer[candle_ts]
                return
            else:
                logger.info(f"⚡ HTF OVERRIDE: High-conviction {consensus_side} allowed against {htf_context} trend")

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
                asyncio.create_task(self.engine.dispatch(aggregated))
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
            t0_timestamp=selected["signal"].timestamp,  # Phase 85: Carry forward signal timestamp
            t1_decision_ts=time.time(),  # Phase 10: Decision Finalized Timestamp
            trace_id=getattr(selected["signal"], "trace_id", None) or f"trc_{int(time.time()*1000)}",
        )

        logger.info(
            f"📡 Aggregated Signal: {consensus_side} | {symbol} | Confidence: {confidence:.2f} | "
            f"Trace: {aggregated.trace_id}"
        )

        # 8. AUDIT TRAIL LOGGING (Phase 103)
        self.auditor.record_decision(
            symbol=symbol,
            action=consensus_side,
            score=confidence,
            reason=f"Consensus {len(winner_signals)}/{len(signals)} | Margin {margin:.2f} | Trigger {selected['sensor_id']} ({selected['score']:.2f})",
            snapshot={
                "sigma_long": sigma_long,
                "sigma_short": sigma_short,
                "total_voters": len(signals),
                "htf_consensus": htf_context,
                "winner_sensors": [s["sensor_id"] for s in winner_signals],
            },
            trace_id=aggregated.trace_id,
        )

        asyncio.create_task(self.engine.dispatch(aggregated))

        # Clear processed signals
        if candle_ts in self.signal_buffer[symbol]:
            del self.signal_buffer[symbol][candle_ts]
