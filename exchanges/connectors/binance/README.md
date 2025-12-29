# Binance Futures Connector

Conector completo para Binance Futures (USDT Perpetual) siguiendo la arquitectura modular de Casino V2.

## ⚠️ Importante: Testnet Deprecado

**Binance Futures Testnet fue deprecado por CCXT** (ver [anuncio oficial](https://t.me/ccxt_announcements/92)).

### Opciones Disponibles

1. **Paper Trading Mode** (Recomendado para testing)
   - Simulación local de órdenes
   - No requiere exchange real
   - Limitado a funcionalidad básica

2. **Live Trading** (⚠️ DINERO REAL)
   - Trading real en producción
   - Usar con EXTREMA precaución
   - Recomendado solo con cantidades muy pequeñas para testing

3. **Exchanges Alternativos** (Mejor opción para testing)
   - **Bybit**: Tiene Demo Trading activo (recomendado)
   - **Kraken**: Tiene Testnet activo
   - Ambos soportan testing seguro sin riesgo

## 🚀 Uso

### Inicialización

```python
from exchanges.connectors.binance import BinanceConnector

# Paper Trading (simulación local)
connector = BinanceConnector(mode="paper")

# Live Trading (⚠️ DINERO REAL)
connector = BinanceConnector(mode="live")
```

### Conexión

```python
await connector.connect()
```

### Crear Orden Simple

```python
order = await connector.create_order(
    symbol="BTC/USD:USD",
    side="buy",
    amount=0.001,
    order_type="market"
)
```

### Crear Orden con TP/SL

```python
order = await connector.create_order_with_tpsl(
    symbol="BTC/USD:USD",
    side="buy",
    amount=0.001,
    order_type="market",
    tp_price=50000,  # Take Profit
    sl_price=48000   # Stop Loss
)
```

**Nota**: Binance crea 3 órdenes separadas (main + TP + SL), similar a Kraken.

### Consultar Balance

```python
balance = await connector.fetch_balance()
usdt_balance = balance.get("total", {}).get("USDT", 0)
```

### Consultar Posiciones

```python
positions = await connector.fetch_positions()
```

### Cerrar Conexión

```python
await connector.close()
```

## 🔑 Configuración de Credenciales

### Variables de Entorno

```bash
# Para Paper Trading o Live
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# O usando nombres alternativos
BINANCE_FUTURES_API_KEY=your_api_key_here
BINANCE_FUTURES_API_SECRET=your_api_secret_here

# Legacy (testnet deprecado, se convierte a paper mode)
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_SECRET=your_testnet_secret
```

### Obtener API Keys

1. Crear cuenta en [Binance](https://www.binance.com)
2. Ir a API Management
3. Crear nueva API Key
4. **Importante**: Configurar restricciones de IP y permisos mínimos necesarios
5. **Para testing**: Usar cuenta con balance mínimo

## 🎯 Características

### Implementadas

- ✅ Conexión REST a Binance Futures
- ✅ Órdenes market y limit
- ✅ TP/SL nativo (3 órdenes separadas)
- ✅ Consulta de balance y posiciones
- ✅ Consulta de ticker y OHLCV
- ✅ Normalización de símbolos (BTC/USD:USD ↔ BTC/USDT:USDT)
- ✅ Validación de límites de exchange
- ✅ Paper trading mode
- ✅ Manejo de errores robusto

### Pendientes

- ⏳ WebSocket support
- ⏳ Gestión avanzada de posiciones
- ⏳ Órdenes condicionales avanzadas

## 📊 Particularidades de Binance

### TP/SL Implementation

Binance **NO** soporta TP/SL en la misma orden como Bybit. Requiere crear 3 órdenes separadas:

1. **Orden Principal**: Market o Limit
2. **Take Profit**: `TAKE_PROFIT_MARKET` order
3. **Stop Loss**: `STOP_MARKET` order

```python
# Internamente, el conector hace:
# 1. Crear orden principal
main_order = await exchange.create_order(symbol, "market", "buy", amount)

# 2. Crear TP order
tp_order = await exchange.create_order(
    symbol, "TAKE_PROFIT_MARKET", "sell", amount,
    params={"stopPrice": tp_price}
)

# 3. Crear SL order
sl_order = await exchange.create_order(
    symbol, "STOP_MARKET", "sell", amount,
    params={"stopPrice": sl_price}
)
```

### Normalización de Símbolos

```python
# Bot format → Binance format
"BTC/USD:USD" → "BTC/USDT:USDT"
"ETH/USD:USD" → "ETH/USDT:USDT"

# Binance format → Bot format
"BTCUSDT" → "BTC/USD:USD"
"ETHUSDT" → "ETH/USD:USD"
```

### Position Mode

Por defecto usa **One-Way Mode** (`positionSide: "BOTH"`).

## 🧪 Testing

### Test Básico

```bash
# Ejecutar test de conexión
.venv/bin/python test_binance_connector.py
```

**Nota**: El test requiere API keys válidas. Para testing seguro sin riesgo, se recomienda usar Bybit o Kraken que tienen testnets activos.

### Test Manual

```python
import asyncio
from exchanges.connectors.binance import BinanceConnector

async def test():
    connector = BinanceConnector(mode="paper")
    await connector.connect()

    # Test ticker
    ticker = await connector.fetch_ticker("BTC/USD:USD")
    print(f"BTC Price: ${ticker['last']:,.2f}")

    await connector.close()

asyncio.run(test())
```

## 🔗 Referencias

- [Binance Futures API Documentation](https://binance-docs.github.io/apidocs/futures/en/)
- [CCXT Binance Documentation](https://docs.ccxt.com/#/exchanges/binance)
- [CCXT Testnet Deprecation Announcement](https://t.me/ccxt_announcements/92)
- [Casino V2 Architecture](../../README.md)

## 📝 Notas de Desarrollo

### Arquitectura Modular

Este conector sigue los principios de arquitectura modular de Casino V2:

- **Conector**: Maneja TODAS las particularidades de Binance
- **Adaptador** (CCXTAdapter): Agnóstico del exchange
- **Separación clara**: Lógica de exchange vs lógica de negocio

### Comparación con Otros Conectores

| Feature | Binance | Bybit | Kraken |
|---------|---------|-------|--------|
| Testnet | ❌ Deprecado | ✅ Demo Trading | ✅ Activo |
| TP/SL en orden | ❌ 3 órdenes | ✅ Nativo | ❌ OCO Monitor |
| WebSocket | ⏳ Pendiente | ✅ Implementado | ✅ Implementado |
| Paper Trading | ✅ CCXT | ✅ Demo | ⏳ Limitado |

### Recomendación

**Para desarrollo y testing seguro, se recomienda usar Bybit** que tiene Demo Trading completamente funcional y no requiere dinero real.

## 🤝 Contribuciones

Al contribuir a este conector:

1. Mantener la arquitectura modular
2. NO agregar lógica de Binance al adaptador
3. Documentar particularidades del exchange
4. Agregar tests para nuevas funcionalidades
5. Seguir el estilo de código del proyecto

## 📄 Licencia

Parte del proyecto Casino V2.
