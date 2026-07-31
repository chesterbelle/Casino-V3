# Roadmap a Producción — Casino-V3

> **Objetivo**: Llevar el bot de backtest exitoso a trading en vivo de manera segura, sistemática y validada.
>
> **Fecha de creación**: 2026-07-24
>
> **Estado actual**: 9/11 activos optimizados (ARB, NEAR, OP, APT, LINK, DOGE, ADA, BNB, XRP certificados). BTC y ETH pendientes.

---

## 📊 Resumen Ejecutivo

**Tesis principal**: No ir a live demo inmediatamente después de optimizar BTC/ETH. Primero validar el sistema en paper trading con activos estables, luego incorporar los casos especiales (BTC/ETH).

**Razón crítica**: BTC y ETH tienen microestructuras fundamentalmente diferentes al resto de activos. Sus perfiles (ILLIQUID_SPEC) presentan desafíos únicos que podrían enmascarar problemas del sistema o introducir riesgos no detectados en backtest.

**Tiempo estimado**: 4-6 semanas para live demo con confianza razonable.

**Riesgo máximo aceptable**: Pérdida del 5% del capital en paper trading antes de abortar y revisar estrategia.

---

## 🎯 Fase 0: Análisis de Estado Actual

### 0.1 Edge Certificado por Activo

| Activo | Net Taker | MFE/MAE | Win Rate | Estado | Perfil |
|--------|-----------|---------|----------|--------|--------|
| SOL | +2.1474% | Alto | 53.8% | ✅ EXCELENTE | MAJOR_LIQUID |
| XRP | +0.5230% | Alto | 64.9% | ✅ BUENO | THIN_VOLATILE |
| AVAX | +0.3500% | Medio | 44.1% | ✅ OK | NOISY_UNCERTAIN |
| LTC | +0.2352% | 1.63 | 53.7% | ✅ CERTIFICADO | NOISY_UNCERTAIN |
| DOGE | +0.6272% | Medio | 57.5% | ✅ OK | THIN_VOLATILE |
| ADA | +0.1682% | Bajo | 15.1% | ⚠️ MARGINAL | MEGA_LIQUID |
| BNB | +0.1638% | Bajo | 57.5% | ⚠️ MARGINAL | MID_LIQUID |
| LINK | +0.2618% | Medio | 57.5% | ✅ OK | MID_LIQUID |
| ARB | ? | ? | ? | 🔄 Pendiente verificación | MEGA_LIQUID |
| NEAR | ? | ? | ? | 🔄 Pendiente verificación | MEGA_LIQUID |
| OP | ? | ? | ? | 🔄 Pendiente verificación | MID_LIQUID |
| APT | ? | ? | ? | 🔄 Pendiente verificación | MEGA_LIQUID |
| **BTC** | ? | ? | ? | ⏳ Sin optimizar | ILLIQUID_SPEC |
| **ETH** | ? | ? | ? | ⏳ Sin optimizar | ILLIQUID_SPEC |

**Conclusión**: 6 activos con edge claro, 3 marginales, 4 sin verificación reciente, 2 sin optimizar.

### 0.2 Problemas Históricos Identificados

| Problema | Activo | Sesión | Resolución | Lección |
|----------|--------|--------|------------|---------|
| ETH PROBLEM | ETH | Múltiples | Sin resolver | Edge marginal o negativo históricamente |
| TA ENTRY FAILURE | AVAX | 2026-07-14 | Bug `abs()` en CVD | Los bugs pueden estar ocultos en features complejos |
| PROFILE CONTRADICTION | SOL/XRP/DOGE | 2026-06-02 | Clustering no determinista | Los perfiles pueden no generalizar como se espera |
| LE ENTRY FAILURE | AVAX | 2026-07-01 | `level_key` fragmentación | Bugs en lógica de estado pueden tardar meses en detectarse |
| VA_GATE BLOQUEO TOTAL | Mensuales | 2026-06-22 | VA integrity = 0.00 en datasets largos | El diseño tiene limitaciones estructurales conocidas |

**Patrón observado**: Los bugs críticos se descubren tardíamente (meses después de implementación). El sistema es complejo y tiene múltiples capas de interacción.

---

## 🚨 Por Qué Excluir BTC/ETH en Paper Trading Inicial

### 1. Microestructura Fundamentalmente Diferente

**BTC (ILLIQUID_SPEC)**:
- **Speed**: 26 trades/seg (más alto del sistema)
- **Book density**: 17.8 (relativamente bajo para su volumen)
- **Comportamiento**: Alta actividad pero libro menos profundo → más susceptible a spoofing
- **Orderbook**: 1436 MB de datos → 10x más pesado que LTC

**ETH (ILLIQUID_SPEC)**:
- **Speed**: 27 trades/seg (el más alto)
- **Book density**: Similar a BTC
- **Historial**: Documentado como "ETH PROBLEM" en múltiples sesiones
- **Orderbook**: 2259 MB → El más pesado del sistema

**Diferencia vs otros activos**:

| Métrica | BTC/ETH | Resto de activos | Ratio |
|---------|---------|------------------|-------|
| Speed (trades/seg) | 26-27 | 4-9 | **3-6x más rápido** |
| Book density | 17.8 | 20-25 | **15% menos denso** |
| Orderbook size (MB) | 1436-2259 | 100-900 | **2-15x más pesado** |
| Edge histórico | ?/Problemático | +0.16% a +2.14% | **Incertidumbre** |

**Implicación**: BTC/ETH operan en un régimen de microestructura diferente que puede no responder igual a los parámetros optimizados para otros activos.

### 2. Riesgo de Enmascarar Problemas del Sistema

**Escenario problemático**:

```
Si incluyes BTC/ETH en paper trading desde el inicio:

1. BTC tiene un bug no detectado en el manejo de orderbook grande
2. ETH tiene edge negativo que no se descubrió en optimización
3. El sistema falla o pierde dinero
4. No sabes si el problema fue:
   - El sistema en general
   - BTC/ETH específicamente
   - La interacción entre activos
   - Infraestructura
```

**Resultado**: Pierdes tiempo debugging sin saber la causa raíz.

**Escenario controlado (sin BTC/ETH)**:

```
Si excluyes BTC/ETH al inicio:

1. Paper trading con activos estables (LTC, SOL, AVAX, etc.)
2. Si el sistema falla → problema de infraestructura/estrategia general
3. Si el sistema funciona → validación de base sólida
4. Luego añades BTC/ETH:
   - Si fallan → problema específico de microestructura
   - Si funcionan → sistema completo validado
```

**Resultado**: Diagnóstico claro de problemas y validación progresiva.

### 3. Problemas de Infraestructura Potenciales

**Memoria**:
- ETH orderbook (2259 MB) + procesamiento en memoria → posible OOM
- 10 activos simultáneos sin ETH: ~3-4 GB RAM
- Con ETH: ~6+ GB RAM → riesgo de crash

**Latencia**:
- Procesar 26-27 trades/seg en ETH vs 4-9 en otros
- Si el sistema no puede mantener el ritmo → lag acumulativo
- Señales desactualizadas → slippage

**Rate limits**:
- Binance tiene límites por IP y por cuenta
- 10+ activos con alta frecuencia → posible violación
- ETH con velocidad extrema → consume más "budget" de rate limit

**WebSocket**:
- Streams masivos en ETH → más desconexiones
- Reconexión más lenta por volumen de datos
- Tiempo de recuperación que afecta trading

**Validación necesaria**:
```python
# Antes de incluir ETH:
assert memoria_disponible > 8 * GB
assert latencia_tick_a_signal < 10 * ms  # Incluso con 27 trades/seg
assert rate_limit_headroom > 0.3  # 30% de margen
```

### 4. Edge No Garantizado en BTC/ETH

**Historial de ILLIQUID_SPEC**:

Según el memory.md (2026-06-02):

> **ILLIQUID_SPEC Backtest**: SOL +0.24% Net Taker (edge marginal), XRP -0.05%, DOGE -0.13%. Solo SOL tiene potencial. **PERO**: profile system los clasifica como MAJOR_LIQUID, no ILLIQUID_SPEC — contradicción con clustering real.

**Observación**: El perfil ILLIQUID_SPEC tuvo resultados mixtos. La contradicción en clustering sugiere que la taxonomía puede no estar calibrada para estos casos.

**Riesgo de optimización**:
- Optimizar BTC/ETH puede dar edge positivo en backtest
- Pero con overfitting a datos históricos
- En live, el edge puede evaporarse o volverse negativo

**Evidencia de overfitting**:
- AVAX TA tuvo score +0.46 en optimización pero falló en validación OOS
- Cross-coin validation timeout en varios casos
- Múltiples activos requirieron targets asimétricos extremos para funcionar

### 5. Complejidad de Debugging en Producción

**Escenario de fallo en live con BTC/ETH**:

```
Hora 0: Sistema arranca con 11 activos (incluye BTC/ETH)
Hora 2: Pérdida de $50 en ETH trade
Hora 4: Pérdida de $30 en BTC trade
Hora 6: Sistema crashea por OOM (memory exhaust)
Hora 7: Reinicio manual
Hora 9: Más pérdidas
Hora 12: Usuario detiene sistema - $150 pérdida total

Preguntas sin respuesta:
- ¿El crash fue por ETH?
- ¿Las pérdidas fueron por edge negativo o bug?
- ¿El sistema está mal o solo BTC/ETH?
- ¿Volver a arrancar con todos o reducir activos?
```

**Escenario de fallo sin BTC/ETH**:

```
Hora 0: Sistema arranca con 9 activos (sin BTC/ETH)
Hora 2: $20 ganancia
Hora 4: $15 ganancia
Hora 12: Sistema estable, $40 ganancia total
Hora 24: Validación exitosa, sistema funciona

Paso 2: Añadir BTC
Hora 0: Sistema con 10 activos
Hora 2: $10 pérdida en BTC
Hora 4: Crash por memory

Diagnóstico claro: El problema es específicamente BTC/memory
No es la estrategia general, no es la infraestructura base
```

---

## 📋 Fase 1: Validación de Sistema (Semana 1-2)

### 1.1 Non-Regression Test en 84 Datasets Certificados

**Objetivo**: Confirmar que los parámetros optimizados no rompieron edge en datos históricos.

**Procedimiento**: Ejecutar `backtest_runner.py` en modo audit para cada activo certificado.
```bash
# Ejemplo para un activo:
python scripts/backtest_runner.py --mode audit --symbol LTCUSDT

# Repetir para cada activo certificado:
# SOLUSDT, AVAXUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, BNBUSDT, LINKUSDT, OPUSDT
```

**Métricas de éxito**:
- Net Taker >= baseline (no regresión)
- Win Rate >= baseline
- MFE/MAE >= baseline
- Zero crashes

**Criterio de paso**:
- >= 80% de activos mantienen o mejoran baseline
- Si < 80% → investigar regresión antes de continuar

**Tiempo estimado**: 2-3 días de ejecución + análisis

### 1.2 Validación de Infraestructura Completa (`/validate-all`)

**Objetivo**: Certificar que cada componente aislado funciona correctamente antes de someterlos a presión conjunta.

**Procedimiento**: Ejecutar el workflow `/validate-all` completo (Capas 0 a 6).

> 👉 El protocolo detallado, comandos exactos y criterios de éxito viven en:
> [`.agent/workflows/validate-all.md`](file:///home/chesterbelle/Casino-V3/.agent/workflows/validate-all.md)

**Resumen de capas**:
- **Capa 0**: Math atómica (Footprint, Absorption, ExitEngine, SignalArbitrator, Fees)
- **Capa 1**: Integridad de datos + integración de salidas
- **Capa 2**: Pipeline de señales (TradeProposal) + pipeline de ejecución (VirtualExchange)
- **Capa 3**: Orquestación (Orchestrator protocols)
- **Capa 4**: Stress & Chaos (multi_symbol_chaos_tester)
- **Capa 6**: Cluster Optimizer (validate-only)

**Criterio de paso**: Todas las capas pasan sin errores.

**Tiempo estimado**: 1-2 días

### 1.3 Stress Test Multi-Coin (`/stress-test`)

**Objetivo**: Verificar que el sistema aguanta carga real sostenida sin degradación, fugas de memoria ni errores de ejecución.

**Procedimiento**: Ejecutar el workflow `/stress-test` (Fase A: Chaos + Fase B: Endurance).

> 👉 El protocolo detallado, comandos exactos y criterios de éxito viven en:
> [`.agent/workflows/stress-test.md`](file:///home/chesterbelle/Casino-V3/.agent/workflows/stress-test.md)

**Resumen de fases**:
- **Fase A (Chaos Test)**: Inyección de órdenes sintéticas a 9 monedas durante 10 min para saturar WebSockets/Croupier/OCOManager. Valida Error Recovery = $0.00 y 0 eventos UNMATCHED.
- **Fase B (Endurance Test)**: Bot real (`main.py`) en dos sub-fases: Mini-Endurance (4h, detección temprana) → Full Endurance (24h, validación definitiva). Opcional Multi-Coin (48h).

**Criterio de paso**:
- Fase A: Error Trades = 0, Integrity = PASS, Total Ops > 30
- Fase B: 0 crashes, RAM estable, trades limpios

**Tiempo estimado**: 1-3 días

### 1.4 Internal Event Bus Refactor (Pre-Fase 2)

**Objetivo**: Eliminar condiciones de carrera en el ruteo interno de eventos del Croupier antes de exponer el sistema a paper trading multi-coin.

**Problema detectado**: El `Engine.dispatch()` ejecuta subscribers con `asyncio.gather` (concurrente). En `_on_order_update_event`, `position_tracker` y `oco_manager` corren en paralelo — OCOManager puede leer estado stale del tracker. En `_on_account_update_event`, `balance_manager` y `position_tracker` también se ejecutan sin orden garantizado. Además, 3 callbacks directos (`on_close_callback`, `add_close_listener`, `add_state_listener`) bypassan el bus por completo.

**Procedimiento**:
1. Crear un bus de eventos interno en Croupier (`_local_bus`) con **procesamiento secuencial FIFO** por event type
2. Migrar las 4 llamadas inline en `_on_order_update_event` y `_on_account_update_event` a `dispatch_local(event)`
3. Migrar los 3 callbacks directos (`on_close_callback`, `add_close_listener`, `add_state_listener`) al bus interno

```python
# Antes (inline, sin orden):
async def _on_order_update_event(self, event):
    data = self._build_order_data(event)
    await asyncio.gather(
        self.position_tracker.handle_order_update(data),
        self.oco_manager.on_order_update(data),
    )

# Después (secuencial, ordenado):
async def _on_order_update_event(self, event):
    data = self._build_order_data(event)
    await self._local_bus.dispatch("order_update", data)
    # Cada componente procesa en orden de registro
```

**Criterio de paso**:
- Zero condiciones de carrera en stress test multi-coin (Phase B.3)
- Los 3 callbacks directos migrados al bus
- Zero cambios en la API pública de los componentes (solo Croupier internamente)

**Tiempo estimado**: 1 día

### 1.5 Análisis de Drawdown y Riesgo

**Objetivo**: Entender el riesgo máximo del sistema antes de exponer capital.

**Procedimiento**:
```python
# Extraer de backtests históricos:
# 1. Máximo drawdown por activo
# 2. Máximo drawdown portfolio (9 activos simultáneos)
# 3. Máxima racha de pérdidas consecutivas
# 4. Tiempo promedio de recuperación

# Calcular:
# 1. Capital mínimo recomendado
# 2. Tamaño de posición máximo por activo
# 3. Stop loss de portfolio (cuando detener el sistema)
```

**Métricas a obtener**:
- Max drawdown histórico: ?%
- Max loss streak: ? trades
- Recovery time: ? horas
- Capital mínimo recomendado: $?

**Criterio de paso**:
- Max drawdown < 20%
- Si > 20% → ajustar parámetros o reducir activos

**Tiempo estimado**: 1 día de análisis

---

## 🧪 Fase 2: Paper Trading Inicial (Semanas 2-3)

### 2.1 Configuración de Paper Trading

**Activos incluidos** (9 activos estables):
```python
PAPER_TRADING_PHASE1 = [
    "LTCUSDT",   # Certificado, edge estable
    "SOLUSDT",   # Mejor edge histórico
    "AVAXUSDT",  # Edge OK, bugs resueltos
    "XRPUSDT",   # Edge bueno, perfil validado
    "DOGEUSDT",  # Edge OK, comportamiento conocido
    "ADAUSDT",   # Edge marginal pero estable
    "BNBUSDT",   # Edge marginal pero conocido
    "LINKUSDT",  # Edge OK
    "OPUSDT",    # Pendiente verificación pero mismo cluster
]
```

**Activos EXCLUIDOS**:
```python
EXCLUDED = [
    "BTCUSDT",   # Sin optimizar, ILLIQUID_SPEC, riesgoso
    "ETHUSDT",   # Sin optimizar, ETH PROBLEM histórico, riesgoso
    "ARBUSDT",   # Sin verificación reciente
    "NEARUSDT",  # Sin verificación reciente
    "APTUSDT",   # Sin verificación reciente
]
```

**Parámetros de paper trading**:
```bash
python main.py --run-type trade --symbol MULTI --mode demo \
  --bet-size 0.01 \            # 1% de equity por posición (conservador)
  --timeout 150 \              # 2.5 horas por sesión
  --close-on-exit \            # Cerrar posiciones al terminar
  --ui \                       # Dashboard para monitoreo
  --max-symbols 9              # Solo los 9 activos certificados
```

**Configuración de riesgo**:
```python
MAX_POSITIONS = 3              # Máximo 3 posiciones simultáneas
RISK_PER_TRADE = 0.01          # 1% del capital por trade
MAX_DAILY_DRAWDOWN = 0.05      # Stop si pierde 5% en un día
MAX_WEEKLY_DRAWDOWN = 0.10     # Stop si pierde 10% en una semana
```

### 2.2 Monitoreo y Métricas

**Dashboard en tiempo real**:
```python
# Métricas a monitorear cada hora:
METRICS = {
    "latency": {
        "tick_to_order": "< 10ms",
        "order_to_fill": "< 50ms",
        "signal_to_dispatch": "< 5ms",
    },
    "system_health": {
        "memory_usage": "< 4GB",
        "cpu_usage": "< 80%",
        "websocket_reconnects": "< 1/hora",
        "rate_limit_violations": "0",
    },
    "trading": {
        "signals_per_hour": "~5-10",
        "win_rate": "> 50%",
        "net_pnl": "> 0%",
        "max_drawdown": "< 5%",
        "open_positions": "<= 3",
    },
    "errors": {
        "api_errors": "0",
        "order_rejections": "0",
        "crashes": "0",
    }
}
```

**Logs estructurados**:
```python
# Cada trade registrado con:
{
    "timestamp": "2026-07-24T10:30:45Z",
    "symbol": "LTCUSDT",
    "side": "LONG",
    "entry_price": 85.42,
    "exit_price": 85.85,
    "pnl": "+0.50%",
    "duration": "45m",
    "scenario": "tactical_absorption",
    "grade": "A",
    "latency_ms": 8.3,
    "slippage_bps": 1.2,
}
```

### 2.3 Duración y Objetivos

**Duración mínima**: 2 semanas (14 días)

**Objetivos de Fase 2**:
```python
CRITERIOS_EXITO = {
    "net_pnl": "> +0.10%",           # Rentabilidad neta positiva
    "win_rate": "45-70%",            # Rango esperado
    "max_drawdown": "< 5%",          # Control de riesgo
    "latencia_avg": "< 10ms",        # Performance
    "crashes": "0",                  # Estabilidad
    "rate_limit_violations": "0",    # Cumplimiento
    "trades_totales": "> 50",        # Muestra estadística
}
```

**Criterios de fallo (abortar inmediatamente)**:
```python
CRITERIOS_FALLO = {
    "net_pnl": "< -5%",
    "max_drawdown": "> 10%",
    "crashes": "> 2 en 14 días",
    "latencia_avg": "> 50ms",
    "rate_limit_violations": "> 0",
}
```

### 2.4 Análisis Post-Paper Trading

**Al final de las 2 semanas**:
```python
# 1. Comparar con backtests
for symbol in PAPER_TRADING_PHASE1:
    compare_paper_vs_backtest(
        symbol,
        paper_pnl,
        paper_win_rate,
        paper_signal_count,
        backtest_pnl,
        backtest_win_rate,
        backtest_signal_count,
    )

# 2. Identificar discrepancias
discrepancies = analyze_gaps(paper_results, backtest_results)

# 3. Calcular slippage real
real_slippage = measure_slippage(paper_trades)

# 4. Validar edge se mantiene
edge_intact = verify_edge(paper_results, expected_edge)
```

**Decisión al final de Fase 2**:

| Resultado | Acción |
|-----------|--------|
| ✅ Todos los criterios de éxito cumplidos | Continuar a Fase 3 (optimizar BTC/ETH) |
| ⚠️ Criterios parciales (ej. pnl positivo pero drawdown alto) | Ajustar parámetros, repetir Fase 2 |
| ❌ Criterios de fallo activados | Abortar, debuggear, volver a Fase 1 |

---

## ⚙️ Fase 3: Optimización de BTC/ETH (Semanas 3-4)

### 3.1 Pre-requisitos para Optimizar BTC/ETH

**Antes de empezar**:
- [ ] Fase 2 completada con éxito (paper trading rentable)
- [ ] Sistema validado en producción con 9 activos
- [ ] Infraestructura estable sin crashes
- [ ] Memoria suficiente disponible (> 8GB)
- [ ] Tiempo de CPU disponible (optimización lleva 4-8 horas cada uno)

### 3.2 Optimización de BTC

**Procedimiento**:
```bash
# 1. Verificar datasets disponibles
ls data/datasets/daily_backtest_ready/ | grep BTCUSDT

# 2. Ejecutar optimización (puede tomar 4-8 horas)
python scripts/cluster_optimizer.py \
  --symbol BTCUSDT \
  --iterations 100 \
  --param-groups all \
  --resume  # Si falla, puede retomar

# 3. Validar resultados
python scripts/backtest_runner.py \
  --mode audit \
  --symbol BTCUSDT \
  --run-type audit

# 4. Ejecutar Edge Auditor
python utils/setup_edge_auditor.py \
  --db data/historian_BTCUSDT.db \
  --window 21600
```

**Métricas esperadas**:
- Net Taker > +0.15% (mínimo aceptable)
- MFE/MAE > 1.2 (edge direccional)
- Señales >= 50 (muestra suficiente)

**Si optimización falla**:
- Edge < +0.15% → Excluir BTC temporalmente
- Edge > +0.15% → Continuar a validación

### 3.3 Optimización de ETH

**Procedimiento** (idéntico a BTC):
```bash
# 1. Verificar datasets
ls data/datasets/daily_backtest_ready/ | grep ETHUSDT

# 2. Optimización (puede tomar 6-10 horas por tamaño)
python scripts/cluster_optimizer.py \
  --symbol ETHUSDT \
  --iterations 100 \
  --param-groups all \
  --resume

# 3-4. Validación igual que BTC
```

**Precaución especial para ETH**:
- Usar `--sequential` en descarga de datos si es necesario
- Monitorear memoria durante optimización
- Si OOM → reducir iteraciones o usar máquina con más RAM

### 3.4 Decisión sobre BTC/ETH

**Post-optimización, evaluar**:

| Resultado BTC | Resultado ETH | Decisión |
|---------------|---------------|----------|
| Edge > +0.15% | Edge > +0.15% | Incluir ambos en Fase 4 |
| Edge > +0.15% | Edge < +0.15% | Incluir solo BTC en Fase 4 |
| Edge < +0.15% | Edge > +0.15% | Incluir solo ETH en Fase 4 |
| Edge < +0.15% | Edge < +0.15% | Excluir ambos, ir a live sin BTC/ETH |

**Nota**: No forzar inclusión si edge es marginal. Mejor un sistema estable con 9 activos que uno inestable con 11.

---

## 🔬 Fase 4: Paper Trading Extendido (Semanas 4-5)

### 4.1 Configuración con BTC/ETH (si aplicable)

**Si BTC y/o ETH pasaron optimización**:
```python
PAPER_TRADING_PHASE2 = PAPER_TRADING_PHASE1.copy()

if btc_edge > 0.15:
    PAPER_TRADING_PHASE2.append("BTCUSDT")

if eth_edge > 0.15:
    PAPER_TRADING_PHASE2.append("ETHUSDT")

# Máximo 11 activos
```

**Parámetros ajustados**:
```bash
python main.py --run-type trade --symbol MULTI --mode demo \
  --bet-size 0.008 \            # Reducir a 0.8% por más activos
  --timeout 150 \
  --close-on-exit \
  --ui \
  --max-symbols ${len(PAPER_TRADING_PHASE2)}
```

### 4.2 Monitoreo Intensivo de BTC/ETH

**Métricas adicionales para BTC/ETH**:
```python
BTC_ETH_METRICS = {
    "memory_usage_eth": "< 6GB",           # ETH consume más memoria
    "latencia_eth": "< 15ms",              # Más permisivo por velocidad
    "rate_limit_eth": "< 0.8 * limit",     # Más headroom por volumen
    "websocket_reconnects_eth": "< 2/hora",# Más reconexiones esperadas
    "eth_signals_per_hour": "~5-15",       # Más señales por velocidad
}
```

**Alertas específicas**:
```python
# Alertar si:
if memory_usage > 6 * GB:
    alert("Posible OOM con ETH - considerar excluir")

if eth_latency > 20 * ms:
    alert("ETH no puede mantener ritmo - reducir activos")

if eth_signals == 0 after 2_hours:
    alert("ETH no genera señales - posible bug")
```

### 4.3 Duración y Objetivos de Fase 4

**Duración**: 2 semanas adicionales (total 4 semanas de paper trading)

**Objetivos**:
- Sistema estable con todos los activos
- Rentabilidad mantenida o mejorada
- Zero crashes relacionados con BTC/ETH
- Confianza alta en infraestructura

---

## 🚀 Fase 5: Go/No-Go Decision (Semana 6)

### 5.1 Checklist Final de Certificación

**Infraestructura**:
- [ ] Zero crashes en 4 semanas de paper trading
- [ ] Latencia promedio < 10ms (sin ETH) o < 15ms (con ETH)
- [ ] Rate limit violations = 0
- [ ] WebSocket reconnects < 2/hora
- [ ] Memory stable (no growth > 100MB/semana)

**Trading**:
- [ ] Net PnL > 0% (rentable en paper trading)
- [ ] Win Rate en rango esperado (45-70%)
- [ ] Max drawdown < 10%
- [ ] Slippage real < 0.02%
- [ ] Edge intacto vs backtest (diferencia < 20%)

**Riesgo**:
- [ ] Max loss streak conocido y tolerable
- [ ] Capital suficiente para drawdown máximo
- [ ] Stop loss de portfolio configurado
- [ ] Emergency shutdown probado

**Operaciones**:
- [ ] Dashboard monitoreo funcionando
- [ ] Logs accesibles y analizables
- [ ] Alertas configuradas
- [ ] Plan de contingencia documentado

### 5.2 Decisión Final

**GO (ir a live demo)**:
- Todos los checkboxes completados
- Net PnL > +0.10% en paper trading
- Confianza alta en sistema

**NO-GO (no ir a live)**:
- Algún checkbox fallido
- Net PnL < 0%
- Crashes recurrentes
- Edge erosionado

**Iterar**:
- Fallos menores → ajustar y repetir Fase 4
- Fallos mayores → volver a Fase 1 o Fase 2

### 5.3 Configuración de Live Demo

**Si GO decision**:
```bash
# Capital inicial conservador
INITIAL_CAPITAL = 100  # USD

# Parámetros de live
python main.py --run-type trade --symbol MULTI --mode live \
  --bet-size 0.005 \            # Muy conservador: 0.5% por trade
  --timeout 150 \
  --close-on-exit \
  --ui \
  --max-symbols 9-11            # Según resultados de paper trading

# Stops de emergencia
MAX_DAILY_LOSS = 10  # USD
MAX_WEEKLY_LOSS = 20  # USD
EMERGENCY_STOP_LOSS = 30  # USD
```

**Monitoreo intensivo primera semana**:
- Revisar logs cada hora
- Validar que slippage real matchea paper trading
- Confirmar que edge se mantiene
- Abortar inmediatamente si pérdida > 10% del capital

---

## 📊 Cronograma Resumido

| Fase | Duración | Objetivo | Criterio de Paso |
|------|----------|----------|------------------|
| **Fase 0** | 1 día | Análisis estado actual | Edge conocido en 9+ activos |
| **Fase 1** | 1-2 semanas | Validación sistema | Non-regression + stress tests + event bus aprobados |
| **Fase 2** | 2 semanas | Paper trading inicial (sin BTC/ETH) | Net PnL > 0%, zero crashes |
| **Fase 3** | 1 semana | Optimizar BTC/ETH | Edge > +0.15% (si aplica) |
| **Fase 4** | 2 semanas | Paper trading extendido (con BTC/ETH si aplica) | Sistema estable, edge mantenido |
| **Fase 5** | 1 día | Decisión GO/NO-GO | Checklist completo |
| **Live Demo** | Indefinido | Trading real | Monitoreo continuo |

**Tiempo total estimado**: 6-8 semanas hasta live demo

---

## ⚠️ Riesgos y Mitigaciones

### Riesgo 1: Edge se erosiona en producción

**Probabilidad**: Media-Alta
**Impacto**: Alto
**Mitigación**:
- Paper trading extensivo antes de live
- Monitoreo de slippage real
- Abortar si edge < 0% en 2 semanas

### Riesgo 2: BTC/ETH no funcionan

**Probabilidad**: Media
**Impacto**: Bajo (si se excluyen al inicio)
**Mitigación**:
- Excluir en paper trading inicial
- Optimizar después de validar base
- Aceptar sistema con 9 activos si BTC/ETH fallan

### Riesgo 3: Infraestructura falla en live

**Probabilidad**: Baja-Media
**Impacto**: Alto
**Mitigación**:
- Stress tests extensivos
- Emergency shutdown probado
- Capital mínimo en live demo

### Riesgo 4: Overfitting a backtests

**Probabilidad**: Media
**Impacto**: Alto
**Mitigación**:
- Validación OOS mensual
- Paper trading antes de live
- Monitoreo de generalización

---

## 📝 Lecciones Clave

1. **Validar antes de expandir**: Primero confirma que funciona con activos fáciles, luego añade casos difíciles.

2. **Diagnóstico progresivo**: Excluir BTC/ETH permite identificar problemas claramente cuando ocurren.

3. **Paper trading no es opcional**: Backtests asumen fills perfectos, live tiene slippage real.

4. **Infraestructura importa**: El mejor alpha es inútil si el sistema crashea.

5. **Conservadurismo inicial**: Mejor perder oportunidad de profit que perder capital real.

6. **BTC/ETH son especiales**: Su microestructura única merece tratamiento separado.

---

## 🎯 Conclusión

**Estrategia recomendada**: Paper trading progresivo sin BTC/ETH → optimizar BTC/ETH → paper trading extendido → live demo.

**Razón principal**: Aislar variables permite diagnóstico claro de problemas y reduce riesgo de pérdida.

**Tiempo necesario**: 6-8 semanas para validación completa.

**Resultado esperado**: Sistema probado en producción con edge validado, listo para live con confianza.

**Si algo falla**: Volver atrás y debuggear es barato en paper trading. En live, es caro.

---

**Documentación relacionada**:
- `.agent/memory.md` - Estado actual del proyecto
- `.agent/changelog.md` - Historial de sesiones
- `CONFIGURATION.md` - Configuración del sistema
- `docs/ARCHITECTURE_MAP.md` - Arquitectura detallada
