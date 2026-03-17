# Protocolo de Backtest V4 (Microstructure Edition)

Este protocolo sustituye a `strategy-audit.md` para validaciones deterministas usando datos históricos de alta fidelidad (ticks).

## 📊 Configuración de la Simulación
- **Engine**: V4 Reactor (`backtest.py`)
- **Feed**: `TRADES` mode (Real tick replay)
- **Exchange**: `VirtualExchangeConnector` (Simulación de OCO/TP/SL)
- **Latency**: Simulated (Default: 0ms para lógica, configurable para stress)

## 🛠️ Procedimiento de Ejecución (REGLA DE PARADA: Detente después de cada ronda y presenta resultados)

### 1. Preparación de Datos
Asegúrate de tener un dataset de ticks en `data/raw/`. Si no, descárgalo:
```bash
.venv/bin/python3 utils/data/download_trades.py --symbol=LTCUSDT --year=2026 --month=01
```

### 1.5. Limpieza de Entorno (IMPORTANTE)
Antes de correr el backtest, resetea la base de datos y el estado para garantizar resultados deterministas:
```bash
.venv/bin/python3 reset_data.py
```

### 2. Ejecución del Test
Corre la estrategia contra el periodo seleccionado (500k ticks para iteración rápida):
```bash
.venv/bin/python3 backtest.py --data=data/raw/LTCUSDT_trades_2026_01.csv --symbol=LTC/USDT:USDT --limit=500000
```

**Nota**: Para validación final, remover `--limit` para procesar el dataset completo (3M ticks).

## 📉 Métricas de Auditoría (KPIs)

| Métrica | Objetivo | Umbral Crítico |
| :--- | :--- | :--- |
| **Profit Factor** | > 1.3 | < 1.0 |
| **Win Rate** | > 55% | < 45% |
| **Max Drawdown** | < 5% | > 10% |
| **Z-Score Edge** | Positivo | Negativo/Cero |
| **Avg RR Ratio** | > 1.2 | < 1.0 |

## 🔍 Checkpoint de Microestructura
Al finalizar el backtest, revisa el log `bot.log` para confirmar:
- [ ] **No Execution Skew**: Las órdenes se llenaron al precio del tick (o con slippage configurado).
- [ ] **Z-Score Parity**: Los triggers coinciden con la distribución estadística esperada.
- [ ] **Reactor Stability**: Cero errores de "Event Overflow" o cuelgues del Engine.

## 📝 Registro de Resultados
Crea una entrada en `backtest-results.log` (o similar) con:
1. Hash del commit (`git rev-parse HEAD`)
2. Parámetros de la estrategia.
3. Resultado final ($ P&L) y P.F.

> [!IMPORTANT]
> **REGLA DE ORO**: Al finalizar cada ronda de backtest, debes presentar los resultados y **DETENERTE** inmediatamente. No inicies la siguiente ronda sin aprobación explícita.
