"""
🔍 Diagnóstico de Sincronización - Casino V2
============================================

Script para medir desincronización entre estado interno y estado real del exchange.

Métricas:
- Balance diff: |internal - exchange|
- Equity diff: |internal - (exchange_balance + unrealized_pnl)|
- Position count diff: |internal - exchange|
- Unrealized PnL diff: |internal - exchange|

Uso:
    python utils/diagnose_sync.py

Requiere:
    - Credenciales de Kraken Demo en .env
    - Mesa configurada en config.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tables.ccxt_adapter import CCXTAdapter
from tables.connectors.kraken.kraken_connector import KrakenConnector

from core import config
from exchanges.adapters.exchange_state_sync import ExchangeStateSync

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DiagnoseSync")


class SyncDiagnostics:
    """Diagnóstico de sincronización entre estado interno y exchange."""

    def __init__(self, table: CCXTAdapter):
        self.table = table
        self.results: Dict[str, Any] = {}

    async def run_diagnostics(self) -> Dict[str, Any]:
        """
        Ejecuta diagnóstico completo.

        Returns:
            Dict con métricas de sincronización
        """
        logger.info("=" * 60)
        logger.info("🔍 DIAGNÓSTICO DE SINCRONIZACIÓN")
        logger.info("=" * 60)

        # 1. Obtener estado interno
        internal_state = self._get_internal_state()
        logger.info("\n📊 Estado Interno:")
        self._log_state(internal_state)

        # 2. Obtener estado del exchange
        exchange_state = await self._get_exchange_state()
        logger.info("\n📡 Estado del Exchange:")
        self._log_state(exchange_state)

        # 3. Calcular diferencias
        diffs = self._calculate_diffs(internal_state, exchange_state)
        logger.info("\n⚠️  Diferencias Detectadas:")
        self._log_diffs(diffs)

        # 4. Determinar estado de sincronización
        sync_status = self._determine_sync_status(diffs)
        logger.info(f"\n🎯 Estado de Sincronización: {sync_status}")

        # 5. Compilar resultados
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "internal_state": internal_state,
            "exchange_state": exchange_state,
            "diffs": diffs,
            "sync_status": sync_status,
            "recommendations": self._generate_recommendations(diffs),
        }

        logger.info("=" * 60)

        return self.results

    def _get_internal_state(self) -> Dict[str, Any]:
        """Obtiene estado interno de la mesa."""
        balance = self.table.balance_manager.get_balance()

        # Estado del PositionTracker
        position_tracker = self.table.position_tracker
        open_positions = len(position_tracker.open_positions)
        blocked_capital = position_tracker.blocked_capital

        # Calcular unrealized PnL interno (aproximado)
        unrealized_pnl_internal = 0.0
        if hasattr(self.table, "_last_candle") and self.table._last_candle:
            current_price = self.table._last_candle.get("close", 0)
            for pos in position_tracker.open_positions:
                if pos.side == "LONG":
                    pnl_pct = (current_price - pos.entry_price) / pos.entry_price
                else:
                    pnl_pct = (pos.entry_price - current_price) / pos.entry_price
                unrealized_pnl_internal += pos.notional * pnl_pct

        equity_internal = balance + unrealized_pnl_internal

        return {
            "balance": balance,
            "unrealized_pnl": unrealized_pnl_internal,
            "equity": equity_internal,
            "open_positions": open_positions,
            "blocked_capital": blocked_capital,
            "source": "internal_state",
        }

    async def _get_exchange_state(self) -> Dict[str, Any]:
        """Obtiene estado real del exchange."""
        try:
            # Balance del exchange
            balance_data = await self.table.connector.fetch_balance()

            # Extraer balance en USD/USDT
            free_balances = balance_data.get("free", {})
            balance_exchange = 0.0
            currency = "USD"

            for curr in ["USD", "USDT", "USDC"]:
                if curr in free_balances and free_balances[curr]:
                    balance_exchange = float(free_balances[curr])
                    currency = curr
                    break

            # Posiciones del exchange (normalized)
            try:
                sync = ExchangeStateSync(self.table.connector)
                positions_dt = await sync.sync_positions()
                positions = [p.__dict__ for p in positions_dt]
            except Exception:
                positions = await self.table.connector.fetch_positions()
            open_positions_exchange = len([p for p in positions if float(p.get("contracts", 0)) != 0])

            # Unrealized PnL del exchange
            unrealized_pnl_exchange = sum(float(p.get("unrealizedPnl", 0)) for p in positions)

            # Equity real
            equity_exchange = balance_exchange + unrealized_pnl_exchange

            # Margin usado
            margin_used = sum(float(p.get("initialMargin", 0)) for p in positions)

            return {
                "balance": balance_exchange,
                "unrealized_pnl": unrealized_pnl_exchange,
                "equity": equity_exchange,
                "open_positions": open_positions_exchange,
                "margin_used": margin_used,
                "currency": currency,
                "source": "exchange_confirmed",
            }

        except Exception as e:
            logger.error(f"❌ Error obteniendo estado del exchange: {e}")
            return {
                "balance": 0.0,
                "unrealized_pnl": 0.0,
                "equity": 0.0,
                "open_positions": 0,
                "margin_used": 0.0,
                "currency": "USD",
                "source": "exchange_error",
                "error": str(e),
            }

    def _calculate_diffs(self, internal: Dict[str, Any], exchange: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula diferencias entre estado interno y exchange."""
        balance_diff = abs(internal["balance"] - exchange["balance"])
        balance_diff_pct = (balance_diff / exchange["balance"] * 100) if exchange["balance"] > 0 else 0

        equity_diff = abs(internal["equity"] - exchange["equity"])
        equity_diff_pct = (equity_diff / exchange["equity"] * 100) if exchange["equity"] > 0 else 0

        unrealized_pnl_diff = abs(internal["unrealized_pnl"] - exchange["unrealized_pnl"])

        position_count_diff = abs(internal["open_positions"] - exchange["open_positions"])

        return {
            "balance_diff": balance_diff,
            "balance_diff_pct": balance_diff_pct,
            "equity_diff": equity_diff,
            "equity_diff_pct": equity_diff_pct,
            "unrealized_pnl_diff": unrealized_pnl_diff,
            "position_count_diff": position_count_diff,
        }

    def _determine_sync_status(self, diffs: Dict[str, Any]) -> str:
        """Determina estado de sincronización basado en diferencias."""
        # Thresholds
        BALANCE_THRESHOLD = 1.0  # 1%
        EQUITY_THRESHOLD = 1.0  # 1%
        POSITION_THRESHOLD = 0  # Debe ser exacto

        if (
            diffs["balance_diff_pct"] < BALANCE_THRESHOLD
            and diffs["equity_diff_pct"] < EQUITY_THRESHOLD
            and diffs["position_count_diff"] <= POSITION_THRESHOLD
        ):
            return "✅ SYNCED"
        elif diffs["balance_diff_pct"] < 5.0 and diffs["equity_diff_pct"] < 5.0:
            return "⚠️  PARTIALLY_SYNCED"
        else:
            return "❌ DESYNCED"

    def _generate_recommendations(self, diffs: Dict[str, Any]) -> list:
        """Genera recomendaciones basadas en diferencias."""
        recommendations = []

        if diffs["balance_diff_pct"] > 1.0:
            recommendations.append(
                "🔴 Balance desincronizado > 1%. " "Implementar sincronización periódica con fetch_balance()."
            )

        if diffs["equity_diff_pct"] > 1.0:
            recommendations.append(
                "🔴 Equity desincronizado > 1%. " "Calcular equity real: balance + unrealized_pnl del exchange."
            )

        if diffs["unrealized_pnl_diff"] > 10.0:
            recommendations.append(
                "🟠 Unrealized PnL difiere significativamente. "
                "Usar unrealized_pnl del exchange, no calculado con velas."
            )

        if diffs["position_count_diff"] > 0:
            recommendations.append(
                "🔴 Número de posiciones no coincide. "
                "Sincronizar PositionTracker con fetch_positions() del exchange."
            )

        if not recommendations:
            recommendations.append("✅ Estado bien sincronizado. Continuar monitoreando.")

        return recommendations

    def _log_state(self, state: Dict[str, Any]) -> None:
        """Log formateado de estado."""
        logger.info(f"  Balance:        {state['balance']:.2f} {state.get('currency', 'USD')}")
        logger.info(f"  Unrealized PnL: {state['unrealized_pnl']:+.2f}")
        logger.info(f"  Equity:         {state['equity']:.2f}")
        logger.info(f"  Open Positions: {state['open_positions']}")
        if "blocked_capital" in state:
            logger.info(f"  Blocked Capital: {state['blocked_capital']:.2f}")
        if "margin_used" in state:
            logger.info(f"  Margin Used:    {state['margin_used']:.2f}")
        logger.info(f"  Source:         {state['source']}")

    def _log_diffs(self, diffs: Dict[str, Any]) -> None:
        """Log formateado de diferencias."""
        logger.info(f"  Balance diff:     {diffs['balance_diff']:.2f} ({diffs['balance_diff_pct']:.2f}%)")
        logger.info(f"  Equity diff:      {diffs['equity_diff']:.2f} ({diffs['equity_diff_pct']:.2f}%)")
        logger.info(f"  Unrealized PnL diff: {diffs['unrealized_pnl_diff']:.2f}")
        logger.info(f"  Position count diff: {diffs['position_count_diff']}")

    def print_report(self) -> None:
        """Imprime reporte final."""
        if not self.results:
            logger.warning("No hay resultados para reportar. Ejecuta run_diagnostics() primero.")
            return

        logger.info("\n" + "=" * 60)
        logger.info("📋 REPORTE DE SINCRONIZACIÓN")
        logger.info("=" * 60)
        logger.info(f"\n🕐 Timestamp: {self.results['timestamp']}")
        logger.info(f"🎯 Estado: {self.results['sync_status']}")

        logger.info("\n📊 Diferencias:")
        diffs = self.results["diffs"]
        logger.info(f"  • Balance:     {diffs['balance_diff']:.2f} ({diffs['balance_diff_pct']:.2f}%)")
        logger.info(f"  • Equity:      {diffs['equity_diff']:.2f} ({diffs['equity_diff_pct']:.2f}%)")
        logger.info(f"  • Posiciones:  {diffs['position_count_diff']}")

        logger.info("\n💡 Recomendaciones:")
        for i, rec in enumerate(self.results["recommendations"], 1):
            logger.info(f"  {i}. {rec}")

        logger.info("=" * 60 + "\n")


async def main():
    """Función principal."""
    logger.info("🚀 Iniciando diagnóstico de sincronización...")

    # Configurar exchange
    exchange = getattr(config, "EXCHANGE", "KRAKEN_DEMO").upper()
    symbol = getattr(config, "KRAKEN_FUTURES_SYMBOL", "BTC/USD:USD")
    timeframe = getattr(config, "KRAKEN_FUTURES_INTERVAL", "1m")

    logger.info(f"Exchange: {exchange}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe}")

    # Crear conector
    connector = KrakenConnector(mode="testing")

    # Crear mesa
    table = CCXTAdapter(connector=connector, symbol=symbol, timeframe=timeframe)

    try:
        # Conectar
        logger.info("\n🔌 Conectando a Kraken Demo...")
        await table.connect()
        logger.info("✅ Conectado")

        # Ejecutar diagnóstico
        diagnostics = SyncDiagnostics(table)
        results = await diagnostics.run_diagnostics()

        # Imprimir reporte
        diagnostics.print_report()

        # Guardar resultados (opcional)
        import json

        output_file = project_root / "logs" / "sync_diagnostics.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"📁 Resultados guardados en: {output_file}")

    except Exception as e:
        logger.error(f"❌ Error durante diagnóstico: {e}", exc_info=True)
        return 1

    finally:
        # Cerrar conexión
        await table.close()
        logger.info("🔌 Conexión cerrada")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
