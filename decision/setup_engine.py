"""
Setup Engine V4 - Precise pattern matching machine for Institutional Scalping.

Replaces the old Consensus Aggregator. Instead of averaging scores, it maintains
a 5-second short-term memory of stateless Tactical events and evaluates strict
multi-condition playbooks. Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional

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
    def __init__(self, engine, context_registry=None):
        self.engine = engine
        self.context_registry = context_registry
        self.tracker = DummyTracker()  # For OrderManager compatibility

        # Memory of tactical events per symbol. (timestamp, event_data)
        # Keeps up to 500 events to cover the 5-second window
        self.memory: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.micro_memory: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))

        # Strict Cooldowns per symbol to prevent double-firing and churn
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 300.0  # 5 minutes per symbol post-trade cooldown
        self._last_prune_ts = 0.0
        self._prune_interval = 0.5  # Prune every 500ms

        self.engine.subscribe(EventType.SIGNAL, self.on_signal)
        self.engine.subscribe(EventType.MICROSTRUCTURE_BATCH, self.on_microstructure_batch)

        logger.info("🎯 Setup Engine initialized (Sniper Mode Activated)")

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
        """Processes incoming tactical events and evaluates playbooks over the 5s window."""
        if event.side != "TACTICAL":
            return

        now = time.time()
        sym = event.symbol

        # 1. Store event in short-term memory
        self.memory[sym].append((now, event))

        # Lazy Pruning (Phase 500) - Only prune every 500ms
        if now - self._last_prune_ts > self._prune_interval:
            self._last_prune_ts = now
            for s in list(self.memory.keys()):
                cutoff = now - 5.0
                while self.memory[s] and self.memory[s][0][0] < cutoff:
                    self.memory[s].popleft()

        # 2. Check strict Post-Trade Cooldown
        if now - self.last_fire_ts[sym] < self.fire_cooldown:
            return

        # 3. Evaluate Strict Playbooks against the 5s memory window
        events = [e[1] for e in self.memory[sym]]

        trigger = self._evaluate_fade_extreme(sym, events)
        if not trigger:
            trigger = self._evaluate_trend_continuation(sym, events)

        # 4. Fire 0ms Latency Action if playbook matches
        if trigger:
            self.last_fire_ts[sym] = now
            logger.warning(
                f"🎯 [SETUP ENGINE] {trigger['setup_name']} PATTERN CONFIRMED! " f"Firing {trigger['side']} on {sym}"
            )

            # Phase 950: Enrich metadata with structural levels from ContextRegistry
            trigger["metadata"] = self._enrich_metadata(trigger["metadata"], sym)

            # Dispatch as AggregatedSignalEvent so AdaptivePlayer receives it
            out_evt = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=now,
                symbol=sym,
                candle_timestamp=now,
                selected_sensor=f"SetupEngine_{trigger['setup_name']}",
                sensor_score=1.0,
                side=trigger["side"],
                confidence=1.0,
                total_signals=1,
                metadata=trigger["metadata"],
                t0_timestamp=getattr(event, "timestamp", now),  # Signal birth (T0)
                t1_decision_ts=now,  # Decision birth (T1)
            )
            await self.engine.dispatch(out_evt)

    async def on_microstructure_batch(self, event: MicrostructureBatchEvent):
        """Processes a batch of real-time microstructural anomalies efficiently."""
        for micro_evt in event.events:
            await self._process_microstructure(micro_evt)

    async def _process_microstructure(self, event: MicrostructureEvent):
        """Internal logic to process a single microstructure event."""
        now = time.time()
        sym = event.symbol

        # 1. Store in memory
        self.micro_memory[sym].append((now, event))

        # Lazy Pruning (Phase 500)
        if now - self._last_prune_ts > self._prune_interval:
            self._last_prune_ts = now
            for s in list(self.micro_memory.keys()):
                cutoff = now - 5.0
                while self.micro_memory[s] and self.micro_memory[s][0][0] < cutoff:
                    self.micro_memory[s].popleft()

        # 2. Check strict Post-Trade Cooldown
        if now - self.last_fire_ts[sym] < self.fire_cooldown:
            return

        # 3. Evaluate Toxic Order Flow playbook
        if len(self.micro_memory[sym]) < 2:
            return

        first_evt = self.micro_memory[sym][0][1]
        curr_evt = self.micro_memory[sym][-1][1]

        # Phase 500/600: Use pre-calculated 5s CVD from SensorManager
        skewness = event.skewness
        price_delta = curr_evt.price - first_evt.price

        if event.price == 0:
            return

        trigger = None

        # Phase 950: Symmetric Thresholds (fixes 90% SHORT bias from Round 1)
        # Z ±3.0 (raised from 2.5 to reduce noise), Skewness symmetric ±0.15 from 0.50
        z = event.z_score

        # Phase 1000: Regime Filter (P2)
        # Check against higher timeframe One-Timeframing (OTF)
        otf = "NEUTRAL"
        if self.context_registry:
            # We don't fetch the whole state, just the specific OTF bias
            otf = self.context_registry.get_regime(sym)  # Returns "UP", "DOWN", or "NEUTRAL"

        # Long: Z > 3.0, Skewness > 0.65 (strong bid dominance), Price UP, OTF non-down
        if z > 3.0 and skewness > 0.65 and price_delta >= 0 and otf != "DOWN":
            trigger = {
                "setup_name": "Toxic_OrderFlow",
                "side": "LONG",
                "metadata": {
                    "trigger": "ToxicOrderFlow",
                    "setup_type": "continuation",
                    "z_score": z,
                    "skewness": skewness,
                    "price_delta": price_delta,
                    "fast_track": True,
                    "price": curr_evt.price,
                },
            }
        # Short: Z < -3.0, Skewness < 0.35 (strong ask dominance), Price DOWN, OTF non-up
        elif z < -3.0 and skewness < 0.35 and price_delta <= 0 and otf != "UP":
            trigger = {
                "setup_name": "Toxic_OrderFlow",
                "side": "SHORT",
                "metadata": {
                    "trigger": "ToxicOrderFlow",
                    "setup_type": "continuation",
                    "z_score": z,
                    "skewness": skewness,
                    "price_delta": price_delta,
                    "fast_track": True,
                    "price": curr_evt.price,
                },
            }

        if trigger:
            self.last_fire_ts[sym] = now
            logger.warning(
                f"🎯 [SETUP ENGINE] {trigger['setup_name']} PATTERN CONFIRMED! " f"Firing {trigger['side']} on {sym}"
            )

            # Phase 950: Enrich metadata with structural levels from ContextRegistry
            trigger["metadata"] = self._enrich_metadata(trigger["metadata"], sym)

            out_evt = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=now,
                symbol=sym,
                candle_timestamp=now,
                selected_sensor=f"SetupEngine_{trigger['setup_name']}",
                sensor_score=1.0,
                side=trigger["side"],
                confidence=1.0,
                total_signals=1,
                metadata=trigger["metadata"],
                t0_timestamp=getattr(event, "timestamp", now),  # Micro birth (T0)
                t1_decision_ts=now,  # Decision birth (T1)
            )
            await self.engine.dispatch(out_evt)

    def _evaluate_fade_extreme(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        Playbook 1: Fade the Extreme (Mean Reversion)
        Trigger Condition:
        1. Context confirms price is near a major volume level (POC, VAH, VAL) -> at_volume_level=True
        2. TacticalAbsorption event occurred against the extreme.
        3. TacticalImbalance event confirms the reversal direction.
        ALL within the last 5 seconds.
        """
        has_absorption = None
        has_imbalance = None
        has_rejection = None

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")

            # For a fade, it MUST happen at a structural volume level
            if not md.get("at_volume_level") and t_type not in ["TacticalRejection", "TacticalTrappedTraders"]:
                continue

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
            # Phase 950: Require at least 1 confirming event in the same direction
            has_confluence = any(c.get("direction") == stacked_dir for c in confirmations)
            if has_confluence:
                return {
                    "setup_name": "Trend_Continuation",
                    "side": stacked_dir,
                    "metadata": {
                        "trigger": "TrendContinuation",
                        "setup_type": "continuation",
                        "levels": stacked.get("levels", []),
                        "confluence_count": sum(1 for c in confirmations if c.get("direction") == stacked_dir),
                    },
                }
        return None
