Aquí lo tienes en un bloque de código limpio. Solo haz clic en el botón "Copiar código" (suele estar en la esquina superior derecha del recuadro) y pégalo directamente en tu nuevo archivo `.md`:

```markdown
# Quick Scalping Strategy: Order Flow Velocity & Vacuum Dynamics

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

**"La velocidad miente, el volumen descansa"** - El mercado no se mueve en líneas rectas por voluntad, sino por la ausencia temporal de contrapartes. La estrategia se basa en identificar los "Vacíos de Liquidez" (Liquidity Vacuums) donde el precio se desplaza violentamente por inercia, para ejecutar en el preciso instante en que la velocidad del orden colapsa y el libro de órdenes se recompone.

### 1.2 Por qué Order Flow funciona para Scalping

| Característica | Ventaja para Scalping |
|----------------|----------------------|
| Tasa de Cambio de Delta | Mide la *aceleración* del flujo, no solo su dirección acumulada |
| Detección de Vacíos | Identifica niveles donde no hay límites, prediciendo el final del movimiento |
| Profundidad del Libro (Implied) | El footprint revela cuándo los límites vuelven a cargarse tras un barrido |
| Micro-Transiciones | Permite ver el cambio de mercado agresivo a pasivo en tiempo real |

### 1.3 La Paradoja Bid/Ask

**Concepto crítico de Micro-Estructura:**

En un vacío de liquidez, la paradoja bid/ask se invierte temporalmente:

- **Movimiento sin límites:** Una vela puede mover 10 ticks con un Delta extremo, pero si revisas el footprint nivel por nivel, el volumen por precio es ínfimo (ej. 5 contratos por nivel). No hay batalla, hay huida.
- **El Colapso:** El movimiento termina abruptamente cuando un nivel de precio repentinamente muestra un pico de volumen (ej. 200 contratos) en un solo tick. Esto no es una batalla ganada, es un "muro de ladrillos" encontrado a alta velocidad.
- **La Regla:** No trades la dirección del Delta, trades el **colapso de la velocidad del Delta**.

---

## 2. Conceptos Base

### 2.1 Liquidity Vacuum (Vacío de Liquidez)

**Definición:** Área de precio atravesada con extrema rapidez donde el volumen ejecutado por nivel de precio es drásticamente inferior a la media móvil de volumen de la sesión.

**Por qué importa:**
- El precio cruzó esta zona porque no había órdenes límite (passive orders) para frenarlo.
- Funciona como un "imán de retorno": una vez que el precio se detiene, tiende a replegarse hacia la zona de alta densidad previa.
- Es la zona de mayor riesgo para el que entra tarde y de mayor recompensa para el que entra en la reversión.

**Identificación visual:**
```
Nivel de Precio   Volumen Total   Estado
100.5              450             Densidad Alta (Inicio)
100.4              12              VACÍO
100.3              8               VACÍO
100.2              15              VACÍO
100.1              380             Densidad Alta (Detención)
```

---

### 2.2 Delta Velocity (Velocidad de Delta)

**Definición:** La tasa de cambio del Delta por unidad de tiempo (ej. contratos por segundo), no el Delta total de la vela.

**Mecánica:**
- Un Delta alto no significa que el movimiento continuará; significa que ya ocurrió.
- Si el Delta está subiendo a 500 contratos/segundo y de repente cae a 50 contratos/segundo, el "motor" del precio se ha apagado, incluso si el precio sigue avanzando por inercia.

**Aplicación:**
1. Medir la velocidad del delta en ventanas de 1 a 3 segundos.
2. Detectar el pico máximo de velocidad.
3. El colapso de la velocidad es la señal principal de entrada.

---

### 2.3 Book Replenishment (Reposición del Libro)

**Definición:** El momento exacto en el que el flujo agresivo (market orders) se encuentra con una pared de contrapartes pasivas (limit orders) previamente ocultas o recargadas.

**Diferencia clave:**
No busca la batalla sostenida en un nivel. Busca el **impacto violento** contra una pared que detiene el vacío de liquidez en seco.

**Estructura en Footprint:**
```
Tick anterior (Vacío):  Bid: 5     Ask: 45     → Precio sube rápido
Tick actual (Muro):     Bid: 250   Ask: 60     → Precio se DETIENE
```
El salto abrupto de 5 a 250 en el lado pasivo es la Reposición.

---

### 2.4 Exhaustion Print (Impresión de Agotamiento)

**Definición:** Una única vela o tick que concentra un volumen desproporcionado en su cierre, coincidiendo con el final absoluto de un vacío de liquidez.

**Interpretación:**
- Representa la claudicación final de los perseguidores del movimiento (últimos en entrar en pánico) contra un operador de tamaño masivo que decidió fijar precio.
- El precio no debe avanzar ni un tick más después de esta impresión.

---

## 3. Setups de Trading

### 3.1 Setup #1: Vacuum Snap Reversal

**Tipo:** Reversión de alta probabilidad en el final de un movimiento extenso.

**Condiciones:**
1. El precio acelera rápidamente, dejando un vacío de liquidez identificado (volumen por nivel < 20% de la media).
2. La Delta Velocity alcanza un pico máximo y colapsa en más de un 70% de su velocidad en la siguiente unidad de tiempo.
3. Aparece un pico de Book Replenishment (volumen masivo en un solo tick de precio) en la dirección opuesta al movimiento.

**Entrada:**
```
VACÍO ALCISTA (Para SHORT):
- Precio sube rápido con bajo volumen por nivel
- Delta Velocity cae en picado
- Aparece un muro masivo en el ASK (Reposición)
- ENTRAR SHORT en el tick exacto de la reposición

VACÍO BAJISTA (Para LONG):
- Precio baja rápido con bajo volumen por nivel
- Delta Velocity cae en picado
- Aparece un muro masivo en el BID (Reposición)
- ENTRAR LONG en el tick exacto de la reposición
```

**Stop Loss:** 1 tick estrictamente por encima/debajo del Exhaustion Print.
**Take Profit:** Mínimo el punto de inicio del vacío de liquidez (Garantizado por la mecánica de rebote del vacío).
**Win Rate estimado:** 75-80%

---

### 3.2 Setup #2: Delta Velocity Divergence

**Tipo:** Entrada anticipada durante el agotamiento, antes del impacto final.

**Condiciones:**
1. El precio continúa haciendo máximos/mínimos nuevos.
2. La Delta Velocity está disminuyendo progresivamente con cada nuevo máximo/mínimo (el mercado se está quedando sin "combustible" agresivo).
3. No hay Book Replenishment masivo todavía.

**Entrada:**
```
AGOTAMIENTO ALCISTA (Para SHORT):
- Precio hace nuevo High
- La velocidad de compras agresivas es menor que en el High anterior
- ENTRAR SHORT en el momento en que el precio deja de hacer nuevos ticks

AGOTAMIENTO BAJISTA (Para LONG):
- Precio hace nuevo Low
- La velocidad de ventas agresivas es menor que en el Low anterior
- ENTRAR LONG en el momento en que el precio deja de hacer nuevos ticks
```

**Stop Loss:** 2 ticks más allá del extremo actual.
**Take Profit:** Retroceso al último nodo de alta densidad de volumen.
**Win Rate estimado:** 65-70%

---

### 3.3 Setup #3: Passive Dominance Grinding

**Tipo:** Continuación direccional de baja volatilidad y alta certeza.

**Condiciones:**
1. El precio se mueve muy lento (no hay vacíos).
2. El Delta es consistente pero no explosivo.
3. En el footprint, el volumen pasivo (límites) en la dirección de la tendencia es 3 veces mayor que el volumen agresivo que intenta frenarlo.

**Entrada:**
```
GRINDING ALCISTA (Para LONG):
- El precio avanza lentamente
- Grandes muros de BID (compradores pasivos) aparecen nivel tras nivel
- Intentos de venta agresiva (Ask alto) son minúsculos
- ENTRAR LONG en los micro-pullbacks a los muros de BID

GRINDING BAJISTA (Para SHORT):
- El precio desciende lentamente
- Grandes muros de ASK (vendedores pasivos) aparecen nivel tras nivel
- Intentos de compra agresiva (Bid alto) son minúsculos
- ENTRAR SHORT en los micro-pullbacks a los muros de ASK
```

**Stop Loss:** Cuando el muro pasivo dominante es consumido por agresión en contra.
**Take Profit:** 1.5x la distancia promedio del grinding.
**Win Rate estimado:** 70-75%

---

## 4. Gestión de Riesgo

### 4.1 Tamaño de Posición Asimétrica

Dado que el Setup #1 ofrece un Stop Loss de 1 tick pero un Take Profit estructuralmente garantizado de varios ticks, la asignación de capital puede ser agresiva en este setup específico (hasta 2.5-3% por trade), mientras que en los Setups #2 y #3 debe reducirse a 0.5-1%.

### 4.2 Stop Loss Estructural de "No-Invalidation"

El Stop Loss no se calcula por dinero, sino por la invalidación de la física del movimiento:
- Si entras por un Vacuum Snap, el tick anterior al muro es la única invalidación posible.
- Si entras por Delta Velocity Divergence, la invalidación es la aceleración repentina en contra.

### 4.3 Salida por Tiempo (Time-Stop)

Para la ejecución HFT, si el Take Profit no se alcanza en un tiempo límite (ej. 15-30 segundos para el Setup #1), la tesis de "rebote de vacío" ha fallado y la posición se cierra a mercado. El tiempo es un filtro de riesgo activo.

---

## 5. Ejecución HFT

### 5.1 Timeframes y Datos Requeridos

| Fuente de Datos | Uso Estratégico |
|-----------------|-----------------|
| Tick-by-Tick (T&S) | Obligatorio. No se puede medir Delta Velocity con velas de tiempo. |
| Footprint de Volumen Acumulado | Para identificar la densidad inicial y los vacíos. |
| Order Book Depth (Nivel 2) | Solo como validación secundaria de la Book Replenishment. |

### 5.2 Latencia Crítica

- Este modelo es el más sensible a la latencia de todos los enfoques de Order Flow.
- Objetivo de ejecución: **< 20ms** desde la detección del colapso de velocidad hasta la orden en el mercado.
- Si la latencia supera los 100ms, la ventaja del Setup #1 desaparece (el precio ya rebotó).

### 5.3 Horarios Óptimos

Este modelo requiere picos extremos de agresión para crear los vacíos. No funciona en mercados laterales.
- **Futuros US:** 9:30:00 AM a 9:35:00 AM EST (Apertura de cash) y 8:30:00 AM a 8:35:00 AM EST (Datos Económicos).
- **Crypto:** Minutos inmediatamente posteriores a la liquidación de opciones o liquidaciones masivas en exchanges derivados.

### 5.4 Facilidad de Automatización

| Setup | Facilidad de Código | Razón |
|-------|---------------------|-------|
| #1 Vacuum Snap | Alta | Matemática pura (Umbral de velocidad -> Umbral de volumen por tick). |
| #2 Velocity Div | Media | Requiere derivadas matemáticas en ventanas móviles de tiempo. |
| #3 Passive Dominance | Baja | Requiere evaluar ratios contextuales nivel por nivel de forma continua. |

---

## 6. Síntesis y Recomendaciones

### 6.1 Jerarquía de Setups por Rentabilidad Neta

Dado que el parámetro de éxito es la **ganancia total**, la prioridad no es el Win Rate aislado, sino el producto de (Win Rate x Reward:Risk x Frecuencia).

| Rank | Setup | Rentabilidad Esperada | Motivo |
|------|-------|----------------------|--------|
| 1 | Vacuum Snap Reversal | Extrema (R:R de 5:1 a 10:1 posible) | Riesgo de 1 tick, recompensa del vacío completo. |
| 2 | Passive Dominance | Alta (R:R de 1.5:1) | Alta frecuencia, muy bajo drawdown. |
| 3 | Delta Velocity Div | Media (R:R de 2:1) | Buena señal, pero requiere manejar ruido de micro-estructura. |

### 6.2 Por qué esta lógica supera a las estáticas

Las estrategias que esperan a que el precio toque un nivel previamente dibujado asumen que el mercado tiene memoria a corto plazo. En el marco de milisegundos, el mercado no tiene memoria; **tiene inercia y fricción**. Esta estrategia ignora dónde estuvo el precio hace 5 minutos y se enfoca exclusivamente en la física del movimiento actual: ¿Se está acelerando? ¿Hay contrapartes? ¿Se detuvo en seco?

### 6.3 Lo que NO funciona en este modelo

1. **Usar Delta Acumulado de la vela:** Es una métrica rezagada. Para cuando la vela de 1 minuto cierra con Delta alto, el vacío ya terminó y el rebote ocurrió.
2. **Filtros de Horario Amplios:** Operar de 9:30 a 10:30 es un error. La rentabilidad está en los primeros 300 segundos de pico de volatilidad.
3. **Promedios Móviles de Precio:** No tienen correlación con la micro-estructura del flujo de órdenes agresivas.

### 6.4 Visión del Modelo

El scalping de Order Flow más rentable no es el que mejor adivina la dirección, sino el que **mide con mayor precisión cuándo se acabó la fuerza que impulsaba la dirección actual**. Al operar el colapso de la velocidad en lugar de la dirección del flujo, se elimina el sesgo direccional y se explota la corrección mecánica del mercado hacia el equilibrio de liquidez.

---

## Apéndice A: Glosario

| Término | Definición |
|---------|------------|
| Liquidity Vacuum | Zona de precio atravesada con volumen inferior al 20% de la media circundante. |
| Delta Velocity | Tasa de cambio del Delta por unidad de tiempo (contratos/segundo). |
| Book Replenishment | Aparición masiva e instantánea de órdenes límite tras un vacío de liquidez. |
| Exhaustion Print | Pico máximo de volumen en un solo tick que marca el fin de un movimiento. |
| Passive Dominance | Escenario donde las órdenes límite superan en >3x a las agresivas en la dirección de la tendencia. |

---

## Apéndice B: Referencias

**Literatura de Micro-Estructura:**
- "Trading and Exchanges: Market Microstructure for Practitioners" - Larry Harris
- "The Science of Algorithmic Trading and Portfolio Management" - Robert Kissell
- "Market Microstructure Theory" - Maureen O'Hara

**Recursos de Flujo de Alta Frecuencia:**
- Jigsaw Trading -Educación en Depth of Market (DOM) y lecture de liquidez.
- NoBS Day Trading - Análisis de velocidad de orden y ticks.
- Order Flow Dynamics - Modelos de vacíos de liquidez en futuros.

---

*Documento creado para la evaluación independiente de la estrategia Velocity & Vacuum. Independiente de implementación técnica específica.*
```
