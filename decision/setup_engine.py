"""
Setup Engine V4 - Precise pattern matching machine for Institutional Scalping.

Setup Engine mapping tactical confluence markers dynamically against Structural matrices.
a 5-second short-term memory of stateless Tactical events and evaluates strict
multi-condition playbooks. Fires instantly (0ms latency) upon pattern completion.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict, Tuple

import config.strategies as strat_config
from core.events import (
    AggregatedSignalEvent,
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    SignalEvent,
)
from decision.guardians import GuardianManager
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger("SetupEngine")


class DummyTracker:
    """Provides a compatible interface for OrderManager without doing anything."""

    def get_stats(self):
        return {}

    def track_signal(self, *args, **kwargs):
        pass

    def track_result(self, *args, **kwargs):
        pass


class SetupEngineV4(TraceBulletMixin):
    def __init__(self, engine, context_registry=None, fast_track=False):
        super().__init__()
        self.engine = engine
        self.context_registry = context_registry
        self.tracker = DummyTracker()
        self.fast_track = fast_track

        # Strict Cooldowns per symbol
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 15.0
        self._last_candle_boundary: Dict[str, float] = defaultdict(float)

        # Layers
        self.guardian_manager = GuardianManager(self._trace_decision)

        # Memories (5s)
        self.memory = defaultdict(lambda: deque(maxlen=500))
        self.micro_memory = defaultdict(lambda: deque(maxlen=500))
        self._last_micro_prune_ts = 0.0
        self._prune_interval = 1.0

        # Scenario Orchestrator (Unification of AMT + Absorption)
        from core.footprint_registry import footprint_registry
        from decision.scenario_manager import ScenarioManager

        self.scenario_manager = ScenarioManager(footprint_registry, context_registry)

        # Event Subscriptions
        self.engine.subscribe(EventType.TICK, self.on_tick)
        self.engine.subscribe(EventType.SIGNAL, self.on_signal)
        self.engine.subscribe(EventType.MICROSTRUCTURE_BATCH, self.on_microstructure_batch)

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
        return stats

    def is_system_warm(self, symbol: str) -> bool:
        """Structural readiness check."""
        if self.fast_track:
            return True
        if self.context_registry:
            vwap = self.context_registry.vwap_state.get(self.context_registry._norm_key(symbol))
            if not vwap or vwap.get("std", 0) == 0:
                return False
        return True

    def _enrich_metadata(self, metadata: dict, symbol: str) -> dict:
        """Phase 950: Inject structural levels from ContextRegistry into trigger metadata.

        This is CRITICAL — without poc/vah/val in metadata, AdaptivePlayer falls
        through to config_fallback TP/SL (0.3%/0.2%), which is mathematically losing.
        """
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)
            metadata["poc"] = poc
            metadata["vah"] = vah
            metadata["val"] = val

        # Phase 980: Pre-Entry Breakeven Guard (Institutional Guard)
        if "tp_price" in metadata and "price" in metadata and metadata["price"] > 0:
            tp_dist = abs(metadata["tp_price"] - metadata["price"]) / metadata["price"]
            # 0.05% Taker + 0.02% Maker + 0.02% Slippage safety
            fee_friction = 0.0009
            if tp_dist < fee_friction:
                metadata["aborted_by_breakeven_guard"] = True
                metadata["cancel_reason"] = f"TP dist {tp_dist:.4%} < Fee {fee_friction:.4%}"

        return metadata

    async def on_tick(self, event):
        """Tick Entry Point: Orquestra la evaluación de escenarios y el despacho."""
        symbol = event.symbol
        price = event.price
        timestamp = event.timestamp

        # 1. Warmup & In-Trade Check (Fast Exit)
        if not self.is_system_warm(symbol):
            return
        if self.context_registry and self.context_registry.is_in_trade(symbol):
            # Trace Phase 3: Blocked by active trade
            self.trace(
                {"symbol": symbol, "price": price, "reason": "IN_TRADE"},
                "SIGNAL_BLOCKED",
            )
            return
        if timestamp - self.last_fire_ts[symbol] < self.fire_cooldown:
            return

        # 2. Candle Synthesis (for TrendAcceptance/Structural logic)
        candle_boundary = timestamp - (timestamp % 60)
        if candle_boundary > self._last_candle_boundary.get(symbol, 0):
            self._last_candle_boundary[symbol] = candle_boundary
            self.scenario_manager.on_candle(symbol, price, timestamp)

        # 3. Evaluate Scenarios via ScenarioManager (Decision Logic)
        signal = self.scenario_manager.on_tick(symbol, price, timestamp)

        # 4. Process and Dispatch if signal found
        if signal:
            await self._process_signal(signal)

    async def on_signal(self, event: SignalEvent):
        """Signal Entry Point: Maneja regímenes y señales tácticas externas."""
        md = event.metadata or {}

        # A. Manejo de Regímenes (Prioridad)
        if md.get("type") == "MarketRegime_V2":
            self._handle_regime_update(event)
            return

        # B. Manejo de Señales Tácticas (Enrutamiento vía ScenarioManager)
        if event.side in ["LONG", "SHORT", "TACTICAL"]:
            # Ensure signal payload has core fields for orchestrator
            payload = md if md.get("tactical_type") else event.__dict__.copy()
            payload["symbol"] = payload.get("symbol") or event.symbol
            payload["timestamp"] = payload.get("timestamp") or event.timestamp
            payload["price"] = payload.get("price") or getattr(event, "price", 0.0)
            payload["side"] = payload.get("side") or event.side

            signal = self.scenario_manager.on_signal(payload)
            if signal:
                await self._process_signal(signal)

    def _handle_regime_update(self, event):
        """Actualiza el ContextRegistry con la info del sensor de régimen."""
        md = event.metadata
        regime_v2 = md.get("regime", "BALANCE")
        # Mapping logic (Legacy compatibility)
        legacy_regime_map = {"BALANCE": "NEUTRAL", "TRANSITION": "TRANSITION", "TREND_UP": "UP", "TREND_DOWN": "DOWN"}
        mapped = legacy_regime_map.get(regime_v2, "NEUTRAL")

        if self.context_registry:
            self.context_registry.set_regime(event.symbol, mapped)
            self.context_registry.set_regime_v2(event.symbol, md)

        logger.info(f"🌐 [REGIME_V2] {event.symbol}: {regime_v2} (conf={md.get('confidence', 0):.2f})")

    async def _process_signal(self, signal: dict):
        """
        ORQUESTRADOR CENTRAL: Transforma una señal táctica en una ejecución.
        1. Valida Guardianes (Regimen/Localización)
        2. Aplica Exhaustion Gate (AMT)
        3. Calcula Targets Estructurales
        4. Despacha Evento
        """
        symbol = signal["symbol"]
        side = signal["side"]
        price = signal["price"]
        now = signal["timestamp"]
        scenario = signal.get("scenario", signal.get("tactical_type", "unknown"))

        # 1. Guardian Evaluation
        passed, multiplier, setup_mode, val_pos = self.guardian_manager.evaluate_all(
            symbol, side, signal, self.context_registry, {}, self.fast_track
        )
        if not passed:
            return

        # 2. Target Calculation (Symmetric Variance-Aware Model)
        tp_price, sl_price, setup_name, level_ref, atr_pct = self._calculate_targets(
            symbol, side, price, setup_mode, val_pos, scenario, signal
        )

        # 3. Metadata Enrichment
        # Consolidated arbitration metadata for full traceability.
        # This will be picked up by the global Audit Handler in main/backtest.
        # Get current micro Z-score for DI relative delta baseline
        _entry_z = 0.0
        if self.context_registry:
            _, _, _entry_z = self.context_registry.get_micro_state(symbol)

        trigger_meta = self._enrich_metadata(
            {
                "trigger": f"AMT_{scenario.upper()}",
                "setup_name": setup_name,
                "price": price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "level_ref": level_ref,
                "sizing_multiplier": multiplier,
                "v3_mode": setup_mode.value,
                "scenario": scenario,
                "is_composite": signal.get("is_composite", False),
                "conviction_score": signal.get("conviction_score", 0),
                "contributors": signal.get("contributing_scenarios", []),
                "footprint_z_score": signal.get("z_score", 0.0),
                # Phase 710: Propagate ATR so SlimExitEngine pillars have a valid
                # entry_atr on OpenPosition (Scale Out / Break Even / Trailing).
                "atr_1m": atr_pct,
                # Phase 710: Propagate micro Z at entry for Delta Invalidation
                # relative delta (DI measures change FROM this baseline, not absolute Z).
                "z_score_entry": _entry_z,
            },
            symbol,
        )

        # 4. Dispatch Signal Event
        self.last_fire_ts[symbol] = now
        out_evt = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=now,
            symbol=symbol,
            candle_timestamp=now,
            selected_sensor=f"SetupEngine_{scenario}",
            sensor_score=1.0,
            side=side,
            confidence=1.0,
            total_signals=1,
            metadata=trigger_meta,
            trace_id=signal.get("trace_id"),
            t0_timestamp=now,
            t1_decision_ts=now,
            setup_type=scenario,
            price=price,
        )
        await self.engine.dispatch(out_evt)

        # Trace Phase 3: Successful Dispatch
        self.trace(
            trigger_meta,
            "PHASE3_DISPATCHED",
            {"setup_type": scenario, "atr_pct": atr_pct, "multiplier": multiplier},
        )

        logger.warning(
            f"🎯 [ORCHESTRATOR] Fired {side} {scenario} on {symbol} | Price: {price:.2f} | TP: {tp_price:.2f} | SL: {sl_price:.2f} (Ref: {level_ref})"
        )

    def _calculate_targets(
        self,
        symbol: str,
        side: str,
        price: float,
        setup_mode,
        val_pos: str,
        scenario: str = "unknown",
        signal: dict = {},
    ) -> Tuple[float, float, str, str]:
        """
        Symmetric Variance-Aware Target Calculator (Professional Standard).

        This model implements a volatility-anchored 'cage' for price action,
        ensuring that all trades have enough room to breathe above the noise floor
        while maintaining mathematical symmetry to maximize Win Rate.

        Logic:
        1. Multiplier Selection:
           - Reversals (Absorption/FB): 2.5x ATR (Standard mean-reversion).
           - Trend Acceptance: 4.5x ATR (Scaled room for trend discovery).
        2. Distance: calculated_dist = ATR * Multiplier.
        3. Floor: Enforce a minimum distance (0.45%) to stay above the LTC noise floor.
        4. Symmetry: TP_pct = SL_pct = max(calculated_dist, Floor).

        Returns:
            Tuple: (tp_price, sl_price, setup_name, level_ref)
        """
        # --- 1. GET CURRENT VOLATILITY (ATR) ---
        # Baseline volatility (0.2%) used as fallback if registry is unavailable.
        atr_pct = 0.20
        if self.context_registry:
            atr_data = self.context_registry.atrs.get(symbol, {})
            # Prefer short-term 1m ATR for immediate noise context
            atr_pct = atr_data.get("short") or atr_data.get("medium") or atr_pct

        # --- 2. MULTIPLIER CONFIGURATION (Symmetric Scaled) ---
        # Industry standard: Reversion trades use tighter cages; trends use wider ones.
        # Everything remains symmetric (1:1 RR) to preserve Win Rate.
        MULTIPLIERS = {
            "trend_acceptance": 4.5,  # Wider cage for runners
            "failed_breakout": 2.5,  # Standard cage for reversals
            "absorption_reversal": 2.5,  # Standard cage for reversals
            "liquidity_exhaustion": 2.5,  # Standard cage for reversals
        }
        mult = MULTIPLIERS.get(scenario, 2.5)

        # --- 3. CALCULATE DISTANCE & ENFORCE NOISE FLOOR ---
        # Noise Floor established via MAE Percentile-90 Analysis (LTC Audit May 2024).
        # Setting targets below this floor results in stochastic stop-outs.
        NOISE_FLOOR_PCT = 0.45

        calculated_dist = atr_pct * mult
        final_dist_pct = max(calculated_dist, NOISE_FLOOR_PCT)

        # --- 4. APPLY SYMMETRY (1:1 Risk/Reward) ---
        # This is the bedrock of high-frequency absorption strategies.
        dist_decimal = final_dist_pct / 100.0

        if side == "LONG":
            tp_price = price * (1 + dist_decimal)
            sl_price = price * (1 - dist_decimal)
        else:
            tp_price = price * (1 - dist_decimal)
            sl_price = price * (1 + dist_decimal)

        # --- 5. IDENTITY & TRACEABILITY ---
        setup_name = f"AMT_{scenario.upper()}_{val_pos}"
        level_ref = f"VAR_AWARE_{mult}x_ATR"

        # Phase 710: Return atr_pct so it can be propagated to entry_atr on OpenPosition.
        # SlimExitEngine's Scale Out / Break Even / Trailing pillars all guard on
        # `if not position.entry_atr` — without this they are permanently disabled.
        return tp_price, sl_price, setup_name, level_ref, atr_pct

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

        pass

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

        from core.observability.historian import historian as hist_local

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
        # Debug console logging for active troubleshooting (Trace Bullet)
        if status == "REJECTED":
            logger.info(f"🚫 [GATE] {symbol} {side} {gate} REJECTED: {reason}")

        hist_local.record_decision_trace(trace_data)

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
