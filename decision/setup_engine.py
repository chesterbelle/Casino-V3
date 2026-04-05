"""
Setup Engine V4 - Precise pattern matching machine for Institutional Scalping.

Replaces the old Consensus Aggregator. Instead of averaging scores, it maintains
a 5-second short-term memory of stateless Tactical events and evaluates strict
multi-condition playbooks. Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

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

        # Phase 1800: Cold Start Warmup Guard (Dynamic)
        # Normal Mode: Requires 60 minutes of data AND structural levels (POC/VAH/VAL).
        # Fast-Track Mode: Bypasses the 60m timer, but STILL REQUIRES structural levels.
        self.first_event_ts = 0.0
        self.warmup_seconds = 0.0 if self.fast_track else 3600.0  # 60 minutes (User's Official Warmup)

        # Phase 800: Failed Auction Memory (Dalton Targets)
        self.failed_auctions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.last_volatility_spike: Dict[str, float] = defaultdict(float)

        # Phase 850: Pullback and Climax Watch states
        self.pullback_watch: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.climax_watch: Dict[str, Dict[str, Any]] = defaultdict(dict)

        self._micro_count = 0
        logger.info(
            f"🎯 Setup Engine initialized (Sniper Mode Activated | Official Warmup: {'0m' if self.fast_track else '60m'})"
        )

    def is_system_warm(self, symbol: str, now: float) -> Tuple[bool, List[str]]:
        """Phase 1800: Checks if the system is ready to trade based on time AND data.
        Returns (is_ready, missing_reasons).
        """
        reasons = []
        # 1. Check structural readiness (Blindness Gate)
        if self.context_registry and not self.context_registry.is_structural_ready(symbol):
            reasons.append("Structural Levels (POC/VAH/VAL)")

        # 2. Check time-based warmup (Calibration Gate)
        if self.first_event_ts == 0.0:
            self.first_event_ts = now

        elapsed = now - self.first_event_ts
        if elapsed < self.warmup_seconds:
            reasons.append(f"Warmup Timer ({round((self.warmup_seconds - elapsed) / 60, 1)}m remain)")

        return len(reasons) == 0, reasons

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
            # Phase 700: Also inject IB levels
            ib_high, ib_low = self.context_registry.get_ib(symbol)
            if ib_high and ib_high > 0:
                metadata["ib_high"] = ib_high
            if ib_low and ib_low > 0:
                metadata["ib_low"] = ib_low
        return metadata

    def _check_level_proximity(self, symbol: str, price: float) -> Optional[dict]:
        """Phase 700: Check if price is within proximity of a structural level.

        Returns the nearest level reference dict or None if price is in open space.
        Levels checked: POC, VAH, VAL, IBH, IBL.
        """
        if not self.context_registry or price <= 0:
            return None

        poc, vah, val = self.context_registry.get_structural(symbol)
        ib_high, ib_low = self.context_registry.get_ib(symbol)

        levels = []
        if poc > 0:
            levels.append(("POC", poc))
        if vah > 0:
            levels.append(("VAH", vah))
        if val > 0:
            levels.append(("VAL", val))
        if ib_high and ib_high > 0:
            levels.append(("IBH", ib_high))
        if ib_low and ib_low > 0:
            levels.append(("IBL", ib_low))

        PROX_THRESHOLD = 1.0 if self.fast_track else 0.0020  # Phase 990: Fast-Track bypasses location gating

        nearest = None
        min_dist = float("inf")
        for name, level_price in levels:
            dist = abs(price - level_price) / price
            if dist < PROX_THRESHOLD and dist < min_dist:
                min_dist = dist
                nearest = {"level_ref": name, "level_price": level_price, "dist_pct": round(dist * 100, 4)}

        return nearest

    def _evaluate_delta_divergence(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        Playbook 3: Delta Divergence (High Probability)
        Trigger Condition:
        1. TacticalDivergence signal in 5s memory (Phase 972: Now requires Delta Flip).
        2. Proximity to structural level (dist_pct < 0.20%).
        3. Wick Confirmation: Rejection wick > 25% of candle size.
        """
        divergence = None
        for e in events:
            md = e.metadata or {}
            if md.get("tactical_type") == "TacticalDivergence":
                divergence = md
                break

        if not divergence:
            return None

        # Get current price
        price = divergence.get("close", 0.0)
        side = divergence.get("direction")

        if price > 0:
            # Phase 972: Wick Confirmation (Dale's Rule)
            # Ensure price isn't closing at the extreme.
            high = divergence.get("high", price)
            low = divergence.get("low", price)
            open_p = divergence.get("open", price)
            total_range = high - low

            if total_range > 0:
                if side == "SHORT":
                    # For SHORT, we need a Top Wick (Price rejected from High)
                    wick_size = high - max(open_p, price)
                else:
                    # For LONG, we need a Bottom Wick (Price rejected from Low)
                    wick_size = min(open_p, price) - low

                wick_ratio = wick_size / total_range
                if wick_ratio < 0.25 and not self.fast_track:
                    # Too 'clean' - price is still pushing hard. Skip unless Fast-Track.
                    return None

            proximity = self._check_level_proximity(symbol, price)
            if proximity:
                # Phase 970: Shark Breath Edge Validation (Axia-Style)
                # Physical stop at certified 0.3% to avoid noise. Invalidation handled by ExitManager.
                tp_pct = 0.0030
                sl_pct = 0.0030
                if side == "LONG":
                    sl_price = price * (1 - sl_pct)
                    tp_price = price * (1 + tp_pct)
                else:
                    sl_price = price * (1 + sl_pct)
                    tp_price = price * (1 - tp_pct)

                trigger_meta = {
                    "trigger": "DeltaDivergence",
                    "setup_type": "reversion",
                    "level_ref": proximity["level_ref"],
                    "level_price": proximity["level_price"],
                    "dist_pct": proximity["dist_pct"],
                    "price": price,
                    "wick_ratio": round(wick_ratio, 2) if total_range > 0 else 0,
                    "z_score": divergence.get("z_score"),
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                }
                trigger_meta = self._enrich_metadata(trigger_meta, symbol)

                return {
                    "setup_name": "Delta_Divergence",
                    "side": divergence["direction"],
                    "metadata": trigger_meta,
                }
        return None

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
            # Phase 700: Wire IB levels to ContextRegistry for proximity gate
            ib_h = event.metadata.get("ib_high")
            ib_l = event.metadata.get("ib_low")
            if ib_h and ib_l and self.context_registry:
                self.context_registry.set_ib(event.symbol, ib_h, ib_l)

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

        # Phase 974: Sniper Patience Lock
        # If the symbol is already 'In Trade' (position open in Croupier),
        # we skip ALL tactical evaluation to avoid self-cannibalization.
        if self.context_registry and self.context_registry.is_in_trade(sym):
            return

        # 3. Evaluate Strict Playbooks against the 5s memory window
        events = [e[2] for e in self.memory[sym]]

        # Phase 900: Dale-Pure Playbook Evaluation (ordered by WR)
        # Priority 1: Trapped Traders (Dale #3, WR 70-75%)
        trigger = self._evaluate_trapped_traders(sym, events)
        setup_type = "reversion"

        # Priority 2: Delta Divergence (Dale #4, WR 70-75%)
        if not trigger:
            trigger = self._evaluate_delta_divergence(sym, events)
            setup_type = "reversion"

        # Priority 3: Fade Extreme / Absorption (Dale #1, WR 65-70%)
        if not trigger:
            trigger = self._evaluate_fade_extreme(sym, events)
            setup_type = "reversion"

        # Priority 4: Trend Continuation (Dale #2, WR 60-65%)
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

            # Phase 700: Level Proximity Gate for Playbook signals
            price = trigger["metadata"].get("price", 0)
            if price > 0:
                proximity = self._check_level_proximity(sym, price)
                if proximity:
                    trigger["metadata"]["level_ref"] = proximity["level_ref"]
                    trigger["metadata"]["level_price"] = proximity["level_price"]
                    trigger["metadata"]["level_dist_pct"] = proximity["dist_pct"]
                    logger.info(
                        f"📍 [LEVEL_CONFIRMED] {sym} Playbook {trigger['setup_name']} near {proximity['level_ref']} "
                        f"@ {proximity['level_price']:.4f} (dist: {proximity['dist_pct']:.4f}%)"
                    )
                else:
                    logger.info(
                        f"📍 [LEVEL_FILTER] {sym} Playbook {trigger['setup_name']} filtered: "
                        f"Price {price:.4f} not near any structural level (threshold: 0.20%)"
                    )
                    return

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
                while self.memory[s] and self.memory[s][0][0] < cutoff:
                    self.memory[s].popleft()
                while self.micro_memory[s] and self.micro_memory[s][0][0] < cutoff:
                    self.micro_memory[s].popleft()

        # 2. Evaluate Toxic Order Flow playbook (BEFORE Cooldown for visibility)
        if len(self.micro_memory[sym]) < 2:
            return

        # Phase 850: Pullback Watch Trigger
        curr_evt = self.micro_memory[sym][-1][2]

        # Phase 850: Pullback Watch Trigger
        if self.pullback_watch[sym].get("active"):
            pb = self.pullback_watch[sym]
            if time.time() - pb["start_ts"] > 60:
                pb["active"] = False
            else:
                retrace_touched = False
                if pb["direction"] == "LONG":
                    if event.price <= pb["target_poc"] * 1.0005:
                        retrace_touched = True
                else:
                    if event.price >= pb["target_poc"] * 0.9995:
                        retrace_touched = True

                if retrace_touched:
                    if self.context_registry:
                        otf = self.context_registry.get_regime(sym)
                        if otf == ("UP" if pb["direction"] == "LONG" else "DOWN") or otf == "NEUTRAL":
                            logger.info(
                                f"🎯 [PULLBACK_TRIGGER] {sym} price {event.price:.4f} hit POC {pb['target_poc']:.4f}. Firing {pb['direction']} Continuation."
                            )
                            await self._dispatch_guarded_signal(
                                sym,
                                pb["direction"],
                                "Trend_Continuation_Pullback",
                                pb["metadata"],
                                curr_evt,
                                setup_type="continuation",
                            )
                            pb["active"] = False
                            return

        skewness = event.skewness

        if event.price == 0:
            return

        z = event.z_score
        otf = "NEUTRAL"

        if self.context_registry:
            otf = self.context_registry.get_regime(sym)
            self.context_registry.set_micro_state(sym, event.cvd, skewness, z)

        # Phase 900: Microstructure is now CONTEXT ONLY — no signal generation.
        # Toxic_OrderFlow removed. Micro state stored for _check_micro_gate().

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

        # 0. Cold Start Warmup Check (Priority 0: Dynamic Readiness)
        is_warm, missing = self.is_system_warm(symbol, now)
        if not is_warm:
            # Throttled logging for warmup
            if getattr(self, "_warmup_log_count", 0) % 50 == 0:
                missing_str = ", ".join(missing)
                logger.info(f"⏳ [WARMUP] {pattern} {side} gated | Waiting for: [{missing_str}]")
            self._warmup_log_count = getattr(self, "_warmup_log_count", 0) + 1
            return

        # 1. Cooldown Check (Priority 1: Speed)
        if now - self.last_fire_ts[symbol] < self.fire_cooldown:
            return

        # 2. Phase 900: Micro-Confirmation Gate (replaces old Confluence Check)
        # Reject signals where real-time order flow contradicts the direction.
        if not self._check_micro_gate(symbol, side):
            logger.info(f"❌ [MICRO_GATE] {pattern} {side} rejected: Real-time flow contradicts direction")
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
            price=getattr(source_event, "price", 0.0) or metadata.get("price", 0.0),
        )
        await self.engine.dispatch(out_evt)

    def _check_micro_gate(self, symbol: str, side: str) -> bool:
        """Phase 900: Micro-Confirmation Gate.

        Checks if real-time order flow supports the proposed direction.
        Returns False to REJECT the signal if the flow strongly contradicts.
        This replaces the old Toxic_OrderFlow signal generation and
        Confluence Check with a pure Dale-aligned context filter.
        """
        if not self.micro_memory[symbol] or self.fast_track:
            return True  # No micro data yet, or Fast-Track forces execution

        latest = self.micro_memory[symbol][-1][2]
        z = latest.z_score

        # Gate: reject if flow is significantly against the direction
        if side == "LONG" and z < -2.0:
            logger.debug(f"❌ [MICRO_GATE] {symbol} LONG blocked: Z-Score {z:.2f} (heavy selling flow)")
            return False
        if side == "SHORT" and z > 2.0:
            logger.debug(f"❌ [MICRO_GATE] {symbol} SHORT blocked: Z-Score {z:.2f} (heavy buying flow)")
            return False

        return True

    def _evaluate_trapped_traders(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """Phase 900: Standalone Trapped Traders Playbook (Dale #3, WR 70-75%).

        Trader Dale: "These traders entered at the wrong time.
        They will eventually reverse, accelerating the move against them."

        Trigger Conditions:
        1. TacticalTrappedTraders detected in 5s memory.
        2. Price near structural level (POC/VAH/VAL).
        3. Regime is not a strong trend in the same direction as the trap.
        """
        trapped = None
        for e in events:
            md = e.metadata or {}
            if md.get("tactical_type") == "TacticalTrappedTraders":
                trapped = md
                break

        if not trapped:
            return None

        direction = trapped.get("direction")
        if not direction:
            return None

        # Regime Gate: Don't trade trapped traders against a strong trend
        regime = self.context_registry.get_regime(symbol) if self.context_registry else "NEUTRAL"
        if not self.fast_track:
            if direction == "LONG" and regime == "DOWN":
                logger.debug("❌ [REGIME GATE] Trapped_Traders LONG rejected in DOWN trend")
                return None
            if direction == "SHORT" and regime == "UP":
                logger.debug("❌ [REGIME GATE] Trapped_Traders SHORT rejected in UP trend")
                return None

        trap_price = trapped.get("trap_price") or trapped.get("high") or trapped.get("low") or 0.0

        # Phase 950: Sniper Mode (HTF Location Gating)
        if trap_price > 0:
            proximity = self._check_level_proximity(symbol, trap_price)
            if not proximity:
                logger.debug(
                    f"❌ [LOCATION GATE] Trapped_Traders {direction} rejected: Price {trap_price:.4f} not near HTF level"
                )
                return None
        else:
            return None  # Invalid price event

        # Phase 970: Shark Breath Edge Validation (Axia-Style)
        # Physical stop at certified 0.3% to avoid noise. Invalidation handled by ExitManager.
        tp_pct = 0.0030
        sl_pct = 0.0030
        if direction == "LONG":
            sl_price = trap_price * (1 - sl_pct)
            tp_price = trap_price * (1 + tp_pct)
        else:
            sl_price = trap_price * (1 + sl_pct)
            tp_price = trap_price * (1 - tp_pct)

        trigger_meta = {
            "trigger": "TrappedTraders",
            "setup_type": "reversion",
            "price": trap_price,
            "trap_price": trap_price,
            "wick_vol_pct": trapped.get("wick_vol_pct"),
            "pattern": trapped.get("pattern", "Trapped_Traders"),
            "candle_high": trapped.get("high"),
            "candle_low": trapped.get("low"),
            "level_ref": proximity["level_ref"],
            "level_price": proximity["level_price"],
            "level_dist_pct": proximity["dist_pct"],
            "tp_price": tp_price,
            "sl_price": sl_price,
        }

        return {"setup_name": "Trapped_Traders", "side": direction, "metadata": trigger_meta}

    def _evaluate_fade_extreme(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """Playbook: Fade the Extreme / Absorption Reversal (Dale #1, WR 65-70%).

        Trigger Condition:
        1. TacticalAbsorption OR TacticalRejection event
        2. Confirmed by TacticalImbalance OR TacticalExhaustion in same direction
        ALL within the last 5 seconds.
        """
        has_absorption = None
        has_imbalance = None
        has_rejection = None
        has_exhaustion = None

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")

            if t_type == "TacticalAbsorption":
                has_absorption = md
            elif t_type == "TacticalImbalance":
                has_imbalance = md
            elif t_type == "TacticalRejection":
                has_rejection = md
            elif t_type == "TacticalExhaustion":
                has_exhaustion = md

        # Confirmation = Imbalance OR Exhaustion in same direction
        confirmations = [c for c in [has_imbalance, has_exhaustion] if c is not None]

        action_node = None
        reversal_direction = None
        trigger_meta = {"trigger": "FadeExtreme", "setup_type": "reversion"}

        # Path A: Absorption + Confirmation
        if has_absorption and confirmations:
            for conf in confirmations:
                if has_absorption["direction"] == conf.get("direction"):
                    reversal_direction = has_absorption["direction"]
                    action_node = has_absorption
                    trigger_meta.update(
                        {
                            "poc": has_absorption.get("poc"),
                            "vah": has_absorption.get("vah"),
                            "val": has_absorption.get("val"),
                        }
                    )
                    break

        # Path B: Rejection + Confirmation
        if not reversal_direction and has_rejection and confirmations:
            for conf in confirmations:
                if has_rejection["direction"] == conf.get("direction"):
                    reversal_direction = has_rejection["direction"]
                    action_node = has_rejection
                    trigger_meta.update(
                        {
                            "poc": has_rejection.get("poc", 0),
                            "vah": has_rejection.get("vah", 0),
                            "val": has_rejection.get("val", 0),
                            "candle_high": has_rejection.get("high"),
                            "candle_low": has_rejection.get("low"),
                        }
                    )
                    break

        if reversal_direction and action_node:
            # Phase 950: Sniper Mode (HTF Location Gating)
            latest_micro_price = self.micro_memory[symbol][-1][2].price if self.micro_memory[symbol] else 0.0
            reaction_price = (
                action_node.get("trap_price") or action_node.get("high") or action_node.get("low") or latest_micro_price
            )

            if reaction_price > 0:
                proximity = self._check_level_proximity(symbol, reaction_price)
                if not proximity:
                    logger.debug(
                        f"❌ [LOCATION GATE] Fade_Extreme {reversal_direction} rejected: Price {reaction_price:.4f} not near HTF level"
                    )
                    return None
            else:
                return None

            # Phase 970: Shark Breath Edge Validation (Axia-Style)
            # Physical stop at certified 0.3% to avoid noise. Invalidation handled by ExitManager.
            tp_pct = 0.0030
            sl_pct = 0.0030
            if reversal_direction == "LONG":
                sl_price = reaction_price * (1 - sl_pct)
                tp_price = reaction_price * (1 + tp_pct)
            else:
                sl_price = reaction_price * (1 + sl_pct)
                tp_price = reaction_price * (1 - tp_pct)

            trigger_meta.update(
                {
                    "price": reaction_price,
                    "level_ref": proximity["level_ref"],
                    "level_price": proximity["level_price"],
                    "level_dist_pct": proximity["dist_pct"],
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                }
            )

            # Regime Gate (Reversion only in Neutral)
            regime = self.context_registry.get_regime(symbol) if self.context_registry else "NEUTRAL"
            if regime in ("UP", "DOWN") and not self.fast_track:
                logger.debug(f"❌ [REGIME GATE] Fade_Extreme rejected in TREND regime ({regime})")
                return None

            # L2 Wall Confirmation
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
            if regime == "NEUTRAL" and not has_confluence and not self.fast_track:
                logger.debug("❌ [REGIME GATE] Trend_Continuation rejected: No confluence in NEUTRAL regime")
                return None

            # Trend Alignment Filter (Phase 1600/1700)
            if not self.fast_track:
                if regime == "UP" and stacked_dir == "SHORT":
                    logger.debug("❌ [REGIME GATE] Trend_Continuation SHORT rejected — Trend is UP")
                    return None
                if regime == "DOWN" and stacked_dir == "LONG":
                    logger.debug("❌ [REGIME GATE] Trend_Continuation LONG rejected — Trend is DOWN")
                    return None

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
            latest_micro_price = getattr(latest_micro, "price", 0.0)
            target_poc = stacked.get("poc", latest_micro_price)

            # Phase 970: Shark Breath Edge Validation (Axia-Style)
            # Physical stop at certified 0.3% to avoid noise. Invalidation handled by ExitManager.
            tp_pct = 0.0030
            sl_pct = 0.0030
            if stacked_dir == "LONG":
                sl_price = latest_micro_price * (1 - sl_pct)
                tp_price = latest_micro_price * (1 + tp_pct)
            else:
                sl_price = latest_micro_price * (1 + sl_pct)
                tp_price = latest_micro_price * (1 - tp_pct)

            # Phase 850: Enter PULLBACK_WATCH instead of firing
            self.pullback_watch[symbol] = {
                "active": True,
                "direction": stacked_dir,
                "target_poc": target_poc,
                "start_ts": time.time(),
                "metadata": {
                    "trigger": "TrendContinuation_Pullback",
                    "setup_type": "continuation",
                    "levels": stacked.get("levels", []),
                    "confluence_count": sum(1 for c in confirmations if c.get("direction") == stacked_dir),
                    "has_confluence": has_confluence,
                    "cvd": getattr(latest_micro, "cvd", 0.0),
                    "vol_ratio": vol_ratio,
                    "skewness": getattr(latest_micro, "skewness", 0.5),
                    "price": latest_micro_price,
                    "target_poc": target_poc,
                    "candle_high": stacked.get("high"),
                    "candle_low": stacked.get("low"),
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                },
            }

            logger.info(
                f"🔍 [PULLBACK_WATCH] {symbol} {stacked_dir} Stack detected. Waiting for retrace to {target_poc:.4f}"
            )
            return None
        return None
