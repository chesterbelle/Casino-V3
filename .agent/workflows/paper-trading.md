---
description: Protocolo oficial para el despliegue del bot en Paper Trading (Phase 1.9 / 2) garantizando visibilidad de parámetros.
---

# Paper Trading & Live Deployment Protocol

## Objetivo Principal
Establecer un proceso seguro, transparente y manual para el despliegue en entornos de simulación (Paper Trading) y producción (Live Trading). **Está prohibido el uso de scripts bash que oculten parámetros o inicien bucles automáticos** que interfieran con la arquitectura de Auto-Healing.

---

## 🛑 SECUENCIA DE COLD START (Día 1 / Despliegue Inicial)

*Solo ejecutar esta secuencia cuando se inicia una nueva campaña desde cero absoluto. NUNCA ejecutar después de un apagón o reinicio imprevisto.*

### Paso 1: Wipe del Exchange (Solo si es Demo/Paper)
Liquida cualquier posición remanente y cancela todas las órdenes abiertas.
```bash
.venv/bin/python utils/emergency_cleanup.py
```

### Paso 2: Validación Cero
Asegura matemáticamente que el exchange está limpio. Si falla, investigar manualmente.
```bash
.venv/bin/python -c "
import asyncio, sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector
async def main():
    conn = BinanceNativeConnector(api_key=os.getenv('BINANCE_TESTNET_API_KEY'), secret=os.getenv('BINANCE_TESTNET_SECRET'), mode='demo')
    await conn.connect()
    pos = [p for p in await conn.fetch_positions() if abs(p['contracts']) > 0]
    orders = await conn.fetch_open_orders(None)
    print('POSICIONES:', len(pos), '| ORDENES:', len(orders))
    assert len(pos) == 0 and len(orders) == 0, 'EXCHANGE NO ESTA EN CERO — ABORTAR'
    await conn.close()
asyncio.run(main())
"
```

### Paso 3: Purga de Estado Local
Elimina estados residuales (`state/*.json`) y el historial viejo (`historian.db`).
```bash
.venv/bin/python utils/reset_data.py
```

---

## 🚀 SECUENCIA DE ARRANQUE NORMAL

Ejecutar este comando explícito en una sesión `setsid` o `nohup` para que el bot sobreviva al cierre de la terminal. Todos los parámetros (especialmente la lista de monedas autorizadas) se inyectan de forma explícita.

**Lista Autorizada (Phase 2):** LTCUSDT, SOLUSDT, AVAXUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, BNBUSDT, LINKUSDT, OPUSDT. (Nótese la ausencia intencional de BTCUSDT y ETHUSDT por su alto ruido y peso).

### Comando de Despliegue:
```bash
setsid .venv/bin/python main.py \
  --run-type trade \
  --symbol LTCUSDT,SOLUSDT,AVAXUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,BNBUSDT,LINKUSDT,OPUSDT \
  --mode demo \
  --bet-size 0.01 \
  --close-on-exit \
  --timeout 1440 \
  --discord \
  2>&1 | tee logs/paper_trading_$(date +%Y%m%d_%H%M%S).log
```

---

## 🔌 PROTOCOLO DE RECUPERACIÓN (Apagones / Crashes)

Si la máquina se apaga inesperadamente, el bot muere. Cuando el sistema reinicia:
1. **NO ejecutes la secuencia de Cold Start (Wipe).**
2. Inicia sesión en la máquina.
3. Ejecuta **únicamente la SECUENCIA DE ARRANQUE NORMAL** mostrada arriba.
4. El bot se conectará a Binance, leerá el estado en `state/`, comparará, y activará el `ReconciliationService` y el `DriftAuditor` de forma autónoma para hacer **Auto-Healing** de las posiciones huérfanas.
