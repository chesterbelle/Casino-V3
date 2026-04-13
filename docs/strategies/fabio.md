# Quick Scalping Strategy: Order Flow & Footprint (LTA-V4)

**Documento de Estrategia Completa**
*Independiente de implementación técnica*

---

## Índice

1. [Filosofía Fundamental](#1-filosofía-fundamental)
2. [Conceptos Base](#2-conceptos-base)
3. [Setups de Trading](#3-setups-de-trading)
4. [Gestión de Riesgo](#4-gestión-de-riesgo)
5. [Ejecución HFT](#5-ejecución-hft)
6. [Síntesis y Recomendaciones](#6-síntesis-y-recomendaciones)

---

## 1. Filosofía Fundamental

### 1.1 El Principio Central

**"Explotar la capitulación"** - El mercado no se mueve por la intención de los "grandes", sino por la **necesidad de liquidez** de los atrapados. La estrategia identifica el punto de "Liquid Trap": donde el flujo agresivo es neutralizado por la absorción institucional, forzando un giro violento por cierre de stops de los traders de ruptura.

### 1.2 Por qué Order Flow funciona para Scalping

| Característica | Ventaja para Scalping |
|----------------|----------------------|
| Filtrado de Intención | Identifica el volumen institucional real mediante el Percentil 90. |
| Delta Estacionario | Detecta frenos de precio sin el lag de indicadores técnicos. |
| Ineficiencia de Subasta | Explota el "negocio incompleto" en niveles de precio específicos. |
| Micro-Value Areas | Define zonas de equilibrio dinámicas en ventanas de 5-10 minutos. |

### 1.3 La Paradoja Bid/Ask

**Concepto crítico de Micro-Estructura:**

El footprint debe interpretarse como una colisión entre agresión y órdenes limitadas:

- **Bid NO es solo vendedores** = Vendedores agresivos (market sell) + Compradores pasivos (limit buy). Si el precio se estanca, hay **Acumulación**.
- **Ask NO es solo compradores** = Compradores agresivos (market buy) + Vendedores pasivos (limit sell). Si el precio se estanca, hay **Distribución**.
- **La clave:** El desequilibrio real ocurre cuando la agresión masiva (Delta alto) falla en desplazar el precio (Absorción institucional).

---

## 2. Conceptos Base

### 2.1 Price Clusters (Zonas de Fricción)

**Definición:** Niveles de precio donde se concentra un volumen masivo que detiene el desplazamiento. Actúan como soportes y resistencias dinámicas que se validan mediante la rotación de volumen y la divergencia de delta.

### 2.2 Stacked Imbalances (Desequilibrios Apilados)

**Definición:** Serie de 3 o más niveles de precios consecutivos con un ratio de agresión superior a 3:1. Indica una entrada masiva de capital que desplaza el mercado con fuerza y define una zona de soporte/resistencia inmediata.

### 2.3 Absorción y Delta Estacionario

**Definición:** Incapacidad del precio para avanzar a pesar de un aumento drástico en el Cumulative Delta. Indica la presencia de una orden **Iceberg** absorbiendo todo el flujo agresivo antes de un giro inminente.

### 2.4 Failed Auction (Subasta Fallida)

**Definición:** Vela que cierra con volumen agresivo en su extremo (High/Low) sin atraer continuidad. Estas zonas actúan como imanes de liquidez hacia donde el precio regresará para "finalizar el negocio".

---

## 3. Setups de Trading

### 3.1 Setup #1: Reversión por Absorción (Liquid Trap)

**Tipo:** Reversión tras limpieza de liquidez (Stop Run).

**Condiciones:**
1. El precio barre un máximo previo y sale del Micro-Value Area (mVA).
2. Aparece un pico de volumen institucional que es absorbido (Delta alto, precio estático).
3. El precio reingresa al rango previo con una divergencia negativa precio-delta.

**Entrada:** Orden Market al confirmar el reingreso al nivel del cluster previo.
**Stop Loss:** 1-2 ticks fuera del extremo del barrido de liquidez.

### 3.2 Setup #2: Continuación por Stacked Imbalance

**Tipo:** Continuación de tendencia por momentum.

**Condiciones:**
1. Detección de un desequilibrio apilado (3+ niveles) a favor del movimiento.
2. El movimiento debe estar respaldado por un aumento del volumen total de la vela.

**Entrada:** Orden Limit en el re-testeo del nivel central del desequilibrio apilado.
**Stop Loss:** Al otro lado del nivel del imbalance apilado.

### 3.3 Setup #3: Delta Divergence (Agotamiento)

**Tipo:** Reversión de micro-tendencia por agotamiento.

**Condiciones:**
1. El precio marca un nuevo extremo fuera del área de valor.
2. El Cumulative Delta diverge (se mueve en dirección opuesta al precio).

**Entrada:** Ejecución inmediata al detectar la pérdida de correlación precio-delta.
**Win Rate estimado:** 70-75% en activos de alta liquidez.

---

## 4. Gestión de Riesgo

### 4.1 Ubicación del Stop Loss
El SL es estructural: debe colocarse 1 tick detrás del cluster de volumen o del extremo donde la tesis de absorción quedaría invalidada. No se recomiendan stops fijos basados en pips.

### 4.2 Objetivos de Salida (Take Profit)
- **Target 1:** El POC (Point of Control) del área de valor actual (Reversión a la media).
- **Target 2:** El extremo opuesto del Micro-Value Area (VBP).

### 4.3 Regla de Invalidación Prematura
Si el flujo de órdenes muestra un imbalance masivo en contra de la posición antes de llegar al SL, la posición debe cerrarse manualmente por cambio en la narrativa de flujo.

---

## 5. Ejecución HFT

### 5.1 Parámetros de Calidad
- **Latencia de Señal:** Ejecución requerida en < 500ms para capturar la ineficiencia.
- **Filtro de Tamaño (Big Orders):** Ignorar trades que no pertenezcan al percentil 90 del volumen histórico cercano.
- **Filtro de Spread:** Desactivación si el spread Bid/Ask supera el promedio móvil de 5 minutos.

---

## 6. Síntesis y Recomendaciones

1. **La Divergencia es la Brújula** - La falta de correlación entre Delta y Precio es la señal más potente del sistema.
2. **El Valor manda** - Los mejores trades ocurren cuando el precio intenta salir del Value Area y falla (Fake Out institucional).
3. **Paciencia sobre Frecuencia** - El éxito radica en identificar cuándo la liquidez minorista ha sido atrapada para operar a favor del "Big Size".

---

## Apéndice A: Glosario

| Término | Definición |
|---------|------------|
| Footprint | Gráfico que muestra volumen bid/ask por nivel de precio |
| Delta | Diferencia neta entre compras y ventas agresivas (Market Orders) |
| mVA | Micro-Value Area (Rango del 70% del volumen en 5-10 min) |
| POC | Point of Control - precio con mayor volumen ejecutado |
| Absorption | Volumen agresivo frenado por órdenes limitadas (Icebergs) |
| Failed Auction | Vela que no cierra correctamente en su extremo (negocio incompleto) |

---

## Apéndice B: Referencias

**Metodologías Consultadas:**
- "Order Flow: Trading Setups" - Johannes Forthmann
- "The Strategies of Contentment" - Juan Colón (Darwinex)
- "Order Flow Trading" - GFF Brokers
- "Markets in Profile" - James Dalton

---

*Documento creado para la evaluación independiente de la estrategia LTA-V4. Independiente de implementación técnica específica.*
