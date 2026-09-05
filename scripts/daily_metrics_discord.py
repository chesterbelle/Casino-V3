#!/usr/bin/env python3
"""
Daily Metrics Telemetry (Fase 1.8)
Extracts key performance indicators from historian.db in read-only mode
and sends a Discord embed. Intended to be run via Cron at 00:00 UTC or periodically.
"""

import datetime
import json
import logging
import os
import sqlite3
from typing import Any, Dict

import requests

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Telemetry")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "historian.db")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def get_daily_metrics() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        logger.error(f"Historian DB not found at {DB_PATH}")
        return {}

    # Connect in read-only mode to avoid locking issues with the active bot
    uri = f"file:{DB_PATH}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get start of today (UTC)
        today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_iso = today.isoformat()

        # Query all closed trades for today
        query = """
            SELECT symbol, timestamp, side, net_pnl, exit_reason
            FROM trades
            WHERE timestamp >= ?
        """
        cursor.execute(query, (today_iso,))
        rows = cursor.fetchall()

        total_trades = len(rows)
        if total_trades == 0:
            return {"total_trades": 0, "pnl": 0.0, "win_rate": 0.0, "max_drawdown": 0.0}

        wins = 0
        total_pnl = 0.0
        peak_equity = 0.0
        current_equity = 0.0
        max_drawdown = 0.0

        for row in rows:
            pnl = float(row["net_pnl"])
            total_pnl += pnl
            if pnl > 0:
                wins += 1

            # Drawdown calculation
            current_equity += pnl
            if current_equity > peak_equity:
                peak_equity = current_equity

            drawdown = peak_equity - current_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0.0

        return {"total_trades": total_trades, "pnl": total_pnl, "win_rate": win_rate, "max_drawdown": max_drawdown}
    except Exception as e:
        logger.error(f"Failed to extract metrics: {e}")
        return {}
    finally:
        if "conn" in locals():
            conn.close()


def send_discord_webhook(metrics: Dict[str, Any]):
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL environment variable is not set. Skipping notification.")
        return

    if not metrics:
        logger.info("No metrics to report.")
        return

    pnl = metrics.get("pnl", 0.0)
    color = 3066993 if pnl >= 0 else 16711680  # Green if profit, Red if loss
    emoji = "🟢" if pnl >= 0 else "🔴"

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    embed = {
        "title": f"📊 Daily Paper Trading Report ({date_str} UTC)",
        "color": color,
        "fields": [
            {"name": "Daily PnL", "value": f"{emoji} **${pnl:.4f}**", "inline": True},
            {"name": "Win Rate", "value": f"**{metrics.get('win_rate', 0):.1f}%**", "inline": True},
            {"name": "Total Trades", "value": f"**{metrics.get('total_trades', 0)}**", "inline": True},
            {"name": "Max Drawdown (Intraday)", "value": f"**${metrics.get('max_drawdown', 0):.4f}**", "inline": False},
        ],
        "footer": {"text": "Casino-V3 Telemetry System"},
    }

    payload = {"embeds": [embed]}

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10
        )
        response.raise_for_status()
        logger.info("✅ Discord telemetry sent successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to send Discord webhook: {e}")


if __name__ == "__main__":
    logger.info("Fetching daily metrics...")
    metrics = get_daily_metrics()
    logger.info(f"Metrics extracted: {metrics}")

    if metrics:
        send_discord_webhook(metrics)
    else:
        logger.info("No data to send today.")
