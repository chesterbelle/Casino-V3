# Total Spectrum Absorption — Manifiesto de Trading

**Clasificación**: Estrategia Institucional de Microestructura
**Mercado**: Futuros de Criptomonedas (24/7, Binance)
**Horizonte**: Scalping Intradía (5s–15min)
**Versión**: V9 — ATR-Based SL + Volume Profile Routing

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

La **Posición de Valor** se determina mediante **Volume Profile** (POC/VAH/VAL). Volume Profile refleja dónde la subasta formó consenso real — el rango de precios donde se concentró el 70% del volumen negociado.

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

### 4.3 Spread Sanity — Protección contra Liquidez Insuficiente
- Rechaza operaciones cuando el spread bid-ask es anormalmente amplio, indicando falta de liquidez o condiciones de mercado adversas.

### 4.4 Liquidity Heatmap — Validación de Nivel
- Verifica que el precio de entrada esté cerca de un nivel de liquidez significativo (POC, VAH, VAL, IB High/Low).
- Señales lejos de estructura son ruido.

---

## 5. Arquitectura de Targets: Tres Modos de Salida

El target de cada operación se calcula según el tipo de setup, usando niveles estructurales del Volume Profile (POC/VAH/VAL) y ATR.

### 5.1 Reversión (OUT_OF_VALUE en Balance)
- **Take Profit**: POC (centro de valor) **solo si está del lado correcto del entry** (POC > price para LONG, POC < price para SHORT). Si POC está del lado equivocado, usar 1.0× ATR desde el entry.
- **Stop Loss**: 1.0× ATR desde el entry, con **mínimo de 0.30%** (alineado con edge-audit calibration). El SL detrás de VAL/VAH era demasiado ancho (avg 1.26% vs MAE 0.194%).
- **R:R Típico**: Depende de la distancia del entry al POC vs. la distancia al SL.

### 5.2 Continuación (Trend Alineado)
- **Take Profit**: 1.5× ATR desde el entry (extensión del trend).
- **Stop Loss**: 1.0× ATR desde el entry, mínimo 0.30%.
- **R:R Típico**: 1.5:1 a 2:1.

### 5.3 Rotación (IN_VALUE en Balance)
- **Take Profit**: El más lejano entre (1.0× ATR desde el entry) y (borde opuesto del Área de Valor: VAH para LONG, VAL para SHORT). Esto asegura suficiente distancia para cubrir fees.
- **Stop Loss**: 1.0× ATR desde el entry, mínimo 0.30%.
- **R:R Típico**: 1:1.

**Principio clave (V9)**: SL = max(1.0× ATR, 0.30%) desde el entry. Los niveles VA (POC/VAH/VAL) se usan solo como **referencia direccional para TP**, no como distancia para SL. El SL detrás de VA era demasiado ancho y destruía el edge.

---

## 6. El Edge Cuantificado (L2 Real, V9 ATR SL)

Todas las métricas fueron generadas con infraestructura L2 de alta fidelidad (Tardis + l2_processor). La absorción se **observa** directamente desde el order book, no se infiere.

### 6.1 Edge Audit V9 — ATR-Based SL + Volume Profile Routing (LTC/USDT, 1 día RANGE)

| Métrica | Valor |
|---|---|
| Total Signals | 178 |
| Decided (W+L) | 33 (Timeouts: 145) |
| Overall Win Rate | 66.7% |
| **Gross Expectancy** | **+0.224%** |
| **Net (Taker 0.12%)** | **+0.104%** ✅ |
| **Net (Maker 0.08%)** | **+0.144%** ✅ |

### 6.2 Desglose por Setup (Dynamic TP/SL)

| Setup | n | W | L | TO | WR% | Avg TP% | Avg SL% | MFE% | MAE% | Ratio | Exp% |
|-------|---|---|---|----|-----|---------|---------|------|------|-------|------|
| continuation | 3 | 3 | 0 | 0 | 100.0% | 0.250% | 0.300% | 0.360% | 0.130% | 2.77 | +0.250% |
| reversion | 105 | 12 | 1 | 92 | 92.3% | 0.485% | 0.300% | 0.153% | 0.104% | 1.48 | +0.425% |
| rotation | 70 | 7 | 10 | 53 | 41.2% | 0.497% | 0.300% | 0.174% | 0.170% | 1.02 | +0.028% |

### 6.3 Targets Uniformes (Calibración)

| Setup | Best TP/SL | WR% | Exp% | Net Taker | Net Maker |
|-------|-----------|-----|------|-----------|----------|
| continuation | 0.4/0.4% | 100.0% | +0.400% | +0.280% | +0.320% |
| reversion | 0.4/0.4% | 81.2% | +0.250% | +0.130% | +0.170% |
| rotation | 0.4/0.4% | 72.7% | +0.182% | +0.062% | +0.102% |

**Overall uniforme**: 0.4/0.4% → WR 81.2%, Exp +0.250%, Net Taker +0.130%

### 6.4 Diagnóstico

1. **Edge positivo por primera vez**: Gross +0.224%, Net Taker +0.104%. El SL ATR-based (0.30% min) resolvió el problema de targets dinámicos.
2. **Reversion domina**: 92.3% WR, +0.425% Exp. Pero 87% timeouts — el TP (POC/ATR) está demasiado lejos. A 0.4/0.4% uniforme, WR=81.2%.
3. **Rotation frágil**: 41.2% WR, 76% timeouts. VAH/VAL targets no se alcanzan. A 0.4/0.4% uniforme, WR=72.7%.
4. **Continuation**: n=3 insuficiente, pero Ratio 2.77 y 100% WR sugieren edge real.
5. **Edge es marginal**: +0.104% net < 3× fee threshold. Un deterioro pequeño en WR lo volvería negativo.

**Siguiente paso**: Reducir TP de reversion (87% timeouts indica TP demasiado lejano), evaluar rotation TP, y fortalecer edge con Limit Sniper (maker entry → +0.144% net).

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

1. **Edge Marginal**: Net Taker +0.104% es < 3× el fee. Un deterioro de ~2% en WR volvería el edge negativo. La estrategia requiere ejecución maker (Limit Sniper → +0.144% net) para mayor robustez.
2. **Timeout Rate**: 82% de señales son timeout (145/178). Los targets dinámicos (POC/ATR) están demasiado lejos del MAE disponible. TP más cercano reduciría timeouts y aumentaría trades decididos.
3. **Rotation Fragility**: 41.2% WR con targets dinámicos. VAH/VAL no se alcanzan en 76% de casos. Necesita TP alternativo.
4. **Volume Profile Warm-up**: El sistema no puede operar hasta que SessionValueArea calcule POC/VAH/VAL. `is_structural_ready()` bloquea señales antes de tener datos.
5. **Latencia**: La detección de absorción requiere procesamiento de ticks en tiempo real. Latencias > 100ms pueden hacer que la señal llegue tarde, cuando el movimiento ya ocurrió.
6. **Concentration/Noise Filters**: Filtros estrictos (Conc≥0.70, Noise≤0.20) eliminan señales de alta Z-score que tenían mejor MFE. Los thresholds actuales (Conc≥0.50, Noise≤0.35) son un compromiso empírico.

---

## 9. Principio de Diseño

El edge viene de **evitar los trades incorrectos**, no de predecir mejor los correctos. Cada componente del framework existe para rechazar una categoría de operación que destruiría el edge:

- **RegimeGuardian**: Usa Volume Profile para determinar posición de valor. Rechaza operaciones contra-trend en mercados que aceptan nuevos precios.
- **Squeeze Guard**: Rechaza entradas en zonas de caos donde el MAE erosiona cualquier ganancia.
- **Absorción como Gatillo**: Rechaza entradas basadas solo en posición estructural sin confirmación de flujo.
- **Targets por Régimen**: Targets estructurales basados en Volume Profile (POC/VAH/VAL) para TP y ATR para SL. Cada setup tiene su propia lógica de TP/SL.

La suma de estos rechazos deja un portfolio de operaciones donde cada una tiene probabilidad condicional positiva por construcción.

---

## 10. Evolución del Framework

### V1 → V2: De indicadores técnicos a microestructura
Reemplazo de RSI/MACD por footprint delta y CVD como señal primaria.

### V2 → V3: De señal única a routing por régimen
Introducción de RegimeGuardian para clasificar IN_VALUE/OUT_OF_VALUE. Implementación de tres modos de setup (reversion/continuation/rotation).

### V3 → V4: Volume Profile Structural Routing
Migración a Volume Profile (POC/VAH/VAL) como referencia estructural. Eliminación de StatisticalLocationGuardian — su función de routing la cumple mejor RegimeGuardian con Volume Profile.

### V4 → V9: ATR-Based SL + Bug Fixes
Cinco bugs críticos corregidos que destruían el edge:
1. **Config thresholds no conectados**: AbsorptionDetector usaba Z≥1.5/Conc≥0.15/Noise≤0.85 hardcodeados en vez de leer config/absorption.py (Z≥3.0/Conc≥0.50/Noise≤0.35).
2. **Concentración era proxy de tiempo**: `_concentration()` devolvía 0.90/0.60/0.30 basado en `time_since_update`, no medía concentración real de volumen. Reimplementada como `dominant_vol / total_vol`.
3. **Noise ratio invertido**: El volumen agresor se clasificaba como "ruido" y el contra-direccional como "señal". Corregido.
4. **POC TP del lado equivocado**: 67% de señales de reversion tenían TP (POC) en dirección opuesta al trade. Añadida validación `poc_valid`.
5. **SL detrás de VA demasiado ancho**: Reversion SL avg 1.26% vs MAE 0.194% (6.5×). Reemplazado por SL = max(1.0× ATR, 0.30%) desde el entry.

Resultado: Gross Expectancy de -0.114% (V4) → **+0.224%** (V9). Net Taker de -0.234% → **+0.104%**.
