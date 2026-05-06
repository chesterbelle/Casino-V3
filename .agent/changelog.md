# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE:**
> 1. **Leer este archivo completo al inicio de cada sesión**. Es la verdad absoluta del proyecto.
> 2. **Actualizar el "Estado Actual" y las "Métricas de Capa"** al final de cada sesión.
> 3. **REGLA DE ORO GIT:** 3 BOTS incompatibles en distintas ramas. NUNCA hacer merge/rebase.
> 4. **REGLA DE PUSH:** Solo tras orden expresa del usuario.

## 📝 Historial de Sesiones

### 2026-05-06: RegimeGuardian V3 — Value Position × Value Acceptance
*   **Descripción**: Reemplazo completo del sistema de detección de régimen basado en velocidad por un modelo estructural basado en Auction Market Theory (AMT). El nuevo modelo clasifica el mercado según Posición de Valor (Z-score relativo a VWAP) × Aceptación de Valor (si el mercado acepta o rechaza nuevos precios).
*   **Detalle Técnico**:
    *   `sensors/regime/market_regime.py`: Nuevo `_synthesize()` elimina TRANSITION state, reemplaza confidence por flags estructurales (`value_acceptance`, `absorption_detected`). Fix del micro layer: absorción ahora tiene dirección (opuesta al CVD agresivo), score > 0, y threshold pv_z < 1.0 (antes < 0.5).
    *   `decision/guardians/regime_guardian.py`: RegimeGuardian V3 con matriz de decisión Value Position × Value Acceptance. BALANCE+OUT_OF_VALUE=strong reversion, TREND+ACCEPTING=continuation, counter-trend BLOQUEADO salvo absorción en EXCESS. Elimina bug de "Local Consensus Override" que permitía counter-trend en tendencias fuertes.
    *   `decision/setup_engine.py`: Fix de setup_type hardcodeado — ahora usa trigger metadata para distinguir reversion vs continuation correctamente.
*   **Hallazgos y Errores**:
    *   *Micro Absorption Invisible*: La absorción devolvía score=0.0 y vote=NEUTRAL, haciendo que fuera invisible para el cálculo de régimen. El `_synthesize()` detectaba la flag pero no tenía peso. Fix: dirección opuesta + score proporcional.
    *   *Absorption Threshold Demasiado Estricto*: pv_z < 0.5 requería precio prácticamente congelado. Cambiado a pv_z < 1.0 (precio se mueve menos de lo esperado).
    *   *Absorción Sin Dirección*: La absorción es direccional (buyers absorbed → reversal DOWN, sellers absorbed → reversal UP). El micro layer perdía esta info con vote=NEUTRAL.
    *   *BALANCE IN_VALUE Bug*: El guardian hardcodeaba "(IN_VALUE)" en el reason incluso cuando Z=4.3. Fix: usar value_position real del Z-score.
    *   *Local Consensus Override*: El V2 guardian permitía counter-trend cuando micro/meso eran NEUTRAL, ignorando el macro TREND. Era el bug original que motivó esta sesión.
*   **Métricas Crudas (9 backtests, LTC × Range/Bear/Bull)**:

| Iteración | Signals | Decided | WR | Gross Exp | Net(Maker) | Continuation Exp | Reversion Exp |
|---|---|---|---|---|---|---|---|
| V2 Guardian | 48 | 21 | 52.4% | -0.023% | N/A | — | — |
| V3 (sin micro fix) | 97 | 53 | 47.2% | +0.001% | -0.079% | +0.011% | -0.018% |
| **V3 (con micro fix)** | **116** | **68** | **55.9%** | **+0.120%** | **+0.040%** | **+0.162%** | -0.005% |

    *   Continuation: 86 signals, WR 56.9%, MFE 0.318%, MAE 0.241%, Ratio 1.32 → WATCH
    *   Reversion: 30 signals, WR 52.9%, MFE 0.277%, MAE 0.240%, Ratio 1.15 → INSUFFICIENT
    *   Counter-trend bloqueados: ~250 señales (SHORT en TREND_UP, LONG en TREND_DOWN)
*   **Commit**: `a58895b` en branch `v7.3.0-total-spectrum-absorption-v3`

### 2026-05-03: Execution Unblocking & Exprimidor Profile Validation
*   **Descripción**: Se resolvió un bloqueo crítico en el sistema de ejecución (Sniper Patience Lock) que congelaba el bot después del primer trade. Se validó el flujo completo del perfil de salida EXPRIMIDOR en SOLUSDT, alcanzando 10 trades en 24h.
*   **Detalle Técnico**:
    *   `main.py`: Se inyectó la dependencia faltante `croupier.context_registry = context_registry` para conectar el orquestador con la memoria de contexto.
    *   `croupier/croupier.py`: Se corrigió el chequeo de cierre de posición (`close_position`) filtrando posiciones en estado `OFF_BOARDING` para que liberen efectivamente el candado `IN_TRADE`.
    *   `decision/guardians/statistical_location_guardian.py`: Se redujo el umbral Z-score para maximizar la recolección de señales tácticas y someter al ExitEngine a estrés de alta frecuencia.
*   **Hallazgos y Errores**:
    *   *Sniper Patience Lock Freeze*: Tras un trade, el PositionTracker hacía un Soft-Delete (`OFF_BOARDING`), lo que causaba que `Croupier` nunca enviara el comando de desbloqueo al `ContextRegistry`.
    *   *Shadow SL Performance*: El mecanismo L2 Shadow SL del perfil EXPRIMIDOR cerró prematuramente y con profit ($+0.4574) 2 operaciones, probando ser efectivo como "Winner Catcher".
### 2026-05-03: Performance O(1) & Structural Integrity (The Silicon Eye)
*   **Descripción**: Se resolvió el cuello de botella crítico en el cálculo del VWAP y se blindó el bot contra errores de naming y precisión mediante una nueva capa de metrología.
*   **Detalle Técnico**:
    *   `core/context_registry.py`: Refactorización de VWAP/STD a complejidad **O(1)** mediante sumas acumulativas y deques.
    *   `core/symbol_manager.py`: Creación del **CanonicalSymbolMapper** para unificar alias (ADAUSDT, ADA/USDT, etc).
    *   `core/tick_registry.py`: Evolución a **The Silicon Eye**; motor de inferencia probabilística que deduce el tick real observando el feed de trades.
    *   `decision/setup_engine.py` & `exit_engine.py`: Implementación de targets dinámicos. **TP = VWAP**, **SL = Entry +/- 3.5Z**.
*   **Hallazgos y Errores**:
    *   *Tick Mismatch*: Se descubrió que el bot fallaba en multi-asset porque no reconocía el formato de nombres de la exchange, aplicando un tick de `0.01` por defecto (2% en ADA), lo que rompía el Market Profile.
    *   *Volume Expansion*: La relajación de filtros (Integridad 0.01, Proximidad 0.35%) permitió certificar el Edge en 9 de 10 monedas auditadas.

### 2026-05-02: Reactive Execution Stability & Validate-All Certification
*   **Descripción**: Se alcanzó la estabilidad determinística en el pipeline reactivo eliminando las "posiciones fantasma" y se certificó la "Capa de Hierro" mediante el protocolo `@/validate-all`.
*   **Detalle Técnico**:
    *   `croupier/components/reconciliation_service.py`: Se implementó el bypass del grace period de 120s en `shutdown_mode`, permitiendo limpiezas instantáneas en auditorías.
    *   `croupier/components/reconciliation_service.py`: Se ajustó el conteo de posiciones locales para ignorar las que están en `OFF_BOARDING`, evitando falsas alarmas de desconexión masiva.
    *   `utils/validators/`: Se modernizaron todos los validadores (Layer 0-4) para alinearse con la arquitectura Absorption V1, corrigiendo errores de tipado y argumentos obsoletos.
*   **Hallazgos y Errores**:
    *   *Ghost Persistence*: El periodo de gracia de reconciliación impedía que los tests de multi-símbolo limpiaran el tracker a tiempo. La solución fue vincular la rigurosidad de la reconciliación al estado de `shutdown_mode`.
    *   *Valentino Purge*: Se confirmó la eliminación de Valentino, sustituyéndolo por el "Winner Catcher" (TP Expansion) como mecanismo primario de captura de volatilidad.

## 🏗️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Propósito**: Paridad 1:1 Demo vs Backtest, Latencia < 50ms, Integridad Contable.
*   **Hito Actual (v7.1.0)**: Estabilidad Reactiva y Cierre de Posiciones Fantasma validado.
*   **Métrica de Estrés**: Loop Lag: **1.01ms** bajo carga de 2,000 eventos/seg.
*   **Tag de Restauración**: `v7.1.0-reactive-stability-pass`

### 2. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA ✅]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Estatus**: Absorption V1 validado como única estrategia activa.

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Propósito**: Protección de capital, gestión de fees y salidas de emergencia.
*   **Exit Engine (5-Layer Stack)**:
    *   Layer 5: **Catastrophic Stop** (Drawdown > 50%).
    *   Layer 4: **Thesis Invalidation** (Flow + Wall Collapse + Counter-Absorption).
    *   Layer 3: **Winner Catcher** (TP Expansion via modify_tp).
    *   Layer 2: **Shadow Protection** (Trailing - ACTIVE).
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
*   **Meta**: RegimeGuardian V3 implementado y validado. Edge positivo (Gross +0.120%, Net Maker +0.040%).
*   **Estado de Git**: Commit `a58895b` en `v7.3.0-total-spectrum-absorption-v3`.
*   **Siguiente paso**: (1) Investigar por qué Reversion no tiene edge propio (-0.005%), (2) Considerar Limit Sniper para reducir fees y amplificar Net edge, (3) Validar con datos más recientes (2025).
