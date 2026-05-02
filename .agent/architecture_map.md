# 🗺️ Mapa Arquitectónico Global: Casino-V3 (LTA V7 Unified)

Este documento representa el análisis arquitectónico exhaustivo, incorporando el flujo completo de datos (Data Feeds), la bifurcación de modos de ejecución (Live vs Backtest) y el motor de decisión unificado. El objetivo es proporcionar un mapa claro de la deuda técnica antes de ejecutar la refactorización.

## 🔀 Bifurcación de Modos de Ejecución (Live vs Backtest)

El diseño principal de Casino-V3 es **Agnóstico al Entorno**, lo que significa que el núcleo lógico (Croupier, SetupEngine, AdaptivePlayer) es exactamente el mismo, pero las capas de entrada (Datos) y salida (Exchange) son intercambiables.

### 🔴 Modo Live / Demo (`main.py`)
*   **Data Feed:** `StreamManager` se conecta a los WebSockets de Binance y mantiene un flujo de red en tiempo real.
*   **Reloj:** Usa el reloj del sistema (`time.time()`) y un Reactor (`Clock`) con latencia real de red.
*   **Exchange:** `BinanceNativeConnector` + `ResilientConnector` (Manejo de Circuit Breakers y desconexiones) + `ExecutionProcess` (Airlock multiproceso para aislar el envío de órdenes).
*   **Monitores:** Mantiene activos los `ReconciliationWorker`, `DriftAuditor`, y `PortfolioGuard` monitoreando el balance y órdenes fantasma en tiempo real.

### 🧪 Modo Backtest (`backtest.py`)
*   **Data Feed:** `BacktestFeed` lee archivos históricos (CSV/Parquet).
*   **Reloj:** Interceptado (Monkey-patched). `time.time()` devuelve el `SIM_TIME` histórico para que la simulación sea determinista a nivel milisegundo.
*   **Exchange:** `VirtualExchangeConnector`. Simula latencia, fills (Maker/Taker), comisiones (fees) y slippage operando sobre los mismos eventos generados por el Feed.
*   **Monitores:** Módulos en tiempo real como el `DriftAuditor` y `ReconciliationWorker` se apagan (`no-op_async`) para evitar latencia innecesaria en la simulación.

---

## 🔄 El Pipeline de Ejecución Unificado (Core Architecture)

```mermaid
graph TD
    %% Entorno
    A1["Modo Live:\nBinance WS"] --> B
    A2["Modo Backtest:\nArchivos CSV/Parquet"] --> B

    %% Capa de Ingesta
    B{"Feed / Stream"} -->|Ticks/CVD| C["SensorManager + \nFootprintRegistry"]
    B -->|OHLCV| D["CandleMaker + \nContextRegistry"]

    %% Capa de Decisión (Cerebro Unificado)
    C -->|Eventos Micro| E["SetupEngine V4\n(LTA V7 Structural Absorption)"]
    D -->|Contexto Macro| E
    E -->|Señal (con Metadatos)| F["AdaptivePlayer\n(Kelly Sizing / Risk)"]

    %% Capa de Orquestación y Ejecución
    F -->|Decisión de Trade| G["Croupier Orchestrator"]
    G -->|Entrada Límite| H["OCOManager\n(Limit Sniper)"]
    G -->|Gestión y Salidas| I["ExitEngine\n(5 Capas de Riesgo)"]

    %% Capa Adaptadora (Fills)
    H -->|Orden| J{"ExchangeAdapter"}
    I -->|Cierre| J
    J -.->|Modo Live| K1["ResilientConnector\n(Binance API)"]
    J -.->|Modo Backtest| K2["VirtualExchange"]

    %% Verdad Absoluta y Persistencia
    J -->|Fills / Updates| L["PositionTracker"]
    L -->|Cierre| M["Historian (SQLite)"]
```

---

## 🧩 Estado de Componentes y Análisis Crítico (Deuda Técnica)

Al observar la arquitectura completa, se evidencia que los problemas de debugging no solo vienen de los "God Objects", sino de la fragilidad al intentar simular el mundo real (VirtualExchange) en paralelo con las exigencias agresivas del mundo en vivo (Binance).

| Componente | Líneas de Código | Riesgo Crítico / Deuda Técnica | Mejora Propuesta (Refactoring Plan) |
|------------|------------------|--------------------------------|-------------------------------------|
| **SetupEngine** | ~1268 | **Fricción Cognitiva:** Toda la lógica de negocio (LTA, Absorption, 6 Guardians, Location Gates) está mezclada con las colas asíncronas de memoria (5s window). | **Extracción de Dominio:** Mover los *Order Flow Guardians* a `decision/guardians/` y las reglas matemáticas (LVN) a `utils/structural_math.py`. El `SetupEngine` debe limitarse a rutear eventos a validadores. |
| **Croupier** | ~1575 | **Fricción de Responsabilidad:** El orquestador sigue manejando el ciclo de vida, barridos de emergencia (`emergency_sweep`), validaciones del `PortfolioGuard` y transiciones de estado de drain. | **Descentralización:** Delegar el `emergency_sweep` a un `EmergencyManager` dedicado, y aislar la lógica del `PortfolioGuard` para que el Croupier actúe solo como controlador de tráfico. |
| **OCOManager** | ~1686 | **Fricción de Concurrencia:** Contiene la lógica del "Limit Sniper" (Tracking, Retries de API, asincronía). Muy propenso a errores silenciosos si Binance responde lento, dificultando saber si el error es del código o de la red. | **Separación por Estados:** Dividir la construcción de la orden (`BracketBuilder`), el envío (`BracketSubmitter`) y la vigilancia (`BracketMonitor`). |
| **VirtualExchange** | Complejo | **Fricción de Simulación:** Simular fills exactos para las órdenes Limit (Limit Sniper) es notoriamente difícil y crea "Falsos Positivos" en Backtest vs Live. | Asegurar que el `OCOManager` no asuma comportamientos ideales en el Backtest que luego Binance rechazará (Ej. Cierres instantáneos por spread cruzado). |

## 🚀 Hoja de Ruta de Refactorización

Para tener un control total del sistema y lograr el objetivo actual (Aumentar frecuencia en SOL sin romper el código), la refactorización debe abordarse desde el núcleo de la toma de decisiones hacia afuera:

1. **Fase 1: Desacoplar Lógica de Negocio (El Cerebro)**
   Desmontar el monolito `setup_engine.py`. Extraer los Guardianes. Esto nos permitirá ver claramente, con tests unitarios simples o trazas de log directas, por qué una señal en SOL está siendo bloqueada por la microestructura o el contexto estructural.
2. **Fase 2: Simplificar la Ejecución Límite (El Brazo Armado)**
   Reducir el tamaño de `oco_manager.py` para aislar los problemas de "fills" que no se llenan en vivo pero sí en el VirtualExchange.
3. **Fase 3: Aligerar el Orquestador (El Croupier)**
   Limpiar `croupier.py` de tareas administrativas.
