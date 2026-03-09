"""
Test de Posiciones Concurrentes - Validación Crítica
-----------------------------------------------------
Verifica que al cerrar una posición, las otras posiciones concurrentes
permanecen abiertas con sus TP/SL intactos.

Escenario:
1. Abre 2 posiciones LONG simultáneamente
2. Posición 1: TP/SL ajustados (0.3%) - se cerrará rápido
3. Posición 2: TP/SL amplios (5%) - quedará abierta
4. Espera a que Posición 1 se cierre por TP/SL
5. Verifica que Posición 2 sigue abierta con TP/SL intactos

Uso:
    python -m utils.test_concurrent_positions --exchange=binance --symbol=LTCUSDT --mode=demo
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from croupier.croupier import Croupier
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors import ResilientConnector
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/concurrent_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
    )


logger = logging.getLogger("ConcurrentPositionsTest")


class ConcurrentPositionsTest:
    def __init__(self, exchange_id="binance", symbol="LTCUSDT", mode="demo"):
        self.exchange_name = exchange_id
        self.symbol = symbol
        self.mode = mode

        # Load API keys
        if self.exchange_name == "binance":
            if self.mode == "demo":
                api_key = os.getenv("BINANCE_TESTNET_API_KEY")
                secret = os.getenv("BINANCE_TESTNET_SECRET")
            else:
                api_key = os.getenv("BINANCE_API_KEY")
                secret = os.getenv("BINANCE_API_SECRET")

            if not api_key or not secret:
                raise ValueError(f"Missing API keys for mode {self.mode}")

            self.api_key = api_key
            self.secret = secret

    async def setup(self):
        logger.info(f"--- Configurando Test de Posiciones Concurrentes ---")

        base_connector = BinanceNativeConnector(
            api_key=self.api_key, secret=self.secret, mode=self.mode, enable_websocket=True
        )

        self.connector = ResilientConnector(connector=base_connector)
        await self.connector.connect()

        self.adapter = ExchangeAdapter(self.connector, self.symbol)

        balance_data = await self.connector.fetch_balance()
        initial_balance = balance_data.get("free", {}).get("USDT", 0.0)

        if initial_balance <= 10:
            raise ValueError(f"Balance insuficiente: ${initial_balance:.2f}")

        logger.info(f"Balance: ${initial_balance:,.2f}")

        self.croupier = Croupier(exchange_adapter=self.adapter, initial_balance=initial_balance)

        # Cleanup inicial
        await self.cleanup(post_test=False)

    async def cleanup(self, post_test=True):
        """Limpia todas las posiciones y órdenes"""
        logger.info("🧹 Limpiando estado...")

        try:
            # Cerrar posiciones
            if hasattr(self, "croupier") and self.croupier:
                exchange_positions = await self.croupier.state_sync.sync_positions()
                symbol_positions = [p for p in exchange_positions if p.symbol == self.symbol]

                for pos in symbol_positions:
                    try:
                        side = "sell" if pos.is_long else "buy"
                        position_side = "LONG" if pos.is_long else "SHORT"
                        await self.connector.create_order(
                            symbol=self.symbol,
                            order_type="market",
                            side=side,
                            amount=abs(pos.size),
                            params={"positionSide": position_side},
                        )
                        logger.info(f"🔨 Posición {pos.side} cerrada")
                    except Exception as e:
                        logger.warning(f"⚠️ Error cerrando posición: {e}")

            # Cancelar órdenes
            try:
                open_orders = await self.connector.fetch_open_orders(self.symbol)
                for order in open_orders:
                    try:
                        await self.connector.cancel_order(order["id"], self.symbol)
                        logger.info(f"❌ Orden {order['id']} cancelada")
                    except Exception as e:
                        logger.warning(f"⚠️ Error cancelando orden: {e}")
            except Exception as e:
                logger.warning(f"⚠️ Error obteniendo órdenes: {e}")

            await asyncio.sleep(3)
            logger.info("✅ Limpieza completada")

            if post_test:
                await self.adapter.disconnect()
                logger.info("✅ Conexión cerrada")
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"⚠️ Error en cleanup: {e}")

    async def run_test(self):
        """Ejecuta el test de posiciones concurrentes"""
        logger.info("=" * 80)
        logger.info("TEST: Posiciones Concurrentes con TP/SL Diferentes")
        logger.info("=" * 80)

        await self.setup()

        # Phase 800: Fetch current price for absolute TP/SL computation
        current_price = await self.adapter.get_current_price(self.symbol)
        logger.info(f"📊 Current price: {current_price:.2f}")

        # 1. Crear Posición 1 (TP/SL ajustados - 0.3%)
        logger.info("\n--- PASO 1: Crear Posición 1 (TP/SL ajustados 0.3%) ---")
        position1 = {
            "symbol": self.symbol,
            "side": "LONG",
            "size": 0.01,
            "tp_price": current_price * 1.003,  # +0.3%
            "sl_price": current_price * 0.997,  # -0.3%
            "leverage": 5,
            "trade_id": "concurrent_pos1_tight",
        }

        result1 = await self.croupier.execute_order(position1)
        logger.info(f"✅ Posición 1 creada: {result1.get('main_order_id')}")
        logger.info(f"   TP: {result1.get('tp_order_id')} | SL: {result1.get('sl_order_id')}")

        # 2. Crear Posición 2 (TP/SL amplios - 5%)
        logger.info("\n--- PASO 2: Crear Posición 2 (TP/SL amplios 5%) ---")
        position2 = {
            "symbol": self.symbol,
            "side": "LONG",
            "size": 0.01,
            "tp_price": current_price * 1.05,  # +5%
            "sl_price": current_price * 0.95,  # -5%
            "leverage": 5,
            "trade_id": "concurrent_pos2_wide",
        }

        result2 = await self.croupier.execute_order(position2)
        logger.info(f"✅ Posición 2 creada: {result2.get('main_order_id')}")
        logger.info(f"   TP: {result2.get('tp_order_id')} | SL: {result2.get('sl_order_id')}")

        # Guardar IDs para verificación
        pos1_tp = result1.get("tp_order_id")
        pos1_sl = result1.get("sl_order_id")
        pos2_tp = result2.get("tp_order_id")
        pos2_sl = result2.get("sl_order_id")

        # 3. Verificar que ambas posiciones están abiertas
        logger.info("\n--- PASO 3: Verificar ambas posiciones abiertas ---")
        open_positions = self.croupier.get_open_positions()
        assert len(open_positions) == 2, f"Deberían haber 2 posiciones, encontradas: {len(open_positions)}"
        logger.info(f"✅ Confirmado: 2 posiciones abiertas")

        # 4. Monitorear hasta que Posición 1 se cierre
        logger.info("\n--- PASO 4: Esperando cierre de Posición 1 (TP/SL ajustados) ---")
        logger.info("Monitoreando cada 5 segundos... (máximo 24h)")

        max_iterations = 17280  # 24 horas
        for i in range(max_iterations):
            await asyncio.sleep(5)
            await self.croupier.monitor_positions()

            open_positions = self.croupier.get_open_positions()

            if i % 12 == 0:  # Log cada minuto
                logger.info(f"[{i*5//60}min] Posiciones abiertas: {len(open_positions)}")

            # Si solo queda 1 posición, Posición 1 se cerró
            if len(open_positions) == 1:
                logger.info(f"\n🎯 ¡Posición 1 cerrada! Tiempo: {i*5} segundos")
                break
        else:
            logger.warning("⚠️ Timeout alcanzado (24h) sin cierre de Posición 1")
            await self.cleanup()
            return

        # 5. Verificar que Posición 2 sigue abierta
        logger.info("\n--- PASO 5: Verificar Posición 2 sigue abierta ---")
        open_positions = self.croupier.get_open_positions()

        assert len(open_positions) == 1, f"Debería quedar 1 posición, encontradas: {len(open_positions)}"
        remaining_pos = open_positions[0]

        assert (
            remaining_pos.trade_id == "concurrent_pos2_wide"
        ), f"La posición restante debería ser pos2, pero es: {remaining_pos.trade_id}"

        logger.info(f"✅ Posición 2 sigue abierta: {remaining_pos.trade_id}")
        logger.info(f"   TP: {remaining_pos.tp_order_id} | SL: {remaining_pos.sl_order_id}")

        # 6. Verificar que TP/SL de Posición 2 siguen activos
        logger.info("\n--- PASO 6: Verificar TP/SL de Posición 2 siguen activos ---")
        open_orders = await self.connector.fetch_open_orders(self.symbol)
        order_ids = [o["id"] for o in open_orders]

        # TP/SL de Posición 1 NO deberían estar
        assert pos1_tp not in order_ids, f"TP de Posición 1 debería estar cancelado"
        assert pos1_sl not in order_ids, f"SL de Posición 1 debería estar cancelado"
        logger.info(f"✅ TP/SL de Posición 1 cancelados correctamente")

        # TP/SL de Posición 2 SÍ deberían estar
        assert pos2_tp in order_ids, f"TP de Posición 2 debería seguir activo"
        assert pos2_sl in order_ids, f"SL de Posición 2 debería seguir activo"
        logger.info(f"✅ TP/SL de Posición 2 siguen activos")

        # 7. Resumen final
        logger.info("\n" + "=" * 80)
        logger.info("✅ TEST EXITOSO: Posiciones Concurrentes")
        logger.info("=" * 80)
        logger.info("Resultados:")
        logger.info(f"  ✅ Posición 1 (TP/SL 0.3%) se cerró automáticamente")
        logger.info(f"  ✅ Posición 2 (TP/SL 5%) permanece abierta")
        logger.info(f"  ✅ TP/SL de Posición 1 cancelados")
        logger.info(f"  ✅ TP/SL de Posición 2 intactos")
        logger.info(f"  ✅ Sistema maneja correctamente posiciones concurrentes")
        logger.info("=" * 80)

        # Cleanup final
        await self.cleanup()


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Test de Posiciones Concurrentes")
    parser.add_argument("--exchange", type=str, default="binance", help="Exchange")
    parser.add_argument("--symbol", type=str, default="LTCUSDT", help="Symbol")
    parser.add_argument("--mode", type=str, default="demo", choices=["demo", "live"], help="Mode")

    args = parser.parse_args()
    setup_logging()

    test = ConcurrentPositionsTest(exchange_id=args.exchange, symbol=args.symbol, mode=args.mode)

    try:
        await test.run_test()
    except Exception as e:
        logger.error(f"❌ Test falló: {e}", exc_info=True)
        await test.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
