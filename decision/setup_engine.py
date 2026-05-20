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

from core.events import (
    AggregatedSignalEvent,
    EventType,
    MicrostructureBatchEvent,
    MicrostructureEvent,
    SignalEvent,
)
from core.telemetry import TraceOutcome, black_box
from decision.guardians import GuardianManager
from utils.trace_bullet import TraceBulletMixin

logger = logging.getLogger("SetupEngine")


class SetupEngineV4(TraceBulletMixin):
    def __init__(self, engine, context_registry=None):
        super().__init__()
        self.engine = engine
        self.context_registry = context_registry

        # Strict Cooldowns per symbol
        self.last_fire_ts = defaultdict(float)
        self.fire_cooldown = 15.0
        self._last_candle_boundary: Dict[str, float] = defaultdict(float)

        # Layers
        self.guardian_manager = GuardianManager(self._trace_decision)

        # Memories (5s)
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

        # 1. Warmup & In-Trade Check
        if not self.is_system_warm(symbol):
            return
        if self.context_registry and self.context_registry.is_in_trade(symbol):
            return
        if timestamp - self.last_fire_ts[symbol] < self.fire_cooldown:
            return

        # 2. Evaluate Scenarios via ScenarioManager
        signal = self.scenario_manager.on_tick(symbol, price, timestamp)

        # 3. Process and Dispatch if signal found
        if signal:
            # Fast-Lane: Signals from AMT Scenarios and TacticalAbsorption (Scalping mode)
            # All fire immediately without tactical confirmation delay.
            if signal.get("source") in ["ScenarioManager", "TacticalAbsorptionV2"]:
                # Guard: Only one position per symbol
                if self.position_tracker.has_position(signal.get("symbol")):
                    return

            # UDT: Recover trace if this was a confirmed candidate
            trace = None
            if "trace_id" in signal:
                trace = black_box.get_trace(signal["trace_id"])

            await self._process_signal(signal, trace=trace)

    async def on_signal(self, event: SignalEvent):
        """Signal Entry Point: Maneja regímenes y señales tácticas externas."""
        md = event.metadata or {}

        # A. Manejo de Regímenes (Prioridad)
        if md.get("type") == "MarketRegime_V2":
            self._handle_regime_update(event)
            return

        # ⚠️ LEGACY/EXPERIMENTAL: The TacticalConfirmationGate (formerly Guardian)
        # Reserved for high-noise signals or setups requiring deep conviction confirmation.
        # Currently bypassed for Absorption Scalping as per Forensic Audit v10.2.
        if event.side == "TACTICAL_CONFIRMATION_REQUIRED":
            return

        # B. Manejo de Señales Tácticas (Enrutamiento vía ScenarioManager)
        if event.side in ["LONG", "SHORT", "TACTICAL"]:
            payload = md if md.get("tactical_type") else event.__dict__.copy()
            payload["symbol"] = payload.get("symbol") or event.symbol
            payload["timestamp"] = payload.get("timestamp") or event.timestamp
            payload["side"] = payload.get("side") or event.side

            # Fast-Lane: TacticalAbsorptionV2 (Scalping) fires immediately
            if event.sensor_id == "TacticalAbsorptionV2":
                trace = black_box.create_trace(event.symbol, "TacticalAbsorptionV2", f"SIG_{int(time.time()*1000)}")
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
            else:
                # Signal is either discarded or pending confirmation in Guardian
                pass

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

    async def _process_signal(self, signal, trace=None):
        """Orquesta la validación final, cálculo de targets y despacho."""
        symbol = signal["symbol"]
        side = signal["side"]
        price = signal["price"]
        now = signal["timestamp"]
        scenario = signal.get("scenario", signal.get("tactical_type", "unknown"))

        # Phase 240: Unified Decision DNA (UDT) - Use existing trace or create new one
        if not trace:
            trace = black_box.create_trace(symbol, side, signal_id=f"SIG_{int(time.time()*1000)}")
            trace.add_step("SetupEngine", True, f"Processing instant signal: {scenario}")

        # 1. Guardian Evaluation
        passed, multiplier, setup_mode, val_pos = self.guardian_manager.evaluate_all(
            symbol, side, signal, self.context_registry, {}, trace=trace
        )
        if not passed:
            trace.finalize(TraceOutcome.DISCARDED, "Rejected by Guardian chain")
            black_box.archive_trace(trace.trace_id)
            return

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
        _entry_z = 0.0
        poc_p, vah_p, val_p, va_w = 0.0, 0.0, 0.0, 0.0
        if self.context_registry:
            _, _, _entry_z = self.context_registry.get_micro_state(symbol)
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
                "level_ref": level_ref,
                "sizing_multiplier": multiplier,
                "v3_mode": setup_mode.value,
                "scenario": scenario,
                "is_composite": signal.get("is_composite", False),
                "conviction_score": signal.get("conviction_score", 0),
                "contributors": signal.get("contributing_scenarios", []),
                "footprint_z_score": signal.get("z_score", 0.0),
                "atr_1m": atr_pct,
                "z_score_entry": _entry_z,
                "trace_id": trace.trace_id,
                "poc_price": poc_p,
                "vah_price": vah_p,
                "val_price": val_p,
                "va_width": va_w,
                "max_holding_time": 3600 if scenario in ["TacticalAbsorptionV2", "absorption_reversal"] else None,
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

        trace.add_step("SetupEngine", True, "Signal dispatched to AdaptivePlayer")
        trace.finalize(TraceOutcome.EXECUTED, f"Trade ready: {setup_name}")
        black_box.archive_trace(trace.trace_id)

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
        3. Floor: Enforce a minimum distance to stay above the LTC noise floor.
        4. Asymmetry (Round 2 Tuning): TP captures MFE expansion (1.0x mult), SL cuts MAE (0.8x mult).

        Returns:
            Tuple: (tp_price, sl_price, setup_name, level_ref)
        """
        # --- 1. GET CURRENT VOLATILITY (ATR) ---
        # Baseline volatility (0.2%) used as fallback if registry is unavailable.
        atr_pct = 0.20
        if self.context_registry:
            atr_data = self.context_registry.atrs.get(symbol, {})
            # Aligned Volatility Horizon:
            # TacticalAbsorptionV2 holds for 1h. Scaling targets with 1m short-term ATR leads to
            # microscopic targets eaten by taker fees. We align the target cage with the 15m medium ATR.
            if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                atr_pct = atr_data.get("medium") or atr_data.get("short") or atr_pct
            else:
                atr_pct = atr_data.get("short") or atr_data.get("medium") or atr_pct

        # --- 2. DYNAMIC AMT GEOMETRIC CALIBRATION (Reversion/Rotation setups) ---
        # If we have structural context, we apply the champion formula calibrated by the Edge Auditor.
        # Otherwise we fall back to classical volatility (ATR) targets.
        applied_dynamic = False
        if self.context_registry and scenario in [
            "TacticalAbsorptionV2",
            "absorption_reversal",
            "failed_breakout",
            "liquidity_exhaustion",
        ]:
            poc, vah, val = self.context_registry.get_structural(symbol)
            if poc and poc > 0 and vah and vah > 0 and val and val > 0:
                dist_to_poc = abs(price - poc)
                dist_to_boundary = (price - val) if side == "LONG" else (vah - price)
                if dist_to_boundary <= 0:
                    dist_to_boundary = dist_to_poc * 0.8

                # Historical Baseline Noise Floors (Restoring scenario-specific standards)
                if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                    tp_noise_floor_pct = atr_pct * 5.0
                    sl_noise_floor_pct = atr_pct * 3.33
                else:
                    tp_noise_floor_pct = atr_pct * 2.5
                    sl_noise_floor_pct = atr_pct * 2.0

                # Calibrated Geometric Multipliers (from recent grid sweep: k_TP=1.5, k_SL=1.2)
                geo_tp_pct = 1.5 * (dist_to_poc / price) * 100.0
                geo_sl_pct = 1.2 * (dist_to_boundary / price) * 100.0

                # Dynamic Expansion: Never drop below historical baseline, but expand if geometry is wider
                tp_dist_pct = max(tp_noise_floor_pct, geo_tp_pct)
                sl_dist_pct = max(sl_noise_floor_pct, geo_sl_pct)

                tp_dist_decimal = tp_dist_pct / 100.0
                sl_dist_decimal = sl_dist_pct / 100.0

                if side == "LONG":
                    tp_price = price * (1 + tp_dist_decimal)
                    sl_price = price * (1 - sl_dist_decimal)
                else:
                    tp_price = price * (1 - tp_dist_decimal)
                    sl_price = price * (1 + sl_dist_decimal)

                setup_name = f"AMT_{scenario.upper()}_{val_pos}"
                level_ref = "AMT_DYNAMIC_GEOMETRIC_CALIBRATED"
                applied_dynamic = True

        if not applied_dynamic:
            # --- 3. FALLBACK TO VOLATILITY MULTIPLIERS (Classic ATR) ---
            # Industry standard: Reversion trades use tighter cages; trends use wider ones.
            # Everything remains symmetric (1:1 RR) to preserve Win Rate.
            MULTIPLIERS = {
                "trend_acceptance": 4.5,  # Wider cage for runners
                "failed_breakout": 2.5,  # Standard cage for reversals
                "absorption_reversal": 5.0,  # 5.0x 15m ATR for macro auction rotation (~0.90% on LTC)
                "liquidity_exhaustion": 2.5,  # Standard cage for reversals
            }
            mult = MULTIPLIERS.get(scenario, 2.5)
            if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                mult = 5.0

            # We calculate the pure mathematical targets based on volatility.
            if scenario in ["TacticalAbsorptionV2", "absorption_reversal"]:
                tp_dist_pct = atr_pct * mult  # 5.0x 15m ATR
                sl_dist_pct = atr_pct * 3.33  # 3.33x 15m ATR (Symmetric 1.5:1 RR)
            else:
                tp_dist_pct = atr_pct * mult
                sl_dist_pct = atr_pct * (mult * 0.8)

            tp_dist_decimal = tp_dist_pct / 100.0
            sl_dist_decimal = sl_dist_pct / 100.0

            if side == "LONG":
                tp_price = price * (1 + tp_dist_decimal)
                sl_price = price * (1 - sl_dist_decimal)
            else:
                tp_price = price * (1 - tp_dist_decimal)
                sl_price = price * (1 + sl_dist_decimal)

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
            for s in list(self.micro_memory.keys()):
                cutoff = now - 5.0
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

        if not getattr(trading_config, "ENABLE_DECISION_TRACE", False):
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
