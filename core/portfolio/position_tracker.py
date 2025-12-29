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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from exchanges.adapters import ExchangeAdapter

import config.trading
from utils.symbol_norm import normalize_symbol

logger = logging.getLogger("PositionTracker")


@dataclass
class OpenPosition:
    """Representa una posición abierta con TP/SL pendientes."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    entry_timestamp: str
    margin_used: float
    notional: float
    leverage: float
    tp_level: float
    sl_level: float
    liquidation_level: Optional[float]
    order: Dict[str, Any]
    main_order_id: Optional[str] = None  # ID de la orden principal (MARKET/LIMIT)
    tp_order_id: Optional[str] = None  # ID de la orden TP (TAKE_PROFIT_MARKET)
    sl_order_id: Optional[str] = None  # ID de la orden SL (STOP_MARKET)
    bars_held: int = 0
    funding_accrued: float = 0.0
    contributors: List[str] = None  # Sensores que contribuyeron a la señal

    # State Machine Status
    # OPENING: In process of creating TP/SL orders (Audit should wait)
    # ACTIVE: Fully established with TP/SL (Audit should enforce)
    # CLOSING: In process of closing (Audit should wait)
    status: str = "ACTIVE"


class PositionTracker:
    """
    Manages open positions with real-time WebSocket confirmation.

    Casino V3 Architecture:
    -----------------------
    Positions are tracked with capital blocking and confirmed via WebSocket events:

    1. Position opened → Capital blocked
    2. TP/SL orders placed on exchange
    3. WebSocket monitors order fills
    4. On fill → confirm_close() called → Capital released

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
        max_concurrent_positions: int = 10,
        adapter: Optional["ExchangeAdapter"] = None,
        on_close_callback: Optional[callable] = None,
    ):
        """
        Args:
            max_concurrent_positions: Máximo número de posiciones simultáneas permitidas
            adapter: ExchangeAdapter para cancelar órdenes OCO (agnóstico del conector)
        """
        self.open_positions: List[OpenPosition] = []
        self.blocked_capital: float = 0.0
        self.max_concurrent_positions = max_concurrent_positions
        self.adapter = adapter  # For OCO cancellation
        self.on_close_callback = on_close_callback
        # Callback for immediate state persistence
        self.state_change_callback: Optional[Callable[[], Awaitable[None]]] = None
        self._background_tasks = set()  # Prevent GC of fire-and-forget tasks
        self.total_trades_opened = 0
        self.total_trades_closed = 0
        self.total_wins = 0  # Track wins
        self.total_losses = 0  # Track losses
        self.total_errors = 0  # Track errors/forced closes
        self.total_timeouts = 0  # Track timeouts

        # Granular Session Counters (New vs Recovered)
        self.recovered_count = 0
        self.new_longs = 0
        self.new_shorts = 0
        # History of closed trades for detailed reporting
        self.history: List[Dict[str, Any]] = []

        # Tracking de confirmaciones pendientes
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}

        logger.info(f"PositionTracker inicializado | Max positions: {max_concurrent_positions}")

    def set_state_change_callback(self, callback: Callable[[], Awaitable[None]]):
        """Register callback for immediate state persistence."""
        self.state_change_callback = callback

    def _trigger_state_change(self):
        """Trigger state save if callback is registered."""
        if self.state_change_callback:
            task = asyncio.create_task(self.state_change_callback())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def get_available_equity(self, total_equity: float) -> float:
        """Calcula capital disponible (total - bloqueado)."""
        return max(0.0, total_equity - self.blocked_capital)

    def get_position(self, trade_id: str) -> Optional["OpenPosition"]:
        """Busca una posición por trade_id."""
        for position in self.open_positions:
            if position.trade_id == trade_id:
                return position
        return None

    def can_open_position(self, required_margin: float, available_equity: float) -> bool:
        """
        Verifica si se puede abrir una nueva posición.

        Args:
            required_margin: Margen requerido para la nueva posición
            available_equity: Capital disponible actualmente

        Returns:
            True si se puede abrir la posición
        """
        # Verificar límite de posiciones concurrentes
        if len(self.open_positions) >= self.max_concurrent_positions:
            return False

        # Verificar capital disponible
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
    ) -> Optional[OpenPosition]:
        """
        Abre una nueva posición y la registra.
        """

        try:
            side_raw = order.get("side", "")
            side = self._normalize_side(side_raw)
            symbol = order.get("symbol", "")
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

            # Calcular niveles de TP/SL
            tp_raw = order.get("take_profit", config.trading.TAKE_PROFIT)
            sl_raw = order.get("stop_loss", config.trading.STOP_LOSS)

            # Normalizar a multiplicadores si vienen como porcentajes (ej: 0.01 -> 1.01)
            # Asumimos que si el valor es < 0.5, es un porcentaje
            if tp_raw < 0.5:
                tp_mult_long = 1.0 + tp_raw
                tp_mult_short = 1.0 - tp_raw
            else:
                tp_mult_long = tp_raw
                tp_mult_short = tp_raw

            if sl_raw < 0.5:
                sl_mult_long = 1.0 - sl_raw
                sl_mult_short = 1.0 + sl_raw
            else:
                sl_mult_long = sl_raw
                sl_mult_short = sl_raw

            if side == "LONG":
                tp_level = entry_price * tp_mult_long
                sl_level = entry_price * sl_mult_long
                liquidation_level = entry_price * (1.0 - (1.0 / leverage) + 0.005)
            elif side == "SHORT":
                # Para SHORT, el TP debe ser menor al entry (ej: 0.99)
                # Si recibimos 1.01 (formato LONG), lo invertimos: 2.0 - 1.01 = 0.99
                if tp_mult_short > 1.0:
                    tp_level = entry_price * (2.0 - tp_mult_short)
                else:
                    tp_level = entry_price * tp_mult_short

                # Para SL, debe ser mayor al entry (ej: 1.01)
                # Si recibimos 0.99 (formato LONG), lo invertimos: 2.0 - 0.99 = 1.01
                if sl_mult_short < 1.0:
                    sl_level = entry_price * (2.0 - sl_mult_short)
                else:
                    sl_level = entry_price * sl_mult_short

                liquidation_level = entry_price * (1.0 + (1.0 / leverage) - 0.005)
            else:
                return None

            # Crear posición
            position = OpenPosition(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                entry_timestamp=entry_timestamp,
                margin_used=margin_used,
                notional=notional,
                leverage=leverage,
                tp_level=tp_level,
                sl_level=sl_level,
                liquidation_level=liquidation_level,
                order=order.copy(),
                main_order_id=main_order_id,
                tp_order_id=tp_order_id,
                sl_order_id=sl_order_id,
                contributors=order.get("contributors", []),
            )

            # Registrar posición
            self.open_positions.append(position)
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
            if position.symbol != current_candle.get("symbol"):
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

            # Time-Based Exit Check (Optimization Alignment)
            # If no TP/SL hit and max bars exceeded, close at market (current close)
            if not exit_reason and position.bars_held >= config.trading.MAX_HOLD_BARS:
                exit_reason = "TIME_EXIT"
                exit_price = float(current_candle.get("close", 0))
                logger.info(
                    f"⏳ Time Limit Reached for {position.trade_id} ({position.bars_held} bars). Closing at {exit_price}"
                )

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
        self, trade_id: str, exit_price: float, exit_reason: str, pnl: float, fee: float = 0.0
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

        Returns:
            Confirmed close result or None if position not found
        """
        # Buscar posición
        position = None
        for pos in self.open_positions:
            if pos.trade_id == trade_id:
                position = pos
                break

        if not position:
            logger.warning(f"⚠️ No se encontró posición para confirmar: {trade_id}")
            return None

        # Crear resultado CONFIRMADO con datos REALES
        result = {
            "trade_id": trade_id,
            "result": "WIN" if pnl > 0 else "LOSS",
            "pnl": pnl,  # ← PNL REAL
            "pnl_pct": pnl / position.notional if position.notional > 0 else 0.0,
            "fee": fee,  # ← FEE REAL
            "funding": position.funding_accrued,
            "liquidated": exit_reason == "LIQUIDATION",
            "margin_used": position.margin_used,
            "notional": position.notional,
            "leverage": position.leverage,
            "symbol": position.symbol,
            "entry_price": position.entry_price,
            "exit_price": exit_price,  # ← PRECIO REAL
            "trigger_price": exit_price,
            "bars_held": position.bars_held,
            "exit_reason": exit_reason,  # ← CONFIRMADO
            "side": position.side,
            "action": "CLOSE",
            "ghost": False,
            "confirmed": True,  # ← FLAG CRÍTICO
            "state_source": "exchange_confirmed",
            "contributors": position.contributors,
        }

        # Remover de pending si estaba
        if trade_id in self.pending_confirmations:
            del self.pending_confirmations[trade_id]

        # Remover posición
        self.open_positions.remove(position)

        # Liberar capital bloqueado
        self.blocked_capital -= position.margin_used
        self.total_trades_closed += 1

        # Track wins/losses based on PnL (positive = win, negative/zero = loss)
        # Any exit that makes money is a win, regardless of exit reason
        if exit_reason in ["ERROR", "FORCED_CLOSE", "CLI_FORCE_CLOSE", "SAFETY_CLOSE"]:
            self.total_errors += 1
        elif exit_reason in ["TIMEOUT", "TIME_EXIT"]:
            self.total_timeouts += 1
        elif pnl > 0:
            self.total_wins += 1
        else:
            self.total_losses += 1

        # Add to history
        self.history.append(result)

        logger.info(
            f"✅ CONFIRMED CLOSE | {position.symbol} {position.side} | "
            f"Exit: {exit_price:.2f} ({exit_reason}) | "
            f"PnL REAL: {pnl:+.2f} | Fee: {fee:.2f} | Bars: {position.bars_held}"
        )

        # Notificar a Gemini (o cualquier otro listener) sobre el resultado
        if self.on_close_callback:
            try:
                self.on_close_callback(trade_id, result)
            except Exception as e:
                logger.error(f"Error en callback on_close_callback: {e}")

            except Exception as e:
                logger.error(f"Error en callback on_close_callback: {e}")

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
            "max_concurrent": self.max_concurrent_positions,
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
            }

            closed_results.append(result)
            self.blocked_capital -= position.margin_used
            self.total_trades_closed += 1

            logger.info(
                f"🔒 FORCE CLOSE | {position.symbol} {position.side} | "
                f"Exit: {close_price:.2f} (FORCED) | "
                f"P&L: {pnl_value:+.2f} ({pnl_pct:.2%}) | Bars: {position.bars_held}"
            )

        self.open_positions.clear()
        self._trigger_state_change()
        return closed_results

    def remove_position(self, trade_id: str) -> bool:
        """
        Remove a position silently (used for reconciliation/cleanup).
        Releases blocked capital but does NOT record stats/history.
        """
        for pos in self.open_positions:
            if pos.trade_id == trade_id:
                self.open_positions.remove(pos)
                self.blocked_capital -= pos.margin_used
                # Cleanup pending confirmations if any
                if trade_id in self.pending_confirmations:
                    del self.pending_confirmations[trade_id]
                logger.warning(f"👻 Removed ghost position: {trade_id}")
                # Count as error so stats balance (Opened = Active + Closed/Error)
                self.total_errors += 1
                self.total_trades_closed += 1
                self._trigger_state_change()
                return True
        return False

    def add_position(self, position: OpenPosition):
        """
        Manually inject a position (used for reconciliation/adoption).
        Updates blocked capital and tracking lists.
        """
        # 0. NORMALIZE SYMBOL
        position.symbol = normalize_symbol(position.symbol)
        self.open_positions.append(position)
        self.blocked_capital += position.margin_used
        # Increment opened counter to ensure 'Total Managed' is correct
        self.total_trades_opened += 1
        # Track specifically as recovered/adopted
        self.recovered_count += 1

        logger.info(f"🧬 Adopted position: {position.trade_id} | {position.symbol} {position.side}")
        self._trigger_state_change()

    async def handle_order_update(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle order update from exchange (VirtualExchange or Binance WebSocket).

        When a TP or SL order fills, this method finds the corresponding position,
        calls confirm_close to properly record the win/loss, and CANCELS the opposite order.

        Args:
            order: Normalized order dict with 'id', 'status', 'price', etc.

        Returns:
            Close result if a position was closed, None otherwise
        """
        order_id = str(order.get("id") or order.get("order_id", ""))
        status = order.get("status", "").lower()

        # Only process filled orders (closed = filled in our normalization)
        if status not in ["closed", "filled"]:
            return None

        # Find position by TP or SL order ID
        position = None
        exit_reason = None
        opposite_order_id = None

        for pos in self.open_positions:
            if pos.tp_order_id == order_id:
                position = pos
                exit_reason = "TP"
                opposite_order_id = pos.sl_order_id  # Cancel SL when TP fills
                break
            elif pos.sl_order_id == order_id:
                position = pos
                exit_reason = "SL"
                opposite_order_id = pos.tp_order_id  # Cancel TP when SL fills
                break

        if not position:
            # Not a TP/SL order, might be a main order - ignore
            return None

        # Extract fill price
        fill_price = float(order.get("price", 0) or 0)
        if fill_price <= 0:
            fill_price = float(order.get("average", 0) or order.get("avgPrice", 0) or 0)

        if fill_price <= 0:
            logger.warning(f"⚠️ Cannot get fill price for order {order_id}")
            return None

        # Calculate PnL (Use amount * price_diff for accuracy)
        # PnL = (Exit - Entry) * Amount * Direction
        price_diff = fill_price - position.entry_price
        direction = 1 if position.side == "LONG" else -1

        # Use amount if available (robustness against notional=0 bug)
        amount_to_use = 0.0
        if position.order and "amount" in position.order:
            amount_to_use = float(position.order["amount"])
        elif position.notional > 0 and position.entry_price > 0:
            amount_to_use = position.notional / position.entry_price

        pnl_value = price_diff * amount_to_use * direction

        # Get fee from order (if available)
        fee = 0.0
        fee_info = order.get("fee", {})
        if isinstance(fee_info, dict):
            fee = float(fee_info.get("cost", 0) or 0)

        logger.info(
            f"📬 Order Update | {order_id} {exit_reason} filled @ {fill_price:.2f} | " f"Position: {position.trade_id}"
        )

        # Store symbol before confirm_close removes position
        symbol = position.symbol

        # Confirm the close
        result = self.confirm_close(
            trade_id=position.trade_id,
            exit_price=fill_price,
            exit_reason=exit_reason,
            pnl=pnl_value,
            fee=fee,
        )

        # Cancel the opposite order (OCO behavior)
        if opposite_order_id and self.adapter:
            try:
                await self.adapter.cancel_order(opposite_order_id, symbol)
                logger.info(
                    f"✅ Cancelled opposite {('SL' if exit_reason == 'TP' else 'TP')} order: {opposite_order_id}"
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to cancel opposite order {opposite_order_id}: {e}")

        return result
