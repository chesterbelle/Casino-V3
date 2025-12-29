"""
🔄 Exchange State Synchronization - Casino V3
==============================================

Componente que sincroniza estado real del exchange con el sistema interno.

Responsabilidades:
- Obtener posiciones reales del exchange
- Obtener fills confirmados desde timestamp
- Calcular equity real (balance + unrealized PnL)
- Detectar eventos (TP/SL ejecutados)

Uso:
    sync = ExchangeStateSync(connector)
    equity = await sync.sync_equity()
    positions = await sync.sync_positions()
    fills = await sync.sync_fills(since=timestamp)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .exchange_adapter import ExchangeAdapter


@dataclass
class Position:
    """Posición abierta en el exchange."""

    symbol: str
    side: str  # "LONG" | "SHORT"
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    margin: float
    leverage: float
    liquidation_price: Optional[float]
    timestamp: int

    @property
    def is_long(self) -> bool:
        return self.side.upper() in ("LONG", "BUY")

    @property
    def is_short(self) -> bool:
        return self.side.upper() in ("SHORT", "SELL")


@dataclass
class Fill:
    """Fill confirmado del exchange."""

    trade_id: str
    order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    price: float  # ← PRECIO REAL
    amount: float
    cost: float
    fee: float
    fee_currency: str
    realized_pnl: float  # ← PNL REAL (si es cierre)
    is_close: bool
    reason: Optional[str]  # "TP" | "SL" | "MANUAL" | None
    timestamp: int
    datetime: str

    @property
    def is_buy(self) -> bool:
        return self.side.lower() == "buy"

    @property
    def is_sell(self) -> bool:
        return self.side.lower() == "sell"


@dataclass
class EquitySnapshot:
    """Snapshot de equity real del exchange."""

    balance: float  # Balance libre
    unrealized_pnl: float  # PnL no realizado
    equity: float  # balance + unrealized_pnl
    margin_used: float  # Margin bloqueado
    margin_available: float  # Margin disponible
    open_positions: int  # Número de posiciones abiertas
    timestamp: int
    currency: str

    @property
    def margin_ratio(self) -> float:
        """Ratio de margin usado vs equity."""
        return (self.margin_used / self.equity) if self.equity > 0 else 0.0

    @property
    def is_healthy(self) -> bool:
        """Verifica si el estado es saludable (margin ratio < 80%)."""
        return self.margin_ratio < 0.8


class ExchangeStateSync:
    """
    Sincronizador de estado real del exchange.

    Este componente es la fuente de verdad para:
    - Balance real
    - Equity real (balance + unrealized PnL)
    - Posiciones abiertas/cerradas
    - Fills confirmados

    Ejemplo:
        sync = ExchangeStateSync(connector)

        # Sincronizar equity
        equity = await sync.sync_equity()
        print(f"Equity real: {equity.equity:.2f}")

        # Obtener fills desde última sync
        fills = await sync.sync_fills()
        for fill in fills:
            if fill.is_close:
                print(f"Cierre confirmado: {fill.price:.2f}")
    """

    def __init__(self, adapter: "ExchangeAdapter"):
        """
        Initialize ExchangeStateSync.

        Args:
            adapter: ExchangeAdapter instance
        """
        self.adapter = adapter
        self.connector = adapter.connector
        self.logger = logging.getLogger("ExchangeStateSync")

        # Tracking de última sincronización
        self.last_sync_time = 0
        self.last_equity_snapshot: Optional[EquitySnapshot] = None
        self.last_positions: List[Position] = []

        # Cache para optimizar llamadas
        self._cache_ttl = 1000  # 1 segundo en ms
        self._cached_equity: Optional[EquitySnapshot] = None
        self._cache_timestamp = 0

        self.logger.info("ExchangeStateSync inicializado")

    async def sync_positions(self) -> List[Position]:
        """
        Obtiene posiciones reales del exchange.

        Returns:
            Lista de posiciones abiertas

        Raises:
            RuntimeError: Si el connector no está conectado
            Exception: Si hay error en la comunicación con el exchange
        """
        try:
            raw_positions = await self.connector.fetch_positions()

            positions = []
            for raw_pos in raw_positions:
                # Filtrar posiciones cerradas (size == 0)
                size = float(raw_pos.get("contracts", 0) or raw_pos.get("size", 0))
                if size == 0:
                    continue

                position = self._normalize_position(raw_pos)
                positions.append(position)

            self.last_positions = positions
            self.logger.debug(f"Sincronizadas {len(positions)} posiciones del exchange")

            return positions

        except Exception as e:
            self.logger.error(f"❌ Error sincronizando posiciones: {e}")
            raise

    async def sync_fills(self, since: Optional[int] = None) -> List[Fill]:
        """
        Obtiene fills confirmados desde timestamp.

        Args:
            since: Timestamp en ms (opcional). Si None, usa last_sync_time

        Returns:
            Lista de fills confirmados

        Raises:
            RuntimeError: Si el connector no está conectado
            Exception: Si hay error en la comunicación con el exchange
        """
        since = since or self.last_sync_time

        try:
            # Obtener trades del usuario
            raw_trades = await self.connector.fetch_my_trades(since=since)

            fills = []
            for raw_trade in raw_trades:
                fill = self._normalize_fill(raw_trade)
                fills.append(fill)

            # Actualizar timestamp de última sync
            if fills:
                self.last_sync_time = max(fill.timestamp for fill in fills)
            else:
                self.last_sync_time = int(time.time() * 1000)

            self.logger.debug(f"Sincronizados {len(fills)} fills desde {since}")

            return fills

        except Exception as e:
            self.logger.error(f"❌ Error sincronizando fills: {e}")
            raise

    async def sync_equity(self, use_cache: bool = True) -> EquitySnapshot:
        """
        Calcula equity real: balance + unrealized PnL.

        Args:
            use_cache: Si True, usa cache si está fresco (< 1s)

        Returns:
            EquitySnapshot con estado completo

        Raises:
            RuntimeError: Si el connector no está conectado
            Exception: Si hay error en la comunicación con el exchange
        """
        # Check cache
        now = int(time.time() * 1000)
        if use_cache and self._cached_equity and (now - self._cache_timestamp) < self._cache_ttl:
            return self._cached_equity

        try:
            # 1. Obtener balance
            balance_data = await self.connector.fetch_balance()

            # 2. Obtener posiciones
            positions = await self.sync_positions()

            # 3. Extraer balance en moneda base
            free_balances = balance_data.get("free", {})
            balance = 0.0
            currency = "USD"

            # Priorizar USD, USDT, USDC
            for curr in ["USD", "USDT", "USDC"]:
                if curr in free_balances and free_balances[curr]:
                    balance = float(free_balances[curr])
                    currency = curr
                    break

            # Si no hay balance en esas monedas, buscar cualquier balance positivo
            if balance == 0:
                for curr, value in free_balances.items():
                    if value and float(value) > 0:
                        balance = float(value)
                        currency = curr
                        break

            # 4. Calcular unrealized PnL y margin
            unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            margin_used = sum(pos.margin for pos in positions)

            # 5. Calcular equity y margin disponible
            equity = balance + unrealized_pnl
            margin_available = balance - margin_used

            # 6. Crear snapshot
            snapshot = EquitySnapshot(
                balance=balance,
                unrealized_pnl=unrealized_pnl,
                equity=equity,
                margin_used=margin_used,
                margin_available=margin_available,
                open_positions=len(positions),
                timestamp=now,
                currency=currency,
            )

            # 7. Actualizar cache
            self._cached_equity = snapshot
            self._cache_timestamp = now
            self.last_equity_snapshot = snapshot

            self.logger.debug(
                f"Equity sincronizado: {equity:.2f} {currency} "
                f"(balance: {balance:.2f}, unrealized: {unrealized_pnl:+.2f})"
            )

            return snapshot

        except Exception as e:
            self.logger.error(f"❌ Error sincronizando equity: {e}")
            raise

    def _normalize_position(self, raw_pos: Dict[str, Any]) -> Position:
        """Normaliza posición del exchange a formato interno."""
        # Determinar side
        side_raw = raw_pos.get("side", "").upper()
        if side_raw in ("LONG", "BUY"):
            side = "LONG"
        elif side_raw in ("SHORT", "SELL"):
            side = "SHORT"
        else:
            # Inferir de contracts/size
            contracts = float(raw_pos.get("contracts", 0))
            side = "LONG" if contracts > 0 else "SHORT"

        return Position(
            symbol=raw_pos.get("symbol", ""),
            side=side,
            size=abs(float(raw_pos.get("contracts", 0) or raw_pos.get("size", 0))),
            entry_price=float(raw_pos.get("entryPrice", 0)),
            mark_price=float(raw_pos.get("markPrice", 0)),
            unrealized_pnl=float(raw_pos.get("unrealizedPnl", 0)),
            margin=float(raw_pos.get("initialMargin", 0)),
            leverage=float(raw_pos.get("leverage", 1)),
            liquidation_price=float(raw_pos.get("liquidationPrice", 0)) if raw_pos.get("liquidationPrice") else None,
            timestamp=raw_pos.get("timestamp", int(time.time() * 1000)),
        )

    def normalize_position(self, raw_pos: Dict[str, Any]) -> Position:
        """Public helper to normalize a raw position (dict) into a Position dataclass.

        This is useful for callers that fetch raw positions from connectors and
        need a canonical representation.
        """
        return self._normalize_position(raw_pos)

    def _normalize_fill(self, raw_trade: Dict[str, Any]) -> Fill:
        """
        Normaliza fill del exchange a formato interno usando campos estándar CCXT.

        ExchangeStateSync es completamente agnóstico - solo usa campos estándar.
        La normalización específica del exchange se maneja en capas superiores.
        """
        # Usar solo campos estándar de CCXT (agnóstico)
        is_close = False  # Por defecto, no es cierre
        realized_pnl = 0.0  # Por defecto, no hay PnL realizado
        reason = None  # Por defecto, no hay razón específica

        # Detectar cierres usando lógica agnóstica básica
        # (La lógica específica se maneja en CCXTAdapter/Connector)

        # Extraer fee
        fee_data = raw_trade.get("fee", {})
        if isinstance(fee_data, dict):
            fee = float(fee_data.get("cost", 0))
            fee_currency = fee_data.get("currency", "USD")
        else:
            fee = float(fee_data) if fee_data else 0.0
            fee_currency = "USD"

        return Fill(
            trade_id=str(raw_trade.get("id", "")),
            order_id=str(raw_trade.get("order", "")),
            symbol=raw_trade.get("symbol", ""),
            side=raw_trade.get("side", "").lower(),
            price=float(raw_trade.get("price", 0)),
            amount=float(raw_trade.get("amount", 0)),
            cost=float(raw_trade.get("cost", 0)),
            fee=fee,
            fee_currency=fee_currency,
            realized_pnl=realized_pnl,
            is_close=is_close,
            reason=reason,
            timestamp=raw_trade.get("timestamp", int(time.time() * 1000)),
            datetime=raw_trade.get("datetime", ""),
        )

    def get_last_equity(self) -> Optional[EquitySnapshot]:
        """Retorna último snapshot de equity (sin hacer nueva llamada)."""
        return self.last_equity_snapshot

    def get_last_positions(self) -> List[Position]:
        """Retorna últimas posiciones sincronizadas (sin hacer nueva llamada)."""
        return self.last_positions

    def clear_cache(self) -> None:
        """Limpia cache de equity."""
        self._cached_equity = None
        self._cache_timestamp = 0
        self.logger.debug("Cache de equity limpiado")
