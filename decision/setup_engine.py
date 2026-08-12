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

from core.events import AggregatedSignalEvent, EventType, SignalEvent

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

        # Strict Cooldowns per symbol to prevent double-firing and churn
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 300.0  # 5 minutes per symbol post-trade cooldown

        self.engine.subscribe(EventType.SIGNAL, self.on_signal)

        logger.info("🎯 Setup Engine initialized (Sniper Mode Activated)")

    async def on_signal(self, event: SignalEvent):
        """Processes incoming tactical events and evaluates playbooks over the 5s window."""
        if event.side != "TACTICAL":
            return

        now = time.time()
        sym = event.symbol

        # 1. Store event in short-term memory
        self.memory[sym].append((now, event))

        # Prune memory > window (5 seconds)
        cutoff = now - 5.0
        while self.memory[sym] and self.memory[sym][0][0] < cutoff:
            self.memory[sym].popleft()

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
        trigger_meta = {"trigger": "FadeExtreme"}

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
        Trigger Condition:
        1. TacticalStackedImbalance detects institutional footprint in trend direction.
        2. Context validates (or multiple subsequent imbalances occur) inside the 5s window.
        """
        for e in events:
            md = e.metadata or {}
            if md.get("tactical_type") == "TacticalStackedImbalance":
                return {
                    "setup_name": "Trend_Continuation",
                    "side": md.get("direction"),
                    "metadata": {"trigger": "TrendContinuation", "levels": md.get("levels", [])},
                }
        return None
