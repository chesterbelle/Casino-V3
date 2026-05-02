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
from decision.guardians import GuardianManager
from utils.structural_math import calculate_lvn_target, check_level_proximity

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

        # Phase 1200: Limit Sniper Integration - Resolve nearest level for maker entry
        if "level_price" not in metadata and self.context_registry and metadata.get("price", 0) > 0:
            proximity = check_level_proximity(symbol, metadata["price"], self.context_registry, self.fast_track)
            if proximity:
                metadata["level_price"] = proximity["level_price"]
                metadata["level_ref"] = proximity["level_ref"]

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
            "TacticalAbsorptionV2",  # Nuevo núcleo LTA V7: Absorción de alta precisión
            "TacticalAbsorption",  # Legacy fallback
            "TacticalDivergence",  # Confirmador: agotamiento de momentum
            "TacticalTrappedTraders",  # Confirmador: participantes atrapados
            "TacticalExhaustion",  # Confirmador: volumen extremo sin follow-through
            "TacticalLiquidationCascade",  # Playbook Beta: fade de dislocación extrema
            "TacticalSinglePrintReversion",  # Market Profile: single print rejection
            "TacticalVolumeClimaxReversion",  # Wyckoff: volume climax without extension
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
        # side = reversal_signal.get("direction") # REMOVED: Metadata 'direction' contains sensor-specific strings like 'SELL_EXHAUSTION'

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
        passed, final_sizing_multiplier = self.guardian_manager.evaluate_all(
            symbol, side, reversal_signal, self.context_registry, self.recent_extremes, self.fast_track
        )
        if not passed:
            return None

        # 4. Directional Logic:
        # If at VAH, we want to SHORT back to POC.
        # If at VAL, we want to LONG back to POC.
        if is_at_vah and side != "SHORT":
            return None
        if is_at_val and side != "LONG":
            return None

        # 5. Calculate Structural Targets (LTA V7 Dynamic Targets)
        # Search for the first Low Volume Node (LVN) in the trade direction
        tp_price = calculate_lvn_target(symbol, price, side)

        if not tp_price:
            # Fallback to structural 0.20% (Increased from 0.15% to cover fees)
            tp_distance_pct = 0.0020
            if side == "LONG":
                tp_price = price * (1 + tp_distance_pct)
            else:
                tp_price = price * (1 - tp_distance_pct)
        else:
            # Ensure LVN TP is at least 0.20% away from entry to cover fees
            tp_dist = abs(tp_price - price) / price
            if tp_dist < 0.0020:
                if side == "LONG":
                    tp_price = price * 1.0020
                else:
                    tp_price = price * 0.9980

        # SL is structural: Buffer outside the edge
        sl_buffer = strat_config.LTA_TICK_PROXY * strat_config.LTA_SL_TICK_BUFFER
        if side == "LONG":
            sl_price = val * (1 - sl_buffer)
        else:
            sl_price = vah * (1 + sl_buffer)

        # 6. Calculate Aggregated Sizing Multiplier (Phase 2350)
        # Multiplier is calculated in GuardianManager

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
                proximity = check_level_proximity(sym, price, self.context_registry, self.fast_track)
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
