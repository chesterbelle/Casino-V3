# AMT Scenario-Based Trading — Manifiesto de Estrategia

**Clasificación**: Scalping de Microestructura basado en Auction Market Theory
**Mercado**: Futuros de Criptomonedas (24/7, Binance)
**Horizonte**: Scalping Intradía (5s–30min)
**Versión**: V10 — AMT Scenario Triggers + Exhaustion Confirmation

---

## 1. Tesis Central

Los mercados de futuros cripto son subastas continuas. En cada momento, la subasta está haciendo una de tres cosas: **aceptando un rango de precios** (balance), **rechazando precios extremos** (reversión), o **buscando nuevos precios** (tendencia).

La mayoría de los sistemas de trading detectan **qué está pasando** (absorción, divergencia, ruptura) pero no responden a **por qué está pasando**. Nuestra estrategia no busca patrones técnicos — busca **narrativas de mercado** completas donde la causa, la confirmación y la consecuencia están alineadas.

Cada operación responde a un escenario AMT específico con tres componentes obligatorios:

1. **Contexto estructural**: ¿Dónde estamos en la subasta? (dentro/fuera del Área de Valor)
2. **Confirmación de flujo**: ¿El agresor se está agotando o intensificando?
3. **Trigger mecánico**: ¿El evento específico que invalida la tesis opuesta ya ocurrió?

El edge no viene de la señal. **Viene de saber qué narrativa de mercado está activa** y operar exactamente esa narrativa con targets calibrados.

---

## 2. Los Cuatro Escenarios de Trading

### Escenario ① — Rechazo de Exceso (Excess Rejection)

**Narrativa AMT**: El precio se mueve fuera del Área de Valor (zona donde el 70% del volumen se negoció). Agresores atacan el extremo — pero la liquidez pasiva los absorbe. El volumen agresivo **se agota** (cada ola es más débil que la anterior). El mercado va a rechazar el exceso y volver al consenso.

**Condiciones de entrada**:
1. Precio fuera del Área de Valor (OUT_OF_VALUE o EXCESS)
2. Absorción detectada: flujo agresivo masivo sin desplazamiento de precio
3. **Agotamiento confirmado**: el delta del agresor en los últimos 2 segundos es significativamente menor que en los últimos 10 segundos (delta ratio < 0.5)
4. Confirmación de flujo: al menos 2 de 3 sensores confirman que el agresor perdió (delta flip, price break, CVD flip)

**Dirección**: Hacia el POC (centro de valor). Si los vendedores se agotaron → LONG. Si los compradores se agotaron → SHORT.

**Filtro de calidad**: Si el delta ratio > 1.5 (el agresor se está **intensificando**, no agotando), la entrada se bloquea. Entrar contra un flujo creciente es la operación más peligrosa.

**Target**: POC del Volume Profile o 1.0× ATR, lo que esté más cerca.
**Stop**: 1.0× ATR desde el entry, mínimo 0.30%.

**Edge observado** (LTC, 1 día, mercado RANGE):
- Win Rate: 64–77%
- Expectancy: +0.09% a +0.18% bruto
- Ratio MFE/MAE: 1.01–1.13

---

### Escenario ② — Ruptura Fallida (Failed Breakout)

**Narrativa AMT**: El precio rompe un nivel estructural (el límite superior o inferior del Área de Valor). Los breakout traders entran agresivamente en la dirección de la ruptura. **Pero el flujo no confirma**: el CVD (Cumulative Volume Delta) no acompaña la ruptura — la convicción es débil. El precio retorna al Área de Valor. Los breakout traders están **atrapados** en el lado equivocado.

**Condiciones de entrada**:
1. Precio rompió VAH (para SHORT) o VAL (para LONG) en los últimos 60 segundos
2. **Delta divergente**: el CVD durante la ruptura NO confirmó la dirección (CVD plano o contrario)
3. Precio retornó dentro del Área de Valor (cruzó de vuelta el nivel roto)
4. El retorno fue rápido (< 60 segundos)

**Dirección**: Opuesta a la ruptura. Ruptura al alza fallida → SHORT. Ruptura a la baja fallida → LONG.

**Mecanismo de ganancia**: Los breakout traders atrapados necesitan cerrar sus posiciones. Sus market orders de cierre generan flujo adicional a favor de nuestra tesis. Este flujo es mecánico, no discrecional.

**Edge observado** (LTC, 1 día, mercado RANGE):
- Win Rate: 36% (bajo — muchos stops)
- Expectancy: +0.08% bruto (positivo — los wins son grandes)
- Perfil: Pocas ganancias grandes, muchas pérdidas pequeñas. Estilo "big winner".

> **Nota**: Este escenario tiene un perfil de riesgo asimétrico. La WR es baja pero la expectancy es positiva porque las rupturas verdaderamente fallidas generan movimientos significativos cuando los atrapados se liquidan.

---

### Escenario ③ — Agotamiento de Liquidez (Liquidity Exhaustion)

**Narrativa AMT**: Un nivel estructural (VAH o VAL) es atacado repetidamente. Cada ataque tiene **menos fuerza** que el anterior — el delta en cada test es menor. El lado atacante está agotando su liquidez. El nivel va a sostenerse.

**Condiciones de entrada**:
1. El mismo nivel fue testeado **3 o más veces** en los últimos 120 segundos (±0.05% de tolerancia)
2. El delta en cada test sucesivo es **declinante** (cada test tiene menos volumen agresivo)
3. El precio rebotó del nivel (no se está consolidando EN el nivel)

**Dirección**: Opuesta al lado atacante. Tests repetidos de VAL sin romperlo → LONG. Tests repetidos de VAH → SHORT.

**Mecanismo de ganancia**: Cada test que falla debilita al atacante y fortalece la convicción del defensor. Después de 3+ tests fallidos con delta declinante, la probabilidad de que el nivel se sostenga es máxima.

**Edge observado** (LTC, 1 día, mercado RANGE):
- Win Rate: 67%
- Expectancy: **+0.32%** bruto (la más alta de todos los escenarios)
- Ratio MFE/MAE: 1.50

> **Este es el escenario con el mejor edge absoluto.** La selectividad es alta (pocas señales, todas de calidad). Requiere paciencia — el agotamiento toma tiempo.

---

### Escenario ④ — Aceptación de Tendencia (Trend Acceptance)

**Narrativa AMT**: El precio sale del Área de Valor con **convicción** — el CVD confirma la dirección de la ruptura. El mercado está genuinamente aceptando nuevos precios. No es una ruptura falsa; es un cambio real de valor. La entrada es en el **pullback** al nivel roto, que ahora actúa como soporte (para LONG) o resistencia (para SHORT).

**Condiciones de entrada**:
1. Precio ha estado fuera del Área de Valor durante **3 o más velas consecutivas** (1 minuto por vela)
2. CVD durante la ruptura **confirmó** la dirección (slope > umbral)
3. Precio hace pullback hacia el nivel roto (VAH o VAL) sin re-entrar completamente al Área de Valor

**Dirección**: A favor de la tendencia. Ruptura al alza confirmada + pullback a VAH → LONG. Ruptura a la baja + pullback a VAL → SHORT.

**Mecanismo de ganancia**: En una tendencia confirmada, el nivel roto (antiguo VAH/VAL) se convierte en soporte/resistencia. Los institucionales que perdieron la ruptura original compran/venden en el pullback. Este es el trade de menor riesgo en una tendencia — entras con la corriente en un nivel donde hay liquidez de soporte.

**Edge observado** (LTC, 1 día, mercado RANGE):
- Edge negativo en mercado de rango (esperado — este escenario necesita tendencias)
- Pendiente de validación en mercados BULL y BEAR

> **Nota**: Este escenario está diseñado para mercados tendenciales. Su edge negativo en un dataset de rango no lo invalida — confirma que la clasificación de régimen es correcta. Su validación requiere datasets de mercados tendenciales.

---

## 3. El Concepto de Agotamiento (Exhaustion)

El agotamiento es el concepto central que unifica los 4 escenarios. No es un indicador — es una **condición observable del flujo de órdenes**.

### ¿Qué es el agotamiento?

Cuando un lado del mercado (compradores o vendedores) ataca un nivel repetidamente con volumen decreciente, está mostrando **agotamiento**. Cada ola de agresión es más débil que la anterior porque:

- Los participantes más convictos ya entraron en las primeras olas
- Los stops de los atrapados ya fueron ejecutados
- La liquidez pasiva del otro lado sigue intacta

### ¿Cómo se mide?

Dos métricas principales:

1. **Delta Ratio**: Comparación del delta reciente (últimos 2 segundos) con el delta extendido (últimos 10 segundos). Un ratio < 0.5 indica que la agresión reciente es menos de la mitad de la agresión total — el flujo se está apagando.

2. **Volume Ratio**: Comparación del volumen reciente con el volumen extendido. Ratio < 0.4 indica que el volumen está cayendo — los participantes están retirándose.

### Validación empírica

Análisis de 155 señales con datos L2 reales (order book de Tardis):

| Grupo | Delta Ratio | Volume < 0.4 | Resultado |
|---|---|---|---|
| **Señales ganadoras** | 0.52 (agotado) | 50% | Agresor perdió fuerza → movimiento a favor |
| **Señales perdedoras** | 0.56 | 0% | Agresor aún activo → movimiento en contra |
| **Timeouts** | 1.22 (intensificándose) | 20% | Sin resolución → sin movimiento |

Las señales ganadoras tienen delta ratio 2× menor que los timeouts. Las perdedoras tienen **cero** volumen declinante — el agresor estaba activo y la entrada fue prematura.

---

## 4. Régimen de Mercado y Routing

No todos los escenarios son válidos en todas las condiciones de mercado. El framework clasifica el mercado en tiempo real para activar los escenarios correctos:

| Condición de Mercado | Escenarios Activos | Escenarios Bloqueados |
|---|---|---|
| **Balance** (dentro del Área de Valor) | ① Rechazo, ③ Agotamiento | ④ Aceptación (no hay trend) |
| **Balance** (fuera del Área de Valor) | ① Rechazo, ② Ruptura Fallida | — |
| **Tendencia confirmada** | ④ Aceptación, ③ Agotamiento | ① Rechazo (counter-trend bloqueado) |
| **Transición** (incertidumbre) | ② Ruptura Fallida | ④ Aceptación (sin confirmación) |

El routing se realiza usando **Volume Profile** (POC, VAH, VAL) y **CVD Slope** como indicadores primarios. No se usan indicadores lagging como medias móviles, RSI o MACD.

---

## 5. Gestión de Riesgo por Escenario

### Stop Loss: Uniforme por diseño

Todos los escenarios usan **SL = max(1.0× ATR, 0.30%)** desde el precio de entrada. Esto asegura que el stop no sea ni demasiado apretado (chop de mercado) ni demasiado ancho (pérdida excesiva).

### Take Profit: Específico por escenario

| Escenario | Target | Rationale |
|---|---|---|
| ① Rechazo | POC o 1.0× ATR | Reversión al consenso |
| ② Ruptura Fallida | Estructural (routing por régimen) | Los atrapados generan momentum |
| ③ Agotamiento | Estructural (routing por régimen) | Rebote del nivel sostenido |
| ④ Aceptación | 1.5× ATR (extensión de trend) | Continuación de tendencia |

### Sizing

El sizing base se ajusta por un multiplicador que combina:
- Calidad de la señal (Z-score del footprint)
- Condición de mercado (contra-trend = sizing reducido)
- Exhaustion score (mayor agotamiento = mayor convicción)

---

## 6. Por Qué Este Edge Existe

### 6.1 Información asimétrica en el order book
La absorción y el agotamiento solo son visibles analizando el flujo de órdenes tick-by-tick. Los gráficos de velas no muestran si el volumen está concentrado en olas decrecientes o si el CVD diverge de la dirección del precio. El 95% de los participantes retail no tienen acceso a esta información en tiempo real.

### 6.2 Comportamiento mecánico de los atrapados
Cuando breakout traders o agresores quedan atrapados en el lado equivocado, su salida es **inevitable y mecánica** — generan flujo direccional predecible. Este flujo no es opinión; es liquidación forzada. Es la fuente de ganancia más confiable en el mercado.

### 6.3 Narrativa completa vs. patrón aislado
La mayoría de los sistemas buscan patrones aislados (una divergencia, un cruce, un nivel). Nuestro framework exige la narrativa completa: contexto + confirmación + trigger. Esto reduce drásticamente los falsos positivos porque no solo preguntamos "¿hubo absorción?" sino "¿hubo absorción + agotamiento + en el contexto estructural correcto + con el flujo confirmando?".

---

## 7. Limitaciones Conocidas

1. **Edge marginal en mercados de rango estrecho**: En mercados sin volatilidad (ATR < 0.1%), los targets son demasiado cercanos para cubrir los costos de trading.

2. **Dependencia de datos L2**: Los escenarios requieren datos de order book en tiempo real. Sin acceso a profundidad L2, la absorción se infiere en vez de observarse — reduciendo la calidad de la señal.

3. **Timeout rate alto (>70%)**: La mayoría de las señales no alcanzan ni el TP ni el SL en la ventana de tiempo. Esto no es necesariamente un problema — indica selectividad — pero implica baja frecuencia de trades decididos.

4. **Escenario ④ sin validar en tendencia**: El escenario de Trend Acceptance mostró edge negativo en mercado de rango. Su validación requiere datasets de mercados tendenciales (bull/bear runs).

5. **Sample size limitado**: Los resultados actuales están basados en 1 día de datos (195 señales). La validación estadística rigurosa requiere múltiples días en diferentes condiciones de mercado.

---

## 8. Evolución del Framework

| Versión | Cambio | Edge |
|---|---|---|
| V1–V2 | Indicadores técnicos → Microestructura | Negativo |
| V3–V4 | Routing por régimen (Volume Profile) | Marginalmente positivo |
| V9 | ATR-based SL + corrección de 5 bugs críticos | **+0.22% bruto** |
| **V10 (AMT)** | Escenarios narrativos + Exhaustion confirmation | **+0.13% bruto (más diversificado)** |

La evolución de V9 a V10 no aumentó el edge bruto — lo **diversificó**. V9 dependía casi exclusivamente de absorción + reversión. V10 añade 3 escenarios independientes (Failed Breakout, Liquidity Exhaustion, Trend Acceptance) que capturan edge en diferentes condiciones de mercado, reduciendo la dependencia de un solo patrón.
