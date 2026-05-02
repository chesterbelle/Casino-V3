# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE:**
> 1. **Leer este archivo completo al inicio de cada sesión**. Es la verdad absoluta del proyecto.
> 2. **Actualizar el "Estado Actual" y las "Métricas de Capa"** al final de cada sesión.
> 3. **REGLA DE ORO GIT:** 3 BOTS incompatibles en distintas ramas. NUNCA hacer merge/rebase.
> 4. **REGLA DE PUSH:** Solo tras orden expresa del usuario.

## 📝 Historial de Sesiones

### 2026-05-01: LTA V7 Sensor Unification & Croupier Exit Engine (Capa de Hierro)
*   **Descripción**: Se resolvió el fallo de inicialización en los workers de sensores (ceguera de footprint) y se refactorizó la configuración del Motor de Salidas para evitar la esquizofrenia algorítmica.
*   **Detalle Técnico**:
    *   `core/sensor_manager.py` & `core/sensor_worker.py`: Se inyectó el símbolo en los ticks y se añadió lógica de "hot-prime" del FootprintRegistry para garantizar que cada proceso hijo inicializa correctamente su `tick_size`.
    *   `config/trading.py`: Se consolidó la configuración fragmentada del ExitEngine en un bloque maestro unificado de 5 capas, operado por un `ACTIVE_EXIT_PROFILE`.
*   **Hallazgos y Errores**:
    *   *Bug (Ceguera de sensores)*: El proceso padre acaparaba la actualización del footprint global, ocultando el hecho de que los workers no sabían procesar ticks. Se solucionó aislando el estado y garantizando la propagación de datos.
    *   *Esquizofrenia Algorítmica*: Activar múltiples salidas tácticas a la vez (ej. Invalidación + Trailing) genera conflictos. Se definió la regla de usar "Perfiles de Ejecución" puros (Exprimidor, Francotirador, Escalador).

## 🏗️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Propósito**: Paridad 1:1 Demo vs Backtest, Latencia < 50ms, Integridad Contable.
*   **Hito Actual (v7.0.0)**: Integridad de Jornadas (`parent_trade_id`) y paridad de Ledger (Delta = 0).
*   **Tag de Restauración**: `v7.0.0-absorption-v2-baseline`
*   **HFT Latency Telemetry (T0-T4)**:
    *   `t0`: Timestamp del tick en el exchange.
    *   `t1_decision_ts`: Momento de decisión en AdaptivePlayer.
    *   `t2_submit_ts`: Momento de envío al exchange (OrderManager).
    *   `t3`: Confirmación de fill del exchange.
    *   `t4_fill_ts`: Registro en PositionTracker.

### 2. Capa de Cristal (Estrategia / Alpha) — [EN EVOLUCIÓN 💎]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Tabla Comparativa de Estrategias**:

| Estrategia | Estado | Gross Expectancy | Net (Maker) | WR% | Razón de Cambio |
|------------|--------|------------------|-------------|-----|-----------------|
| **LTA V6** | Obsoleta | -0.0176% | -0.0976% | 49.5% | No viable en 2024 (Targets inalcanzables). |
| **Abs. V2.1** | **ACTUAL** | **+0.1230%** | **+0.0430%** | 57.1% | Certificada Agnóstica (SOL, LTC, ADA, SUI). |

*   **Lecciones de Cristal**:
    *   **Root Cause Analysis (FEES)**: Las comisiones consumen el 130% del PnL bruto si se entra a mercado. El MFE de las señales suele ser delgado (~0.24%), por lo que la fricción (0.066%/RT) es el enemigo #1.
    *   **Expectancia Definitiva**: El éxito se mide en % de Expectancia Bruta (WR × Avg Win % - LR × Avg Loss %).
    *   **Criterio de Viabilidad**: Gross Expectancy > 0.36% (Certificado) | > 0.12% (Viable solo con Limit Sniper).

### 3. Capa de Acero (Resiliencia / Ejecución) — [EN DESARROLLO ⚔️]
*   **Propósito**: Protección de capital, gestión de fees y salidas de emergencia.
*   **Comparativa de Ejecución (LTC 24h Audit)**:

| Metric | Baseline (Market) | Limit Sniper | Delta |
|--------|-------------------|-------------|-------|
| Trades | 30 | 29 | -1 |
| WR | 30.0% | **41.4%** | **+11.4%** |
| Fees | 4.37 | **2.64** | **-1.73 (-40%)** |
| Net | -6.28 | **-4.73** | **+1.55** |

*   **Exit Engine (5-Layer Stack)**:
    *   Layer 5: **Catastrophic Stop** (Drawdown > 50%).
    *   Layer 4: **Thesis Invalidation** (Flow + Wall Collapse + Counter-Absorption).
    *   Layer 3: **Valentino** (Scale-out 50% al 70% del TP + BE).
    *   Layer 2: **Shadow Protection** (Trailing - DISABLED por defecto).
    *   Layer 1: **Session Drain** (Salida progresiva al cerrar).

---

## 📘 Manual Técnico (Protocolos y Flags)

### CLI Flags — Propósito Exacto
*   **`--close-on-exit`**: Sweep de cierre al final. Activa **Drain Phase** defensiva si hay timeout.
*   **`--fast-track`**: Bypasea gates estructurales para testeo de infraestructura. Miente al `SetupEngine` para forzar OCOs. **NUNCA en producción**.
*   **`--audit`**: Zero-Interference Mode. Registra señales sin ejecutarlas para validar Edge puro.

### Protocolos de Validación
*   **`/fast-track-parity`**: Verifica paridad mecánica Demo vs Backtest (30 min, LTC).
*   **`/execution-quality-audit`**: Verifica pipeline asíncrono y latencia (15 min, LTC).
*   **`/edge-audit`**: Certificación de Alpha basada en Expectancia Bruta.
*   **`/long-range-edge-audit`**: Validación en condiciones Range/Bear/Bull (9 backtests).

### Reglas de Operación
1.  **Agnosticismo**: Prohibido el ajuste de parámetros por moneda. La lógica debe capturar el edge institucional global.
2.  **No Sintéticos**: Prohibido inyectar señales falsas. Si no hay trades, se investiga el bug orgánico.
3.  **Flytest**: Valida notional y precisión antes de cada sesión. BTC suele fallar por min notional ($100).

## ⚠️ Gotchas Críticos
1.  **Symbol Normalization**: Usar siempre `normalize_symbol()` (BTC/USDT:USDT ≠ BTCUSDT).
2.  **Historian 0 trades**: Si hay ejecución pero no registro, verificar `confirm_close` en PositionTracker.
3.  **Stagnation Profit-Aware**: El exit por estancamiento NUNCA debe cerrar trades ganadores.
4.  **Fill Price Bug**: Limit BUY por encima del mercado debe llenar al mejor precio (comportamiento real).

---

## 🎯 Objetivo de la Sesión Actual
*   **Meta**: Incrementar la frecuencia de trades en SOL (actual: 11/día, target: 15-20/día) sin degradar la expectancia.
*   **Estado de Git**: Tag `v7.0.0-absorption-v2-baseline` creado.
*   **Siguiente paso**: Análisis de bloqueos del `Location Gate` y `AbsorptionReversalGuardian`.
