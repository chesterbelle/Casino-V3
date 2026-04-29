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
import config.trading as trading_config
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

        # Phase 2.3: Absorption V2 - Two-phase architecture (detect → confirm → enter)
        from decision.absorption_reversal_guardian import AbsorptionReversalGuardian
        from decision.absorption_setup_engine import AbsorptionSetupEngine
        from sensors.absorption.absorption_detector import AbsorptionDetector

        self.absorption_detector = AbsorptionDetector()
        self.absorption_guardian = AbsorptionReversalGuardian(fast_track=fast_track)
        self.absorption_engine = AbsorptionSetupEngine(fast_track=fast_track)

        # Subscribe to candle events for absorption detection
        self.engine.subscribe(EventType.CANDLE, self.on_candle_absorption)

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

        # Phase 800: Failed Auction Memory (Dalton Targets)
        self.failed_auctions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.last_volatility_spike: Dict[str, float] = defaultdict(float)

        # Phase 2000: Recent candle extremes for Failed Auction lookback (Axia-style)
        # Stores last N candle (high, low) per symbol from SessionValueArea events
        self.recent_extremes: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=strat_config.LTA_FAILED_AUCTION_LOOKBACK)
        )

        # Phase 850: Pullback and Climax Watch states
        self.pullback_watch: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.climax_watch: Dict[str, Dict[str, Any]] = defaultdict(dict)

        self._micro_count = 0
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

        if self.context_registry and not self.context_registry.is_structural_ready(symbol):
            reasons.append("Structural Levels (POC/VAH/VAL)")

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

        # Phase 980: Pre-Entry Breakeven Guard (Institutional Guard)
        if "tp_price" in metadata and "price" in metadata and metadata["price"] > 0:
            tp_dist = abs(metadata["tp_price"] - metadata["price"]) / metadata["price"]
            # 0.05% Taker + 0.02% Maker + 0.02% Slippage safety
            fee_friction = 0.0009
            if tp_dist < fee_friction:
                metadata["aborted_by_breakeven_guard"] = True
                metadata["cancel_reason"] = f"TP dist {tp_dist:.4%} < Fee {fee_friction:.4%}"

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

    def _evaluate_lta_structural(self, symbol: str, events: List[SignalEvent]) -> Optional[dict]:
        """
        LTA V4: Structural Reversion (Unified Playbook)

        Strategy: Identify extreme exhaustion/absorption at VA edges and
        target the POC (Point of Control) as the primary magnet.

        Conditions:
        1. Price is near VAH or VAL (dist < 0.25%).
        2. Footprint confluence (Absorption, Rejection, Delta Flip, or Cascade Fade).
        3. Target is the current POC.
        4. All 6 Order Flow Guardians must PASS.
        """
        if not self.context_registry:
            return None

        # 1. Get structural anchors
        poc, vah, val = self.context_registry.get_structural(symbol)
        if not (poc > 0 and vah > 0 and val > 0):
            return None

        # 2. Find the most recent reversal signal in 5s memory
        reversal_signal = None
        # Phase 800: Expanded Whitelist for LTA V4 Confluence
        # Phase 2100: LTA V5 Sensor Consolidation - Eliminated redundant sensors
        TACTICAL_WHITELIST = (
            "TacticalAbsorption",  # Núcleo: defensa del borde VA
            "TacticalDivergence",  # Confirmador: agotamiento de momentum
            "TacticalTrappedTraders",  # Confirmador: participantes atrapados
            "TacticalExhaustion",  # Confirmador: volumen extremo sin follow-through
            "TacticalLiquidationCascade",  # Playbook Beta: fade de dislocación extrema
            # LTA V5: NEW SENSORS (Phase 3)
            "TacticalSinglePrintReversion",  # Market Profile: single print rejection
            "TacticalVolumeClimaxReversion",  # Wyckoff: volume climax without extension
            # ELIMINATED in LTA V5:
            # "TacticalRejection" → Redundante con TacticalAbsorption (correlación >0.85)
            # "TacticalStackedImbalance" → Contradictorio (predice continuación en playbook de reversión)
            # "TacticalImbalance" → Menos específico que TacticalTrappedTraders
        )
        for e in events:
            md = e.metadata or {}
            t_type = md.get("tactical_type")
            if t_type in TACTICAL_WHITELIST:
                reversal_signal = md
                break

        if not reversal_signal:
            return None

        # Phase A1: OHLC Backfill — tick-based sensors (Absorption, etc.) emit
        # only 'price' but no candle OHLC.  The Failed Auction gate requires
        # high/low/open/close to verify wick rejection.  We search the 5-second
        # signal memory for the most recent candle-based event that carries OHLC
        # and merge those values into the reversal signal.
        for ohlc_key in ("high", "low", "open", "close"):
            if not reversal_signal.get(ohlc_key):
                # Search memory backwards for a signal that has this key
                for _, _, mem_event in reversed(self.memory[symbol]):
                    mem_md = mem_event.metadata or {}
                    if mem_md.get(ohlc_key) and mem_md[ohlc_key] > 0:
                        reversal_signal[ohlc_key] = mem_md[ohlc_key]
                        break

        price = reversal_signal.get("close") or reversal_signal.get("price") or 0.0
        side = reversal_signal.get("direction")

        if price <= 0:
            return None

        # 3. Location Gate: Must be at the edges to play LTA
        if self.fast_track:
            # Phase 990: Infrastructure Validation Bypass
            # Mock edge proximity to guarantee execution flow tests during short windows
            is_at_vah = side == "SHORT"
            is_at_val = side == "LONG"
        else:
            is_at_vah = abs(price - vah) / price < strat_config.LTA_PROXIMITY_THRESHOLD
            is_at_val = abs(price - val) / price < strat_config.LTA_PROXIMITY_THRESHOLD

        if not (is_at_vah or is_at_val):
            return None

        # Phase 2000: Order Flow Guardians (6 Gates — AMT/Axia Validation)
        # Guardian 1: Regime Alignment (prevents fading strong trends)
        regime_mult = self._check_regime_alignment(symbol, side, reversal_signal)
        if regime_mult <= 0:
            return None

        # Guardian 2: POC Migration Gate
        poc_mult = self._check_poc_migration(symbol, side)
        if poc_mult <= 0:
            return None

        # Guardian 3: VA Integrity Gate (dynamic by liquidity window)
        va_mult = self._check_va_integrity(symbol)
        if va_mult <= 0:
            return None

        # Guardian 4: REMOVED in Phase 2300 — Failed Auction
        # Concept operates at session timeframe (hours), not 1m candles.
        # SessionValueArea already handles this correctly at session level.
        # Tactical sensors (Absorption, TrappedTraders) already confirm rejection.
        # Keeping it caused inverted discrimination (-29% in trending conditions).

        # Guardian 5: Delta Divergence Confirmation
        if not self._check_delta_divergence(symbol, side):
            return None

        # Guardian 6: Spread Sanity (prevents entries during illiquid micro-moments)
        if not self._check_spread_sanity(symbol):
            return None

        # 4. Directional Logic:
        # If at VAH, we want to SHORT back to POC.
        # If at VAL, we want to LONG back to POC.
        if is_at_vah and side != "SHORT":
            return None
        if is_at_val and side != "LONG":
            return None

        # 5. Calculate Structural Targets (LTA Core)
        # Phase 2400: Reduced TP from POC (full reversion) to 0.15% partial reversion
        # Reason: MFE data shows price moves 0.19% on average, not full distance to POC
        # Old: tp_price = poc (full reversion)
        # New: tp_price = entry + 0.15% (partial reversion aligned with MFE reality)
        tp_distance_pct = 0.0015  # 0.15% - aligned with actual MFE from audit data
        if side == "LONG":
            tp_price = price * (1 + tp_distance_pct)
        else:
            tp_price = price * (1 - tp_distance_pct)

        # SL is structural: Buffer outside the edge
        sl_buffer = strat_config.LTA_TICK_PROXY * strat_config.LTA_SL_TICK_BUFFER
        if side == "LONG":
            sl_price = val * (1 - sl_buffer)
        else:
            sl_price = vah * (1 + sl_buffer)

        # 6. Calculate Aggregated Sizing Multiplier (Phase 2350)
        final_sizing_multiplier = regime_mult * poc_mult * va_mult

        # 7. Metadata Enrichment
        trigger_meta = {
            "trigger": f"LTA_{reversal_signal.get('tactical_type')}",
            "setup_type": "reversion",
            "price": price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "poc": poc,
            "vah": vah,
            "val": val,
            "level_ref": "VAH" if is_at_vah else "VAL",
            "z_score": reversal_signal.get("z_score"),
            "sizing_multiplier": final_sizing_multiplier,
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
        self.memory[symbol].append((now, event.timestamp, event))

        # Phase 2.3: Absorption V1 signals now come from on_candle_absorption (main process)
        # No longer routed through worker SignalEvents

        # 2. EVALUATE PRE-FLIGHT (Limit Sniper Phase 1)
        # DISABLED: PreFlight generated extra signals that eroded edge (3.4x more trades, worse quality).
        # Limit Sniper now only changes order TYPE (market→limit) on existing LTA signals,
        # not generates new signals. See _execute_main_order in oco_manager.py.
        # t_type = md.get("tactical_type")
        # if t_type and t_type != "PreFlightProximity":
        #     await self._evaluate_pre_flight(symbol, event)

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

            # Phase A2: Sync session-aware structural levels to ContextRegistry
            s_poc = event.metadata.get("poc")
            s_vah = event.metadata.get("vah")
            s_val = event.metadata.get("val")
            s_va_integrity = event.metadata.get("va_integrity", 0.0)  # Phase 2000
            if s_poc and s_vah and s_val and self.context_registry:
                self.context_registry.update_structural_from_session(
                    event.symbol, s_poc, s_vah, s_val, va_integrity=s_va_integrity
                )

            # Phase B1: Track current liquidity window for dynamic VA thresholds
            window_name = event.metadata.get("liquidity_window")
            if window_name and self.context_registry:
                self.context_registry.current_window[event.symbol] = window_name

            # Phase 2000: Track recent candle extremes for Failed Auction lookback
            c_high = event.metadata.get("candle_high")
            c_low = event.metadata.get("candle_low")
            if c_high and c_low:
                self.recent_extremes[event.symbol].append({"high": c_high, "low": c_low})

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
            for s in list(self.memory.keys()):
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
            t1_decision_ts=now,  # Phase 1130: Use simulation-aware 'now' for deterministic parity
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

    async def _evaluate_pre_flight(self, symbol: str, event: SignalEvent):
        """
        Phase 2360: Limit Sniper Pre-Flight Mode.
        Detects structural proximity and pre-positions LIMIT orders.
        """
        # Master switch check
        if not getattr(trading_config, "LIMIT_SNIPER_ENABLED", False):
            return

        if self.fast_track or not self.context_registry:
            return

        now_wall = time.time()
        # 1. Get structural anchors and current price
        poc, vah, val = self.context_registry.get_structural(symbol)
        if not (poc > 0 and vah > 0 and val > 0):
            return

        md = event.metadata or {}
        price = md.get("price") or md.get("close") or 0.0
        if price <= 0:
            return

        # 2. Proximity Gate (0.20% by default)
        is_at_vah = abs(price - vah) / price < strat_config.LTA_PROXIMITY_THRESHOLD
        is_at_val = abs(price - val) / price < strat_config.LTA_PROXIMITY_THRESHOLD

        if not (is_at_vah or is_at_val):
            return

        # 3. Determine potential side and targets
        side = "SHORT" if is_at_vah else "LONG"

        # 4. Guardian Quick-Check (Regime must be Balance/Neutral)
        # We don't want to pre-position in a hard trend
        regime_mult = self._check_regime_alignment(symbol, side, md)
        if regime_mult <= 0:
            return

        # 5. Apply Front-Running Offset (Phase 2361)
        offset = getattr(trading_config, "LIMIT_SNIPER_OFFSET_PCT", 0.0)
        if side == "SHORT":
            # Short limit slightly BELOW the level
            entry_price = vah * (1 - offset)
        else:
            # Long limit slightly ABOVE the level
            entry_price = val * (1 + offset)

        # 6. Emit PRE_FLIGHT event for OrderManager
        # This tells the OrderManager to place a LIMIT order
        pre_flight_metadata = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "tp_price": poc,
            "sl_price": vah * (1 + 0.0015) if is_at_vah else val * (1 - 0.0015),  # Standard structural buffer
            "type": "limit_sniper",
            "is_pre_flight": True,
            "tactical_type": "PreFlightProximity",
        }

        # We use a custom event type for Pre-Flight (OrderManager will subscribe to this)
        # Note: We use AGGREGATED_SIGNAL so it reaches OrderManager/Player flow
        out_evt = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=event.timestamp,
            symbol=symbol,
            candle_timestamp=event.timestamp,
            selected_sensor="SetupEngine_PreFlight",
            sensor_score=1.0,
            side=side,
            confidence=1.0,
            total_signals=1,
            metadata=pre_flight_metadata,
            t0_timestamp=now_wall,
            t1_decision_ts=event.timestamp,
            setup_type="reversion",
            price=price,
        )
        await self.engine.dispatch(out_evt)
        logger.debug(f"🎯 [PRE-FLIGHT] {symbol} {side} proximity detected. Pre-positioning LIMIT.")

    def _check_regime_alignment(self, symbol: str, side: str, reversal_signal: dict) -> float:
        """
        Phase 2100: Regime Alignment Gate (Guardian 1) — Anticipatory Version.
        Phase 2350: Transition Recovery — Allow entries in TRANSITION if flow is extreme.

        Returns a sizing multiplier (0.0 to 1.0).
        """
        if self.fast_track:
            return 1.0

        if not self.context_registry:
            return 1.0

        # --- Phase 2100: Try V2 regime first ---
        regime_v2_data = getattr(self.context_registry, "_regime_v2", {}).get(symbol)
        if regime_v2_data:
            regime_v2 = regime_v2_data.get("regime", "BALANCE")
            direction = regime_v2_data.get("direction", "NEUTRAL")
            confidence = regime_v2_data.get("confidence", 0.0)
            layers = regime_v2_data.get("layers", {})

            metrics = {
                "regime_v2": regime_v2,
                "direction": direction,
                "confidence": confidence,
                "side": side,
                "layers": {k: v.get("vote") for k, v in layers.items()},
            }

            # 1. Consensus Override: If Micro & Meso are both NEUTRAL, we prioritize local balance
            # even if Macro thinks we are trending. This captures "local range" reversions.
            micro_vote = (
                layers.get("micro", {}).get("vote", "NEUTRAL")
                if isinstance(layers.get("micro"), dict)
                else layers.get("micro", "NEUTRAL")
            )
            meso_vote = (
                layers.get("meso", {}).get("vote", "NEUTRAL")
                if isinstance(layers.get("meso"), dict)
                else layers.get("meso", "NEUTRAL")
            )

            if micro_vote == "NEUTRAL" and meso_vote == "NEUTRAL":
                # Local balance confirmed - allow reversal with soft-sizing if confidence is low
                local_mult = 1.0 if confidence < 0.6 else strat_config.LTA_SOFT_GATE_REDUCTION
                self._trace_decision(
                    symbol,
                    "PASS",
                    "REGIME_ALIGNMENT_V2",
                    f"Local consensus (Micro/Meso Neutral) overrides Macro {regime_v2}",
                    metrics,
                    0.0,
                    side,
                )
                return local_mult

            # 2. Confidence Filter: If confidence is very low, don't block counter-trend
            if confidence < 0.5:
                self._trace_decision(
                    symbol,
                    "PASS",
                    "REGIME_ALIGNMENT_V2",
                    f"Low confidence ({confidence:.2f}) - counter-trend allowed",
                    metrics,
                    0.0,
                    side,
                )
                return strat_config.LTA_SOFT_GATE_REDUCTION

            # BALANCE → always allow reversion (our edge lives here)
            if regime_v2 == "BALANCE":
                self._trace_decision(symbol, "PASS", "REGIME_ALIGNMENT_V2", "Balance regime", metrics, 0.0, side)
                return 1.0

            # TRANSITION → Recovery Logic
            if regime_v2 == "TRANSITION":
                # Phase 2350: Recovery via extreme micro-flow
                z_score = abs(reversal_signal.get("z_score", 0.0))
                if z_score >= strat_config.LTA_TRANSITION_Z_THRESHOLD:
                    logger.info(
                        f"🛡️ [REGIME_V2] {symbol} {side} RECOVERED in TRANSITION: "
                        f"Extreme Z-Score {z_score:.2f} >= {strat_config.LTA_TRANSITION_Z_THRESHOLD}"
                    )
                    self._trace_decision(
                        symbol, "PASS", "REGIME_ALIGNMENT_V2", "Transition Recovery (Extreme Flow)", metrics, 0.0, side
                    )
                    return strat_config.LTA_SOFT_GATE_REDUCTION

                logger.info(
                    f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TRANSITION state "
                    f"(conf={confidence:.2f}, dir={direction}) — market leaving balance"
                )
                self._trace_decision(
                    symbol,
                    "REJECT",
                    "REGIME_ALIGNMENT_V2",
                    f"TRANSITION state (dir={direction}, conf={confidence:.2f})",
                    metrics,
                    0.0,
                    side,
                )
                return 0.0

            # TREND_UP → Block ALL reversions (Phase 2400: Deep Analysis showed 75.6% timeouts in BULL)
            # Old logic: Allowed LONG (trend-aligned)
            # New logic: Block ALL (mean-reversion doesn't work in trending markets)
            if regime_v2 == "TREND_UP":
                logger.info(
                    f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_UP active "
                    f"(conf={confidence:.2f}) — mean-reversion disabled in trending markets"
                )
                self._trace_decision(
                    symbol,
                    "REJECT",
                    "REGIME_ALIGNMENT_V2",
                    f"TREND_UP - mean-reversion disabled (conf={confidence:.2f})",
                    metrics,
                    0.0,
                    side,
                )
                return 0.0

            # TREND_DOWN → Block ALL reversions (Phase 2400: Deep Analysis showed negative expectancy in BEAR)
            # Old logic: Allowed SHORT (trend-aligned)
            # New logic: Block ALL (mean-reversion doesn't work in trending markets)
            if regime_v2 == "TREND_DOWN":
                logger.info(
                    f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_DOWN active "
                    f"(conf={confidence:.2f}) — mean-reversion disabled in trending markets"
                )
                self._trace_decision(
                    symbol,
                    "REJECT",
                    "REGIME_ALIGNMENT_V2",
                    f"TREND_DOWN - mean-reversion disabled (conf={confidence:.2f})",
                    metrics,
                    0.0,
                    side,
                )
                return 0.0

        # --- Legacy fallback: OTF-based regime (Phase 2000) ---
        regime = self.context_registry.get_regime(symbol)
        otf = self.context_registry.otf.get(symbol, "NEUTRAL")
        metrics = {"regime": regime, "otf": otf, "side": side, "source": "legacy_otf"}

        if regime == "NEUTRAL" or otf == "NEUTRAL":
            self._trace_decision(symbol, "PASS", "REGIME_ALIGNMENT", "Neutral regime (legacy)", metrics, 0.0, side)
            return 1.0

        if side == "LONG" and regime == "UP":
            self._trace_decision(symbol, "PASS", "REGIME_ALIGNMENT", "Trend-aligned LONG (legacy)", metrics, 0.0, side)
            return 1.0
        if side == "SHORT" and regime == "DOWN":
            self._trace_decision(symbol, "PASS", "REGIME_ALIGNMENT", "Trend-aligned SHORT (legacy)", metrics, 0.0, side)
            return 1.0

        logger.info(f"🛡️ [REGIME_OTF] {symbol} {side} blocked: Counter-trend (Regime: {regime}, OTF: {otf})")
        self._trace_decision(
            symbol, "REJECT", "REGIME_ALIGNMENT", "Counter-trend reversion (legacy)", metrics, 0.0, side
        )
        return 0.0

    def _check_poc_migration(self, symbol: str, side: str) -> float:
        """
        Phase 1150: POC Migration Gate (Guardian 2).
        Phase 2350: Conversion to Soft Gate.

        Returns a sizing multiplier (0.0 to 1.0).
        """
        if self.fast_track:
            return 1.0

        if not self.context_registry:
            return 1.0

        migration = self.context_registry.get_poc_migration(symbol, lookback_ticks=300)
        threshold = strat_config.LTA_POC_MIGRATION_THRESHOLD
        metrics = {"migration": migration, "threshold": threshold}

        # If we want to LONG (at VAL), POC should NOT be migrating DOWN.
        if side == "LONG" and migration < -threshold:
            # Phase 2350: Check for hard block (1.5x threshold)
            if migration < -(threshold * 1.5):
                logger.info(f"🛡️ [POC_MIGRATION] {symbol} LONG blocked: POC migrated {migration:.4%} (hard discovery)")
                self._trace_decision(
                    symbol, "REJECT", "POC_MIGRATION", "Hard migration against side", metrics, 0.0, side
                )
                return 0.0

            # Soft gate
            logger.info(f"🛡️ [POC_MIGRATION] {symbol} LONG soft-gate: POC migrated {migration:.4%} (soft discovery)")
            self._trace_decision(symbol, "PASS", "POC_MIGRATION", "Soft migration against side", metrics, 0.0, side)
            return strat_config.LTA_SOFT_GATE_REDUCTION

        # If we want to SHORT (at VAH), POC should NOT be migrating UP.
        if side == "SHORT" and migration > threshold:
            # Phase 2350: Check for hard block (1.5x threshold)
            if migration > (threshold * 1.5):
                logger.info(f"🛡️ [POC_MIGRATION] {symbol} SHORT blocked: POC migrated {migration:.4%} (hard discovery)")
                self._trace_decision(
                    symbol, "REJECT", "POC_MIGRATION", "Hard migration against side", metrics, 0.0, side
                )
                return 0.0

            # Soft gate
            logger.info(f"🛡️ [POC_MIGRATION] {symbol} SHORT soft-gate: POC migrated {migration:.4%} (soft discovery)")
            self._trace_decision(symbol, "PASS", "POC_MIGRATION", "Soft migration against side", metrics, 0.0, side)
            return strat_config.LTA_SOFT_GATE_REDUCTION

        self._trace_decision(symbol, "PASS", "POC_MIGRATION", "Healthy migration", metrics, 0.0, side)
        return 1.0

    def _check_va_integrity(self, symbol: str) -> float:
        """
        Phase 2200: VA Integrity Gate (Restructured — Soft Gate).
        Phase 2350: Multi-tier Soft Gate.

        Returns a sizing multiplier (0.0 to 1.0).
        """
        if self.fast_track:
            return 1.0

        if not self.context_registry:
            return 1.0

        integrity = self.context_registry.get_va_integrity(symbol)

        # Phase B1: Dynamic threshold by liquidity window
        current_window = getattr(self.context_registry, "current_window", {}).get(symbol, "")
        va_thresholds = getattr(strat_config, "LTA_VA_INTEGRITY_BY_WINDOW", {})
        threshold = va_thresholds.get(current_window, strat_config.LTA_VA_INTEGRITY_MIN)

        # Phase 2350: Soft gate logic
        critical_threshold = threshold * 0.50

        metrics = {
            "integrity": integrity,
            "threshold": threshold,
            "critical_threshold": critical_threshold,
            "window": current_window,
        }

        # Hard Reject
        if integrity < critical_threshold:
            logger.info(
                f"🛡️ [VA_INTEGRITY] {symbol} rejected: Integrity {integrity:.4f} critically low "
                f"< {critical_threshold:.4f} ({current_window})"
            )
            self._trace_decision(symbol, "REJECT", "VA_INTEGRITY", "Critically low VA density", metrics, 0.0, "")
            return 0.0

        # Soft Gate
        if integrity < threshold:
            self._trace_decision(symbol, "PASS", "VA_INTEGRITY", "Soft VA density (sizing reduced)", metrics, 0.0, "")
            return strat_config.LTA_SOFT_GATE_REDUCTION

        self._trace_decision(symbol, "PASS", "VA_INTEGRITY", "Acceptable VA density", metrics, 0.0, "")
        return 1.0

    def _check_failed_auction(self, symbol: str, side: str, reversal_signal: dict) -> bool:
        """
        Phase 2300: Failed Auction Confirmation (Redesigned).

        REDESIGN from Phase 2200:
        The original check only verified that price PROBED the edge.
        Problem: In a crash, price always probes the edge (it blows through it).
        This caused the guardian to be INVERTED — rejecting more in RANGE than in CRASH.

        New logic: Price must have probed the edge AND closed back inside the VA.
        This is the true definition of a "Failed Auction" — the market attempted
        to break out but was rejected and returned to value.

        A probe that doesn't close back inside = continuation (not a failed auction).
        A probe that closes back inside = rejection (valid failed auction).
        """
        if self.fast_track:
            return True

        poc, vah, val = self.context_registry.get_structural(symbol)
        price = reversal_signal.get("close", 0.0)
        high = reversal_signal.get("high", 0.0)
        low = reversal_signal.get("low", 0.0)

        # Phase 2300: Extended lookback — use max(high) and min(low) across recent candles
        recent = self.recent_extremes.get(symbol)
        if recent and len(recent) > 0:
            lookback_high = max(c["high"] for c in recent)
            lookback_low = min(c["low"] for c in recent)
            high = max(high, lookback_high) if high > 0 else lookback_high
            low = min(low, lookback_low) if low > 0 else lookback_low

        metrics = {
            "price": price,
            "high": high,
            "low": low,
            "val": val,
            "vah": vah,
            "lookback_candles": len(recent) if recent else 0,
        }

        if side == "LONG":
            # Must have probed below VAL
            if low > val:
                logger.info(f"🛡️ [FAILED_AUCTION] {symbol} LONG blocked: No probe below VAL ({low:.4f} > {val:.4f})")
                self._trace_decision(symbol, "REJECT", "FAILED_AUCTION", "No probe below edge", metrics, price, side)
                return False

            # Phase 2300: Must have CLOSED back above VAL (failed auction confirmation)
            # If price closed below VAL, it's a continuation (breakdown), not a rejection
            if price > 0 and price < val:
                logger.info(
                    f"🛡️ [FAILED_AUCTION] {symbol} LONG blocked: "
                    f"Price closed below VAL ({price:.4f} < {val:.4f}) — continuation, not rejection"
                )
                self._trace_decision(
                    symbol, "REJECT", "FAILED_AUCTION", "Close below edge — continuation", metrics, price, side
                )
                return False

        if side == "SHORT":
            # Must have probed above VAH
            if high < vah:
                logger.info(f"🛡️ [FAILED_AUCTION] {symbol} SHORT blocked: No probe above VAH ({high:.4f} < {vah:.4f})")
                self._trace_decision(symbol, "REJECT", "FAILED_AUCTION", "No probe above edge", metrics, price, side)
                return False

            # Phase 2300: Must have CLOSED back below VAH (failed auction confirmation)
            # If price closed above VAH, it's a continuation (breakout), not a rejection
            if price > 0 and price > vah:
                logger.info(
                    f"🛡️ [FAILED_AUCTION] {symbol} SHORT blocked: "
                    f"Price closed above VAH ({price:.4f} > {vah:.4f}) — continuation, not rejection"
                )
                self._trace_decision(
                    symbol, "REJECT", "FAILED_AUCTION", "Close above edge — continuation", metrics, price, side
                )
                return False

        self._trace_decision(symbol, "PASS", "FAILED_AUCTION", "Valid probe with close inside VA", metrics, price, side)
        return True

    def _check_delta_divergence(self, symbol: str, side: str) -> bool:
        """
        Phase 2200: Delta Divergence Confirmation (Restructured).

        CHANGE from Phase 1150:
        Threshold relaxed from z < -1.5 to z < -2.5.
        Rationale: In legitimate reversions, flow can be at -1.8 to -2.0 just
        before turning. The old threshold was blocking valid exhaustion setups.
        Only truly extreme, sustained flow (z < -2.5) should block a LONG.
        """
        if self.fast_track:
            return True

        if not self.context_registry:
            return True

        state = self.context_registry.micro_state.get(symbol)
        if not state:
            return True

        z_score = state.get("z_score", 0.0)
        metrics = {"z_score": z_score, "threshold": 2.5}

        if side == "LONG":
            # Reject only if selling flow is extremely strong (z < -2.5)
            if z_score < -2.5:
                logger.info(f"🛡️ [DELTA_DIVERGENCE] {symbol} LONG blocked: Extreme selling flow (Z: {z_score:.2f})")
                self._trace_decision(
                    symbol, "REJECT", "DELTA_DIVERGENCE", "Orderflow pressure too high", metrics, 0.0, side
                )
                return False

        if side == "SHORT":
            # Reject only if buying flow is extremely strong (z > 2.5)
            if z_score > 2.5:
                logger.info(f"🛡️ [DELTA_DIVERGENCE] {symbol} SHORT blocked: Extreme buying flow (Z: {z_score:.2f})")
                self._trace_decision(
                    symbol, "REJECT", "DELTA_DIVERGENCE", "Orderflow pressure too high", metrics, 0.0, side
                )
                return False

        self._trace_decision(symbol, "PASS", "DELTA_DIVERGENCE", "Orderflow supportive/neutral", metrics, 0.0, side)
        return True

    def _check_spread_sanity(self, symbol: str) -> bool:
        """
        Phase 2000: Spread Sanity Gate (Guardian 6).
        Prevents entries during illiquid micro-moments where the spread
        is abnormally wide, which would eat the edge via slippage.
        """
        if self.fast_track:
            return True

        if not self.context_registry:
            return True

        spread_data = getattr(self.context_registry, "spread_state", {}).get(symbol)
        if not spread_data:
            return True  # No spread data yet, allow (conservative start)

        current = spread_data.get("current", 0.0)
        avg_5m = spread_data.get("avg_5m", 0.0)
        metrics = {"current_spread": current, "avg_5m": avg_5m}

        if avg_5m > 0 and current > avg_5m * 2.0:
            logger.info(f"🛡️ [SPREAD_SANITY] {symbol} rejected: Spread {current:.6f} > 2x avg {avg_5m:.6f}")
            self._trace_decision(symbol, "REJECT", "SPREAD_SANITY", "Wide spread", metrics, 0.0, "")
            return False

        self._trace_decision(symbol, "PASS", "SPREAD_SANITY", "Normal spread", metrics, 0.0, "")
        return True

    async def on_candle_absorption(self, event):
        """
        Phase 2.3 V2: Two-phase absorption detection.

        PHASE 1 — DETECTION: AbsorptionDetector finds candidates
        PHASE 2 — CONFIRMATION: AbsorptionReversalGuardian verifies ≥2/3 confirmations

        Called directly from Engine on CANDLE events (main process).
        No IPC, no worker queue — direct access to FootprintRegistry.
        """
        # Extract candle data
        symbol = getattr(event, "symbol", None)
        timestamp = getattr(event, "timestamp", 0)
        close_price = getattr(event, "close", 0)
        open_price = getattr(event, "open", 0)
        high_price = getattr(event, "high", 0)
        low_price = getattr(event, "low", 0)

        # Fallback: try metadata for non-standard candle events
        if not symbol:
            md = getattr(event, "metadata", {}) or {}
            symbol = md.get("symbol")
            close_price = md.get("close", close_price)
            open_price = md.get("open", open_price)
            high_price = md.get("high", high_price)
            low_price = md.get("low", low_price)

        if not symbol or close_price <= 0:
            return

        # ── PHASE 2: Check if guardian has a pending candidate for this symbol ──
        confirmed_signal = self.absorption_guardian.on_candle(
            symbol, timestamp, close_price, open_price, high_price, low_price
        )

        if confirmed_signal:
            # Phase 2 CONFIRMED → process through setup engine → dispatch
            setup = self.absorption_engine.process_confirmed_signal(confirmed_signal)
            if not setup:
                logger.debug(f"❌ [ABSORPTION_V2] Setup rejected for {symbol}")
                return

            # Cooldown check before dispatch (use event timestamp for backtest compatibility)
            if timestamp - self.last_fire_ts[symbol] < self.fire_cooldown:
                logger.debug(f"❌ [ABSORPTION_V2] Cooldown active for {symbol}")
                return

            # Build AggregatedSignalEvent
            trigger_metadata = {
                "strategy": "AbsorptionScalpingV2",
                "setup_type": f"AbsorptionV2_{setup['side']}",
                "absorption_level": setup["absorption_level"],
                "delta": setup["delta"],
                "z_score": setup["z_score"],
                "concentration": setup["concentration"],
                "noise": setup["noise"],
                "tp_price": setup["tp_price"],
                "sl_price": setup["sl_price"],
                "entry_price": setup["entry_price"],
                "price": setup["entry_price"],
                "sensor_id": "AbsorptionDetector",
                "timestamp": setup["timestamp"],
                "confirmations": setup.get("confirmations", 0),
                "is_contra_trend": setup.get("is_contra_trend", False),
                "size_multiplier": setup.get("size_multiplier", 1.0),
            }

            trigger_metadata = self._enrich_metadata(trigger_metadata, symbol)

            agg_event = AggregatedSignalEvent(
                type=EventType.AGGREGATED_SIGNAL,
                timestamp=timestamp,
                symbol=symbol,
                candle_timestamp=timestamp,
                selected_sensor="AbsorptionDetector",
                sensor_score=setup["z_score"],
                side=setup["side"],
                confidence=setup["concentration"],
                total_signals=1,
                setup_type=f"AbsorptionV2_{setup['side']}",
                metadata=trigger_metadata,
                t0_timestamp=timestamp,
                price=close_price,
            )

            logger.info(
                f"🎯 [ABSORPTION_V2] Setup FIRED: {symbol} {setup['side']} @ {setup['entry_price']:.2f} "
                f"(TP={setup['tp_price']:.2f}, SL={setup['sl_price']:.2f}, "
                f"conf={setup.get('confirmations', 0)}/3)"
            )

            # Update cooldown (use event timestamp for backtest compatibility)
            self.last_fire_ts[symbol] = timestamp

            await self.engine.dispatch(agg_event)
            return

        # ── PHASE 1: Run absorption detector for new candidates ──
        candidate = self.absorption_detector.on_candle(
            symbol, timestamp, close_price, open_price, high_price, low_price
        )
        if candidate:
            # Register candidate with guardian for Phase 2 confirmation
            self.absorption_guardian.register_candidate(candidate)
            logger.info(
                f"📋 [ABSORPTION_V2] Candidate detected: {symbol} {candidate['direction']} @ {close_price:.2f} "
                f"— waiting for confirmation"
            )
