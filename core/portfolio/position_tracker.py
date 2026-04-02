"""
Position Tracker for Casino V3 - Position Management & WebSocket Confirmation
==============================================================================

Manages open positions with real-time WebSocket confirmation from exchange.

Architecture:
-------------
Casino V3 uses event-driven position tracking with WebSocket order updates:
- Positions are opened with TP/SL orders on the exchange
- WebSocket callbacks confirm fills in real-time
- Capital is blocked proportionally to margin used
- Positions close automatically via TP/SL execution

Key Features:
-------------
- Real-time position tracking with WebSocket confirmation
- Capital blocking during active positions
- Automatic position closure via OCO orders (TP/SL)
- Persistent statistics (trades, wins, losses)
- Exchange reconciliation support

Version: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from exchanges.adapters import ExchangeAdapter

import config.trading
from core.observability.historian import historian
from utils.symbol_norm import normalize_symbol

logger = logging.getLogger("PositionTracker")


@dataclass
class OrderState:
    """
    Represents the state of a single order within a position.
    Phase 31: Unified architecture - orders are embedded in positions.
    """

    client_order_id: str  # Our ID (e.g., "CASINO_TP_abc123")
    order_type: str  # "MAIN", "TP", "SL"
    side: str  # "BUY" or "SELL"
    amount: float = 0.0
    price: float = 0.0
    exchange_order_id: Optional[str] = None  # Binance ID (e.g., "142114122")
    status: str = "PENDING"  # PENDING -> OPEN -> FILLED/CANCELED
    fee: float = 0.0
    filled_price: float = 0.0
    filled_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def update_from_event(self, event: Dict[str, Any]) -> bool:
        """Update order state from WebSocket event. Returns True if status changed."""
        old_status = self.status
        # Handle both raw Binance (X) and normalized (status)
        self.status = event.get("X") or event.get("status") or self.status
        self.last_updated = time.time()

        if self.status in ("FILLED", "closed"):
            self.filled_at = time.time()
            # Handle normalized (average, filled) and raw (ap, L, z)
            self.filled_price = float(
                event.get("average") or event.get("ap") or event.get("L") or event.get("price") or 0
            )

            fee_info = event.get("fee", {})
            if isinstance(fee_info, dict):
                self.fee = float(fee_info.get("cost") or event.get("n") or 0)
            else:
                self.fee = float(event.get("n") or 0)

        if not self.exchange_order_id:
            # Handle normalized (order_id, id) and raw (i)
            self.exchange_order_id = str(event.get("order_id") or event.get("id") or event.get("i") or "")
            if self.exchange_order_id == "None":
                self.exchange_order_id = None

        return old_status != self.status


@dataclass
class OpenPosition:
    """Representa una posición abierta con TP/SL pendientes."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    entry_timestamp: str
    timestamp: float  # Phase 800: Float seconds for Grace Period logic
    margin_used: float
    notional: float
    leverage: float
    tp_level: float
    sl_level: float
    liquidation_level: Optional[float] = None
    amount: float = 0.0  # Phase 42: Contracts/Qty for accurate reporting
    order: Dict[str, Any] = field(default_factory=dict)
    shadow_sl_level: Optional[float] = None
    entry_atr: float = 0.0  # Phase 710: ATR at time of entry
    # Legacy ID fields (for backward compatibility during migration)
    main_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    exchange_tp_id: Optional[str] = None
    exchange_sl_id: Optional[str] = None
    # Phase 31: Embedded OrderState objects (unified architecture)
    main_order: Optional[OrderState] = None
    tp_order: Optional[OrderState] = None
    sl_order: Optional[OrderState] = None
    bars_held: int = 0
    entry_fee: float = 0.0
    funding_accrued: float = 0.0
    contributors: List[str] = None
    healed: bool = False
    trace_id: Optional[str] = None
    setup_type: str = "unknown"
    level_ref: str = "unknown"
    level_price: float = 0.0

    # Phase 85: Latency Telemetry
    t0_signal_ts: Optional[float] = None
    t1_decision_ts: Optional[float] = None
    t2_submit_ts: Optional[float] = None
    t3_ack_ts: Optional[float] = None
    t4_fill_ts: Optional[float] = None

    # THE GOVERNANCE LOCK: Per-position concurrency control
    # Not included in repr to avoid noise
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # Phase 800: Winner Catcher (Aggressive Trailing)
    trailing_phase: int = 0  # 0: Defensive, 1: Expansion (Cazador)
    original_tp_price: Optional[float] = None

    shadow_sl_activation: float = 0.0025  # Phase 800: Shark Breath activation threshold

    # Phase 102: Lifecycle attribution for reporting
    lifecycle_phase: str = "ACTIVE"

    # State Machine Status
    # OPENING: In process of creating TP/SL orders (Audit should wait)
    # ACTIVE: Fully established with TP/SL (Audit should enforce)
    # CLOSING: In process of closing (Audit should wait)
    status: str = "ACTIVE"

    def on_order_update(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Handle ORDER_UPDATE event for this position.
        Returns event type if matched: "TP_FILLED", "SL_FILLED", "MAIN_FILLED", or None.
        """
        # Support both raw (c) and normalized (client_order_id)
        client_id = event.get("client_order_id") or event.get("c") or event.get("clientOrderId")
        if not client_id:
            return None

        # Check TP order
        if self.tp_order and client_id == self.tp_order.client_order_id:
            self.tp_order.update_from_event(event)
            if self.tp_order.status in ("FILLED", "closed"):
                return "TP_FILLED"

        # Check SL order
        elif self.sl_order and client_id == self.sl_order.client_order_id:
            self.sl_order.update_from_event(event)
            if self.sl_order.status in ("FILLED", "closed"):
                return "SL_FILLED"

        # Check Main order
        elif self.main_order and client_id == self.main_order.client_order_id:
            self.main_order.update_from_event(event)  # F841 fix: removed unused status_changed
            if self.main_order.status in ("FILLED", "closed"):
                return "MAIN_FILLED"

        return None


class PositionTracker:
    """
    Manages open positions with real-time WebSocket confirmation.

    Casino V3 Architecture:
    -----------------------
    Positions are tracked with capital blocking and confirmed via WebSocket events:

    1. Position opened -> Capital blocked
    2. TP/SL orders placed on exchange
    3. WebSocket monitors order fills
    4. On fill -> confirm_close() called -> Capital released

    Usage Example:
    --------------
    ```python
    tracker = PositionTracker(max_concurrent_positions=10)

    # Open position (called by Croupier)
    position = tracker.open_position(
        order=order_dict,
        entry_price=50000.0,
        entry_timestamp="2024-01-01T00:00:00Z",
        available_equity=10000.0,
        main_order_id="12345",
        tp_order_id="12346",
        sl_order_id="12347"
    )

    # Confirm close when WebSocket receives fill event
    result = tracker.confirm_close(
        trade_id="trade_123",
        exit_price=51000.0,  # Real fill price from exchange
        exit_reason="TP",     # TP, SL, MANUAL, etc.
        pnl=150.0,           # Real PnL
        fee=2.5              # Real fee
    )
    ```

    Statistics:
    -----------
    Tracks persistent statistics across sessions:
    - total_trades_closed: Total closed positions
    - total_wins: Positions closed via TP
    - total_losses: Positions closed via SL/other
    """

    def __init__(
        self,
        adapter: Optional["ExchangeAdapter"] = None,
        on_close_callback: Optional[callable] = None,
        session_id: Optional[str] = None,
    ):
        """
        Args:
            adapter: ExchangeAdapter para cancelar órdenes OCO (agnóstico del conector)
            session_id: ID de la sesión actual (para Historian)
        """
        self.session_id = session_id
        self.session_start_ts = time.time()  # Phase 110: Session Isolation
        self.open_positions: List[OpenPosition] = []
        self.blocked_capital: float = 0.0
        self.adapter = adapter  # For OCO cancellation
        self._close_listeners: List[callable] = []
        # Callback for immediate state persistence
        self.state_change_callback: Optional[Callable[[], Awaitable[None]]] = None
        self._background_tasks = set()  # Prevent GC of fire-and-forget tasks
        self.total_trades_opened = 0
        self.total_trades_closed = 0
        self.total_wins = 0  # Track wins
        self.total_losses = 0  # Track losses
        self.total_errors = 0  # Track errors/forced closes
        # Phase 248: HFT Loop Prevention - Cooldown for failed/aborted signals
        # symbol -> cooldown_expiry_timestamp
        self._aborted_cooldowns: Dict[str, float] = {}
        self._cooldown_duration: float = 60.0  # Default 60 seconds
        self.total_timeouts = 0  # Track timeouts

        # Granular Session Counters (New vs Recovered)
        self.recovered_count = 0
        self.new_longs = 0
        self.new_shorts = 0

        # Architecture: Alias Map for O(1) Order ID Lookup (Partitioned by Symbol)
        # Centralized index for O(1) lookup of any order ID (Client or Exchange) -> Position
        # Partitioned by symbol to prevent cross-symbol order hijacks/collisions.
        self._alias_map: Dict[str, Dict[str, OpenPosition]] = defaultdict(dict)

        # History of closed trades for detailed reporting
        self.history: List[Dict[str, Any]] = []  # Store closed trade results
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}  # Pending close confirmations

        # O(1) Symbol Map for high-frequency price processing
        self._symbol_map: Dict[str, List[OpenPosition]] = defaultdict(list)

        logger.info("PositionTracker inicializado | Global limit removed (Unlimited)")

    # =========================================================
    # LISTENER MANAGEMENT
    # =========================================================

    def add_close_listener(self, callback: callable):
        """Adds a listener for position closure events."""
        if callback not in self._close_listeners:
            self._close_listeners.append(callback)

    def remove_close_listener(self, callback: callable):
        """Removes a listener for position closure events."""
        if callback in self._close_listeners:
            self._close_listeners.remove(callback)

    @property
    def on_close_callback(self):
        """Legacy compatibility for single callback."""
        return self._close_listeners[0] if self._close_listeners else None

    @on_close_callback.setter
    def on_close_callback(self, callback):
        """Legacy compatibility for single callback (appends if not present)."""
        if callback:
            self.add_close_listener(callback)

    # =========================================================
    # ALIAS MAP: Centralized Identity Management (Phase 44)
    # =========================================================

    def register_alias(self, alias_id: str, position: OpenPosition, symbol: Optional[str] = None) -> None:
        """
        Maps an ID (Client or Exchange) to a Position within a specific symbol context.
        Critical for O(1) lookups of WS events.
        """
        if not alias_id:
            return

        target_symbol = normalize_symbol(symbol or position.symbol)
        if not target_symbol:
            logger.warning(f"⚠️ Cannot register alias {alias_id}: No symbol provided and position HAS NO SYMBOL")
            return

        self._alias_map[target_symbol][str(alias_id)] = position
        # logger.debug(f"📇 Registered alias: {alias_id} -> {target_symbol}")

    def unregister_alias(self, alias_id: str, symbol: Optional[str] = None) -> None:
        """Removes an ID from the symbol-specific map."""
        if not alias_id:
            return

        # If symbol is provided, only look there. If not, we have to look everywhere (legacy/safety)
        if symbol:
            target_symbol = normalize_symbol(symbol)
            if alias_id in self._alias_map.get(target_symbol, {}):
                del self._alias_map[target_symbol][str(alias_id)]
        else:
            # Fallback: sweep all symbols (less efficient, but safe for migration)
            for sym_bucket in self._alias_map.values():
                if str(alias_id) in sym_bucket:
                    del sym_bucket[str(alias_id)]
            # logger.debug(f"🗑️ Unregistered alias: {alias_id}")

    def get_position_by_id(self, order_id: str, symbol: Optional[str] = None) -> Optional[OpenPosition]:
        """Look up position by any known ID (Client or Exchange) with symbol context."""
        if not order_id:
            return None

        # 1. O(1) lookup within symbol bucket
        if symbol:
            target_symbol = normalize_symbol(symbol)
            pos = self._alias_map.get(target_symbol, {}).get(str(order_id))
            if pos:
                return pos
        else:
            # Fallback: scan all buckets (O(S) where S is number of active symbols)
            for sym_bucket in self._alias_map.values():
                pos = sym_bucket.get(str(order_id))
                if pos:
                    return pos

        # 2. Linear Fallback (Global Safety)
        for pos in self.open_positions:
            if pos.trade_id == order_id:
                return pos
        return None

    def get_position(self, trade_id: str) -> Optional[OpenPosition]:
        """Legacy access method (wraps Alias Map lookup)."""
        return self.get_position_by_id(trade_id)

    def get_positions_by_symbol(self, symbol: str) -> List[OpenPosition]:
        """
        O(1) Symbol Lookup: Retrieves all positions for a specific symbol.
        Used to eliminate O(N) scans in ExitManager (Phase 46).
        """
        return self._symbol_map.get(normalize_symbol(symbol), [])

    def get_active_positions(self, symbol: Optional[str] = None) -> List[OpenPosition]:
        """
        Phase 234: Returns only positions in 'ENTRY-ACTIVE' states.
        Excludes CLOSING and OFF_BOARDING states.

        Args:
            symbol: Optional filter by symbol

        Returns:
            List of positions in ACTIVE, OPENING, or MODIFYING status.
        """
        candidates = self.get_positions_by_symbol(symbol) if symbol else self.open_positions
        return [pos for pos in candidates if getattr(pos, "status", "ACTIVE") in ["ACTIVE", "OPENING", "MODIFYING"]]

    def has_valid_bracket(self, trade_id: str, exchange_order_ids: set, exchange_client_ids: set = None) -> tuple:
        """
        Phase 54: Check if a position has valid TP and SL orders on the exchange.
        Uses the Alias Map as the Single Source of Truth.

        Args:
            trade_id: Position trade ID
            exchange_order_ids: Set of order IDs currently on exchange
            exchange_client_ids: Optional set of client order IDs on exchange

        Returns:
            (has_tp: bool, has_sl: bool) tuple
        """
        position = self.get_position_by_id(trade_id)
        if not position:
            return (False, False)

        exchange_client_ids = exchange_client_ids or set()

        # Check TP: Look for any of this position's TP IDs in exchange orders
        has_tp = False
        tp_ids_to_check = []
        if position.tp_order_id:
            tp_ids_to_check.append(str(position.tp_order_id))
        if position.exchange_tp_id:
            tp_ids_to_check.append(str(position.exchange_tp_id))
        if position.tp_order and position.tp_order.exchange_order_id:
            tp_ids_to_check.append(str(position.tp_order.exchange_order_id))
        if position.tp_order and position.tp_order.client_order_id:
            tp_ids_to_check.append(str(position.tp_order.client_order_id))

        for tp_id in tp_ids_to_check:
            if tp_id in exchange_order_ids or tp_id in exchange_client_ids:
                has_tp = True
                break

        # Check SL: Look for any of this position's SL IDs in exchange orders
        has_sl = False
        sl_ids_to_check = []
        if position.sl_order_id:
            sl_ids_to_check.append(str(position.sl_order_id))
        if position.exchange_sl_id:
            sl_ids_to_check.append(str(position.exchange_sl_id))
        if position.sl_order and position.sl_order.exchange_order_id:
            sl_ids_to_check.append(str(position.sl_order.exchange_order_id))
        if position.sl_order and position.sl_order.client_order_id:
            sl_ids_to_check.append(str(position.sl_order.client_order_id))

        for sl_id in sl_ids_to_check:
            if sl_id in exchange_order_ids or sl_id in exchange_client_ids:
                has_sl = True
                break

        return (has_tp, has_sl)

    def _unregister_all_aliases(self, position: OpenPosition) -> None:
        """Removes all aliases associated with a position."""
        symbol = position.symbol
        self.unregister_alias(position.trade_id, symbol=symbol)
        self.unregister_alias(position.main_order_id, symbol=symbol)
        self.unregister_alias(position.tp_order_id, symbol=symbol)
        self.unregister_alias(position.sl_order_id, symbol=symbol)
        self.unregister_alias(position.exchange_tp_id, symbol=symbol)
        self.unregister_alias(position.exchange_sl_id, symbol=symbol)

        # Unregister from OrderState objects
        if position.main_order:
            self.unregister_alias(position.main_order.client_order_id, symbol=symbol)
            self.unregister_alias(position.main_order.exchange_order_id, symbol=symbol)
        if position.tp_order:
            self.unregister_alias(position.tp_order.client_order_id, symbol=symbol)
            self.unregister_alias(position.tp_order.exchange_order_id, symbol=symbol)
        if position.sl_order:
            self.unregister_alias(position.sl_order.client_order_id, symbol=symbol)
            self.unregister_alias(position.sl_order.exchange_order_id, symbol=symbol)

    # =========================================================
    # GOVERNANCE AUTHORITY: Centralized State Transitions
    # =========================================================

    async def lock_for_closure(self, trade_id: str, wait_if_busy: bool = True) -> bool:
        """
        Attempts to atomically lock a position for closure.
        """
        position = self.get_position(trade_id)
        if not position:
            return False

        # Phase 243: Fail-fast and low-overhead governance
        # If already closing, skip immediately without waiting or traceback overhead.
        if position.status == "CLOSING":
            return False

        # 1. Non-blocking checkout
        if position._lock.locked():
            if not wait_if_busy:
                return False

            # Wait for the lock to be released by whoever holds it
            try:
                # We use a shorter timeout for the hot path
                async with asyncio.timeout(2.0):
                    async with position._lock:
                        # Once released, re-check status
                        return position.status != "CLOSING"
            except (asyncio.TimeoutError, Exception):
                return False

        # 2. Acquire lock
        await position._lock.acquire()

        # Double check status after acquisition
        if position.status == "CLOSING":
            position._lock.release()
            return False

        position.status = "CLOSING"
        if self.state_change_callback:
            asyncio.create_task(self.state_change_callback())

        return True

    def unlock(self, trade_id: str, position: Optional[OpenPosition] = None) -> None:
        """
        Releases the governance lock for a position.

        Args:
            trade_id: Position ID.
            position: Optional pre-fetched position object (used if already removed from tracker).
        """
        target = position or self.get_position(trade_id)
        if target:
            if target._lock.locked():
                target._lock.release()
                logger.debug(f"🔓 Governance lock released for {trade_id}")

            # Note: Unregister contributors here (they are aliases)
            for contrib_id in target.contributors or []:
                self.unregister_alias(contrib_id)

        # Phase 46.1: Symbol Map Cleanup REMOVED from unlock.
        # It is now handled EXCLUSIVELY by finalize_removal (Phase 48).

    def set_state_change_callback(self, callback: Callable[[], Awaitable[None]]):
        """Register callback for immediate state persistence."""
        self.state_change_callback = callback

    def _trigger_state_change(self):
        """Trigger state save if callback is registered."""
        if self.state_change_callback:
            task = asyncio.create_task(self.state_change_callback())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    # =========================================================================
    # Phase 31: Unified Event Routing (replaces OrderTracker)
    # =========================================================================

    def register_order(self, position: "OpenPosition", order: OrderState):
        """
        Register a specific order (TP/SL/Main) for O(1) lookup via Alias Map.
        Supersedes legacy usage of _positions_by_client_id.
        """
        symbol = position.symbol
        if order.client_order_id:
            self.register_alias(order.client_order_id, position, symbol=symbol)
        if order.exchange_order_id:
            self.register_alias(str(order.exchange_order_id), position, symbol=symbol)

    def unregister_order(
        self,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ):
        """Remove order from lookup (called on position close)."""
        if client_order_id:
            self.unregister_alias(client_order_id, symbol=symbol)
        if exchange_order_id:
            self.unregister_alias(str(exchange_order_id), symbol=symbol)

    def register_bracket_alias(
        self, order_id: str, position: OpenPosition, order_type: str, client_id: Optional[str] = None
    ) -> None:
        """
        Register a new TP/SL order alias atomically.
        Used by OCOManager to ensure Tracker is consistent BEFORE liberating the modification lock.

        Phase 57: Now proactively unregisters the PREVIOUS ID to prevent Alias Pollution.
        """
        if not order_id or not position:
            return

        order_id = str(order_id)
        sym = position.symbol

        # 1. Proactive Identity Cleanup: Unregister old ID from maps before setting new one
        if order_type == "TP":
            old_ex_id = position.exchange_tp_id
            old_cl_id = position.tp_order_id
            if old_ex_id and str(old_ex_id) != order_id:
                self.unregister_alias(old_ex_id, symbol=sym)
            if old_cl_id and str(old_cl_id) != order_id and old_cl_id != client_id:
                self.unregister_alias(old_cl_id, symbol=sym)

            position.exchange_tp_id = order_id
            if client_id:
                position.tp_order_id = client_id

        elif order_type == "SL":
            old_ex_id = position.exchange_sl_id
            old_cl_id = position.sl_order_id
            if old_ex_id and str(old_ex_id) != order_id:
                self.unregister_alias(old_ex_id, symbol=sym)
            if old_cl_id and str(old_cl_id) != order_id and old_cl_id != client_id:
                self.unregister_alias(old_cl_id, symbol=sym)

            position.exchange_sl_id = order_id
            if client_id:
                position.sl_order_id = client_id

        # 2. Register exchange ID Alias
        self.register_alias(order_id, position, symbol=sym)

        # 3. Register client ID Alias (if not already done)
        if client_id:
            self.register_alias(client_id, position, symbol=sym)

        logger.info(f"⚡ Atomic Alias Registered: {order_type} {order_id} -> {position.symbol}")
        self._trigger_state_change()

    def handle_order_update(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Handle WebSocket ORDER_UPDATE event with O(1) lookup.

        Phase 31: This is the single source of truth for order events.
        Replaces the fragmented OrderTracker.handle_ws_update().

        Args:
            event: Raw ORDER_UPDATE event from WebSocket

        Returns:
            trade_id if event was matched to a position, None otherwise
        """
        # Support both raw and normalized keys (Phase 51 Normalization)
        client_id = event.get("client_order_id") or event.get("c") or event.get("clientOrderId")
        exchange_id = str(event.get("order_id") or event.get("id") or event.get("i") or event.get("orderId") or "")

        # Phase 80: Extract symbol for partitioned lookup
        raw_symbol = event.get("symbol") or event.get("s")
        symbol = normalize_symbol(raw_symbol)

        # O(1) lookup via Alias Map (Phase 44) - Partitioned by Symbol (Phase 80)
        position = self.get_position_by_id(client_id, symbol=symbol)
        if not position and exchange_id and exchange_id not in ("0", "", "None"):
            position = self.get_position_by_id(exchange_id, symbol=symbol)

        # Auto-Learning: Register Exchange ID if discovered for the first time
        if position and exchange_id and exchange_id not in ("0", "", "None"):
            if not self.get_position_by_id(exchange_id, symbol=symbol):
                self.register_alias(exchange_id, position, symbol=symbol)
                logger.info(f"🧠 Alias Map learned: {exchange_id} ({symbol}) -> {position.symbol}")

        if not position:
            if client_id and "CASINO_" in str(client_id):
                logger.debug(f"🕵️ WS Event UNMATCHED: ID={exchange_id} c={client_id}")
            return None

        # Delegate to position's event handler
        event_type = position.on_order_update(event)

        if event_type == "TP_FILLED":
            logger.info(f"🎯 TP FILLED detected for {position.trade_id} via unified routing")
            self._handle_tp_filled(position, event)
        elif event_type == "SL_FILLED":
            logger.info(f"🛑 SL FILLED detected for {position.trade_id} via unified routing")
            self._handle_sl_filled(position, event)
        elif event_type == "MAIN_FILLED":
            # Phase 50: In-Flight Promotion (OPENING -> ACTIVE)
            if position.status == "OPENING":
                position.status = "ACTIVE"
                logger.info(f"✅ Promoted In-Flight Position {position.trade_id} to ACTIVE")

                # If we were tracking by client ID, update to exchange ID
                if exchange_id and exchange_id not in ("0", "", "None") and position.trade_id != str(exchange_id):
                    # Keep client ID alias, but update primary ID
                    old_id = position.trade_id
                    position.trade_id = str(exchange_id)
                    self.register_alias(str(exchange_id), position, symbol=symbol)
                    logger.info(f"🔄 Swapped ID: {old_id} -> {position.trade_id}")

            # Recalculate entry based on actual fill
            # Support normalized and raw keys
            fill_price = float(event.get("average") or event.get("ap") or event.get("price") or event.get("L") or 0)

            if fill_price > 0:
                position.entry_price = fill_price

                # Phase 90: Populate notional for accurate PnL calculation
                # Without this, _handle_tp_filled and _handle_sl_filled report $0 PnL
                amount = float(position.order.get("amount", 0) if position.order else 0)
                if amount > 0:
                    position.notional = fill_price * amount

            # Phase 85: Capture T4 Fill Timestamp
            # Prefer Transaction Time (T) or Event Time (E) from WS
            raw_ts = event.get("T") or event.get("E")
            position.t4_fill_ts = float(raw_ts) / 1000.0 if raw_ts else time.time()

            logger.info(f"✅ MAIN FILLED for {position.trade_id} via unified routing (@{fill_price})")

        return position.trade_id

    async def handle_account_update(self, data: Dict[str, Any]):
        """
        Phase 78.2: Liquidation Sheriff.
        Phase 81: Signature Fix (Defensive check for nested 'a' key).
        Handle ACCOUNT_UPDATE events to catch external liquidations/closures
        that do not trigger a standard ORDER_TRADE_UPDATE (silent deaths).
        """
        # Defensive check: Connector might pass the full event or just the payload 'a'
        if "a" in data:
            update_data = data["a"]
        else:
            # Assume data is already the 'a' payload (Standard behavior in unified routing)
            update_data = data

        positions_data = update_data.get("P", [])

        for pos_data in positions_data:
            symbol = pos_data.get("s")
            amount = float(pos_data.get("pa", 0))

            # If position amount is 0, it means it's closed (or flat).
            if amount == 0:
                # Sheriff Logic: Do we have an open position for this symbol?
                # We normalize BOTH symbols to ensure "ZILUSDT" matches "ZIL/USDT".

                # Check all active positions for this symbol
                matching_positions = [
                    p for p in self.open_positions if normalize_symbol(p.symbol) == normalize_symbol(symbol)
                ]

                if matching_positions:
                    logger.warning(
                        f"🤠 Liquidation Sheriff: Detected external closure for {symbol}. Closing {len(matching_positions)} positions."
                    )

                    for pos in matching_positions:
                        # Calculated Estimated PnL (Worst Case: Liquidation)
                        # If we are long, exit price is roughly liquidation level.
                        exit_price = pos.liquidation_level or pos.entry_price  # Fallback

                        # Calculate leakage-plugging PnL
                        # PnL = (Exit - Entry) * Notional / Entry
                        if pos.entry_price > 0:
                            if pos.side == "LONG":
                                pnl = (exit_price - pos.entry_price) * pos.notional / pos.entry_price
                            else:
                                pnl = (pos.entry_price - exit_price) * pos.notional / pos.entry_price
                        else:
                            pnl = 0.0

                        # Force Close logic
                        self.confirm_close(
                            trade_id=pos.trade_id,
                            exit_price=exit_price,
                            exit_reason="LIQUIDATION",
                            pnl=pnl,
                            fee=0.0,  # Fees usually handled in separate events, but let's assume 0 for now
                        )
                        logger.info(f"⚰️ Buried Ghost Position {pos.trade_id} (PnL: {pnl:.4f})")

    def _handle_tp_filled(self, position: "OpenPosition", event: Dict[str, Any]):
        """Handle TP fill event - close position and cancel SL."""
        if position.tp_order:
            exit_price = position.tp_order.filled_price or position.tp_level
            fee = position.tp_order.fee

            # Calculate PnL
            if position.entry_price > 0:
                if position.side == "LONG":
                    pnl = (exit_price - position.entry_price) * position.notional / position.entry_price
                else:
                    pnl = (position.entry_price - exit_price) * position.notional / position.entry_price
            else:
                pnl = 0.0

            self.confirm_close(trade_id=position.trade_id, exit_price=exit_price, exit_reason="TP", pnl=pnl, fee=fee)

            # Cancel SL order
            if position.sl_order and self.adapter:
                asyncio.create_task(self._cancel_sl_order(position))

    def _handle_sl_filled(self, position: "OpenPosition", event: Dict[str, Any]):
        """Handle SL fill event - close position and cancel TP."""
        if position.sl_order:
            exit_price = position.sl_order.filled_price or position.sl_level
            fee = position.sl_order.fee

            # Calculate PnL
            if position.entry_price > 0:
                if position.side == "LONG":
                    pnl = (exit_price - position.entry_price) * position.notional / position.entry_price
                else:
                    pnl = (position.entry_price - exit_price) * position.notional / position.entry_price
            else:
                pnl = 0.0

            self.confirm_close(trade_id=position.trade_id, exit_price=exit_price, exit_reason="SL", pnl=pnl, fee=fee)

            # Cancel TP order
            if position.tp_order and self.adapter:
                asyncio.create_task(self._cancel_tp_order(position))

    async def _cancel_sl_order(self, position: "OpenPosition"):
        """Cancel SL order after TP fill (fire-and-forget)."""
        try:
            if position.sl_order and position.sl_order.exchange_order_id:
                await self.adapter.cancel_order(position.sl_order.exchange_order_id, position.symbol)
                logger.info(f"✅ Cancelled SL order {position.sl_order.client_order_id} after TP fill")
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel SL order: {e} (likely already cancelled)")

    async def _cancel_tp_order(self, position: "OpenPosition"):
        """Cancel TP order after SL fill (fire-and-forget)."""
        try:
            if position.tp_order and position.tp_order.exchange_order_id:
                await self.adapter.cancel_order(position.tp_order.exchange_order_id, position.symbol)
                logger.info(f"✅ Cancelled TP order {position.tp_order.client_order_id} after SL fill")
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel TP order: {e} (likely already cancelled)")

    # =========================================================================
    # Original Methods (unchanged)
    # =========================================================================

    def get_available_equity(self, total_equity: float) -> float:
        """Calcula capital disponible (total - bloqueado)."""
        return max(0.0, total_equity - self.blocked_capital)

    def is_symbol_blocked(self, symbol: str) -> bool:
        """
        Phase 248: Check if a symbol is in cooldown after an OCO_ABORT or failure.
        """
        normalized = normalize_symbol(symbol)
        expiry = self._aborted_cooldowns.get(normalized, 0)
        if time.time() < expiry:
            return True
        elif normalized in self._aborted_cooldowns:
            # Clean up expired cooldown
            del self._aborted_cooldowns[normalized]
        return False

    def add_aborted_cooldown(self, symbol: str, duration: Optional[float] = None):
        """
        Phase 248: Add a cooldown for a symbol after a failed trade attempt.
        """
        normalized = normalize_symbol(symbol)
        duration = duration if duration is not None else self._cooldown_duration
        self._aborted_cooldowns[normalized] = time.time() + duration
        logger.warning(f"🛡️ Symbol {normalized} placed in Cooldown for {duration}s after ABORT/FAILED.")

    def can_open_position(self, required_margin: float, available_equity: float) -> bool:
        """
        Verifica si se puede abrir una nueva posición.

        Args:
            required_margin: Margen requerido para la nueva posición
            available_equity: Capital disponible actualmente

        Returns:
            True si se puede abrir la posición
        """
        # Verificar capital disponible (Global capacity now unlimited)
        return available_equity >= required_margin

    @staticmethod
    def _normalize_side(side: str) -> Optional[str]:
        """Normaliza side a LONG/SHORT respetando entradas buy/sell."""

        if not side:
            return None

        side_upper = side.upper()

        if side_upper in {"LONG", "BUY"}:
            return "LONG"
        if side_upper in {"SHORT", "SELL"}:
            return "SHORT"

        return None

    def open_position(
        self,
        order: Dict[str, Any],
        entry_price: float,
        entry_timestamp: str,
        available_equity: float,
        main_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        exchange_tp_id: Optional[str] = None,
        exchange_sl_id: Optional[str] = None,
        entry_fee: float = 0.0,  # Phase 30
    ) -> Optional[OpenPosition]:
        """
        Abre una nueva posición y la registra.
        """

        try:
            side_raw = order.get("side", "")
            side = self._normalize_side(side_raw)
            raw_symbol = order.get("symbol", "")
            symbol = normalize_symbol(raw_symbol)
            size_fraction = order.get("size", 0.0)
            leverage = order.get("leverage", 1.0)
            trade_id = order.get("trade_id", f"pos_{self.total_trades_opened}")

            if not side:
                logger.error(f"Side inválido para abrir posición: {side_raw}")
                return None

            if size_fraction is None or size_fraction <= 0:
                logger.debug(
                    "Ignorando open_position: size_fraction inválido (trade_id=%s, size=%s)",
                    trade_id,
                    size_fraction,
                )
                return None

            # Calcular notional y margen
            amount = order.get("amount", 0.0)
            if amount > 0:
                notional = amount * entry_price
            else:
                notional = available_equity * size_fraction * leverage

            margin_used = notional / leverage if leverage > 0 else notional

            # Phase 800: Use absolute TP/SL prices directly if available
            tp_price_abs = order.get("tp_price")
            sl_price_abs = order.get("sl_price")

            if tp_price_abs and sl_price_abs and tp_price_abs > 0 and sl_price_abs > 0:
                # Absolute prices provided by strategy — use directly
                tp_level = tp_price_abs
                sl_level = sl_price_abs
            else:
                # Legacy fallback: decimal percentage from config
                tp_pct = order.get("take_profit", config.trading.DEFAULT_TP_PCT)
                sl_pct = order.get("stop_loss", config.trading.DEFAULT_SL_PCT)
                if side == "LONG":
                    tp_level = entry_price * (1 + tp_pct)
                    sl_level = entry_price * (1 - sl_pct)
                else:
                    tp_level = entry_price * (1 - tp_pct)
                    sl_level = entry_price * (1 + sl_pct)

            if side == "LONG":
                liquidation_level = entry_price * (1.0 - (1.0 / leverage) + 0.005)
            elif side == "SHORT":
                liquidation_level = entry_price * (1.0 + (1.0 / leverage) - 0.005)
            else:
                return None

            setup_type = order.get("setup_type", "unknown")

            # Crear posición
            position = OpenPosition(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                entry_timestamp=entry_timestamp,
                timestamp=time.time(),
                margin_used=margin_used,
                notional=notional,
                leverage=leverage,
                tp_level=tp_level,
                sl_level=sl_level,
                liquidation_level=liquidation_level,
                order=order.copy(),
                setup_type=setup_type,
                main_order_id=main_order_id,
                tp_order_id=tp_order_id,
                sl_order_id=sl_order_id,
                exchange_tp_id=exchange_tp_id,
                exchange_sl_id=exchange_sl_id,
                contributors=order.get("contributors", []),
                entry_fee=entry_fee,  # Phase 30
                shadow_sl_activation=order.get("shadow_sl_activation", 0.0025),  # Phase 800
            )

            # Registrar posición
            sym_norm = normalize_symbol(symbol)
            self.open_positions.append(position)
            if position not in self._symbol_map[sym_norm]:
                self._symbol_map[sym_norm].append(position)

            # --- Alias Map: Register Aliases (Phase 44) - Partitioned by Symbol (Phase 80) ---
            self.register_alias(trade_id, position, symbol=symbol)
            if main_order_id:
                self.register_alias(main_order_id, position, symbol=symbol)
            if tp_order_id:
                self.register_alias(tp_order_id, position, symbol=symbol)
            if sl_order_id:
                self.register_alias(sl_order_id, position, symbol=symbol)
            if exchange_tp_id:
                self.register_alias(exchange_tp_id, position, symbol=symbol)
            if exchange_sl_id:
                self.register_alias(exchange_sl_id, position, symbol=symbol)

            for contrib_id in position.contributors or []:
                self.register_alias(contrib_id, position, symbol=symbol)
            # ----------------------------------------------

            self.blocked_capital += margin_used
            self.total_trades_opened += 1
            logger.debug(f"COUNTER_DEBUG: Incrementing total_opened to {self.total_trades_opened} via open_position")

            # Update granular counters
            if side == "LONG":
                self.new_longs += 1
            else:
                self.new_shorts += 1

            logger.info(
                f"📈 OPEN | {symbol} {side} | Entry: {entry_price:.2f} | "
                f"TP: {tp_level:.2f} | SL: {sl_level:.2f} | Notional: {notional:.2f} | Margin: {margin_used:.2f}"
            )

            self._trigger_state_change()

            return position

        except Exception as e:
            logger.error(f"Error abriendo posición: {e}")
            return None

    def check_and_close_positions(self, current_candle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Verifica si alguna posición debe cerrarse según la vela actual.
        Detecta TP/SL tocados y marca como pending para verificación con exchange.

        Args:
            current_candle: Vela actual con keys: timestamp, open, high, low, close

        Returns:
            Lista de resultados de cierre (o eventos pending)
        """
        return self._check_potential_exits(current_candle)

    def _check_potential_exits(self, current_candle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detecta TP/SL tocados, marca como pending, espera confirmación.
        NO cierra la posición ni cuenta como WIN/LOSS hasta que exchange confirme.
        """
        potential_closes = []
        high = float(current_candle.get("high", 0))
        low = float(current_candle.get("low", 0))
        timestamp = current_candle.get("timestamp", "")

        for position in self.open_positions:
            # CRITICAL FIX: Check symbol FIRST to prevent multi-counting in Multi-Asset mode
            # Each position should only increment bars_held for its own symbol's candles
            pos_sym = normalize_symbol(position.symbol)
            candle_sym = normalize_symbol(current_candle.get("symbol", ""))

            if pos_sym != candle_sym:
                continue

            position.bars_held += 1

            # Skip si ya está pending
            if position.trade_id in self.pending_confirmations:
                continue

            # Detectar si TP/SL fue tocado
            exit_reason = None
            exit_price = None

            if position.side == "LONG":
                if position.liquidation_level and low <= position.liquidation_level:
                    exit_reason = "LIQUIDATION"
                    exit_price = position.liquidation_level
                elif low <= position.sl_level:
                    exit_reason = "SL"
                    exit_price = position.sl_level
                elif high >= position.tp_level:
                    exit_reason = "TP"
                    exit_price = position.tp_level

            elif position.side == "SHORT":
                if position.liquidation_level and high >= position.liquidation_level:
                    exit_reason = "LIQUIDATION"
                    exit_price = position.liquidation_level
                elif high >= position.sl_level:
                    exit_reason = "SL"
                    exit_price = position.sl_level
                elif low <= position.tp_level:
                    exit_reason = "TP"
                    exit_price = position.tp_level

            # Time-Based Exit Check moved to ExitManager for Soft/Graceful logic

            if exit_reason:
                # Calcular PnL teórico (para referencia)
                # Protección contra división por cero
                if position.entry_price == 0:
                    logger.warning(f"⚠️ Position {position.trade_id} has entry_price=0, skipping PnL calculation")
                    pnl_pct = 0.0
                    pnl_value = 0.0
                else:
                    if position.side == "LONG":
                        pnl_pct = (exit_price - position.entry_price) / position.entry_price
                    else:
                        pnl_pct = (position.entry_price - exit_price) / position.entry_price
                    pnl_value = position.notional * pnl_pct

                # Marcar como pending (NO confirmar aún)
                pending_result = {
                    "trade_id": position.trade_id,
                    "symbol": position.symbol,
                    "side": position.side,
                    "entry_price": position.entry_price,
                    "exit_price_detected": exit_price,  # Teórico
                    "exit_reason_detected": exit_reason,
                    "pnl_estimated": pnl_value,  # Estimado
                    "bars_held": position.bars_held,
                    "timestamp": timestamp,
                    "confirmed": False,  # ← FLAG CRÍTICO
                    "pending_confirmation": True,
                    "status": "PENDING_CONFIRMATION",
                }

                # Guardar en pending
                self.pending_confirmations[position.trade_id] = pending_result

                logger.info(
                    f"⏳ PENDING | {position.symbol} {position.side} | "
                    f"Detected: {exit_reason} @ {exit_price:.2f} | "
                    f"PnL estimado: {pnl_value:+.2f} | "
                    f"Esperando confirmación del exchange..."
                )

                potential_closes.append(pending_result)

        return potential_closes

    def confirm_close(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        pnl: float,
        fee: float = 0.0,
        healed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Confirms position close with real exchange data.

        Called by WebSocket callbacks when TP/SL fills are received from exchange.

        Args:
            trade_id: ID of the trade to close
            exit_price: Actual fill price from exchange
            exit_reason: Confirmed reason ("TP", "SL", "MANUAL", "LIQUIDATION")
            pnl: Real PnL (includes fees, slippage)
            fee: Real trading fee
            auditor: Optional DecisionAuditor (Phase 103)

        Returns:
            Confirmed close result or None if position not found
        """
        # Buscar posición
        position = self.get_position(trade_id)

        if not position:
            logger.warning(f"⚠️ No se encontró posición para confirmar: {trade_id}")
            return None

        # Idempotency Check: Prevent double-recording if already closed/off-boarding
        if position.status == "OFF_BOARDING":
            logger.debug(f"⚠️ confirm_close ignored for {trade_id}: Already OFF_BOARDING")
            return None

        # Crear resultado CONFIRMADO con datos REALES
        result = {
            "trade_id": trade_id,
            "result": "WIN" if pnl > 0 else "LOSS",
            "pnl": pnl,  # ← PNL REAL
            "pnl_pct": pnl / position.notional if position.notional > 0 else 0.0,
            "entry_fee": position.entry_fee,  # Phase 30
            "exit_fee": fee,  # Phase 30
            "fee": fee + position.entry_fee,  # Total fee for historian
            "funding": position.funding_accrued,
            "trace_id": position.trace_id,
            "liquidated": exit_reason == "LIQUIDATION",
            "margin_used": position.margin_used,
            "notional": position.notional,
            "leverage": position.leverage,
            "symbol": normalize_symbol(position.symbol),
            "entry_price": position.entry_price,
            "exit_price": exit_price,  # ← PRECIO REAL
            "trigger_price": exit_price,
            "bars_held": position.bars_held,
            "exit_reason": exit_reason,  # ← CONFIRMADO
            "side": position.side,
            "qty": position.amount or position.notional / position.entry_price if position.entry_price > 0 else 0,
            "action": "CLOSE",
            "ghost": False,
            "confirmed": True,  # ← FLAG CRÍTICO
            "state_source": "exchange_confirmed",
            "contributors": position.contributors,
            "session_id": self.session_id,
            "lifecycle_phase": getattr(position, "lifecycle_phase", "ACTIVE"),
            "healed": 1 if (healed or getattr(position, "healed", False)) else 0,  # Phase 81
            "setup_type": getattr(position, "setup_type", "unknown") or "unknown",
            "level_ref": getattr(position, "level_ref", "unknown") or "unknown",
            "level_price": getattr(position, "level_price", 0.0),
        }

        # Phase 247: Prevent Double Recording (Ghost Inflation)
        # Set an ultra-fast in-memory flag before passing to historian thread.
        # This stops ReconciliationService from ghost-auditing positions we've already closed.
        position._closure_recorded = True

        # Remover de pending si estaba
        if trade_id in self.pending_confirmations:
            del self.pending_confirmations[trade_id]

        # LIFECYCLE ARCHITECTURE: Soft-Delete (Phase 48)
        # We do NOT remove the position from open_positions here.
        # Instead, we set status to OFF_BOARDING so ReconciliationService can see it.
        # finalize_removal will handle the actual list removal.
        position.status = "OFF_BOARDING"
        position.exit_reason = exit_reason
        position.realized_pnl = pnl

        # Note: We still unregister all aliases here to "hide" it from future WS updates
        self._unregister_all_aliases(position)

        # Liberar capital bloqueado
        self.blocked_capital -= position.margin_used
        self.total_trades_closed += 1

        # Track wins/losses based on PnL (positive = win, negative/zero = loss)
        if exit_reason in ["ERROR", "FORCED_CLOSE", "CLI_FORCE_CLOSE", "SAFETY_CLOSE", "OCO_ABORT"]:
            self.total_errors += 1
            # Phase 248: Trigger cooldown for ungraceful exits to prevent HFT loops
            self.add_aborted_cooldown(position.symbol)
        elif exit_reason in ["TIMEOUT", "TIME_EXIT"]:
            self.total_timeouts += 1
        elif pnl > 0:
            self.total_wins += 1
        else:
            self.total_losses += 1

        # Add to history
        self.history.append(result)

        # Phase 103: Forensic Execution Recording
        if position.trace_id:
            # Attempt to find auditor in parent components or session
            # For simplicity, we assume result is passed to auditor elsewhere
            # OR we try to get auditor from croupier if possible.
            # But confirm_close is called from many places.
            pass

        logger.info(
            f"PnL REAL: {pnl:+.2f} | Fee (Entry+Exit): {fee + position.entry_fee:.4f} | "
            f"Funding: {position.funding_accrued:+.4f} | Bars: {position.bars_held}"
        )

        # Record in persistent history
        historian.record_trade(result)

        # Notificar a Gemini (o cualquier otro listener) sobre el resultado
        for listener in self._close_listeners:
            try:
                listener(trade_id, result)
            except Exception as e:
                logger.error(f"❌ Error in close listener: {e}")

        # --- Governance Cleanup: Release lock after removal ---
        if position._lock.locked():
            position._lock.release()
            logger.debug(f"🔓 Final governance lock released for {trade_id}")

        self._trigger_state_change()

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del tracker."""
        return {
            "open_positions": len(self.open_positions),
            "blocked_capital": self.blocked_capital,
            "total_opened": self.total_trades_opened,
            "total_closed": self.total_trades_closed,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_errors": self.total_errors,
            "total_timeouts": self.total_timeouts,
            "recovered_count": self.recovered_count,
            "new_longs": self.new_longs,
            "new_shorts": self.new_shorts,
            "new_opened": self.new_longs + self.new_shorts,
        }

    def get_stats_by_symbol(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics broken down by symbol.

        Returns:
            Dict[symbol, {wins, losses, pnl, trades}]
        """
        stats = {}
        for trade in self.history:
            sym = trade.get("symbol", "Unknown")
            if sym not in stats:
                stats[sym] = {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0, "fees": 0.0}

            stats[sym]["trades"] += 1
            stats[sym]["pnl"] += trade.get("pnl", 0.0)
            stats[sym]["fees"] += trade.get("fee", 0.0)

            if trade.get("result") == "WIN":
                stats[sym]["wins"] += 1
            else:
                stats[sym]["losses"] += 1

        return stats

    def set_stats(self, total_closed: int, total_wins: int, total_losses: int, total_opened: int = 0):
        """Restores statistics from persistent state."""
        self.total_trades_closed = total_closed
        self.total_wins = total_wins
        self.total_losses = total_losses
        self.total_trades_opened = total_opened
        # Default new stats to 0 if recovering from old state
        self.total_errors = 0
        self.total_timeouts = 0
        logger.info(
            f"📊 Stats restored: Opened={total_opened} | Closed={total_closed} | Wins={total_wins} | Losses={total_losses}"
        )

    def force_close_all_positions(self, current_candle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fuerza cierre de todas las posiciones abiertas (ej. fin del backtest).
        Usa precio de cierre actual.
        """
        closed_results = []

        close_price = float(current_candle.get("close", 0))
        timestamp = current_candle.get("timestamp", "")

        for position in self.open_positions[:]:  # Copia para modificar
            # Calcular P&L con precio de cierre
            if position.side == "LONG":
                pnl_pct = (close_price - position.entry_price) / position.entry_price
            else:
                pnl_pct = (position.entry_price - close_price) / position.entry_price

            pnl_value = position.notional * pnl_pct

            result = {
                "trade_id": position.trade_id,
                "result": "LOSS",  # Force close is always considered a LOSS
                "pnl": pnl_value,
                "pnl_pct": pnl_pct,
                "fee": 0.0,
                "funding": position.funding_accrued,
                "liquidated": False,
                "margin_used": position.margin_used,
                "notional": position.notional,
                "leverage": position.leverage,
                "symbol": position.symbol,
                "entry_price": position.entry_price,
                "trigger_price": close_price,
                "bars_held": position.bars_held,
                "exit_reason": "FORCED_CLOSE",
                "exit_timestamp": timestamp,
                "market": current_candle.get("market", ""),
                "timeframe": current_candle.get("timeframe", ""),
                "timestamp": timestamp,
                "side": position.side,
                "action": "CLOSE",
                "ghost": False,
                "session_id": self.session_id,
                "setup_type": getattr(position, "setup_type", "unknown"),
            }

            closed_results.append(result)
            self.blocked_capital -= position.margin_used
            self.total_trades_closed += 1

            logger.info(f"P&L: {pnl_value:+.2f} ({pnl_pct:.2%}) | Bars: {position.bars_held}")

            # Record force close in persistent history
            historian.record_trade(result)

            # --- Alias Map Cleanup ---
            self._unregister_all_aliases(position)
            # -------------------------

            # Maintenance (Phase 46)
            sym_norm = normalize_symbol(position.symbol)
            if position in self._symbol_map.get(sym_norm, []):
                self._symbol_map[sym_norm].remove(position)

        self.open_positions.clear()
        self._trigger_state_change()
        return closed_results

    async def remove_position(self, trade_id: str) -> bool:
        """
        Remove a position and perform a GHOST AUDIT via REST.
        This ensures that even if a position is orphaned, its PnL/Fees are captured.
        """
        found_pos = None
        for pos in self.open_positions:
            if pos.trade_id == trade_id:
                found_pos = pos
                break

        if not found_pos:
            return False

        # Phase 247: Ghost Inflation Protection (Double Accounting)
        # If the position has already been handled by `confirm_close` (Healer/Liq Sheriff),
        # its PnL is already in the DB. Skip ghost audit entirely.
        if getattr(found_pos, "_closure_recorded", False) or getattr(found_pos, "status", "") == "OFF_BOARDING":
            logger.info(f"⏭️ Skipping Ghost Audit for {trade_id} (Already Handled). Proceeding to cleanup.")
            self._unregister_all_aliases(found_pos)
            await self.finalize_removal(trade_id)
            return True

        # 1. GHOST AUDIT
        audit_fee = found_pos.entry_fee
        audit_pnl = 0.0
        audit_reason = "GHOST_REMOVAL"
        exit_price = found_pos.entry_price

        if self.adapter:
            try:
                logger.info(f"🕵️ Analyzing Ghost Position {trade_id} ({found_pos.symbol}) for residual costs...")
                # Fetch recent trades for this symbol (Phase 244: with strict 2.0s timeout to prevent execution cap stalls)
                try:
                    import asyncio

                    trades = await asyncio.wait_for(
                        self.adapter.fetch_my_trades(found_pos.symbol, limit=20), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Ghost Audit: fetch_my_trades timed out. Network may be unresponsive.")
                    trades = []

                # Match by trade_id
                relevant_trades = [
                    t
                    for t in trades
                    if str(t.get("order_id") or t.get("id")) == str(trade_id)
                    or str(t.get("order_id")) == str(found_pos.tp_order_id)
                    or str(t.get("order_id")) == str(found_pos.sl_order_id)
                ]

                if relevant_trades:
                    total_fee = sum(float((t.get("fee") or {}).get("cost", 0) or 0) for t in relevant_trades)
                    total_pnl = sum(float(t.get("realized_pnl", 0) or 0) for t in relevant_trades)
                    audit_fee += total_fee
                    audit_pnl = total_pnl
                    # Use avg price of trades if possible, else stick to current logic
                    if len(relevant_trades) > 0:
                        exit_price = sum(float(t.get("price", 0)) for t in relevant_trades) / len(relevant_trades)
                    logger.info(
                        f"✅ Ghost Audit Success: Found {len(relevant_trades)} trades. Fee={audit_fee:.4f}, PnL={audit_pnl:.4f}"
                    )
                else:
                    logger.warning(f"⚠️ Ghost Audit: No exchange trades found for {trade_id}. Using ticker fallback.")
                    try:
                        ticker_price = await self.adapter.get_current_price(found_pos.symbol)
                        exit_price = ticker_price
                        # Calculate estimated PnL: (Exit - Entry) * Qty * Direction
                        direction = 1 if found_pos.side.upper() in ["LONG", "BUY"] else -1
                        qty = found_pos.notional / found_pos.entry_price if found_pos.entry_price > 0 else 0
                        audit_pnl = (exit_price - found_pos.entry_price) * qty * direction
                        logger.info(
                            f"📊 Ghost Audit: Ticker Fallback Price: {exit_price:.4f} | Est. PnL: {audit_pnl:+.4f}"
                        )
                    except Exception as pe:
                        logger.warning(
                            f"⚠️ Ghost Audit: Could not get ticker for {found_pos.symbol}: {pe}. Using entry price."
                        )
            except Exception as e:
                # CRITICAL (Phase 77): If audit fails, do NOT remove the position.
                # We want to retry in the next reconciliation cycle instead of losing data.
                logger.error(f"❌ Ghost Audit Failed for {trade_id}: {e}. Keeping position in tracker for retry.")
                return False

        # 2. RECORD IN HISTORIAN
        historian.record_external_closure(
            symbol=found_pos.symbol,
            side=found_pos.side,
            qty=found_pos.notional / found_pos.entry_price if found_pos.entry_price > 0 else 0,
            entry_price=found_pos.entry_price,
            exit_price=exit_price,
            fee=audit_fee,
            funding=found_pos.funding_accrued,
            reason=audit_reason,
            session_id=self.session_id,
        )

        found_pos.exit_reason = audit_reason
        found_pos.realized_pnl = audit_pnl
        found_pos.bars_held = self._calculate_bars_held(found_pos)

        # LIFECYCLE ARCHITECTURE: Soft-Delete (Phase 48)
        found_pos.status = "OFF_BOARDING"

        # Unregister aliases
        self._unregister_all_aliases(found_pos)

        # Audit stats
        self.total_errors += 1
        self.total_trades_closed += 1

        # Phase 77: Ensure state is saved after marking as OFF_BOARDING
        self._trigger_state_change()

        return True

    async def finalize_removal(self, trade_id: str) -> bool:
        """Actual list removal called by GC."""
        found_pos = None
        for pos in self.open_positions:
            if pos.trade_id == trade_id:
                found_pos = pos
                break

        if not found_pos:
            return False

        self.open_positions.remove(found_pos)
        sym_norm = normalize_symbol(found_pos.symbol)
        if found_pos in self._symbol_map.get(sym_norm, []):
            self._symbol_map[sym_norm].remove(found_pos)

        logger.info(f"🧹 GC: Terminated OFF_BOARDING position {trade_id}")
        self._trigger_state_change()
        return True

    def _calculate_bars_held(self, position: OpenPosition) -> int:
        """Calculates holding time in bars (minutes)."""
        if not position.entry_timestamp:
            return 0
        try:
            val = float(position.entry_timestamp)
            if val > 10**11:
                val /= 1000.0  # ms to s
            held_seconds = time.time() - val
            return max(0, int(held_seconds / 60))
        except Exception:
            return 0

    # =========================================================
    # Phase 50: In-Flight Architecture Restoration
    # =========================================================

    def register_inflight_position(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        amount: float,
        notional: float,
        leverage: float,
        order_params: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> OpenPosition:
        """Optimistically registers a position before fill."""
        normalized_symbol = normalize_symbol(symbol)
        position = OpenPosition(
            trade_id=client_order_id,
            symbol=normalized_symbol,
            side=side,
            entry_price=0.0,
            entry_timestamp=str(int(time.time() * 1000)),
            timestamp=time.time(),
            margin_used=notional / leverage if leverage else 0,
            notional=notional,
            amount=amount,
            leverage=leverage,
            tp_level=0.0,
            sl_level=0.0,
            liquidation_level=None,
            order=order_params,
            main_order_id=client_order_id,
            status="OPENING",
            t0_signal_ts=order_params.get("t0_signal_ts"),  # Phase 85: Signal Latency
            t1_decision_ts=order_params.get("t1_decision_ts"),  # Phase 10: Decision Latency
            trace_id=trace_id or order_params.get("trace_id"),
            setup_type=order_params.get("setup_type") or order_params.get("params", {}).get("setup_type") or "unknown",
            entry_atr=float(order_params.get("atr_1m", 0.0)),
        )
        main_order_state = OrderState(
            client_order_id=client_order_id,
            order_type="MAIN",
            side=side,
            amount=amount,
            status="NEW",
            created_at=time.time(),
        )
        position.main_order = main_order_state
        self.register_alias(client_order_id, position, symbol=normalized_symbol)
        self.register_order(position, main_order_state)
        self.open_positions.append(position)
        self._symbol_map[normalized_symbol].append(position)
        if side == "LONG":
            self.new_longs += 1
        else:
            self.new_shorts += 1
        return position

    def register_inflight_bracket(
        self,
        position: OpenPosition,
        tp_client_id: str,
        sl_client_id: str,
    ) -> None:
        """
        Pre-registers TP/SL client_order_ids BEFORE sending orders to exchange.
        Ensures WS events for these orders can be matched even if they arrive
        before the HTTP response.

        Phase 52: Closes the race condition gap for bracket orders.
        """
        # Pre-register aliases for O(1) lookup when WS events arrive
        symbol = position.symbol
        self.register_alias(tp_client_id, position, symbol=symbol)
        self.register_alias(sl_client_id, position, symbol=symbol)
        logger.debug(f"📌 Pre-registered bracket aliases: TP={tp_client_id}, SL={sl_client_id} for {symbol}")

    def restore_state(self, positions: List[OpenPosition]) -> None:
        """
        Restores state from persistence and rehydrates internal indexes.
        Critical for preventing 'Amnesia' on restart.
        """
        self.open_positions.clear()
        self._alias_map.clear()
        self._symbol_map.clear()

        # Reset counters
        self.total_trades_opened = 0
        self.recovered_count = 0
        self.new_longs = 0
        self.new_shorts = 0

        for pos in positions:
            # 1. Add to main list
            self.open_positions.append(pos)

            # 2. Rehydrate Symbol Map (Critical for Reconciliation)
            # Use normalize_symbol to ensure consistency
            sym_norm = normalize_symbol(pos.symbol)
            self._symbol_map[sym_norm].append(pos)

            # 3. Rehydrate Alias Map (Critical for OCO/Updates) - Phase 80: Partitioned by Symbol
            self.register_alias(pos.trade_id, pos, symbol=sym_norm)

            # Re-register orders if they exist
            if pos.main_order:
                self.register_order(pos, pos.main_order)
            if pos.tp_order:
                self.register_order(pos, pos.tp_order)
            if pos.sl_order:
                self.register_order(pos, pos.sl_order)

            # Pre-register exchange IDs if we have them directly on pos object (legacy/hybrid)
            if pos.exchange_tp_id:
                self.register_alias(str(pos.exchange_tp_id), pos, symbol=sym_norm)
            if pos.exchange_sl_id:
                self.register_alias(str(pos.exchange_sl_id), pos, symbol=sym_norm)

            # Update counters
            self.total_trades_opened += 1
            self.recovered_count += 1
            if pos.side == "LONG":
                self.new_longs += 1
            else:
                self.new_shorts += 1

        logger.info(f"🧠 State Restored: Rehydrated {len(positions)} positions into memory.")

    def add_position(self, position: OpenPosition):
        """
        Manually inject a position (used for reconciliation/adoption).
        Updates blocked capital and tracking lists.
        """
        # 0. NORMALIZE SYMBOL
        position.symbol = normalize_symbol(position.symbol)

        # Check if already exists
        if self.get_position(position.trade_id):
            logger.warning(f"⚠️ Position {position.trade_id} already exists. Skipping add.")
            return

        self.open_positions.append(position)
        self.blocked_capital += position.margin_used

        # Phase 46.1: Ensure O(1) Symbol Map is updated for adopted positions
        sym_norm = position.symbol
        if position not in self._symbol_map[sym_norm]:
            self._symbol_map[sym_norm].append(position)
        # Increment opened counter to ensure 'Total Managed' is correct
        self.total_trades_opened += 1
        # Track specifically as recovered/adopted
        self.recovered_count += 1

        logger.info(f"🧬 Adopted position: {position.trade_id} | {position.symbol} {position.side}")

        # Index Re-hydration (Cures Internal Blindness during Recovery/Adoption)
        if position.tp_order:
            self.register_order(position, position.tp_order)
        if position.sl_order:
            self.register_order(position, position.sl_order)
        if position.main_order:
            self.register_order(position, position.main_order)

        self._trigger_state_change()

    # Phase 31: Legacy async handle_order_update REMOVED
    # PositionTracker.handle_order_update (sync, O(1) lookup) is now the single source of truth

    async def _cancel_opposite_order_safe(self, order_id: str, symbol: str):
        """Helper to cancel opposite order without blocking."""
        try:
            logger.debug(f"🧹 OCO: Attempting to cancel opposite order {order_id} for {symbol}")
            await self.adapter.cancel_order(order_id, symbol)
        except Exception as e:
            # Ignore "Unknown order" as it might be already filled/canceled
            if "Unknown order" not in str(e):
                logger.warning(f"⚠️ Failed to cancel opposite order {order_id}: {e}")

    async def _enrich_trade_with_rest(
        self,
        order_id: str,
        symbol: str,
        trade_id: str,
        exit_reason: str,
        fill_price: float,
        pnl_estimated: float,
    ):
        """
        Fetch authoritative trade details from REST API when WS data is incomplete.
        This provides the REAL fee and REAL PnL for the historian.
        """
        fee_real = 0.0
        pnl_real = pnl_estimated

        try:
            # Short delay to allow exchange to index the trade
            await asyncio.sleep(1.0)

            trades = await self.adapter.fetch_my_trades(symbol, limit=5)
            # Find the trade(s) corresponding to this order_id
            matched_trades = [t for t in trades if str(t.get("order") or t.get("orderId")) == str(order_id)]

            if matched_trades:
                total_fee = sum(float((t.get("fee") or {}).get("cost", 0) or 0) for t in matched_trades)
                # Recalculate PnL if we have precise fills
                # (Optional: for now we stick to estimated PnL but update Fee)
                fee_real = total_fee
                logger.info(f"✅ Enriched trade {order_id} with real fee: {fee_real:.4f} {symbol.split(':')[0]}")
            else:
                logger.warning(f"⚠️ Could not find trade {order_id} in REST history. Proceeding with 0.0 fee.")

        except Exception as e:
            logger.error(f"❌ Failed to enrich trade {order_id}: {e}")

        return fee_real, pnl_real
