# ABSORPTION SCALPING V2.1: The Ultimate Absorption Strategy

## Filosofía Central

El mercado es una guerra entre agresores y defensores. Cuando un bando ataca con todo su volumen y no logra mover el precio, queda expuesto: se quedó sin munición. El otro bando lo devora y el precio gira.

Esta versión **V2.1 (Ultimate)** institucionaliza la estrategia mediante una arquitectura de **Triple Guardián**, eliminando la subjetividad y el sesgo direccional. No solo buscamos la absorción física; exigimos alineación con el régimen macro, estabilidad en el flujo de órdenes y ubicación estructural precisa.

La diferencia entre un trader retail y uno institucional en order flow es la disciplina de los filtros. **V2.1 no opera absorciones; opera desequilibrios de alta probabilidad certificados por auditoría.**

---

## 1. El Principio de Esfuerzo sin Resultado (Agnóstico)

### 1.1 El Concepto Simétrico
Históricamente, los sistemas de detección de absorción sufrían de un sesgo matemático: en tendencias alcistas, era más fácil detectar absorciones de venta que de compra debido a la media del delta. **V2.1 introduce el Z-Score Simétrico (Mean=0)**, lo que garantiza que la detección sea 100% agnóstica. Medimos la anomalía del volumen contra el cero absoluto, no contra la tendencia de la vela.

### 1.2 La Trampa del "Catching Knives"
Detectar absorción es fácil; sobrevivir a ella no. El mayor riesgo es entrar mientras el "tren" agresivo aún tiene inercia. Por eso, V2.1 separa estrictamente la **Detección** (Fase 1) de la **Confirmación** (Fase 2) y añade una capa de **Guardianes de Seguridad**.

---

## 2. Los Guardianes Institucionales (La Matriz de Alpha)

Para que una señal de absorción sea ejecutable, debe superar tres compuertas de seguridad lógica:

### 2.1 Guardian 0: Regime Alignment (Hard Gate)
Basado en la metodología de firmas como Axia Futures y Jigsaw Trading. No operamos contra la tendencia macro.
- **BALANCE:** Se permiten tanto entradas LARGAS como CORTAS.
- **TREND_UP:** Solo se permiten entradas LARGAS. Los shorts son bloqueados.
- **TREND_DOWN:** Solo se permiten entradas CORTAS. Los longs son bloqueados.
- **TRANSITION:** Prohibido operar. El mercado está rompiendo su estructura y es impredecible.

### 2.2 Guardian 1: Flow Exhaustion (Surge Filter)
Incluso con absorción, no entramos si el bando agresivo sigue "golpeando" con fuerza inusual.
- Utilizamos el **Flow Momentum** (Z-Score de la velocidad del delta).
- Si el impulso agresor supera ±2.5Z, la entrada se bloquea. Esperamos a que el bando atacante se fatigue antes de entrar en la contra-ofensiva.

### 2.3 Guardian 1.5: Location Gate (Ubicación Estructural)
La absorción en el "vacío" es ruido. La absorción real ocurre en niveles donde las instituciones tienen interés en defender.
- Solo se aceptan señales que ocurran a menos de **0.25%** de una zona estructural: **VAH, VAL, POC o IB (Initial Balance)**.

---

## 3. El Setup de Entrada

### 3.1 FASE 1 — Detección (AbsorptionDetector)
Identificamos un candidato que cumpla:
1. **Z-Score Simétrico > 3.0:** Volumen anormalmente extremo comparado con el resto del footprint (media 0).
2. **Concentración > 70%:** El volumen debe estar en un nivel de precio claro, no disperso.
3. **Precio Estancado:** Desplazamiento < 0.05% en la dirección del ataque.

### 3.2 FASE 2 — Confirmación (AbsorptionReversalGuardian)
Una vez detectado el candidato, esperamos el giro real (≥2 de 3 confirmaciones en ventana de 3 velas):
- **Confirmación A (Delta Reversal):** El flujo cambia de bando agresivamente.
- **Confirmación B (Price Break):** El precio rompe el nivel de absorción en sentido contrario.
- **Confirmación C (CVD Flip):** La pendiente del Cumulative Volume Delta gira.

---

## 4. Gestión de Riesgo y Operación

### 4.1 Entrada y Sizing
- **Entrada:** Market Order inmediata tras la confirmación de Fase 2.
- **Sniper Mode:** Uso obligatorio de **Limit Sniper** (Maker Orders) para capturar el rebate de comisiones, esencial en estrategias de alta frecuencia donde el edge es delgado (+0.1230% bruto).

### 4.2 Salida
- **Stop Loss (SL):** Nivel de absorción ± buffer de 0.15%. Si el precio invalida el nivel de defensa, la tesis ha muerto.
- **Take Profit (TP):** Dinámico basado en **Low Volume Nodes (LVN)**. Buscamos el primer "vacío" de liquidez donde el precio pueda correr sin resistencia.
- **Invalidación (Counter-Absorption):** Si mientras estamos en un trade aparece una absorción institucional en nuestra contra, cerramos la posición inmediatamente. El mercado ha cambiado de opinión.

---

## 5. Validación y Edge Generalizado

La arquitectura V2.1 ha sido certificada mediante un **Generalized Edge Audit** en una sección cruzada de 10 criptomonedas (SOL, SUI, ADA, LTC, etc.):
- **Expectativa Bruta:** **+0.1230%** (Promedio global).
- **Short Performance:** Históricamente el lado más rentable del sistema (+0.15%).
- **Generalización:** Efectiva en activos con alta liquidez y volatilidad estructural. Falla en activos lentos o con spread manipulado (BNB, LINK, DOGE), los cuales deben ser excluidos del universo de trading.

---

## Resumen Ejecutivo

**Ultimate Absorption V2.1** es un sistema agnóstico que mide la fatiga institucional. No adivina suelos ni techos; verifica matemáticamente que un bando ha agotado su munición en un nivel estructural clave y entra solo cuando el flujo de órdenes confirma el contraataque.

> **Regla de Oro:** La absorción es el hecho; el régimen es el permiso; el flujo es el timing; y la estructura es la ubicación. Solo cuando los cuatro coinciden, hay trade.
