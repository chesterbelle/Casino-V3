# Total Spectrum Absorption — Manifiesto de Trading

**Clasificación**: Estrategia Institucional de Microestructura
**Mercado**: Futuros de Criptomonedas (24/7, Binance)
**Horizonte**: Scalping Intradía (5s–15min)
**Versión**: V4 — Volume Profile Structural Routing

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

El mercado se clasifica en tiempo real según dos ejes: **Posición de Valor** (¿dónde está el precio relativa al Área de Valor?) y **Aceptación de Valor** (¿el mercado está aceptando o rechazando nuevos precios?).

La **Posición de Valor** se determina mediante **Volume Profile** (POC/VAH/VAL), no VWAP. Volume Profile refleja dónde la subasta formó consenso real; VWAP es un promedio tiempo-ponderado que asume simetría gaussiana — incompatible con la teoría de subastas.

### 2.1 Balance — El Mercado Acepta el Rango

El mercado opera dentro de un Área de Valor (Value Area) definida por Volume Profile: el rango de precios donde se concentró el 70% del volumen. POC (Point of Control) es el precio con mayor volumen; VAH y VAL son los límites superior e inferior del área.

**Operaciones con edge**:
- **Reversión desde Extremos**: Cuando el precio está fuera del Área de Valor (OUT_OF_VALUE), la reversión hacia POC es la operación natural. El mercado rechazó esos precios y vuelve al consenso.
- **Rotación Interna**: Cuando el precio está dentro del Área de Valor (IN_VALUE), la reversión a POC es estructuralmente débil (el target está demasiado cerca). En su lugar, operamos la rotación hacia el borde opuesto del área (LONG cerca de VAL → target VAH, SHORT cerca de VAH → target VAL).

### 2.2 Desequilibrio — El Mercado Rechaza el Rango

El mercado rompe el Área de Valor y acepta nuevos precios. Un trend está en formación.

**Operaciones con edge**:
- **Continuación Alineada**: Cuando el mercado acepta nuevos precios (ACCEPTING) y nuestra posición está alineada con la dirección del trend, la continuación es la operación de mayor probabilidad. El target es una extensión de 1.5× ATR desde el entry.
- **Reversión por Absorción en Exceso**: La única excepción al trend. Cuando el precio alcanza un extremo excesivo (EXCESS: más allá de VAH/VAL + 50% del ancho del VA) y detectamos absorción (agresores neutralizados), la reversión tiene edge. El mercado intentó extenderse y fue rechazado.

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

### 4.2 Regime Guardian — Routing por Posición de Valor (Volume Profile)
- Determina la posición del precio relativa al Área de Valor (IN_VALUE / OUT_OF_VALUE / EXCESS) usando POC/VAH/VAL.
- Clasifica el setup correcto para cada combinación de régimen × posición × aceptación (ver Sección 2).
- Reemplaza al antiguo Statistical Location Guard (VWAP Z-score), que rechazaba 91.6% de señales válidas porque VWAP y Market Profile son distribuciones incompatibles.

### 4.3 Spread Sanity — Protección contra Liquidez Insuficiente
- Rechaza operaciones cuando el spread bid-ask es anormalmente amplio, indicando falta de liquidez o condiciones de mercado adversas.

### 4.4 Liquidity Heatmap — Validación de Nivel
- Verifica que el precio de entrada esté cerca de un nivel de liquidez significativo (POC, VAH, VAL, IB High/Low).
- Señales lejos de estructura son ruido.

---

## 5. Arquitectura de Targets: Tres Modos de Salida

El target de cada operación se calcula según el tipo de setup, usando niveles estructurales del Volume Profile (POC/VAH/VAL), no VWAP.

### 5.1 Reversión (OUT_OF_VALUE en Balance)
- **Take Profit**: POC (centro de valor — el precio al que el mercado formó consenso).
- **Stop Loss**: Detrás de VAL + buffer (LONG) o VAH + buffer (SHORT). Si el precio rompe el Área de Valor en contra, la tesis de reversión se invalida.
- **Buffer**: 0.5× ATR detrás del nivel estructural, mínimo 3 ticks.
- **R:R Típico**: Depende de la distancia del entry al POC vs. la distancia al SL.

### 5.2 Continuación (Trend Alineado)
- **Take Profit**: 1.5× ATR desde el entry (extensión del trend).
- **Stop Loss**: POC + buffer (si el precio cruza el centro de valor, el trend se invalida).
- **R:R Típico**: 1.5:1 a 2:1.

### 5.3 Rotación (IN_VALUE en Balance)
- **Take Profit**: El más lejano entre (1.0× ATR desde el entry) y (borde opuesto del Área de Valor: VAH para LONG, VAL para SHORT). Esto asegura suficiente distancia para cubrir fees.
- **Stop Loss**: Detrás del borde más cercano del Área de Valor + buffer (VAL + buffer para LONG, VAH + buffer para SHORT). Si el precio rompe el VA, la rotación se invalida.
- **R:R Típico**: 1:1.

**Principio clave**: Los targets son relativos al **precio de entrada** y los **niveles estructurales del Volume Profile**. El ATR actúa como safety net mínimo. Si el VA es demasiado estrecho para cubrir fees, el ATR asegura una distancia mínima.

---

## 6. El Edge Cuantificado (L2 Real, V4 Volume Profile)

Todas las métricas fueron generadas con infraestructura L2 de alta fidelidad (Tardis + l2_processor). La absorción se **observa** directamente desde el order book, no se infiere.

### 6.1 Edge Audit V4 — Volume Profile Routing (LTC/USDT, 1 día RANGE)

| Métrica | Valor |
|---|---|
| Total Signals | 503 |
| Decided (W+L) | 300 (Timeouts: 203) |
| Overall Win Rate | 60.3% |
| Gross Expectancy | -0.114% |
| Net (Taker 0.12%) | -0.234% ❌ |
| Net (Maker 0.08%) | -0.194% ❌ |

### 6.2 Desglose por Setup (Dynamic TP/SL)

| Setup | n | WR% | Avg TP% | Avg SL% | MFE% | MAE% | Ratio | Exp% | Verdict |
|-------|---|-----|---------|---------|------|------|-------|------|---------|
| continuation | 8 | 62.5% | 0.427% | 1.008% | 0.466% | 0.213% | 2.19 | +0.199% | LOW_N |
| reversion | 234 | 64.9% | -0.222% | 1.260% | 0.228% | 0.194% | 1.17 | -0.586% | FAILED |
| rotation | 262 | 43.5% | 1.080% | 0.802% | 0.236% | 0.220% | 1.08 | +0.018% | FRAGILE |

### 6.3 Targets Uniformes (Edge Latente)

| Setup | Best TP/SL | WR% | Exp% | Net Taker | Net Maker |
|-------|-----------|-----|------|-----------|-----------|
| continuation | 0.4/0.4% | 80.0% | +0.240% | +0.120% | +0.160% |
| reversion | 0.4/0.4% | 56.9% | +0.056% | -0.064% | -0.024% |
| rotation | 0.3/0.3% | 56.4% | +0.039% | -0.081% | -0.041% |

**Overall uniforme**: 0.3/0.3% → WR 57.6%, Exp +0.046%, Net Taker -0.074%

### 6.4 Diagnóstico

1. **El routing V4 funciona**: +26% más señales vs V3 (503 vs 399), WR sube de 33% → 60%. Volume Profile clasifica mejor que VWAP Z.
2. **El problema sigue siendo targets dinámicos**: Reversion SL promedio = 1.260% (6.5× el MAE de 0.194%). El SL detrás de VAL/VAH es demasiado ancho para el MAE disponible.
3. **Edge latente existe**: A targets uniformes 0.3/0.3%, WR = 57.6%, Exp = +0.046%. Pero no cubre fees de taker.
4. **Continuation es prometedor**: Ratio 2.19, WR 62.5%, pero n=8 es insuficiente.
5. **Rotation: 76% timeouts** (200/262) — los targets VAH/VAL no se alcanzan en el tiempo disponible.

**Siguiente paso**: Calibrar SL tighter (usar ATR en vez de VA completa para SL) y TP más cercanos (POC en vez de VAH/VAL para rotation).

---

## 7. Por Qué Este Edge Existe

El edge de Total Spectrum Absorption se sustenta en tres ineficiencias del mercado cripto:

### 7.1 Ineficiencia de Información — Microestructura en Tiempo Real
La mayoría de los participantes de cripto operan con indicadores lagging (medias móviles, RSI, MACD). El análisis de footprint y CVD en tiempo real proporciona información sobre la intención institucional que los indicadores tradicionales no pueden capturar hasta que es demasiado tarde.

### 7.2 Ineficiencia Conductual — Trapped Traders
Cuando participantes agresivos son absorbidos en un extremo del Área de Valor, quedan "atrapados". Su necesidad de salir de la posición genera un flujo direccional adicional que acelera el movimiento a favor de nuestra tesis. Este es el mecanismo de ganancia de la reversión.

### 7.3 Ineficiencia de Régimen — Routing Correcto
La mayoría de los sistemas de trading aplican una sola lógica (reversión o continuación) independientemente del estado del mercado. Operar reversión en un trend fuerte, o continuación en un rango choppy, destruye el edge. El routing por régimen usando Volume Profile (Balance → Reversión/Rotación, Trend → Continuación) captura la probabilidad condicional correcta para cada estado.

---

## 8. Riesgos y Limitaciones

1. **Fee Sensitivity**: El edge bruto es negativo con targets dinámicos (-0.114%). Solo a targets uniformes 0.3/0.3% existe edge latente (+0.046%), insuficiente para cubrir fees de taker. La estrategia requiere ejecución maker (Limit Sniper) y/o calibración de targets.
2. **SL Calibration**: El SL detrás de VAL/VAH es demasiado ancho (avg 1.260% para reversion vs MAE 0.194%). Necesita ajuste — probablemente ATR-based con VA como máximo, no como mínimo.
3. **RANGE Fragility**: En mercados laterales sin volatilidad, el VA es estrecho y los targets dinámicos generan timeouts masivos (76% en rotation).
4. **Volume Profile Warm-up**: El sistema no puede operar hasta que SessionValueArea calcule POC/VAH/VAL. `is_structural_ready()` bloquea señales antes de tener datos.
5. **Latencia**: La detección de absorción requiere procesamiento de ticks en tiempo real. Latencias > 100ms pueden hacer que la señal llegue tarde, cuando el movimiento ya ocurrió.

---

## 9. Principio de Diseño

El edge viene de **evitar los trades incorrectos**, no de predecir mejor los correctos. Cada componente del framework existe para rechazar una categoría de operación que destruiría el edge:

- **RegimeGuardian (V4)**: Usa Volume Profile para determinar posición de valor. Rechaza operaciones contra-trend en mercados que aceptan nuevos precios. Reemplazó VWAP Z-score (que rechazaba 91.6% de señales válidas).
- **Squeeze Guard**: Rechaza entradas en zonas de caos donde el MAE erosiona cualquier ganancia.
- **Absorción como Gatillo**: Rechaza entradas basadas solo en posición estructural sin confirmación de flujo.
- **Targets por Régimen**: Targets estructurales basados en Volume Profile (POC/VAH/VAL), no VWAP. Cada setup tiene su propia lógica de TP/SL.

La suma de estos rechazos deja un portfolio de operaciones donde cada una tiene probabilidad condicional positiva por construcción.

---

## 10. Evolución del Framework

### V1 → V2: De indicadores técnicos a microestructura
Reemplazo de RSI/MACD por footprint delta y CVD como señal primaria.

### V2 → V3: De señal única a routing por régimen
Introducción de RegimeGuardian con VWAP Z-score para clasificar IN_VALUE/OUT_OF_VALUE. Implementación de tres modos de setup (reversion/continuation/rotation).

### V3 → V4: De VWAP a Volume Profile
Eliminación de VWAP Z-score del pipeline de decisiones. Razones:
- VWAP y Market Profile son distribuciones incompatibles (tiempo-ponderado vs volumen-ponderado).
- VWAP Z como hard gate rechazaba 91.6% de señales de absorción válidas.
- Volume Profile (POC/VAH/VAL) refleja consenso real de la subasta, no un promedio estadístico.
- StatisticalLocationGuardian eliminado — su función de routing la cumple mejor RegimeGuardian con Volume Profile.
- Targets cambiados de VWAP-based a Volume Profile-based (TP=POC, SL=detrás de VA + buffer).
