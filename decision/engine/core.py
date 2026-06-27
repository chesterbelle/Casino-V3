"""
Setup Engine V10 - Orchestrator for AMT scenario evaluation and signal dispatch.

Evaluates tactical confluence markers against structural matrices.
Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict

from config import trading as config
from core.coin_profiler import coin_profiler
from core.events import (
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    SignalEvent,
)
from core.telemetry import TraceOutcome, black_box
from decision.engine.profile_manager import profile_manager
from decision.engine.proposal import TradeProposal
from decision.engine.quality_scorer import evaluate_quality
from decision.engine.targets import TargetingMixin
from decision.engine.telemetry import TelemetryMixin
from decision.guardians.guardian_result import SetupMode

logger = logging.getLogger("SetupEngine")


class SetupEngineV4(TelemetryMixin, TargetingMixin):
    def __init__(self, engine, context_registry=None):
        super().__init__()
        self.engine = engine
        self.context_registry = context_registry

        # Strict Cooldowns per symbol
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 15.0
        self._last_candle_boundary: Dict[str, float] = defaultdict(float)

        # Memories (5s)
        self.micro_memory = defaultdict(lambda: deque(maxlen=500))
        self._last_micro_prune_ts = 0.0
        self._prune_interval = 1.0
        self._micro_count = 0

        # Profile classification tracking
        self._profile_classified: Dict[str, bool] = defaultdict(bool)

        # Scenario Orchestrator (Unification of AMT + Absorption)
        from core.pressure.engine import PressureEngine
        from decision.signal_arbitrator import SignalArbitrator

        # Shared PressureEngine (per-coin facade) from SensorManager.
        # SensorManager owns updates; SetupEngine is read-only.
        sm = getattr(self.engine, "sensor_manager", None)
        self.pressure_engine = sm.pressure_engine if sm else PressureEngine()
        self.scenario_manager = SignalArbitrator(self.pressure_engine)

        # Event Subscriptions
        self.engine.subscribe(EventType.TICK, self.on_tick)
        self.engine.subscribe(EventType.SIGNAL, self.on_signal)
        self.engine.subscribe(EventType.MICROSTRUCTURE_BATCH, self.on_microstructure_batch)
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        logger.info("🎯 LTA V10 Orchestrator initialized (Crystal Pipe Architecture)")

    def get_scenario_stats(self):
        """Expose distribution stats from ScenarioManager."""
        stats = self.scenario_manager.get_stats()
        dist = stats["scenario_distribution"]
        total = stats["total_signals"]

        logger.info("📊 --- SCENARIO DISTRIBUTION REPORT ---")
        for sc, count in dist.items():
            pct = (count / total * 100) if total > 0 else 0
            logger.info(f"🔹 {sc:20}: {count:3} ({pct:5.1f}%)")
        logger.info(f"📈 TOTAL SIGNALS DISPATCHED: {total}")

    async def on_candle(self, event):
        """Propagate candle events to ScenarioManager for TrendAcceptance tracking."""
        from core.context_registry import ContextRegistry

        reg = ContextRegistry()
        poc, vah, val = reg.get_structural(event.symbol)
        structural_levels = {"poc": poc, "vah": vah, "val": val}
        self.scenario_manager.on_candle(event.symbol, event.close, event.timestamp, structural_levels)

    def is_system_warm(self, symbol: str) -> bool:
        """Structural readiness check."""
        if self.context_registry:
            vwap = self.context_registry.vwap_state.get(self.context_registry._norm_key(symbol))
            if not vwap or vwap.get("std", 0) == 0:
                return False
        return True

    def _enrich_metadata(self, metadata: dict, symbol: str) -> dict:
        """Inject structural levels from ContextRegistry into trigger metadata.

        This is CRITICAL — without poc/vah/val in metadata, AdaptivePlayer falls
        through to config_fallback TP/SL (0.3%/0.2%), which is mathematically losing.
        """
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)
            metadata["poc"] = poc
            metadata["vah"] = vah
            metadata["val"] = val

        # Pre-Entry Breakeven Guard (Institutional Guard)
        if "tp_price" in metadata and "price" in metadata and metadata["price"] > 0:
            tp_dist = abs(metadata["tp_price"] - metadata["price"]) / metadata["price"]
            # 0.05% Taker + 0.02% Maker + 0.02% Slippage safety
            fee_friction = 0.0009
            if tp_dist < fee_friction:
                metadata["aborted_by_breakeven_guard"] = True
                metadata["cancel_reason"] = f"TP dist {tp_dist:.4%} < Fee {fee_friction:.4%}"

        return metadata

    async def on_tick(self, event):
        """Tick Entry Point: Orchestrates scenario evaluation and signal dispatch."""
        symbol = event.symbol
        price = event.price
        timestamp = event.timestamp

        # 1. Warmup & In-Trade Check
        if not self.is_system_warm(symbol):
            return
        if self.context_registry and self.context_registry.is_in_trade(symbol):
            if not getattr(config, "AUDIT_MODE", False):
                return
        if timestamp - self.last_fire_ts[symbol] < self.fire_cooldown:
            return

        # 2. Classify coin profile on first encounter
        if not self._profile_classified[symbol]:
            self._classify_and_set_profile(symbol)

        # Get structural levels + VA integrity from ContextRegistry
        from core.context_registry import ContextRegistry

        reg = ContextRegistry()
        poc, vah, val = reg.get_structural(symbol)
        va_integrity = reg.get_va_integrity(symbol)
        structural_levels = {"poc": poc, "vah": vah, "val": val, "va_integrity": va_integrity}

        # 3. Evaluate Scenarios via ScenarioManager
        signal = self.scenario_manager.on_tick(symbol, price, timestamp, structural_levels)

        # 4. Process and Dispatch if signal found
        if signal:
            # UDT: Recover trace if this was a confirmed candidate
            trace = None
            if "trace_id" in signal:
                trace = black_box.get_trace(signal["trace_id"])

            await self._process_signal(signal, trace=trace)

    def _classify_and_set_profile(self, symbol: str):
        """Classify coin into profile. Static JSON takes priority over runtime classification."""
        if not self.context_registry:
            return

        # 1. First: check static assignment in clusters_fixed.json
        try:
            import json

            with open("config/clusters_fixed.json") as f:
                data = json.load(f)
            for profile_name, info in data.get("clusters", {}).items():
                if symbol in info.get("members", []):
                    profile_manager.set_profile(symbol, profile_name)
                    self._profile_classified[symbol] = True
                    logger.info(f"🏷️ [PROFILE] {symbol} → {profile_name} (static from clusters_fixed.json)")
                    return
        except Exception as e:
            logger.debug(f"Static profile lookup failed for {symbol}: {e}")

        # 2. Fallback: runtime classification via microstructure metrics
        spread_data = self.context_registry.spread_state.get(symbol, {})
        spread_current = spread_data.get("current", 0)
        spread_avg = spread_data.get("avg_5m", 1)
        spread_ratio = spread_current / spread_avg if spread_avg > 0 else 1.0

        depth_ratio = self.context_registry.l2_imbalance.get(symbol, 1.0)

        pulse = self.context_registry.get_pulse(symbol)
        speed = pulse.get("speed", 0.0)

        coin_stats = {
            "spread_ratio": spread_ratio,
            "depth_ratio": depth_ratio,
            "speed": speed,
        }

        profile = coin_profiler.classify(symbol, coin_stats)
        profile_manager.set_profile(symbol, profile)
        self._profile_classified[symbol] = True

        logger.info(
            f"🏷️ [PROFILE] {symbol} → {profile} (runtime) | "
            f"spread_ratio={spread_ratio:.2f}, depth_ratio={depth_ratio:.2f}, speed={speed:.4f}"
        )

    async def on_signal(self, event: SignalEvent):
        """Signal Entry Point: Handles external tactical signals."""
        md = event.metadata or {}

        # ⚠️ LEGACY: TACTICAL_CONFIRMATION_REQUIRED signals are no longer used.
        if event.side == "TACTICAL_CONFIRMATION_REQUIRED":
            return

        # B. Tactical Signal Handling (Route via ScenarioManager)
        if event.side in ["LONG", "SHORT", "TACTICAL"]:
            payload = md if md.get("tactical_type") else event.__dict__.copy()
            payload["symbol"] = payload.get("symbol") or event.symbol
            payload["timestamp"] = payload.get("timestamp") or event.timestamp
            payload["side"] = payload.get("side") or event.side

            # Fast-Lane: tactical_absorption fires immediately
            # Fast-Lane: tactical_absorption fires immediately (instant signal).
            # No pasa por ScenarioManager — la absorción debe detectarse en el
            # tick exacto. Los otros 3 escenarios (FB/LE/TA) son señales de
            # confirmación y pasan por orquestación completa.
            # Ver ADR-1 en docs/architectural_decisions.md.
            if event.sensor_id == "tactical_absorption":
                trace = black_box.create_trace(event.symbol, "tactical_absorption", f"SIG_{int(time.time()*1000)}")
                await self._process_signal(payload, trace=trace)
                return

            # UDT: Generate DNA for other tactical signals
            trace = black_box.create_trace(
                payload["symbol"], payload.get("side", "TACTICAL"), f"SIG_{int(time.time()*1000)}"
            )
            trace.add_step("SetupEngine", True, f"Received external signal: {payload.get('tactical_type')}")

            # Route through ScenarioManager
            orchestrated_signal = self.scenario_manager.on_signal(payload, trace=trace)

            if orchestrated_signal:
                await self._process_signal(orchestrated_signal, trace=trace)

    async def _process_signal(self, signal, trace=None):
        """Orchestrates final validation, target calculation, and dispatch."""
        symbol = signal["symbol"]
        side = signal["side"]
        price = signal["price"]
        now = signal["timestamp"]
        scenario = signal.get(
            "scenario", signal.get("metadata", {}).get("scenario", signal.get("tactical_type", "unknown"))
        )

        # Unified Decision Trace (UDT): Use existing trace or create new one
        if not trace:
            trace = black_box.create_trace(symbol, side, signal_id=f"SIG_{int(time.time()*1000)}")
            trace.add_step("SetupEngine", True, f"Processing instant signal: {scenario}")

        # 1. Quality Scoring (v8.4 Crystal Reforge — replaces guardian chain)
        quality = evaluate_quality(symbol, side, signal, self.context_registry, trace=trace)
        if not quality.passed:
            trace.finalize(TraceOutcome.DISCARDED, quality.block_reason)
            black_box.archive_trace(trace.trace_id)
            return
        if quality.grade is None:
            trace.finalize(TraceOutcome.DISCARDED, f"Low quality score: {quality.quality_score}")
            black_box.archive_trace(trace.trace_id)
            return

        # 1b. Per-scenario L2 hard check
        try:
            guardian_params = profile_manager.get_guardian_params(symbol)
            l2_key = f"l2_ratio_min_{scenario}"
            l2_min = guardian_params.get(l2_key)
            if l2_min is not None:
                l2_ratio = self.context_registry.get_l2_ratio(symbol, side)
                if l2_ratio is not None and l2_ratio < l2_min:
                    reason = f"BLOCKED (THIN WALL) for {scenario} | L2 {l2_ratio:.2f} < {l2_min}"
                    trace.add_step("SetupEngine", False, reason)
                    trace.finalize(TraceOutcome.DISCARDED, reason)
                    black_box.archive_trace(trace.trace_id)
                    return
        except Exception:
            pass

        setup_mode = quality.setup_mode
        val_pos = quality.value_position

        # Classify scenarios by inherent market dynamic
        REVERSION_SCENARIOS = {"failed_breakout", "liquidity_exhaustion"}
        DIRECTIONAL_SCENARIOS = {"tactical_absorption", "trend_acceptance"}

        if scenario in REVERSION_SCENARIOS:
            setup_mode = SetupMode.REVERSION
        elif scenario in DIRECTIONAL_SCENARIOS:
            setup_mode = SetupMode.CONTINUATION

        # 2. Target Calculation
        tp_price, sl_price, setup_name, level_ref, atr_pct = self._calculate_targets(
            symbol, side, price, setup_mode, val_pos, scenario, signal
        )

        trace.add_step(
            "SetupEngine",
            True,
            "Targets calculated",
            {"tp": round(tp_price, 4), "sl": round(sl_price, 4), "atr": round(atr_pct, 4)},
        )

        # 3. Metadata Enrichment
        entry_z = 0.0
        poc_p, vah_p, val_p, va_w = 0.0, 0.0, 0.0, 0.0
        if self.context_registry:
            _, _, entry_z = self.context_registry.get_micro_state(symbol)
            _poc, _vah, _val = self.context_registry.get_structural(symbol)
            poc_p = _poc or 0.0
            vah_p = _vah or 0.0
            val_p = _val or 0.0
            if vah_p > val_p:
                va_w = vah_p - val_p

        trigger_meta = self._enrich_metadata(
            {
                "trigger": f"AMT_{scenario.upper()}",
                "setup_name": setup_name,
                "price": price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "tp_distance_pct": abs(tp_price - price) / price * 100 if tp_price and price > 0 else 0.0,
                "sl_distance_pct": abs(sl_price - price) / price * 100 if sl_price and price > 0 else 0.0,
                "level_ref": level_ref,
                "v3_mode": setup_mode.value,
                "scenario": scenario,
                "is_composite": signal.get("is_composite", False),
                "conviction_score": signal.get("conviction_score", 0),
                "contributors": signal.get("contributing_scenarios", []),
                "footprint_z_score": signal.get("z_score", 0.0),
                "atr_1m": atr_pct,
                "z_score_entry": entry_z,
                "trace_id": trace.trace_id,
                "poc_price": poc_p,
                "vah_price": vah_p,
                "val_price": val_p,
                "va_width": va_w,
                "max_holding_time": (config.ABSORPTION_MAX_HOLDING_SEC if scenario == "tactical_absorption" else None),
            },
            symbol,
        )

        # 4. Dispatch TradeProposal (V8.5 Planar Architecture)
        self.last_fire_ts[symbol] = now

        # Use grade from quality scorer
        grade = quality.grade
        trigger_meta["quality_score"] = quality.quality_score
        trigger_meta["quality_scores"] = quality.scores

        proposal = TradeProposal(
            symbol=symbol,
            side=side,
            entry_price=price,
            tp_price=tp_price,
            sl_price=sl_price,
            grade=grade,
            narrative=f"{setup_name}-{grade}-Sc:{scenario}",
            trace_id=signal.get("trace_id", trace.trace_id),
            timestamp=now,
            setup_type=scenario,
            meta=trigger_meta,
        )

        trace.add_step("SetupEngine", True, "TradeProposal dispatched to AdaptivePlayer")
        trace.finalize(TraceOutcome.EXECUTED, f"Trade ready: {setup_name}")
        black_box.archive_trace(trace.trace_id)

        await self.engine.dispatch(proposal)

        # Trace Phase 3: Successful Dispatch
        self.trace(
            trigger_meta,
            "PHASE3_DISPATCHED",
            {"setup_type": scenario, "atr_pct": atr_pct, "quality_score": quality.quality_score},
        )

        logger.info(
            f"🎯 [V8.5] Fired {side} {scenario} on {symbol} | Price: {price:.2f} | TP: {tp_price:.2f} | SL: {sl_price:.2f} | Grade: {grade}"
        )

    async def on_microstructure_batch(self, event: MicrostructureBatchEvent):
        """Processes a batch of real-time microstructural anomalies efficiently."""
        self._micro_count += 1

        if self._micro_count % 1000 == 0:
            logger.info(f"📥 [SETUP] Micro batch received: {self._micro_count} | Events: {len(event.events)}")

        for micro_evt in event.events:
            await self._process_microstructure(micro_evt)

    async def _process_microstructure(self, event: MicrostructureEvent):
        """Internal logic to process a single microstructure event."""
        now = event.timestamp
        symbol = event.symbol

        # 1. Store in memory (market_time, wall_time, event)
        self.micro_memory[symbol].append((now, time.time(), event))

        # Lazy Pruning - Using Market Time
        if now - self._last_micro_prune_ts > self._prune_interval:
            self._last_micro_prune_ts = now
            for s in list(self.micro_memory.keys()):
                cutoff = now - 5.0
                while self.micro_memory[s] and self.micro_memory[s][0][0] < cutoff:
                    self.micro_memory[s].popleft()

        # 2. Evaluate Toxic Order Flow playbook (BEFORE Cooldown for visibility)
        if len(self.micro_memory[symbol]) < 2:
            return

        skewness = event.skewness

        if event.price == 0:
            return

        z = event.z_score
        if self.context_registry:
            self.context_registry.set_micro_state(symbol, event.cvd, skewness, z)
            # Feed spread data to ContextRegistry for spread sanity gate
            if hasattr(event, "spread") and event.spread > 0:
                self.context_registry.update_spread(symbol, event.spread)

        # Microstructure is now CONTEXT ONLY — no signal generation.
