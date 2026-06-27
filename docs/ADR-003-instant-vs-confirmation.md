# ADR-003: Separación de Flujo Instantáneo vs Confirmación

**Fecha:** 2026-06-27
**Estado:** Aceptado
**Autor:** Lead Developer (Casino-V3 Refactor)

---

## Contexto

El sistema AMT V10 tiene 4 escenarios de trading:
1.  **Tactical Absorption** (Detección de absorción institucional con CVD divergente).
2.  **Failed Breakout** (Breakout de Value Area con delta no confirmado).
3.  **Liquidity Exhaustion** (Múltiples tests de nivel con delta declinante).
4.  **Trend Acceptance** (Breakout + CVD confirmado + Pullback).

Sin embargo, el flujo de ejecución no es uniforme:
- **Tactical Absorption** se ejecuta de forma **instantánea** y bypassa el `SignalArbitrator` (antes `ScenarioManager`).
- Los otros **3 escenarios** fluyen a través del `SignalArbitrator` para arbitraje y filtrado.

Esto genera confusión en desarrolladores nuevos que esperan encontrar los 4 escenarios en el mismo lugar.

---

## Decisión

**Mantener la separación de flujos.**

- **Tactical Absorption** → **Fast Lane** (Señal directa a `SetupEngine`).
- **Failed Breakout / Liquidity Exhaustion / Trend Acceptance** → **Confirmation Lane** (Señal → `SignalArbitrator` → Filtro VA_GATE → Arbitraje → `SetupEngine`).

---

## Justificación (Trade-off: Latencia vs Confirmación)

### **Tactical Absorption (Latencia Crítica)**
La absorción institucional es un fenómeno de **microsegundos**:
- Ocurre en un solo tick del orderbook.
- El "wall" de absorción puede desaparecer en el siguiente tick.
- **Requerimiento:** La señal debe generarse en el **mismo tick** que se detecta. Cualquier延迟 (incluso 1 tick de espera para arbitraje) reduce la probabilidad de ejecución exitosa.
- **Decisión:** Bypasear el orquestador. No hay conflicto posible con otros escenarios (es la única señal de "absorción pura").

### **Los Otros 3 Escenarios (Confirmación Crítica)**
Estos escenarios dependen de **estructura de mercado** (Value Area, niveles, tendencias):
- Requieren múltiples ticks para confirmarse (ej. un breakout debe fallar y regresar, un nivel debe testearse 3 veces).
- **Requerimiento:** Precisión sobre latencia. Es mejor esperar 1-2 ticks y confirmar que la estructura se cumple, que entrar rápido y falso.
- **Beneficio del `SignalArbitrator`:**
  1.  **VA_GATE:** Filtra señales de mean-reversion en regímenes de tendencia (evita operar en contra del régimen).
  2.  **Arbitraje de Conflictos:** Si `Failed Breakout` dice SHORT y `Trend Acceptance` dice LONG en el mismo tick, el arbitrador decide por prioridad × score.
  3.  **Fusión de Señales:** Si 2 escenarios dicen LONG, se puede aumentar la convicción.

---

## Consecuencias

### **Positivas:**
- **Tactical Absorption:** Máxima velocidad de ejecución. Atrapa la absorción en el tick exacto.
- **Los otros 3:** Mayor calidad de señal gracias al filtrado por régimen y al arbitraje.
- **Claridad:** Cada escenario está optimizado para su propósito (velocidad vs estructura).

### **Negativas:**
- **Complejidad Cognitiva:** Un desarrollador nuevo debe entender que hay 2 flujos distintos. (Esta deuda se paga con este ADR).
- **Debugging:** Si una señal de absorción no aparece, no se debe buscar en el `SignalArbitrator`, sino en el detector directo.

---

## Mapa de Flujo

```
Tick → PressureEngine (Calcula features)
         ↓
         ├─→ TacticalAbsorptionDetector → (Si detecta) → SetupEngine → Orden
         │    [Fast Lane: Sin filtros, sin arbitraje]
         │
         └─→ SignalArbitrator
              ├─→ FailedBreakoutDetector
              ├─→ LiquidityExhaustionDetector
              ├─→ TrendAcceptanceDetector
              │
              ├─→ [VA_GATE Filter] (¿Régimen permite esta señal?)
              ├─→ [Conflict Resolution] (¿LONG vs SHORT? Gana mayor convicción)
              │
              └─→ SetupEngine → Orden
                   [Confirmation Lane: Con filtros y arbitraje]
```

---

## Notas para Futuros Desarrolladores

1.  **NO intentes "unificar" el flujo.** Mover `TacticalAbsorption` al `SignalArbitrator` rompería su ventaja de latencia.
2.  **Si debuggas una señal de absorción:** Ve directo a `decision/scenarios/tactical_absorption.py`. No está en el `SignalArbitrator`.
3.  **Si debuggas una señal de breakout/exhaustion/trend:** Ve al `SignalArbitrator` (`decision/signal_arbitrator.py`) y revisa el VA_GATE.

---

## Referencias

- Archivo: `decision/scenarios/tactical_absorption.py` (Detector instantáneo).
- Archivo: `decision/signal_arbitrator.py` (Orquestador de confirmación).
- Documento: `docs/ARCHITECTURE_MAP.md` (Diagrama general del sistema).
