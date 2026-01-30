import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import exchange as exchange_config
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/connectivity_test.log")],
)
logger = logging.getLogger("ConnStressTester")


class ConnectivityStressTester:
    def __init__(self, duration_minutes=60, symbol="BTCUSDT"):
        self.duration_seconds = duration_minutes * 60
        self.symbol = symbol
        self.connector = BinanceNativeConnector(
            api_key=exchange_config.BINANCE_API_KEY, secret=exchange_config.BINANCE_API_SECRET, mode="demo"
        )

        # Stats
        self.start_time = 0
        self.ws_events_received = 0
        self.orders_executed = 0
        self.orders_matched = 0
        self.latency_samples = []
        self.discrepancies = []
        self.ws_event_history = []

        self.running = False
        self.target_orders = {}  # client_id -> order_data

    async def on_order_update(self, event):
        """Handle WS order update."""
        self.ws_events_received += 1
        client_id = event.get("client_order_id")
        status = event.get("status")

        logger.debug(f"🕵️ WS Order Event: {client_id} | Status: {status}")

        # Record latency if we have locally-generated timestamp
        if client_id in self.target_orders:
            # Use appropriate reference time (Cancel time vs Entry time)
            if status == "canceled" and "cancelled_at" in self.target_orders[client_id]:
                ref_time = self.target_orders[client_id]["cancelled_at"]
            else:
                ref_time = self.target_orders[client_id]["sent_at"]

            reception_time = time.time()
            latency = (reception_time - ref_time) * 1000
            self.latency_samples.append(latency)

            if status in ["open", "canceled", "closed"]:
                self.orders_matched += 1
                logger.info(f"✅ WS Match: {client_id} | Status: {status} | Latency: {latency:.2f}ms")

        self.ws_event_history.append({"timestamp": time.time(), "event": event})

    async def on_account_update(self, event):
        """Handle WS account update."""
        self.ws_events_received += 1
        logger.debug(f"💰 WS Account Update Received")

    async def run_traffic_loop(self):
        """Generates traffic by creating and cancelling orders."""
        logger.info(f"🚦 Starting traffic loop for {self.symbol}...")

        while self.running:
            try:
                # 1. Create Limit Order (Far away to avoid fill)
                client_id = f"TEST_{int(time.time()*1000)}"

                # Get current price to be safe
                ticker = await self.connector.fetch_ticker(self.symbol)
                curr_price = float(ticker["last"])
                target_price = curr_price * 0.5  # 50% below market

                logger.info(f"📤 Sending Test Order: {client_id} @ {target_price}")

                order_data = {
                    "symbol": self.symbol,
                    "side": "buy",
                    "order_type": "limit",
                    "amount": 0.5,
                    "price": target_price,
                    "params": {"client_order_id": client_id},
                }

                self.target_orders[client_id] = {"sent_at": time.time(), "data": order_data}

                self.orders_executed += 1
                resp = await self.connector.create_order(**order_data)
                exchange_id = resp.get("id")

                # 2. Wait 5s
                await asyncio.sleep(5)

                # 3. Cancel Order
                logger.info(f"🗑️ Cancelling Test Order: {client_id} ({exchange_id})")
                self.target_orders[client_id]["cancelled_at"] = time.time()
                await self.connector.cancel_order(exchange_id, self.symbol)

                # 4. Wait 10s for next cycle
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"❌ Error in traffic loop: {e}")
                await asyncio.sleep(5)

    async def run_audit_loop(self):
        """Periodically prints status to log."""
        while self.running:
            await asyncio.sleep(60)
            try:
                duration = time.time() - self.start_time
                avg_lat = sum(self.latency_samples) / len(self.latency_samples) if self.latency_samples else 0
                load_factor = self.connector.get_load_factor()
                logger.info(
                    f"📊 STATUS | Runtime: {duration/60:.2f}m | "
                    f"Sent: {self.orders_executed} | WS Matches: {self.orders_matched} | "
                    f"Avg Latency: {avg_lat:.2f}ms | Exchange Load: {load_factor:.2%}"
                )
            except Exception as e:
                logger.error(f"❌ Error in audit loop: {e}")

    async def start(self):
        self.running = True
        self.start_time = time.time()

        # Setup connector
        self.connector.set_order_update_callback(self.on_order_update)
        self.connector.set_account_update_callback(self.on_account_update)

        await self.connector.connect()

        # Start loops
        traffic_task = asyncio.create_task(self.run_traffic_loop())
        audit_task = asyncio.create_task(self.run_audit_loop())

        logger.info(f"⏱️ Stress test started. Duration: {self.duration_seconds/60} minutes.")

        try:
            await asyncio.sleep(self.duration_seconds)
        finally:
            self.running = False
            traffic_task.cancel()
            audit_task.cancel()
            await self.connector.close()
            self.generate_report()

    def generate_report(self):
        duration = time.time() - self.start_time
        avg_latency = sum(self.latency_samples) / len(self.latency_samples) if self.latency_samples else 0
        loss_rate = (1 - (self.orders_matched / (self.orders_executed * 2))) * 100 if self.orders_executed > 0 else 0

        report = {
            "test_config": {
                "symbol": self.symbol,
                "duration_min": duration / 60,
                "timestamp": datetime.now().isoformat(),
            },
            "metrics": {
                "total_ws_events": self.ws_events_received,
                "total_orders_sent": self.orders_executed,
                "orders_matched_ws": self.orders_matched,
                "packet_loss_est": f"{loss_rate:.2f}%",
                "avg_latency_ms": f"{avg_latency:.2f}ms",
                "max_latency_ms": f"{max(self.latency_samples) if self.latency_samples else 0:.2f}ms",
            },
        }

        report_path = "logs/connectivity_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=4)

        logger.info("=" * 40)
        logger.info("📊 CONNECTIVITY STRESS TEST REPORT")
        logger.info("=" * 40)
        logger.info(f"⏱️ Runtime: {duration/60:.2f} min")
        logger.info(f"📩 Total WS Events: {self.ws_events_received}")
        logger.info(f"📤 Orders Sent/Cancelled: {self.orders_executed}")
        logger.info(f"✅ WS Matches: {self.orders_matched}")
        logger.info(f"📉 Est. Packet Loss: {loss_rate:.2f}%")
        logger.info(f"⚡ Avg Latency: {avg_latency:.2f}ms")
        logger.info(f"Report saved to: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binance Connectivity Stress Tester")
    parser.add_argument("--duration", type=int, default=60, help="Duration in minutes")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading symbol")
    args = parser.parse_args()

    tester = ConnectivityStressTester(duration_minutes=args.duration, symbol=args.symbol)
    try:
        asyncio.run(tester.start())
    except KeyboardInterrupt:
        logger.info("🛑 Manually stopped. Generating report...")
        tester.generate_report()
