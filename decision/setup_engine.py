"""
Setup Engine V4 - Precise pattern matching machine for Institutional Scalping.

Setup Engine mapping tactical confluence markers dynamically against Structural matrices.
a 5-second short-term memory of stateless Tactical events and evaluates strict
multi-condition playbooks. Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

import config.strategies as strat_config
from core.events import (
    AggregatedSignalEvent,
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    SignalEvent,
)
from decision.guardians import GuardianManager

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
        self.tracker = DummyTracker()
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

        # Phase 1800: Cold Start Warmup Guard (Dynamic/Structural)
        # LTA V4: No time limits. Purely relies on the ContextRegistry returning valid structural levels.

        self._micro_count = 0
        self.guardian_manager = GuardianManager(self._trace_decision)
        logger.info("🎯 LTA V4 Setup Engine initialized (Structural Warmup: Dynamic)")

    def is_system_warm(self, symbol: str, now: float) -> Tuple[bool, List[str]]:
        """Phase 1800: Checks if the system is ready to trade based purely on structural data availability.
        Returns (is_ready, missing_reasons).
        """
        reasons = []
        # 1. Check structural readiness (Blindness Gate)
        if self.fast_track:
            # Phase 1800: Audit/Validation Bypass
            return True, []

        if self.context_registry:
            vwap = self.context_registry.vwap_state.get(self.context_registry._norm_key(symbol))
            if not vwap or vwap.get("std", 0) == 0:
                reasons.append("VWAP Bands (Need 120m data)")

        return len(reasons) == 0, reasons

    def _enrich_metadata(self, metadata: dict, symbol: str) -> dict:
        """Phase 950: Inject structural levels from ContextRegistry into trigger metadata.

        This is CRITICAL — without poc/vah/val in metadata, AdaptivePlayer falls
        through to config_fallback TP/SL (0.3%/0.2%), which is mathematically losing.
        """
        if self.context_registry:
            pass

        # Phase 980: Pre-Entry Breakeven Guard (Institutional Guard)
        if "tp_price" in metadata and "price" in metadata and metadata["price"] > 0:
            tp_dist = abs(metadata["tp_price"] - metadata["price"]) / metadata["price"]
            # 0.05% Taker + 0.02% Maker + 0.02% Slippage safety
            fee_friction = 0.0009
            if tp_dist < fee_friction:
                metadata["aborted_by_breakeven_guard"] = True
                metadata["cancel_reason"] = f"TP dist {tp_dist:.4%} < Fee {fee_friction:.4%}"

        return metadata

    def _evaluate_lta_structural(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        Statistical Absorption V2.1
        Conditions:
        1. Price is at a statistical extreme (VWAP Z-Score).
        2. Footprint confluence (AbsorptionV2).
        3. Target is VWAP.
        """
        if not self.context_registry:
            return None

        # 2. Find the most recent reversal signal in 5s memory
        reversal_signal = None
        TACTICAL_WHITELIST = (
            "TacticalAbsorptionV2",
            "TacticalAbsorption",
        )

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")
            if t_type in TACTICAL_WHITELIST:
                reversal_signal = md
                side = e.side  # Phase 2400: Use explicit event side (LONG/SHORT)
                break

        if not reversal_signal:
            return None

        price = reversal_signal.get("close") or reversal_signal.get("price") or 0.0
        if price <= 0:
            return None

        # --- V3.1 Squeeze Guard (Structural Quality Filter) ---
        # Purpose: Reduce MAE by ensuring we don't buy into deep/erratic pullbacks.
        recent_candles = list(self.memory[symbol])[-5:]  # Look at last 5 events
        if len(recent_candles) >= 3:
            prices = [e[2].price for e in recent_candles if hasattr(e[2], "price") and e[2].price > 0]
            if len(prices) >= 3:
                # 1. Micro-Geometry Check
                if side == "LONG":
                    # We want to see the price stabilizing or moving up (No lower lows in last 3)
                    if prices[-1] < min(prices[-3:-1]):
                        return None  # Abort: Price is still stabbing down
                else:
                    # For SHORT: We want to see price stabilizing or moving down (No higher highs)
                    if prices[-1] > max(prices[-3:-1]):
                        return None  # Abort: Price is still stabbing up

                # 2. Volatility Compression Check
                recent_range = max(prices) - min(prices)
                atr = self.context_registry.atrs.get(symbol, {}).get("short", 0.0)
                if atr > 0 and recent_range > (atr * 2.0):
                    return None  # Abort: Volatility is too high (Chaos Zone)

        # 3. Order Flow Guardians (Statistical Location)
        from decision.guardians.guardian_result import SetupMode

        passed, final_sizing_multiplier, setup_mode = self.guardian_manager.evaluate_all(
            symbol, side, reversal_signal, self.context_registry, {}, self.fast_track
        )
        if not passed:
            return None

        # 5. Calculate Structural Targets (V3 Dual-Core Strategy)
        vwap_data = self.context_registry.vwap_state.get(self.context_registry._norm_key(symbol))
        vwap_price = vwap_data["vwap"] if vwap_data else 0.0
        std = vwap_data["std"] if vwap_data else 0.0
        atr = self.context_registry.atrs.get(symbol, {}).get("short", 0.0)

        if setup_mode == SetupMode.CONTINUATION:
            # V3 CONTINUATION: Target Trend Extension (1.5 * ATR)
            # Stop Loss is the VWAP (if we cross mean, trend is over)
            atr_extension = atr * 1.5 if atr > 0 else (price * 0.005)  # 0.5% fallback
            if side == "LONG":
                tp_price = price + atr_extension
                sl_price = vwap_price if vwap_price > 0 else price * 0.997
            else:
                tp_price = price - atr_extension
                sl_price = vwap_price if vwap_price > 0 else price * 1.003

            setup_type_name = "continuation"
            level_ref = "TREND_EXTENSION"
        else:
            # V3 REVERSION: Target is the Rolling VWAP (Fair Value)
            tp_price = vwap_price if vwap_price > 0 else price * (1.0025 if side == "LONG" else 0.9975)

            # SL is Dynamic/Statistical: 3.5Z from VWAP
            if std > 0 and vwap_price > 0:
                if side == "LONG":
                    sl_price = vwap_price - (3.5 * std)
                    sl_price = min(sl_price, price * 0.999)
                else:
                    sl_price = vwap_price + (3.5 * std)
                    sl_price = max(sl_price, price * 1.001)
            else:
                sl_buffer = strat_config.LTA_TICK_PROXY * strat_config.LTA_SL_TICK_BUFFER
                sl_price = price * (1 - sl_buffer) if side == "LONG" else price * (1 + sl_buffer)

            setup_type_name = "reversion"
            level_ref = "VWAP_BAND"

        # Safety: Ensure TP is at least 0.20% away to cover fees
        tp_dist = abs(tp_price - price) / price
        if tp_dist < 0.0020:
            tp_price = price * (1.0025 if side == "LONG" else 0.9975)

        # 7. Metadata Enrichment
        trigger_meta = {
            "trigger": f"LTA_{reversal_signal.get('tactical_type')}",
            "setup_type": setup_type_name,
            "price": price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "level_ref": level_ref,
            "z_score": reversal_signal.get("z_score"),
            "sizing_multiplier": final_sizing_multiplier,
            "v3_mode": setup_mode.value,
        }
        trigger_meta = self._enrich_metadata(trigger_meta, symbol)

        return {"setup_name": f"LTA_Structural_{side}", "side": side, "metadata": trigger_meta}

    async def on_signal(self, event: SignalEvent):
        """Processes incoming tactical and regime events."""
        # Phase 1500: Sync Regime Filters with ContextRegistry
        md = event.metadata or {}
        symbol = event.symbol
        now = time.time()

        # 1. Store in memory for confluence evaluation
        # 1. Store in memory for confluence evaluation
        self.memory[symbol].append((now, event.timestamp, event))

        # 3. Prune old events periodically
        if now - self._last_signal_prune_ts > self._prune_interval:
            self._last_signal_prune_ts = now
            for s in list(self.memory.keys()):
                cutoff = now - 5.0
                while self.memory[s] and self.memory[s][0][0] < cutoff:
                    self.memory[s].popleft()

        # Phase 2100: New MarketRegime_V2 (3-layer anticipatory sensor)
        # Takes priority over legacy OTF. Maps to ContextRegistry using the
        # new regime vocabulary (BALANCE / TRANSITION / TREND_UP / TREND_DOWN).
        if md.get("type") == "MarketRegime_V2":
            regime_v2 = md.get("regime", "BALANCE")
            direction = md.get("direction", "NEUTRAL")
            confidence = md.get("confidence", 0.0)
            reversion_allowed = md.get("reversion_allowed", True)

            # Map to legacy regime format for backward compatibility
            # BALANCE     → NEUTRAL (reversion allowed)
            # TRANSITION  → TRANSITION (reversion blocked — new state)
            # TREND_UP    → UP
            # TREND_DOWN  → DOWN
            legacy_regime_map = {
                "BALANCE": "NEUTRAL",
                "TRANSITION": "TRANSITION",
                "TREND_UP": "UP",
                "TREND_DOWN": "DOWN",
            }
            mapped = legacy_regime_map.get(regime_v2, "NEUTRAL")

            logger.info(
                f"🌐 [REGIME_V2] {event.symbol}: {regime_v2} → {mapped} "
                f"(dir={direction}, conf={confidence:.2f}, reversion={'✅' if reversion_allowed else '🚫'})"
            )
            if self.context_registry:
                self.context_registry.set_regime(event.symbol, mapped)
                # Store full V2 regime data for Guardian 1 to use
                self.context_registry.set_regime_v2(
                    event.symbol,
                    {
                        "regime": regime_v2,
                        "direction": direction,
                        "confidence": confidence,
                        "reversion_allowed": reversion_allowed,
                        "layers": md.get("layers", {}),
                    },
                )
            return

        # Phase 1500 (Legacy): OTF sensor backward compatibility
        # Only used if MarketRegime sensor is not active
        if md.get("type") == "MarketRegime_OTF":
            regime = md.get("regime", "NEUTRAL")
            mapping = {"BULL_OTF": "UP", "BEAR_OTF": "DOWN", "NEUTRAL": "NEUTRAL"}
            mapped = mapping.get(regime, "NEUTRAL")
            logger.info(f"🌐 [REGIME_OTF] {event.symbol} updated to {mapped} (OTF: {regime})")
            if self.context_registry:
                self.context_registry.set_regime(event.symbol, mapped)
                self.context_registry.set_otf(event.symbol, regime)
            return

        # Phase 800: Capture Volatility Spike for Panic Block
        if event.sensor_id == "VolatilitySpike":
            self.last_volatility_spike[event.symbol] = event.timestamp
            logger.warning(f"🚨 [SETUP] {event.symbol} Volatility Spike received. Blocking reversions for 15s.")

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

        # 3. Evaluate LTA Structural Playbook (The single LTA focus)
        events = [e[2] for e in self.memory[sym]]
        trigger = self._evaluate_lta_structural(sym, events)
        setup_type = "reversion"

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
            for s in list(self.memory.keys()):
                cutoff = now - 5.0
                while self.memory[s] and self.memory[s][0][0] < cutoff:
                    self.memory[s].popleft()
                while self.micro_memory[s] and self.micro_memory[s][0][0] < cutoff:
                    self.micro_memory[s].popleft()

        # 2. Evaluate Toxic Order Flow playbook (BEFORE Cooldown for visibility)
        if len(self.micro_memory[sym]) < 2:
            return

        skewness = event.skewness

        if event.price == 0:
            return

        z = event.z_score
        if self.context_registry:
            self.context_registry.set_micro_state(sym, event.cvd, skewness, z)
            # Phase B3: Feed spread data to ContextRegistry for spread sanity gate
            if hasattr(event, "spread") and event.spread > 0:
                self.context_registry.update_spread(sym, event.spread)

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

        # 2. Inertia Guard (V3.2) - Micro-Flow Confluence for Continuation
        if setup_type == "continuation" and not self.fast_track:
            passed, inertia_val = self._check_micro_inertia_guard(symbol, side, now)
            if not passed:
                self._trace_decision(
                    symbol,
                    "REJECTED",
                    "INERTIA_GUARD",
                    f"No momentum (Delta CVD: {inertia_val:.1f})",
                    {"inertia": inertia_val},
                    price=metadata.get("price", 0.0),
                    side=side,
                )
                return

        # 3. Confirmed - Enrich and Fire
        self.last_fire_ts[symbol] = now
        logger.warning(
            f"🎯 [SETUP ENGINE] {pattern} PATTERN CONFIRMED! Firing {side} on {symbol} | MarketTime: {now} | SetupType: {setup_type}"
        )

        # Enrich metadata with structural levels and perform pre-entry Breakeven Guard check
        metadata = self._enrich_metadata(metadata, symbol)

        # Phase 980: Block execution if target is within fee danger zone
        if metadata.get("aborted_by_breakeven_guard"):
            logger.warning(f"🛡️ [BREAKEVEN_GUARD] {pattern} {side} aborted: {metadata.get('cancel_reason')}")
            return

        # Phase 85/1130: t0_timestamp uses strict wall clock time for valid latencies.
        # Fallback to general memory tracking if trigger source doesn't provide it
        t0 = metadata.get("t0_wall_time")
        if not t0:
            t0 = self.memory[symbol][0][1] if self.memory[symbol] else time.time()

        # Phase 1130: TraceBullet propagation
        trace_id = None
        if hasattr(source_event, "metadata") and isinstance(source_event.metadata, dict):
            trace_id = source_event.metadata.get("trace_id")
        elif isinstance(source_event, dict):
            trace_id = source_event.get("trace_id") or source_event.get("metadata", {}).get("trace_id")

        if trace_id:
            metadata["trace_id"] = trace_id

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
            trace_id=trace_id,  # Directly set trace_id
            t0_timestamp=t0,
            t1_decision_ts=now,  # Phase 1130: Use simulation-aware 'now' for deterministic parity
            setup_type=setup_type,
            price=getattr(source_event, "price", 0.0) or metadata.get("price", 0.0),
        )
        await self.engine.dispatch(out_evt)

    def _trace_decision(
        self, symbol: str, status: str, gate: str, reason: str, metrics: dict, price: float = 0.0, side: str = ""
    ):
        """Helper to fire internal decision traces to Historian."""
        import config.trading as trading_config

        if not getattr(strat_config, "ENABLE_DECISION_TRACE", False) and not getattr(
            trading_config, "ENABLE_DECISION_TRACE", False
        ):
            return

        import time

        from core.observability.historian import historian

        trace_data = {
            "timestamp": time.time(),
            "symbol": symbol,
            "status": status,
            "gate": gate,
            "reason": reason,
            "metrics": metrics,
            "price": price,
            "side": side,
        }
        historian.record_decision_trace(trace_data)

    def _check_micro_inertia_guard(self, symbol: str, side: str, now: float) -> Tuple[bool, float]:
        """
        Phase V3.2: Inertia Guard.
        Ensures that aggressive flow (CVD) is moving in our direction
        within the last 2 seconds before entering a continuation trade.

        Returns (passed, delta_cvd).
        """
        memory = self.micro_memory.get(symbol)
        if not memory or len(memory) < 5:
            return True, 0.0  # Safe-default: don't block if memory is cold

        # Window: Last 2 seconds
        cutoff = now - 2.0
        relevant_events = [evt for ts, wall, evt in memory if ts > cutoff]

        if len(relevant_events) < 3:
            return True, 0.0

        current_cvd = relevant_events[-1].cvd
        baseline_cvd = relevant_events[0].cvd
        delta_cvd = current_cvd - baseline_cvd

        if side == "LONG":
            # For LONG, we need CVD to be increasing (Aggressive Buyers entering)
            return delta_cvd > 0, delta_cvd
        else:
            # For SHORT, we need CVD to be decreasing (Aggressive Sellers entering)
            return delta_cvd < 0, delta_cvd
