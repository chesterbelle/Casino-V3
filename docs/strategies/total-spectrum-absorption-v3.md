# Total Spectrum Absorption — Manifiesto de Trading

**Clasificación**: Estrategia Institucional de Microestructura
**Mercado**: Futuros de Criptomonedas (24/7, Binance)
**Horizonte**: Scalping Intradía (5s–15min)

---

## 1. Tesis Central

El mercado alterna entre dos estados fundamentales: **Balance** (aceptación de valor) y **Desequilibrio** (rechazo de valor). En cada estado, existe un tipo de operación con edge estadístico positivo. La mayoría de los traders fracasan porque aplican la misma lógica en ambos estados.

**Total Spectrum Absorption** es un framework de trading que:

1. **Identifica el estado del mercado** en tiempo real usando Auction Market Theory.
2. **Selecciona el tipo de operación correcto** para ese estado (reversión, continuación o rotación).
3. **Solo ejecuta cuando la microestructura confirma** que los participantes agresivos han sido neutralizados por liquidez institucional pasiva (absorción).

El edge no viene de predecir dirección. Viene de **saber qué tipo de operación tiene probabilidad positiva en el estado actual del mercado**, y exigir confirmación de flujo antes de entrar.

---

## 2. Los Tres Regímenes de Mercado

El mercado se clasifica en tiempo real según dos ejes: **Posición de Valor** (¿dónde está el precio relativo al valor aceptado?) y **Aceptación de Valor** (¿el mercado está aceptando o rechazando nuevos precios?).

### 2.1 Balance — El Mercado Acepta el Rango

El mercado opera dentro de un Área de Valor (Value Area) definida por el VWAP y sus bandas de desviación. El precio rota entre los límites superior e inferior del área.

**Operaciones con edge**:
- **Reversión desde Extremos**: Cuando el precio alcanza el borde del Área de Valor (OUT_OF_VALUE), la reversión hacia la media es la operación natural. Win Rate histórico: 70.4%.
- **Rotación Interna**: Cuando el precio está dentro del Área de Valor (IN_VALUE), la reversión a VWAP es estructuralmente débil (el target está demasiado cerca). En su lugar, operamos la rotación hacia el borde opuesto del área. Win Rate histórico: 55.6%.

### 2.2 Desequilibrio — El Mercado Rechaza el Rango

El mercado rompe el Área de Valor y acepta nuevos precios. Un trend está en formación.

**Operaciones con edge**:
- **Continuación Alineada**: Cuando el mercado acepta nuevos precios (ACCEPTING) y nuestra posición está alineada con la dirección del trend, la continuación es la operación de mayor probabilidad. El target es una extensión de 1.5× ATR desde el entry.
- **Reversión por Absorción en Exceso**: La única excepción al trend. Cuando el precio alcanza un extremo excesivo (EXCESS, >3σ del VWAP) y detectamos absorción (agresores neutralizados), la reversión tiene edge. El mercado intentó extenderse y fue rechazado.

### 2.3 Counter-Trend — La Trampa

Operar en contra de un trend donde el mercado está aceptando nuevos precios es la operación con mayor probabilidad de pérdida. El sistema **bloquea** estas operaciones por defecto.

La única excepción: absorción detectada en un extremo excesivo (EXCESS + REJECTING). Esto indica que el trend intentó extenderse y fue rechazado por liquidez institucional — un potencial punto de inflexión.

---

## 3. El Gatillo Táctico: Absorción Institucional

Ninguna operación se ejecuta basándose únicamente en el régimen. El sistema exige confirmación de microestructura: **Absorción**.

La absorción ocurre cuando participantes agresivos (market orders) descargan volumen masivo contra un muro de liquidez pasiva (limit orders) **sin lograr desplazar el precio significativamente**. Esto indica:

- **Agresores atrapados**: Compraron/vendieron en un extremo pero no pudieron mover el mercado. Sus posiciones son vulnerables.
- **Liquidez institucional defendiendo el nivel**: Los pasivos están absorbiendo el flujo agresivo, indicando convicción direccional.

La absorción se detecta en tiempo real mediante:
- **Delta Velocity Z-Score**: Magnitud del flujo agresivo relativa a su historia reciente (cross-sectional).
- **Price Velocity Z-Score**: Si el delta es extremo pero el precio no se mueve proporcionalmente, hay absorción.
- **Concentración y Ruido**: Filtros adicionales para distinguir absorción institucional de ruido de retail.

**Direccionalidad de la Absorción**: La absorción es direccional. Cuando compradores agresivos son absorbidos (CVD sube, precio no sube), la dirección esperada es **bajista** — los compradores atrapados tendrán que vender. Viceversa para vendedores absorbidos.

---

## 4. Filtros de Calidad Estructural

No toda absorción es igual. El sistema aplica filtros de calidad para rechazar señales de baja probabilidad:

### 4.1 Squeeze Guard — Geometría de Precio
- **Micro-Geometría**: Rechaza entradas donde el precio sigue haciendo nuevos extremos (lower lows para LONG, higher highs para SHORT). El precio debe estar estabilizando.
- **Compresión de Volatilidad**: Rechaza zonas de caos donde el rango reciente excede 2× el ATR. La volatilidad excesiva destruye el edge del scalping.

### 4.2 Statistical Location Guard — Umbral Mínimo de Extremo
- Para reversiones: el precio debe estar al menos a 2.0σ del VWAP. Operar dentro de la zona de ruido (cerca de la media) es azar.
- Para continuaciones: el precio no debe estar sobre-extendido (>3.5σ). Las extensiones extremas son peligrosas incluso en trend.

### 4.3 Spread Sanity — Protección contra Liquidez Insuficiente
- Rechaza operaciones cuando el spread bid-ask es anormalmente amplio, indicando falta de liquidez o condiciones de mercado adversas.

---

## 5. Arquitectura de Targets: Tres Modos de Salida

El target de cada operación se calcula según el tipo de setup, no de forma genérica:

### 5.1 Reversión (OUT_OF_VALUE en Balance)
- **Take Profit**: VWAP (el valor justo al que el precio tiende a regresar).
- **Stop Loss**: 3.5σ por debajo del VWAP (invalidación estadística de la tesis de reversión).
- **R:R Típico**: 1:1 a 1:2 dependiendo de la distancia del entry al VWAP.

### 5.2 Continuación (Trend Alineado)
- **Take Profit**: 1.5× ATR desde el entry (extensión del trend).
- **Stop Loss**: VWAP (si el precio cruza la media, el trend se invalida).
- **R:R Típico**: 1.5:1 a 2:1.

### 5.3 Rotación (IN_VALUE en Balance)
- **Take Profit**: El más lejano entre (1.0× ATR desde el entry) y (borde del Área de Valor). Esto asegura suficiente distancia para cubrir fees.
- **Stop Loss**: 1.0× ATR desde el entry (no en el borde opuesto del Área de Valor, que puede estar demasiado lejos).
- **R:R Típico**: 1:1.

**Principio clave**: Los targets de rotación son relativos al **precio de entrada**, no al VWAP. Si el precio está a +0.5σ del VWAP, el borde superior del Área de Valor (+1σ) está solo 0.5σ arriba — insuficiente para cubrir costos de transacción. El ATR asegura un mínimo de distancia.

---

## 6. El Edge Cuantificado

Validado mediante 9 backtests de estrés (LTC/USDT en condiciones Range, Bear y Bull, 3 días cada una, ventana MFE/MAE de 15 minutos):

### 6.1 Métricas Globales

| Métrica | Valor |
|---|---|
| Gross Expectancy | +0.155% por trade |
| Net Expectancy (Maker) | +0.075% por trade |
| Net Expectancy (Taker) | +0.035% por trade |
| Win Rate Global | 56.2% |
| Avg MFE (excursión favorable) | 0.733% |
| Avg MAE (excursión adversa) | 0.586% |

### 6.2 Desglose por Tipo de Setup

| Setup | Señales | Win Rate | Gross Expectancy |
|---|---|---|---|
| Rotación (IN_VALUE) | 81 | 55.6% | +0.104% |
| Reversión (OUT_OF_VALUE) | 27 | 70.4% | +0.108% |
| Continuación (OUT_OF_VALUE trend) | 13 | 53.8% | +0.049% |

### 6.3 Desglose por Condición de Mercado

| Condición | Señales | Win Rate | MFE/MAE Ratio | Veredicto |
|---|---|---|---|---|
| BULL (Trend Alcista) | 37 | 71.4% | 2.25 | ✅ CERTIFIED |
| RANGE (Mercado Lateral) | 31 | 50.0% | 1.34 | ⚠️ WATCH |
| BEAR (Trend Bajista) | 58 | 50.0% | 1.00 | ⚠️ WATCH |

**Observación**: El edge es más fuerte en condiciones de trend (BULL), donde la continuación y la reversión por absorción en extremos son de alta probabilidad. En RANGE, la rotación funciona pero el edge es marginal. En BEAR, el edge es neutro — el sistema no genera señales de alta calidad en trends bajistas débiles.

---

## 7. Por Qué Este Edge Existe

El edge de Total Spectrum Absorption se sustenta en tres ineficiencias del mercado cripto:

### 7.1 Ineficiencia de Información — Microestructura en Tiempo Real
La mayoría de los participantes de cripto operan con indicadores lagging (medias móviles, RSI, MACD). El análisis de footprint y CVD en tiempo real proporciona información sobre la intención institucional que los indicadores tradicionales no pueden capturar hasta que es demasiado tarde.

### 7.2 Ineficiencia Conductual — Trapped Traders
Cuando participantes agresivos son absorbidos en un extremo estadístico, quedan "atrapados". Su necesidad de salir de la posición genera un flujo direccional adicional que acelera el movimiento a favor de nuestra tesis. Este es el mecanismo de ganancia de la reversión.

### 7.3 Ineficiencia de Régimen — Routing Correcto
La mayoría de los sistemas de trading aplican una sola lógica (reversión o continuación) independientemente del estado del mercado. Operar reversión en un trend fuerte, o continuación en un rango choppy, destruye el edge. El routing por régimen (Balance → Reversión/Rotación, Trend → Continuación) captura la probabilidad condicional correcta para cada estado.

---

## 8. Riesgos y Limitaciones

1. **Fee Sensitivity**: El edge bruto (+0.155%) es delgado. Con fees de taker (0.12% round-trip), el net es +0.035%. La estrategia requiere ejecución maker o reducción de fees para ser robusta.
2. **RANGE Fragility**: En mercados laterales sin volatilidad, el edge es marginal (Ratio 1.34). La rotación depende de que el Área de Valor tenga suficiente amplitud.
3. **BEAR Neutrality**: El sistema no captura edge significativo en trends bajistas de baja confianza. Las señales de continuación SHORT en TREND_DOWN son filtradas agresivamente por los guardians.
4. **Falso Trend**: El sensor de régimen puede clasificar fluctuaciones de rango como trends de baja confianza (confidence < 0.5). Estos falsos trends generan señales de continuación que fallan en mercados que son realmente range-bound.
5. **Latencia**: La detección de absorción requiere procesamiento de ticks en tiempo real. Latencias > 100ms pueden hacer que la señal llegue tarde, cuando el movimiento ya ocurrió.

---

## 9. Principio de Diseño

El edge viene de **evitar los trades incorrectos**, no de predecir mejor los correctos. Cada componente del framework existe para rechazar una categoría de operación que destruiría el edge:

- **RegimeGuardian**: Rechaza operaciones contra-trend en mercados que aceptan nuevos precios.
- **Squeeze Guard**: Rechaza entradas en zonas de caos donde el MAE erosiona cualquier ganancia.
- **Statistical Location Guard**: Rechaza operaciones dentro de la zona de ruido estadístico.
- **Absorción como Gatillo**: Rechaza entradas basadas solo en posición estadística sin confirmación de flujo.
- **Targets por Régimen**: Rechaza targets genéricos que no respetan la estructura del setup (reversión a VWAP cuando ya estás IN_VALUE, SL en VAL cuando está 1.5σ abajo).

La suma de estos rechazos deja un portfolio de operaciones donde cada una tiene probabilidad condicional positiva por construcción.
