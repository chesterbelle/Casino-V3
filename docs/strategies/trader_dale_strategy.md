# Quick Scalping Strategy: Order Flow & Footprint

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

**"Seguir a los grandes"** - La estrategia se basa en detectar y seguir la actividad de instituciones que mueven el mercado. Los traders minoristas somos "peces pequeños" que podemos beneficiarnos siguiendo las huellas de los "tiburones".

### 1.2 Por qué Order Flow funciona para Scalping

| Característica | Ventaja para Scalping |
|----------------|----------------------|
| Visibilidad de volumen | Sabes QUIÉN está operando y CUÁNTO |
| Señales leading | Delta e imbalance anticipan movimiento |
| Micro-estructura | Ves lo que otros no ven en el price action |
| Velocidad | Reaccionas en segundos, no en minutos |

### 1.3 La Paradoja Bid/Ask

**Concepto crítico de Dale:**

El footprint muestra bid (izquierda) y ask (derecha), pero:

- **Bid NO es solo vendedores** = Vendedores agresivos (market sell) + Compradores pasivos (limit buy)
- **Ask NO es solo compradores** = Compradores agresivos (market buy) + Vendedores pasivos (limit sell)

**¿Cómo distinguir?** Solo por contexto:
- En tendencia bajista sin soporte → Bid = vendedores agresivos
- En soporte con volumen pesado → Bid = compradores pasivos (absorción)

---

## 2. Conceptos Base

### 2.1 Volume Clusters (Zonas de Volumen Pesado)

**Definición:** Niveles de precio donde se concentra volumen significativamente mayor al promedio.

**Por qué importa:**
- Revelan actividad institucional
- Funcionan como soporte/resistencia dinámico
- El precio tiende a reaccionar al volver a estos niveles

**Identificación visual:**
```
Footprint con celdas más oscuras = mayor volumen
Cluster significativo = 3x o más el volumen promedio del nivel
```

**Aplicación en scalping:**
1. Identificar clusters en las últimas 5-10 velas
2. Marcar como niveles de referencia
3. Esperar reacción del precio al acercarse

---

### 2.2 Stacked Imbalances (Desequilibrios Apilados)

**Definición:** Serie de desequilibrios consecutivos en la misma dirección.

**Ejemplo visual:**
```
Precio    Bid    Ask    → Imbalance
100.5     50     200    ← Compradores dominan
100.4     45     180    ← Compradores dominan
100.3     40     150    ← Compradores dominan
```

**Tres desequilibrios seguidos = Stacked Imbalance**

**Interpretación:**
- Indica continuación de momentum
- Funciona como zona de soporte/resistencia
- Confirma dirección del movimiento

**Ratio de imbalance típico:**
- Imbalance significativo: 3:1 o mayor (ask:bid o bid:ask)
- Stacked: Mínimo 3 niveles consecutivos

---

### 2.3 Absorption (Absorción)

**Definición:** Volumen pesado en AMBOS lados (bid y ask) sin movimiento de precio significativo.

**Mecánica:**
```
Escenario en RESISTENCIA:

Precio llega a resistencia
Volumen masivo aparece:
  - Ask: 500+ contratos (vendedores pasivos con limit orders)
  - Bid: 400+ contratos (compradores agresivos con market orders)

Precio NO sube → Compradores siendo absorbidos
Resultado: Reversión bajista
```

**Escenario en SOPORTE:**
```
Precio llega a soporte
Volumen masivo aparece:
  - Bid: 500+ contratos (compradores pasivos con limit orders)
  - Ask: 300+ contratos (vendedores agresivos con market orders)

Precio NO baja → Vendedores siendo absorbidos
Resultado: Reversión alcista
```

**Señal de entrada:**
- Esperar que el volumen se agote
- Entrar cuando el precio comienza a revertir
- Stop al otro lado del nivel

---

### 2.4 Trapped Traders (Traders Atrapados)

**Definición:** Traders que entraron en dirección de un movimiento que falló en continuar.

**Patrón:**
```
1. Precio sube + Imbalance comprador fuerte en el high
   → Señal clara de continuación alcista

2. Siguiente vela: Precio BAJA
   → Los compradores están "atrapados"

3. Estos traders eventualmente venderán para salir
   → Acelera el movimiento bajista
```

**Identificación:**
- Imbalance fuerte o volumen pesado en extremo de vela
- Siguiente vela va en dirección OPUESTA
- Señal de reversión inminente

**Nota de Dale:** "No están realmente atrapados - pueden salir cuando quieran. Pero el término se usa porque entraron en el momento equivocado y ahora presionarán el mercado en dirección opuesta."

---

### 2.5 Cumulative Delta Divergence

**Definición:** Divergencia entre el movimiento del precio y el cumulative delta.

**Cumulative Delta:** Suma acumulada de (volumen ask - volumen bid). Indica presión neta compradora/vendedora.

**Tipos de divergencia:**

| Precio | Delta | Interpretación |
|--------|-------|----------------|
| Sube | Baja/Plano | Compradores perdiendo fuerza → Reversión bajista |
| Baja | Sube/Plano | Vendedores perdiendo fuerza → Reversión alcista |

**Principio clave de Dale:**
> "El precio SIEMPRE sigue al delta eventualmente"

**Aplicación:**
1. Precio aproximándose a soporte/resistencia
2. Delta divergiendo mientras precio continúa
3. Entrar cuando precio toca el nivel
4. Expectativa: Precio seguirá al delta

---

### 2.6 Failed Auction (Subasta Fallida)

**Definición:** Vela que no cierra correctamente en su extremo.

**Estructura correcta de vela:**
```
HIGH correcto:
  Bid: 0      ← Nadie vendió en el high
  Ask: XXX    ← Hubo compradores

LOW correcto:
  Bid: XXX    ← Hubo vendedores
  Ask: 0      ← Nadie compró en el low
```

**Failed Auction:**
```
HIGH con Failed Auction:
  Bid: 50     ← Hubo ventas en el high (no debería)
  Ask: XXX

LOW con Failed Auction:
  Bid: XXX
  Ask: 30     ← Hubo compras en el low (no debería)
```

**Interpretación:**
- El mercado "debería" haber continuado pero no lo hizo
- Zona de "negocio incompleto"
- El precio tiende a volver a testear estos niveles

**Uso práctico:**
- Clusters de failed auctions = zona de atracción
- No entrar solo por esto - usar como nivel de referencia
- Si precio se acerca, alta probabilidad de testeo

---

### 2.7 Big Orders (Órdenes Grandes)

**Definición:** Órdenes individuales de tamaño inusual (iceberg o single large order).

**Detección:**
- Usar "Trades Filter" que muestra solo órdenes grandes
- Tamaño significativo: 3-5x el tamaño promedio de orden
- Ejemplo: 500+ contratos en ES donde el promedio es 50-100

**Interpretación por ubicación:**

| Ubicación | Bid/Ask | Probable tipo |
|-----------|---------|---------------|
| En soporte | Bid | Buy Limit (comprador pasivo institucional) |
| En resistencia | Ask | Sell Limit (vendedor pasivo institucional) |
| En tendencia | Bid | Market Sell (vendedor agresivo) |
| En tendencia | Ask | Market Buy (comprador agresivo) |

**Señal:**
1. Precio toca nivel clave
2. Aparece orden grande
3. Confirmación de que el nivel es válido
4. Entrar en dirección de la reversión/continuación

---

### 2.8 Market Profile Concepts (Dalton)

**Value Area (VA):** Rango de precios donde se concentró el 70% del volumen.

**Componentes:**
- **POC (Point of Control):** Precio con mayor volumen
- **VAH (Value Area High):** Extremo superior del VA
- **VAL (Value Area Low):** Extremo inferior del VA

**Aplicación en scalping:**

| Situación | Acción |
|-----------|--------|
| Precio dentro del VA | Mercado en balance - fade en extremos |
| Precio rompe VAH | Posible tendencia alcista - buscar continuación |
| Precio rompe VAL | Posible tendencia bajista - buscar continuación |
| Precio rechaza VAH/VAL | Reversión - entrar contra el movimiento |

**Initial Balance (IB):** Rango de la primera hora de sesión.

**Adaptación para scalping:**
- IB tradicional (60 min) es demasiado largo
- Para HFT: Usar "micro-IB" de 5-10 minutos
- Funciona como referencia de rango inicial

**Day Types (Dalton):**

| Tipo | Característica | Estrategia |
|------|----------------|------------|
| Trend Day | Extensión > 100% del IB | Seguir dirección, no fade |
| Normal Day | Extensión 20-100% | Ambos lados funcionan |
| Range Day | Extensión < 20% | Fade en extremos del IB |

---

## 3. Setups de Trading

### 3.1 Setup #1: Absorption Reversal

**Tipo:** Reversión en niveles clave

**Condiciones:**
1. Precio aproximándose a soporte/resistencia identificado
2. Volumen pesado aparece en AMBOS lados del footprint
3. Precio NO progresa a través del nivel
4. Delta muestra agotamiento

**Entrada:**
```
En SOPORTE:
- Esperar volumen pesado en bid + ask
- Precio detiene su descenso
- Delta estabiliza o sube
- ENTRAR LONG cuando precio comienza a subir

En RESISTENCIA:
- Esperar volumen pesado en bid + ask
- Precio detiene su ascenso
- Delta estabiliza o baja
- ENTRAR SHORT cuando precio comienza a bajar
```

**Stop Loss:** 1-2 ticks al otro lado del nivel

**Take Profit:** Próximo nivel de volumen o Value Area opuesto

**Win Rate estimado:** 65-70% (según Dale)

---

### 3.2 Setup #2: Stacked Imbalance Continuation

**Tipo:** Continuación de momentum

**Condiciones:**
1. Tres o más desequilibrios consecutivos en misma dirección
2. En dirección de la tendencia actual
3. No en nivel de soporte/resistencia importante

**Entrada:**
```
ALCISTA:
- 3+ imbalances compradores apilados
- Precio en movimiento alcista
- ENTRAR LONG en el primer pullback al stacked imbalance

BAJISTA:
- 3+ imbalances vendedores apilados
- Precio en movimiento bajista
- ENTRAR SHORT en el primer pullback al stacked imbalance
```

**Stop Loss:** Al otro lado del stacked imbalance

**Take Profit:** Extensión igual al rango del movimiento previo

**Win Rate estimado:** 60-65%

---

### 3.3 Setup #3: Trapped Traders Reversal

**Tipo:** Reversión rápida

**Condiciones:**
1. Imbalance fuerte o volumen pesado en extremo de vela
2. Señal clara de continuación en esa dirección
3. Siguiente vela va en dirección OPUESTA

**Entrada:**
```
TRAPPED BUYERS:
- Vela muestra imbalance comprador fuerte en el high
- Siguiente vela abre y baja inmediatamente
- ENTRAR SHORT en la apertura de la segunda vela

TRAPPED SELLERS:
- Vela muestra imbalance vendedor fuerte en el low
- Siguiente vela abre y sube inmediatamente
- ENTRAR LONG en la apertura de la segunda vela
```

**Stop Loss:** 2-3 ticks más allá del extremo de la vela trampa

**Take Profit:** Rango completo de la vela trampa

**Win Rate estimado:** 70-75%

---

### 3.4 Setup #4: Delta Divergence

**Tipo:** Reversión con confirmación

**Condiciones:**
1. Precio aproximándose a nivel clave (VAH/VAL, soporte/resistencia)
2. Delta divergiendo del precio
3. Precio toca el nivel

**Entrada:**
```
DIVERGENCIA ALCISTA (para SHORT):
- Precio sube hacia resistencia
- Delta baja o va plano
- Precio toca resistencia
- ENTRAR SHORT

DIVERGENCIA BAJISTA (para LONG):
- Precio baja hacia soporte
- Delta sube o va plano
- Precio toca soporte
- ENTRAR LONG
```

**Stop Loss:** 2-3 ticks al otro lado del nivel

**Take Profit:** Value Area opuesto o próximo nivel de volumen

**Win Rate estimado:** 70-75% (setup favorito de Dale)

---

### 3.5 Setup #5: Big Order Confirmation

**Tipo:** Confirmación de nivel

**Condiciones:**
1. Precio toca nivel clave identificado
2. Aparece orden grande (3-5x tamaño promedio)
3. En dirección apropiada (limit order en nivel)

**Entrada:**
```
En SOPORTE:
- Orden grande aparece en BID
- Probable Buy Limit institucional
- ENTRAR LONG inmediatamente

En RESISTENCIA:
- Orden grande aparece en ASK
- Probable Sell Limit institucional
- ENTRAR SHORT inmediatamente
```

**Stop Loss:** 2-3 ticks al otro lado del nivel

**Take Profit:** Próximo nivel de volumen

**Win Rate estimado:** 65-70%

---

## 4. Gestión de Riesgo

### 4.1 Tamaño de Posición

**Regla base:** 1-2% del capital por trade

**Para scalping HFT:**
- Usar 0.5-1% debido a mayor frecuencia
- Considerar correlación entre trades simultáneos

### 4.2 Stop Loss Dinámico

**Métodos:**

| Método | Cómo calcular |
|--------|---------------|
| Nivel de volumen | Al otro lado del cluster más cercano |
| Tick fijo | 3-5 ticks para futuros líquidos |
| ATR múltiplo | 0.5-1x ATR de las últimas 10 velas |
| Estructura | Al otro lado del swing high/low |

**Recomendación para HFT:** Tick fijo de 3-5 ticks

### 4.3 Take Profit

**Métodos:**

| Método | Cuándo usar |
|--------|-------------|
| Ratio fijo | R:R 1:1 o 1.5:1 para alta frecuencia |
| Nivel de volumen | Cuando hay cluster visible en dirección |
| Value Area | Target VAH/VAL o POC |
| Trailing | En movimientos de continuación |

**Recomendación para HFT:** 1.5:1 fijo o trailing agresivo

### 4.4 Máximo de Trades por Sesión

**Para evitar over-trading:**
- Límite de pérdidas consecutivas: 3
- Límite de trades perdedores por sesión: 5
- Pause después de 3 pérdidas consecutivas (15-30 min)

---

## 5. Ejecución HFT

### 5.1 Timeframes Recomendados

| Timeframe | Uso |
|-----------|-----|
| 1 minuto | Principal para scalping |
| 5 minutos | Contexto de estructura |
| Tick chart | Para entradas precisas |
| Renko/Range | Alternativa para reducir ruido |

### 5.2 Velocidad de Ejecución

**Latencia crítica:**
- Order flow requiere reacción en segundos
- Ideal: < 100ms desde señal hasta orden
- Aceptable: < 500ms

**Para bots automatizados:**
- Procesar footprint en tiempo real
- No esperar cierre de vela para señales obvias
- Fast-track para señales de alta confianza

### 5.3 Instrumentos Recomendados

**Criterios de selección:**
1. Alta liquidez (spread mínimo)
2. Datos de order flow disponibles
3. Volatilidad suficiente para targets
4. Horas activas conocidas

**Ejemplos:**
- Futuros: ES, NQ, CL, GC
- Forex: EURUSD, GBPUSD (con futuros)
- Crypto: BTCUSDT, ETHUSDT (24/7)

### 5.4 Horarios Óptimos

**Para futuros (hora local del exchange):**
- Apertura US: 9:30-10:30 EST
- London open: 3:00-5:00 AM EST
- Overlap London-NY: 8:00-11:00 AM EST

**Para crypto (24/7):**
- Alta actividad: 8:00-16:00 UTC (London)
- Peak: 13:00-16:00 UTC (Overlap)
- Evitar: 21:00-00:00 UTC (Quiet)

### 5.5 Consideraciones para Automatización

**Señales más fáciles de automatizar:**
1. Stacked Imbalance (detectable por ratio)
2. Delta Divergence (comparación numérica)
3. Absorption (volumen en ambos lados > threshold)

**Señales que requieren más validación:**
1. Trapped Traders (necesita contexto de vela siguiente)
2. Big Orders (requiere trades filter)
3. Failed Auction (necesita análisis de estructura de vela)

---

## 6. Síntesis y Recomendaciones

### 6.1 Jerarquía de Setups por Confianza

| Nivel | Setup | Win Rate | Facilidad de automatización |
|-------|-------|----------|----------------------------|
| 1 | Delta Divergence | 70-75% | Alta |
| 2 | Trapped Traders | 70-75% | Media |
| 3 | Absorption Reversal | 65-70% | Alta |
| 4 | Big Order Confirmation | 65-70% | Media |
| 5 | Stacked Imbalance | 60-65% | Alta |

### 6.2 Combinación de Setups

**Mayor probabilidad = Múltiples confirmaciones:**

Ejemplo de trade ideal:
```
1. Precio aproximándose a VAH (contexto Market Profile)
2. Delta divergiendo mientras precio sube
3. Absorption visible en footprint al tocar VAH
4. Orden grande aparece en ASK (sell limit)
5. ENTRAR SHORT

4 confirmaciones → Alta probabilidad de éxito
```

**Para HFT automatizado:**
- Priorizar setups con 2+ confirmaciones
- O setups individuales de nivel 1-2 con alta confianza

### 6.3 Lo que NO funciona

**Errores comunes:**

1. **Over-analyzing cada número** - Perderse en los detalles del footprint
2. **Ignorar contexto** - Entrar solo por señal sin considerar nivel
3. **Esperar demasiado** - Perder oportunidad por buscar "perfecto"
4. **No respetar stops** - Dejar que pérdidas pequeñas se agranden
5. **Over-trading** - Operar sin confirmaciones por aburrimiento

### 6.4 Adaptación de Dalton para Scalping

**Conceptos que SÍ aplican:**
- Value Area como niveles de referencia
- Volume clusters como soporte/resistencia
- Single prints como zonas de debilidad

**Conceptos que NO aplican directamente:**
- IB de 60 minutos (demasiado largo)
- Day Type classification (no hay "días" en crypto 24/7)
- Esperar clasificación antes de operar

**Adaptación recomendada:**
- Usar "micro-IB" de 5-10 minutos
- Operar desde el inicio con NORMAL_WINDOW por defecto
- Dejar que el contexto evolucione, no bloquear señales

### 6.5 Visión Personal del Autor

**Lo que he aprendido sintetizando esta estrategia:**

1. **Order flow es leading, no lagging** - A diferencia de indicadores técnicos, el footprint muestra intención ANTES de que el precio se mueva.

2. **Contexto es todo** - Una señal de imbalance significa cosas diferentes según dónde aparece (en soporte vs. en tendencia).

3. **La paradoja bid/ask es fundamental** - Sin entender esto, el footprint es confuso. Con entenderlo, es transparente.

4. **Simplicidad gana** - Mejor dominar 2-3 setups que conocer 10 superficialmente.

5. **Para HFT, eliminar filtros complejos** - WindowType, IB duration, Day Type - conceptos útiles para swing trading pero que bloquean scalping.

6. **El delta es el indicador más poderoso** - Divergencia entre precio y delta tiene 70-75% de win rate. Debería ser el setup principal.

---

## Apéndice A: Glosario

| Término | Definición |
|---------|------------|
| Footprint | Gráfico que muestra volumen bid/ask por nivel de precio |
| Delta | Diferencia entre volumen ask y bid (compradores - vendedores agresivos) |
| Cumulative Delta | Suma acumulada del delta |
| Imbalance | Desequilibrio significativo entre bid y ask (ratio > 3:1) |
| Stacked Imbalance | 3+ desequilibrios consecutivos en misma dirección |
| Absorption | Volumen pesado en ambos lados sin movimiento de precio |
| Volume Cluster | Zona de volumen significativamente mayor al promedio |
| Value Area | Rango donde se concentró 70% del volumen |
| POC | Point of Control - precio con mayor volumen |
| Failed Auction | Vela que no cierra correctamente en su extremo |
| Trapped Traders | Traders que entraron en dirección de movimiento que falló |

---

## Apéndice B: Referencias

**Libros:**
- "Trading Order Flow: Looking Behind the Screen" - Trader Dale
- "Order Flow: Trading Setups" - Trader Dale
- "Markets in Profile" - James Dalton
- "Mind Over Markets" - James Dalton

**Recursos online:**
- Trader Dale - trader-dale.com
- Axia Futures - axiafutures.com
- TRADEPRO Academy - tradeproacademy.com

---

*Documento creado para evaluación independiente de la estrategia. No depende de implementación técnica específica.*
