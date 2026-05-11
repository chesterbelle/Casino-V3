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
from decision.absorption_reversal_guardian import AbsorptionReversalGuardian
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

        # Phase 2: Absorption Confirmation Guardian
        self.absorption_guardian = AbsorptionReversalGuardian(fast_track=self.fast_track)
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        logger.info("🎯 LTA V4 Setup Engine initialized (Structural Warmup: Dynamic, Absorption Phase 2: ACTIVE)")

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

    def _find_tactical_signal(self, events: List[SignalEvent]) -> Optional[Tuple[dict, str]]:
        """Find the most recent tactical absorption signal in 5s memory."""
        TACTICAL_WHITELIST = (
            "TacticalAbsorptionV2",
            "TacticalAbsorption",
        )

        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")
            if t_type in TACTICAL_WHITELIST:
                return md, e.side
        return None

    def _check_squeeze_guard(self, symbol: str, side: str) -> bool:
        """V3.1 Squeeze Guard: Reject entries into deep/erratic pullbacks.

        Returns True if the signal passes quality filters.
        """
        recent_candles = list(self.memory[symbol])[-5:]
        if len(recent_candles) < 3:
            return True  # Not enough data to filter — allow

        prices = [e[2].price for e in recent_candles if hasattr(e[2], "price") and e[2].price > 0]
        if len(prices) < 3:
            return True

        # 1. Micro-Geometry Check: No lower lows (LONG) or higher highs (SHORT)
        if side == "LONG":
            if prices[-1] < min(prices[-3:-1]):
                return False  # Price still stabbing down
        else:
            if prices[-1] > max(prices[-3:-1]):
                return False  # Price still stabbing up

        # 2. Volatility Compression Check: Reject chaos zones
        recent_range = max(prices) - min(prices)
        atr = self.context_registry.atrs.get(symbol, {}).get("short", 0.0)
        if atr > 0 and recent_range > (atr * 2.0):
            return False  # Volatility too high

        return True

    def _calculate_targets(
        self, symbol: str, side: str, price: float, setup_mode, value_position: str = "OUT_OF_VALUE"
    ) -> Tuple[float, float, str, str]:
        """Calculate structural TP/SL based on Volume Profile (POC/VAH/VAL).

        V7: ATR-based SL with VA as directional reference.
        - SL = 1.0× ATR from entry (covers 2-3× MAE, per edge audit calibration)
        - VA levels used for TP direction only, not SL distance
        - Reversion: TP = POC (if valid) or ATR, SL = ATR
        - Rotation: TP = opposite VA boundary or ATR, SL = ATR
        - Continuation: TP = 1.5× ATR extension, SL = ATR

        Returns (tp_price, sl_price, setup_type_name, level_ref).
        """
        from decision.guardians.guardian_result import SetupMode

        # Get Volume Profile structural levels
        poc, vah, val = 0.0, 0.0, 0.0
        if self.context_registry:
            poc, vah, val = self.context_registry.get_structural(symbol)

        atr = self.context_registry.atrs.get(symbol, {}).get("short", 0.0) if self.context_registry else 0.0
        # ATR-based distances (fallback to % of price if ATR unavailable)
        atr_dist = atr * 1.0 if atr > 0 else (price * 0.003)
        # SL = max(1.0× ATR, 0.30%) — minimum 0.30% per edge-audit calibration
        atr_sl = atr * 1.0 if atr > 0 else (price * 0.003)
        min_sl = price * 0.003  # 0.30% minimum SL (LTA_SL_TICK_BUFFER aligned)
        atr_sl = max(atr_sl, min_sl)

        if setup_mode == SetupMode.CONTINUATION:
            if value_position == "IN_VALUE":
                # ROTATION: Price inside Value Area → target opposite VA boundary
                # LONG near VAL → target VAH, SHORT near VAH → target VAL
                # ATR as minimum distance safety net
                if side == "LONG":
                    tp_atr = price + atr_dist
                    tp_price = max(tp_atr, vah) if vah > 0 else tp_atr
                    sl_price = price - atr_sl
                else:
                    tp_atr = price - atr_dist
                    tp_price = min(tp_atr, val) if val > 0 else tp_atr
                    sl_price = price + atr_sl
                setup_type_name = "rotation"
                level_ref = "VA_ROTATION"
            else:
                # TREND EXTENSION: Target 1.5 * ATR, SL = ATR
                atr_extension = atr * 1.5 if atr > 0 else (price * 0.005)
                if side == "LONG":
                    tp_price = price + atr_extension
                    sl_price = price - atr_sl
                else:
                    tp_price = price - atr_extension
                    sl_price = price + atr_sl
                setup_type_name = "continuation"
                level_ref = "TREND_EXTENSION"
        else:
            # REVERSION: Target = POC (center of value) if valid, else ATR
            # SL = ATR from entry (calibrated to cover 2-3× MAE)
            poc_valid = poc > 0 and ((side == "LONG" and poc > price) or (side == "SHORT" and poc < price))
            if poc_valid:
                tp_price = poc
            else:
                # POC on wrong side or unavailable — use ATR-based TP
                if side == "LONG":
                    tp_price = price + atr_dist
                else:
                    tp_price = price - atr_dist

            # SL = ATR from entry (simple, calibrated)
            if side == "LONG":
                sl_price = price - atr_sl
            else:
                sl_price = price + atr_sl
            setup_type_name = "reversion"
            level_ref = "VA_REVERSION"

        # Safety: Ensure TP is at least 0.20% away to cover fees
        tp_dist = abs(tp_price - price) / price
        if tp_dist < 0.0020:
            tp_price = price * (1.0025 if side == "LONG" else 0.9975)

        return tp_price, sl_price, setup_type_name, level_ref

    def _evaluate_lta_structural(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        LTA V4 Structural Playbook — Dual-Core (Reversion/Continuation).

        Pipeline:
        1. Find tactical absorption signal
        2. Squeeze Guard (quality filter)
        3. Order Flow Guardians (regime + location)
        4. Calculate structural TP/SL
        """
        if not self.context_registry:
            return None

        # 1. Find tactical signal
        result = self._find_tactical_signal(events)
        if not result:
            return None
        reversal_signal, side = result

        price = reversal_signal.get("close") or reversal_signal.get("price") or 0.0
        if price <= 0:
            return None

        # 2. Squeeze Guard (Structural Quality Filter)
        if not self._check_squeeze_guard(symbol, side):
            return None

        # 3. Order Flow Guardians
        passed, final_sizing_multiplier, setup_mode, value_position = self.guardian_manager.evaluate_all(
            symbol, side, reversal_signal, self.context_registry, {}, self.fast_track
        )
        if not passed:
            return None

        # 4. Calculate Structural Targets
        tp_price, sl_price, setup_type_name, level_ref = self._calculate_targets(
            symbol, side, price, setup_mode, value_position
        )

        # 5. Metadata Enrichment
        trigger_meta = {
            "trigger": f"LTA_{reversal_signal.get('tactical_type')}",
            "setup_type": setup_type_name,
            "price": price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "level_ref": level_ref,
            "footprint_z_score": reversal_signal.get("z_score"),
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

            value_acceptance = md.get("value_acceptance", "NEUTRAL")
            absorption_detected = md.get("absorption_detected", False)

            logger.info(
                f"🌐 [REGIME_V2] {event.symbol}: {regime_v2} → {mapped} "
                f"(dir={direction}, conf={confidence:.2f}, va={value_acceptance}, "
                f"abs={'✅' if absorption_detected else '—'}, "
                f"reversion={'✅' if reversion_allowed else '🚫'})"
            )
            if self.context_registry:
                self.context_registry.set_regime(event.symbol, mapped)
                # Store full V2 regime data for Guardian V3 to use
                self.context_registry.set_regime_v2(
                    event.symbol,
                    {
                        "regime": regime_v2,
                        "direction": direction,
                        "confidence": confidence,
                        "reversion_allowed": reversion_allowed,
                        "value_acceptance": value_acceptance,
                        "absorption_detected": absorption_detected,
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

        # Phase 2: Intercept absorption candidates for confirmation
        TACTICAL_ABSORPTION_IDS = ("TacticalAbsorptionV2", "TacticalAbsorption", "AbsorptionDetector")
        if event.sensor_id in TACTICAL_ABSORPTION_IDS or (md and md.get("tactical_type") in TACTICAL_ABSORPTION_IDS):
            candidate = {
                "symbol": event.symbol,
                "side": event.side,
                "direction": md.get("direction", ""),
                "absorption_level": md.get("absorption_level", 0.0),
                "level": md.get("absorption_level", 0.0),
                "delta": md.get("delta", 0.0),
                "z_score": md.get("z_score", md.get("footprint_z_score", 0.0)),
                "concentration": md.get("concentration", 0.0),
                "noise": md.get("noise", 0.0),
                "trace_id": md.get("trace_id", ""),
            }
            self.absorption_guardian.register_candidate(candidate)
            self.trace(
                event,
                "PHASE2_INTERCEPT",
                {"direction": md.get("direction", ""), "z_score": md.get("z_score", md.get("footprint_z_score", 0.0))},
            )
            return  # Don't evaluate yet — wait for Phase 2 confirmation

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

        # 4. Fire 0ms Latency Action if playbook matches using Guarded Dispatch
        if trigger:
            setup_type = trigger["metadata"].get("setup_type", "reversion")
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

    async def on_candle(self, event):
        """Phase 2: Evaluate pending absorption candidates on each candle close."""
        symbol = event.symbol
        if symbol not in self.absorption_guardian.pending:
            return

        confirmed = self.absorption_guardian.on_candle(
            symbol=symbol,
            timestamp=event.timestamp,
            close_price=event.close,
            open_price=event.open,
            high_price=event.high,
            low_price=event.low,
        )

        if confirmed:
            # Phase 2 confirmed — process through normal pipeline
            side = confirmed["side"]
            price = confirmed["price"]
            sym = confirmed["symbol"]
            now = confirmed["timestamp"]

            # Build reversal_signal dict for guardian_manager
            reversal_signal = {
                "close": price,
                "price": price,
                "z_score": confirmed.get("z_score", 0.0),
                "footprint_z_score": confirmed.get("z_score", 0.0),
                "concentration": confirmed.get("concentration", 0.0),
                "noise": confirmed.get("noise", 0.0),
                "absorption_level": confirmed.get("absorption_level", 0.0),
                "direction": confirmed.get("direction", ""),
                "tactical_type": "TacticalAbsorptionV2",
            }

            # Run through Order Flow Guardians (regime + location)
            passed, final_sizing_multiplier, setup_mode, value_position = self.guardian_manager.evaluate_all(
                sym, side, reversal_signal, self.context_registry, {}, self.fast_track
            )
            if not passed:
                return

            # Calculate Structural Targets
            tp_price, sl_price, setup_type_name, level_ref = self._calculate_targets(
                sym, side, price, setup_mode, value_position
            )

            # Build metadata
            trigger_meta = {
                "trigger": "LTA_TacticalAbsorptionV2",
                "setup_type": setup_type_name,
                "price": price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "level_ref": level_ref,
                "footprint_z_score": confirmed.get("z_score", 0.0),
                "sizing_multiplier": final_sizing_multiplier * confirmed.get("size_multiplier", 1.0),
                "v3_mode": setup_mode.value,
                "confirmations": confirmed.get("confirmations", 0),
                "confirmation_details": confirmed.get("confirmation_details", {}),
                "phase": "confirmed",
            }
            trigger_meta = self._enrich_metadata(trigger_meta, sym)

            if trigger_meta.get("aborted_by_breakeven_guard"):
                logger.warning(f"🛡️ [BREAKEVEN_GUARD] Absorption {side} aborted: {trigger_meta.get('cancel_reason')}")
                return

            # Dispatch
            self.last_fire_ts[sym] = now
            logger.warning(
                f"🎯 [SETUP ENGINE] LTA_Structural_{side} PATTERN CONFIRMED! "
                f"Firing {side} on {sym} | MarketTime: {now} | SetupType: {setup_type_name} | "
                f"Confirmations: {confirmed.get('confirmations', 0)}/3"
            )

            out_evt = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=now,
                symbol=sym,
                candle_timestamp=now,
                selected_sensor="SetupEngine_LTA_Structural",
                sensor_score=1.0,
                side=side,
                confidence=1.0,
                total_signals=1,
                metadata=trigger_meta,
                trace_id=confirmed.get("trace_id"),
                t0_timestamp=now,
                t1_decision_ts=now,
                setup_type=setup_type_name,
                price=price,
            )
            self.trace(
                out_evt,
                "PHASE2_CONFIRMED",
                {"confirmations": confirmed.get("confirmations", 0), "setup_type": setup_type_name},
            )
            await self.engine.dispatch(out_evt)

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
