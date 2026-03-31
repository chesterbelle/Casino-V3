"""
Setup Engine V4 - Precise pattern matching machine for Institutional Scalping.

Replaces the old Consensus Aggregator. Instead of averaging scores, it maintains
a 5-second short-term memory of stateless Tactical events and evaluates strict
multi-condition playbooks. Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from core.events import (
    AggregatedSignalEvent,
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    SignalEvent,
)

logger = logging.getLogger("SetupEngine")


class DummyTracker:
    """Provides a compatible interface for OrderManager without doing anything."""

    def get_stats(self):
        return {}

    def track_signal(self, *args, **kwargs):
        pass

    def track_result(self, *args, **kwargs):
        pass


class SetupEngineV4:
    def __init__(self, engine, context_registry=None, fast_track=False):
        self.engine = engine
        self.context_registry = context_registry
        self.tracker = DummyTracker()  # For OrderManager compatibility
        self.fast_track = fast_track

        # Memory of tactical events per symbol. (timestamp, event_data)
        # Keeps up to 500 events to cover the 5-second window
        self.memory: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.micro_memory: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

        # Strict Cooldowns per symbol to prevent double-firing and churn
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 15.0  # Reduced to 15s to capture volatility waves (Round 6)
        self._last_signal_prune_ts = 0.0
        self._last_micro_prune_ts = 0.0
        self._prune_interval = 0.5  # Prune every 500ms

        self.engine.subscribe(EventType.SIGNAL, self.on_signal)
        self.engine.subscribe(EventType.MICROSTRUCTURE_BATCH, self.on_microstructure_batch)

        # Phase 1800: Cold Start Warmup Guard
        # Require 20 minutes of market data before firing any signals
        # to allow Volume Profile (POC/VAH/VAL) and CVD to calibrate properly
        self.first_event_ts = 0.0
        self.warmup_seconds = 0.0 if self.fast_track else 1200.0  # 20 minutes

        # Phase 800: Failed Auction Memory (Dalton Targets)
        self.failed_auctions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.last_volatility_spike: Dict[str, float] = defaultdict(float)

        self._micro_count = 0
        logger.info(
            f"🎯 Setup Engine initialized (Sniper Mode Activated | Warmup: {'0m' if self.fast_track else '20m'})"
        )

    def _enrich_metadata(self, metadata: dict, symbol: str) -> dict:
        """Phase 950: Inject structural levels from ContextRegistry into trigger metadata.

        This is CRITICAL — without poc/vah/val in metadata, AdaptivePlayer falls
        through to config_fallback TP/SL (0.3%/0.2%), which is mathematically losing.
        """
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)
            if poc > 0 and vah > 0 and val > 0:
                metadata["poc"] = poc
                metadata["vah"] = vah
                metadata["val"] = val
        return metadata

    async def on_signal(self, event: SignalEvent):
        """Processes incoming tactical and regime events."""
        # Phase 1500: Sync Regime Filters with ContextRegistry
        md = event.metadata or {}
        if md.get("type") == "MarketRegime_OTF":
            regime = md.get("regime", "NEUTRAL")
            mapping = {"BULL_OTF": "UP", "BEAR_OTF": "DOWN", "NEUTRAL": "NEUTRAL"}
            mapped = mapping.get(regime, "NEUTRAL")
            logger.info(f"🌐 [REGIME] {event.symbol} updated to {mapped} (OTF: {regime})")
            if self.context_registry:
                self.context_registry.set_regime(event.symbol, mapped)
                self.context_registry.set_otf(event.symbol, regime)
            return

        # Phase 800: Capture Volatility Spike for Panic Block
        if event.sensor_id == "VolatilitySpike":
            self.last_volatility_spike[event.symbol] = event.timestamp
            logger.warning(f"🚨 [SETUP] {event.symbol} Volatility Spike received. Blocking reversions for 15s.")

        # Phase 800: Capture Failed Auction Targets from Session sensor
        if event.sensor_id == "SessionValueArea" and event.metadata:
            new_fa = event.metadata.get("failed_auctions", [])
            if new_fa:
                self.failed_auctions[event.symbol] = new_fa
                logger.info(f"🎯 [SETUP] {event.symbol} Updated Failed Auction Targets: {len(new_fa)} levels")

        if event.side not in ["TACTICAL", "LONG", "SHORT", "NEUTRAL"]:
            return

        now = event.timestamp
        sym = event.symbol

        # 1. Store event in short-term memory (market_time, wall_time, event)
        self.memory[sym].append((now, time.time(), event))

        # Lazy Pruning (Phase 500) - Only prune every 500ms (Using Market Time)
        if now - self._last_signal_prune_ts > self._prune_interval:
            self._last_signal_prune_ts = now
            for s in list(self.memory.keys()):
                cutoff = now - 5.0
                while self.memory[s] and self.memory[s][0][0] < cutoff:
                    self.memory[s].popleft()

        # 2. Check strict Post-Trade Cooldown
        if now - self.last_fire_ts[sym] < self.fire_cooldown:
            return

        # 3. Evaluate Strict Playbooks against the 5s memory window
        events = [e[2] for e in self.memory[sym]]

        trigger = self._evaluate_fade_extreme(sym, events)
        setup_type = "reversion"
        if not trigger:
            trigger = self._evaluate_trend_continuation(sym, events)
            setup_type = "continuation"

        # 4. Fire 0ms Latency Action if playbook matches using Guarded Dispatch
        if trigger:
            # Enrichment (Phase 1300): Add vol_ratio and skew to memory-based signals
            # vol_ratio = self.context_registry.get_volatility_ratio(sym) if self.context_registry else 1.0
            latest_skew = 0.5
            if self.micro_memory[sym]:
                latest_skew = self.micro_memory[sym][-1][2].skewness
            trigger["metadata"]["skewness"] = latest_skew

            # Phase 1600 Enrichment: Delta Velocity Multiplier
            dv_multiplier = 1.0
            recent_dv = [
                e[2]
                for e in self.memory[sym]
                if e[2].metadata and e[2].metadata.get("tactical_type") == "TacticalDeltaVelocity"
            ]
            if recent_dv:
                dv_multiplier = recent_dv[-1].metadata.get("sizing_multiplier", 1.0)
            trigger["metadata"]["dv_multiplier"] = dv_multiplier

            await self._dispatch_guarded_signal(
                sym, trigger["side"], trigger["setup_name"], trigger["metadata"], event, setup_type=setup_type
            )

    async def on_microstructure_batch(self, event: MicrostructureBatchEvent):
        """Processes a batch of real-time microstructural anomalies efficiently."""
        if hasattr(self, "_micro_count"):
            self._micro_count += 1
        else:
            self._micro_count = 1

        if self._micro_count % 1000 == 0:
            logger.info(f"📥 [SETUP] Micro batch received: {self._micro_count} | Events: {len(event.events)}")

        for micro_evt in event.events:
            await self._process_microstructure(micro_evt)

    async def _process_microstructure(self, event: MicrostructureEvent):
        """Internal logic to process a single microstructure event."""
        now = event.timestamp
        sym = event.symbol

        # 1. Store in memory (market_time, wall_time, event)
        self.micro_memory[sym].append((now, time.time(), event))

        # Lazy Pruning (Phase 500) - Using Market Time
        if now - self._last_micro_prune_ts > self._prune_interval:
            self._last_micro_prune_ts = now
            for s in list(self.micro_memory.keys()):
                cutoff = now - 5.0
                while self.micro_memory[s] and self.micro_memory[s][0][0] < cutoff:
                    self.micro_memory[s].popleft()

        # 2. Evaluate Toxic Order Flow playbook (BEFORE Cooldown for visibility)
        if len(self.micro_memory[sym]) < 2:
            return

        first_evt = self.micro_memory[sym][0][2]
        curr_evt = self.micro_memory[sym][-1][2]
        skewness = event.skewness
        price_delta = curr_evt.price - first_evt.price

        if event.price == 0:
            return

        trigger = None
        z = event.z_score
        otf = "NEUTRAL"

        if self.context_registry:
            otf = self.context_registry.get_regime(sym)
            self.context_registry.set_micro_state(sym, event.cvd, skewness, z)

        # Throttled Debug Monitor (Phase 1300 Optimization)
        if getattr(self, "_tick_count", 0) % 10000 == 0:
            logger.debug(
                f"🔍 [MONITOR] {sym} | Z: {z:.2f} | OTF: {otf} | Skew: {skewness:.2f} | CVD: {event.cvd:.2f} | "
                f"Spread: {event.spread:.4f} | B5: {event.bid_depth_5:.2f} | A5: {event.ask_depth_5:.2f}"
            )

        # 3. Phase 1300: Slippage Guard (Market Impact Estimation)
        # Assuming a default size of 100 USDT for impact calculation
        order_size_usdt = 100.0
        # Simple slippage estimate: OrderSize / (Available Liquidity in Top 5 * 0.5)
        estimated_slippage_pct = 0.0

        # L2 Warmup Check: If both depths are 0, it likely means the L2 sensor hasn't
        # received its first snapshot yet (common at start of backtest/demo)
        l2_ready = event.bid_depth_5 > 0 or event.ask_depth_5 > 0

        if l2_ready and (side_for_impact := ("BUY" if z > 0 else "SELL")):
            relevant_depth = event.ask_depth_5 if side_for_impact == "BUY" else event.bid_depth_5
            if relevant_depth > 0:
                # Price impact approximation (%)
                estimated_slippage_pct = (order_size_usdt / (relevant_depth * event.price)) * 100
            else:
                estimated_slippage_pct = 1.0  # Empty book for one side (Toxic)
        elif not l2_ready:
            # Bypass guard during L2 warmup to avoid False Negatives in Parity Checks
            estimated_slippage_pct = 0.0

        # Adaptive Thresholds (Phase 1300)
        vol_ratio = 1.0
        if self.context_registry:
            vol_ratio = self.context_registry.get_volatility_ratio(sym)

        # Adjust base thresholds (2.0 and 3.0) by vol_ratio
        # During expansion (vol_ratio > 1), thresholds DECREASE (easier to enter)
        # During contraction (vol_ratio < 1), thresholds INCREASE (harder to enter)
        adaptive_threshold_trend = 2.5 / vol_ratio
        adaptive_threshold_neutral = 4.5 / vol_ratio

        # Clamp adaptive thresholds to prevent extreme values
        adaptive_threshold_trend = max(1.5, min(3.0, adaptive_threshold_trend))
        adaptive_threshold_neutral = max(2.5, min(4.5, adaptive_threshold_neutral))

        # Sharp Sniper (Round 6) logic...
        is_long_z = (z > adaptive_threshold_trend and otf == "UP") or (
            z > adaptive_threshold_neutral and otf == "NEUTRAL"
        )
        price_confirm_long = (price_delta >= 0) if z <= 3.5 else True
        skew_confirm_long = skewness > 0.55 or skewness == 0.5

        if is_long_z:
            if not skew_confirm_long:
                logger.debug(f"❌ [REJECT LONG] {sym} | Z: {z:.2f} | Skew {skewness:.2f} failed confirm")
            elif not price_confirm_long:
                logger.debug(f"❌ [REJECT LONG] {sym} | Z: {z:.2f} | PriceDelta {price_delta:.4f} failed confirm")
            else:
                trigger = {
                    "setup_name": "Toxic_OrderFlow",
                    "side": "SHORT",
                    "setup_type": "reversion",
                    "metadata": {
                        "trigger": "Toxic_OrderFlow",
                        "setup_type": "reversion",
                        "z_score": z,
                        "skewness": skewness,
                        "price": curr_evt.price,
                        "vol_ratio": vol_ratio,
                        "t0_wall_time": self.micro_memory[sym][0][1],
                    },
                }

        # Short logic...
        if not trigger and (
            (z < -adaptive_threshold_trend and (otf == "DOWN"))
            or (z < -adaptive_threshold_neutral and otf == "NEUTRAL")
        ):
            price_confirm_short = (price_delta <= 0) if z >= -3.5 else True
            skew_confirm_short = skewness < 0.45 or skewness == 0.5

            if not skew_confirm_short:
                logger.debug(f"❌ [REJECT SHORT] {sym} | Z: {z:.2f} | Skew {skewness:.2f} failed confirm")
            elif not price_confirm_short:
                logger.debug(f"❌ [REJECT SHORT] {sym} | Z: {z:.2f} | PriceDelta {price_delta:.4f} failed confirm")
            else:
                trigger = {
                    "setup_name": "Toxic_OrderFlow",
                    "side": "LONG",
                    "setup_type": "reversion",
                    "metadata": {
                        "trigger": "Toxic_OrderFlow",
                        "setup_type": "reversion",
                        "z_score": z,
                        "skewness": skewness,
                        "price": curr_evt.price,
                        "vol_ratio": vol_ratio,
                        "t0_wall_time": self.micro_memory[sym][0][1],
                    },
                }

        # Phase 1600: Balanced Regime Gating & Slippage Guard (R12)
        if trigger:
            side = trigger.get("side", "")
            setup_type = trigger.get("metadata", {}).get("setup_type", "unknown")

            # 0. Panic Block (Phase 800)
            # Don't catch falling knives during extreme spikes
            if setup_type == "reversion" and (now - self.last_volatility_spike[sym]) < 15.0:
                logger.warning(f"🚫 [PANIC BLOCK] {sym} {side} Reversion rejected due to recent Volatility Spike")
                trigger = None

            if not trigger:
                pass
            # 1. Regime Filter
            elif side == "SHORT" and otf == "UP":
                logger.debug("❌ [REGIME GATE] Toxic_OrderFlow SHORT rejected — OTF=UP")
                trigger = None
            elif side == "LONG" and otf == "DOWN":
                logger.debug("❌ [REGIME GATE] Toxic_OrderFlow LONG rejected — OTF=DOWN")
                trigger = None

            # 2. Slippage Guard (Phase 1300 / 800 Adaptive)
            # Base threshold: 0.08%
            # Adaptive threshold: max(0.08, ATR_1m / Price * 0.25)
            atr_1m = getattr(event, "atr_1m", 0.0)

            base_max_slippage = 0.08
            adaptive_slippage_limit = base_max_slippage
            if atr_1m > 0 and event.price > 0:
                adaptive_slippage_limit = max(base_max_slippage, (atr_1m / event.price) * 0.25 * 100)

            if trigger and estimated_slippage_pct > adaptive_slippage_limit:
                logger.warning(
                    f"⚠️ [SLIPPAGE GUARD] {sym} {side} Rejected | "
                    f"Est. Slippage: {estimated_slippage_pct:.4f}% > {adaptive_slippage_limit:.4f}% (Adaptive)"
                )
                trigger = None

            # 3. Phase 800: Dalton Target Confluence (Failed Auction Proximity)
            if trigger and trigger.get("setup_type") == "reversion":
                price = event.price
                targets = self.failed_auctions.get(sym, [])
                near_target = False
                for target in targets:
                    target_p = target.get("price", 0)
                    # 0.05% proximity threshold
                    if abs(price - target_p) / target_p < 0.0005:
                        near_target = True
                        logger.info(f"🎯 [DALTON_TARGETED] {sym} Reversion near {target['type']} @ {target_p}")
                        break

                if near_target:
                    # Boost confidence
                    trigger["metadata"]["dalton_confirmed"] = True
                    trigger["metadata"]["confidence_boost"] = 1.5

        if trigger:
            await self._dispatch_guarded_signal(sym, trigger["side"], trigger["setup_name"], trigger["metadata"], event)

    async def _dispatch_guarded_signal(
        self, symbol: str, side: str, pattern: str, metadata: dict, source_event: Any, setup_type: str = "unknown"
    ):
        """
        Phase 1105: Centralized Guarded Dispatch.
        Enforces:
        1. Micro-Confluence (Footprint confirmation)
        2. Cooldown (Timing)
        3. Metadata Enrichment (SVA levels)
        """
        if isinstance(source_event, dict):
            now = source_event.get("timestamp", time.time())
        else:
            now = getattr(source_event, "timestamp", time.time())

        # 0. Cold Start Warmup Check (Priority 0: Calibration)
        if self.first_event_ts == 0.0:
            self.first_event_ts = now
        elif now - self.first_event_ts < self.warmup_seconds:
            # Throttled logging for warmup
            if getattr(self, "_warmup_log_count", 0) % 50 == 0:
                logger.info(
                    f"⏳ [WARMUP] {pattern} gated | Time elapsed: {(now - self.first_event_ts) / 60:.1f}m / 60m"
                )
            self._warmup_log_count = getattr(self, "_warmup_log_count", 0) + 1
            return

        # 1. Cooldown Check (Priority 1: Speed)
        if now - self.last_fire_ts[symbol] < self.fire_cooldown:
            return

        # 2. Confluence Check (Priority 2: Quality)
        # Ensure signal is backed by recent Footprint events (Absorption, Imbalance, Exhaustion)
        recent_tactical = [
            e[2]
            for e in self.memory[symbol]
            if e[2].metadata
            and e[2].metadata.get("tactical_type")
            in ("TacticalAbsorption", "TacticalImbalance", "TacticalExhaustion", "TacticalStackedImbalance")
        ]

        if not recent_tactical and abs(metadata.get("z_score", 0)) < 4.0:
            logger.debug(
                f"❌ [FILTER] {pattern} rejected: No Footprint Confluence in last 5s (Z: {metadata.get('z_score', 0):.2f})"
            )
            return

        # 2.5 Phase 1000: Microstructure Context Filter (POC vs Price)
        if hasattr(self, "sensor_manager") and self.sensor_manager:
            micro_sensor = self.sensor_manager.get_sensor("MicroStructureContext")
            if micro_sensor:
                micro_state = micro_sensor.get_state()
                micro_bias = micro_state.get("bias", "NEUTRAL")

                if side == "LONG" and micro_bias == "BEARISH":
                    logger.debug(f"❌ [FILTER] {pattern} LONG rejected: MicroStructure is BEARISH (Price < POC)")
                    return
                elif side == "SHORT" and micro_bias == "BULLISH":
                    logger.debug(f"❌ [FILTER] {pattern} SHORT rejected: MicroStructure is BULLISH (Price > POC)")
                    return

        # 3. Confirmed - Enrich and Fire
        self.last_fire_ts[symbol] = now
        logger.warning(
            f"🎯 [SETUP ENGINE] {pattern} PATTERN CONFIRMED! Firing {side} on {symbol} | MarketTime: {now} | SetupType: {setup_type}"
        )

        # Enrich metadata with structural levels
        metadata = self._enrich_metadata(metadata, symbol)

        # Phase 85/1130: t0_timestamp uses strict wall clock time for valid latencies.
        # Fallback to general memory tracking if trigger source doesn't provide it
        t0 = metadata.get("t0_wall_time")
        if not t0:
            t0 = self.memory[symbol][0][1] if self.memory[symbol] else time.time()

        out_evt = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=now,
            symbol=symbol,
            candle_timestamp=now,
            selected_sensor=f"SetupEngine_{pattern}",
            sensor_score=1.0,
            side=side,
            confidence=1.0,
            total_signals=1,
            metadata=metadata,
            t0_timestamp=t0,
            t1_decision_ts=time.time(),  # explicit wall time for Phase 1130 latency verification
            setup_type=setup_type,
        )
        await self.engine.dispatch(out_evt)

    def _evaluate_fade_extreme(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        Playbook 1: Fade the Extreme (Mean Reversion)
        Trigger Condition (Adjusted for more signals):
        1. TacticalAbsorption OR TacticalRejection/TrappedTraders event
        2. TacticalImbalance event confirms the reversal direction
        3. Optional: at_volume_level confirmation (not required)
        ALL within the last 5 seconds.
        """
        has_absorption = None
        has_imbalance = None
        has_rejection = None

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")

            # Adjustment: Accept any absorption/rejection event, not just at volume levels
            if t_type == "TacticalAbsorption":
                has_absorption = md
            elif t_type == "TacticalImbalance":
                has_imbalance = md
            elif t_type in ["TacticalRejection", "TacticalTrappedTraders"]:
                has_rejection = md

        # We need either Reaction (Rejection/TrappedTraders) or Absorption + Imbalance
        reversal_direction = None
        trigger_meta = {"trigger": "FadeExtreme", "setup_type": "reversion"}

        if has_absorption and has_imbalance:
            if has_absorption["direction"] == has_imbalance["direction"]:
                reversal_direction = has_absorption["direction"]
                trigger_meta.update(
                    {
                        "poc": has_absorption.get("poc"),
                        "vah": has_absorption.get("vah"),
                        "val": has_absorption.get("val"),
                    }
                )

        elif has_rejection and has_imbalance:
            if has_rejection["direction"] == has_imbalance["direction"]:
                reversal_direction = has_rejection["direction"]
                trigger_meta.update(
                    {
                        "poc": has_imbalance.get("poc", 0),
                        "vah": has_imbalance.get("vah", 0),
                        "val": has_imbalance.get("val", 0),
                    }
                )

        if reversal_direction:
            # Phase 1600: Regime Gate (Reversion only in Neutral)
            regime = self.context_registry.get_regime(symbol) if self.context_registry else "NEUTRAL"
            if regime in ("UP", "DOWN"):
                logger.debug(f"❌ [REGIME GATE] Fade_Extreme rejected in TREND regime ({regime})")
                return None

            # Phase 1300: L2 Wall Confirmation for Fade_Extreme
            # RELAXED FOR PARITY CHECK (R4): From 0.55/0.45 -> 0.51/0.49
            if self.micro_memory[symbol]:
                latest = self.micro_memory[symbol][-1][2]
                skew = latest.skewness
                if reversal_direction == "LONG" and skew < 0.51:
                    logger.debug(f"❌ [L2 GUARD] Fade_Extreme LONG rejected: No Bid Wall (Skew: {skew:.2f})")
                    return None
                if reversal_direction == "SHORT" and skew > 0.49:
                    logger.debug(f"❌ [L2 GUARD] Fade_Extreme SHORT rejected: No Ask Wall (Skew: {skew:.2f})")
                    return None

            return {"setup_name": "Fade_Extreme", "side": reversal_direction, "metadata": trigger_meta}

        return None

    def _evaluate_trend_continuation(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        Playbook 2: Trend Continuation (Breakout)
        Trigger Condition (Phase 950 — Confluence Required):
        1. TacticalStackedImbalance detects institutional footprint in trend direction.
        2. At least ONE confirming event (TacticalImbalance or TacticalDivergence)
           in the SAME direction within the 5s memory window.
        """
        stacked = None
        confirmations = []

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")
            direction = md.get("direction")

            if t_type == "TacticalStackedImbalance":
                stacked = md
            elif t_type in ("TacticalImbalance", "TacticalDivergence") and direction:
                confirmations.append(md)

        if stacked:
            stacked_dir = stacked.get("direction")

            # Phase 1600: Tighten Confluence Gate
            regime = self.context_registry.get_regime(symbol) if self.context_registry else "NEUTRAL"
            has_confluence = any(c.get("direction") == stacked_dir for c in confirmations)

            # In Neutral regime, we REQUIRE confluence for trend continuation
            if regime == "NEUTRAL" and not has_confluence:
                logger.debug("❌ [REGIME GATE] Trend_Continuation rejected: No confluence in NEUTRAL regime")
                return None

            # In Trend regime (UP/DOWN), we allow it even without confluence if stacked imbalance is strong
            # but we still guard against CVD divergence.

            # CVD Divergence Guard (Phase 1300)
            # Find the latest Microstructure event for CVD
            latest_micro = None
            if self.micro_memory[symbol]:
                latest_micro = self.micro_memory[symbol][-1][2]

            if latest_micro:
                cvd = latest_micro.cvd
                # Reject if CVD is opposing the stacked imbalance significantly
                if stacked_dir == "LONG" and cvd < -50:  # Phase 850: Tightened from -500
                    logger.debug(f"❌ [FILTER] Trend_Continuation rejected: CVD Divergence ({cvd:.2f})")
                    return None
                elif stacked_dir == "SHORT" and cvd > 50:  # Phase 850: Tightened from +500
                    logger.debug(f"❌ [FILTER] Trend_Continuation rejected: CVD Divergence SHORT ({cvd:.2f})")
                    return None

            vol_ratio = self.context_registry.get_volatility_ratio(symbol) if self.context_registry else 1.0
            skewness = getattr(latest_micro, "skewness", 0.5)

            return {
                "setup_name": "Trend_Continuation",
                "side": stacked_dir,
                "setup_type": "continuation",
                "metadata": {
                    "trigger": "TrendContinuation",
                    "setup_type": "continuation",
                    "levels": stacked.get("levels", []),
                    "confluence_count": sum(1 for c in confirmations if c.get("direction") == stacked_dir),
                    "has_confluence": has_confluence,
                    "cvd": getattr(latest_micro, "cvd", 0.0),
                    "vol_ratio": vol_ratio,
                    "skewness": skewness,
                    "price": getattr(latest_micro, "price", 0.0),
                },
            }
        return None
