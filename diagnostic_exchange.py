import asyncio
import hashlib
import hmac
import json
import os
import sys
import time

import aiohttp

sys.path.append(os.getcwd())  # noqa: E402
from config.exchange import (  # noqa: E402
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    BINANCE_BASE_URL,
)


async def diagnostic():
    url = f"{BINANCE_BASE_URL}/fapi/v1/positionRisk"
    ts = int(time.time() * 1000)
    query = f"timestamp={ts}"
    signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    signed_url = f"{url}?{query}&signature={signature}"

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    print(f"📡 Requesting: {url}")
    print(f"🔑 API Key: {BINANCE_API_KEY[:5]}...{BINANCE_API_KEY[-5:] if BINANCE_API_KEY else 'None'}")

    async with aiohttp.ClientSession() as session:
        async with session.get(signed_url, headers=headers) as resp:
            text = await resp.text()
            print(f"📥 Status: {resp.status}")
            try:
                data = json.loads(text)
            except Exception:
                print(f"❌ Raw Text: {text}")
                return

            if not isinstance(data, list):
                print(f"❌ Error Response: {data}")
                return

            print(f"📊 Total positions in response: {len(data)}")
            non_zero = [p for p in data if float(p.get("positionAmt", 0)) != 0]
            print(f"🚩 Non-zero positions: {len(non_zero)}")
            for p in non_zero:
                print(f"   - {p['symbol']}: {p['positionAmt']} ({p['positionSide']})")

            # Check for ANY mention of CRV, STORJ, DOT
            ghosts = [p for p in data if p["symbol"] in ["CRVUSDT", "STORJUSDT", "DOTUSDT"]]
            print("👻 Ghost Symbols Status:")
            for p in ghosts:
                print(
                    f"   - {p['symbol']}: amt={p['positionAmt']} side={p['positionSide']} pnl={p['unRealizedProfit']}"
                )

        # Check Position Mode
        mode_url = f"{BINANCE_BASE_URL}/fapi/v1/positionSide/dual"
        mode_ts = int(time.time() * 1000)
        mode_query = f"timestamp={mode_ts}"
        mode_sig = hmac.new(BINANCE_API_SECRET.encode(), mode_query.encode(), hashlib.sha256).hexdigest()
        async with session.get(f"{mode_url}?{mode_query}&signature={mode_sig}", headers=headers) as mresp:
            m_text = await mresp.text()
            try:
                mode_data = json.loads(m_text)
                print(f"🔄 Hedge Mode (Dual Side): {mode_data.get('dualSidePosition')}")
            except Exception:
                print(f"❌ Mode Error: {m_text}")


if __name__ == "__main__":
    asyncio.run(diagnostic())
