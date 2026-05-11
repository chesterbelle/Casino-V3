# Análisis Académico: Contradicciones en el Pipeline de Decisión de Casino-V3

**Fecha**: 2026-05-04
**Branch**: `v7.1.0-lta-v7-structural-absorption`
**Autor**: Auditoría interna (Backtest + Code Review)
**Propósito**: Documento de discusión para revisión entre analistas

---

## 1. Resumen Ejecutivo

Se identificó una **contradicción fundamental** en la lógica de entrada del sistema. El pipeline de decisión mezcla dos frameworks de trading conceptualmente diferentes como hard gates simultáneos:

- **Market Profile** (Steidlmayer/Dalton) para la localización de entrada (VAH/VAL proximity)
- **VWAP Statistical Mean Reversion** para el filtrado (Z > 2.0), el target (VWAP) y el stop (3.5σ)

Estas dos distribuciones (volumen-por-precio vs. tiempo-por-precio) no están alineadas espacialmente, lo que provoca que señales de absorción legítimas sean vetadas por un filtro estadístico que mide algo diferente. El resultado empírico es **1 entrada en 24 horas sobre 1,416 señales detectadas**.

---

## 2. Evidencia Empírica

### 2.1 Funnel de Señales (SOL/USDT, 24h, Backtest con instrumentación)

```
Gate                        Count    % del total     Descripción
─────────────────────────────────────────────────────────────────
Absorption Detector          1,416    100.0%         Señales de absorción emitidas (Z_delta > 1.5)
SensorManager dispatch         286     20.2%         Llegan al SetupEngine con side LONG/SHORT
Proximity Gate (VAH/VAL)       188     13.3%  KILL   Precio lejos de VAH/VAL (>0.35%)
8 Guardians (hard-gate)        642      —    KILL    Rechazos totales (múltiples eval. por ventana 5s):
  ├── STATISTICAL_LOCATION     588     91.6%  KILL     Z_price < 2.0 del Rolling VWAP
  ├── VA_INTEGRITY              36      5.6%  KILL     Densidad de VA insuficiente
  ├── DELTA_DIVERGENCE          14      2.2%  KILL     Z_cvd > 2.5 contra posición
  └── POC_MIGRATION              4      0.6%  KILL     POC migrando contra side
PATTERN CONFIRMED                5      0.4%         Señales que pasan todo el pipeline
Entries ejecutadas               2      0.1%         Trades registrados por el Historian
```

### 2.2 Edge Audit (Zero-Interference, `--audit` mode)

```
Signals:  2  |  Price Samples: 47,795  |  Decision Traces: 2,910

Setup    n    Avg MFE%    Avg MAE%    Ratio    Gross Expectancy    Status
reversion  2     0.298%     0.068%     4.42       +0.315%          INSUFFICIENT (n<20)
```

**Observación**: Las 2 señales que sí pasaron mostraron un Ratio MFE/MAE de 4.42 y Win Rate del 100%. El edge parece real cuando la señal pasa, pero la muestra es insuficiente (n=2).

### 2.3 Backtest Comparativo de Exit Profiles (ESCALADOR, mejor perfil)

```
Profile      Trades  WR%    PF     Gross PnL   Fees     Net PnL
ESCALADOR      2     50%    5.42    +$0.03     $0.10    -$0.07
FRANCOTIRADOR  6     50%    0.35    -$0.21     $0.41    -$0.62
EXPRIMIDOR     3     33%    0.48    -$0.33     $0.31    -$0.64
```

---

## 3. La Contradicción Teórica

### 3.1 Dos Frameworks, Un Pipeline

El sistema implementa una estrategia de **Structural Absorption Reversion** que intenta combinar:

| Componente | Framework Usado | Referencia en Código |
|---|---|---|
| **Señal de entrada** | Order Flow (absorción en footprint) | `absorption_detector.py` L28: `z_score_min = 1.5` |
| **Localización de entrada** | Market Profile (VAH/VAL proximity) | `setup_engine.py` L215-216: `LTA_PROXIMITY_THRESHOLD = 0.0035` |
| **Filtro de entrada** | VWAP Estadístico (Z > 2.0) | `statistical_location_guardian.py` L30: `min_z = 2.0` |
| **Target (TP)** | VWAP Estadístico | `setup_engine.py` L250: `tp_price = vwap_price if vwap_price > 0 else poc` |
| **Stop (SL)** | VWAP Estadístico (3.5σ) | `setup_engine.py` L263: `sl_price = vwap_price - (3.5 * std)` |

### 3.2 Por qué son incompatibles

**Market Profile** (VAH/VAL/POC) se construye a partir de la distribución de **volumen por precio** en una ventana de sesión. Define el *Value Area* como el rango donde se concentra el 70% del volumen.

**Rolling VWAP** se calcula como el promedio de precio ponderado por volumen **en el tiempo** (rolling 120 minutos). Sus bandas (±nσ) representan desviaciones estándar de esa media temporal.

Estas son **dos distribuciones diferentes**:

```
Distribución Market Profile:  f(price) = volume_at_price / total_volume
Distribución VWAP:            f(time)  = Σ(price × volume) / Σ(volume)

VAL ≠ VWAP - 2σ  (en general)
```

#### Ejemplo numérico del dataset:

```
Sesión LONDON (SOL/USDT):
  VAL  = $85.01   (borde inferior del Value Area, distribución de volumen)
  VAH  = $85.59
  POC  = $85.30
  VWAP = $85.35   (media ponderada temporal, rolling 120min)
  σ    = $0.18

Precio cae a $85.05:
  ✅ Proximity Gate:  |$85.05 - $85.01| / $85.05 = 0.047% < 0.35%  → PASS
  ✅ Absorption:      Z_delta = -4.5 (sell exhaustion)               → SIGNAL
  ❌ Statistical Location: Z = ($85.05 - $85.35) / $0.18 = -1.67    → REJECT (< 2.0)
```

**El precio está en el borde del Value Area con absorción confirmada, pero el filtro VWAP dice que no está "suficientemente lejos de la media".**

### 3.3 La asimetría temporal

| Indicador | Tipo | Latencia |
|---|---|---|
| Absorción (Z_delta footprint) | **LEADING** | Tiempo real — detecta actividad institucional mientras ocurre |
| VWAP Z-score | **LAGGING** | Retrasado — refleja dónde ha estado el precio, no dónde va |

Usar un indicador lagging como hard gate sobre uno leading es análogo a usar el retrovisor para decidir si frenar ante un obstáculo visible por el parabrisas.

---

## 4. Cuádruple Filtrado de Z-Score

Se identificaron **cuatro** capas independientes que evalúan Z-scores relacionados, creando un filtro multiplicativo:

| # | Componente | Input | Threshold | Archivo |
|---|---|---|---|---|
| 1 | AbsorptionDetector | Z del delta cross-sectional en footprint | \|Z\| > 1.5 | `absorption_detector.py` L28 |
| 2 | Statistical Location Guardian | Z del precio vs VWAP rolling 120min | \|Z\| > 2.0 | `statistical_location_guardian.py` L30 |
| 3 | Delta Divergence Guardian | Z del CVD (microstructure state) | \|Z\| > 2.5 | `delta_divergence_guardian.py` L27 |
| 4 | Micro Gate | Z del CVD (microstructure state) | \|Z\| > 2.0 | `setup_engine.py` L663 |

**Observaciones**:
- Gates 3 y 4 miden **exactamente lo mismo** (Z del CVD micro-state) con diferente threshold. Gate 4 (Z > 2.0) es más estricto que Gate 3 (Z > 2.5 para reject), haciendo que uno subsuma al otro parcialmente.
- Gate 1 (absorción) mide el delta **por nivel de precio** en el footprint (cross-sectional). Gates 2-4 miden el flujo **agregado** en el tiempo. Son conceptos relacionados pero dimensionalmente diferentes.

---

## 5. El Target Incorrecto

```python
# setup_engine.py, línea 250
tp_price = vwap_price if vwap_price > 0 else poc
```

Si la tesis de entrada es Market Profile ("precio en VAL con absorción → reversión hacia POC"), el target debería ser **POC**, no VWAP.

En un mercado trending:

```
Ejemplo: SOL trending descendente en la sesión
  POC  = $87.70  (donde se concentró el volumen)
  VWAP = $88.10  (sesgado por el inicio alcista de la sesión)

Si entramos LONG en VAL = $87.44:
  TP → POC ($87.70) = +0.30% de recorrido  ← Alcanzable (dentro del MFE promedio)
  TP → VWAP ($88.10) = +0.75% de recorrido ← Inalcanzable para micro-scalping
```

El mismo razonamiento aplica al SL. Un stop a **3.5σ del VWAP** no tiene relación con la tesis de "nivel defendido por absorción". El SL correcto sería **detrás del nivel estructural** (VAL/VAH + buffer).

---

## 6. Comparación con Metodología Estándar de Order Flow

### 6.1 Lo que hacen los practitioners (Trader Dale, Axia, Jigsaw Trading)

```
1. Identificar nivel clave        → Volume Profile (POC, VAH, VAL, HVN previos)
2. Confirmar con footprint         → Absorción, delta imbalance, iceberg detection
3. Entrar si hay confluencia       → Nivel + confirmación de flujo = ENTRY
4. Target                          → POC o siguiente HVN (dentro del Value Area)
5. Stop                            → Detrás del nivel estructural (tesis invalidada si se rompe)
```

**NO usan VWAP Z-score como hard gate de entrada.** VWAP se utiliza como referencia contextual ("¿estamos por encima o por debajo del fair value intradía?"), pero no bloquea trades con absorción confirmada.

### 6.2 Lo que dice la literatura académica

- **Cont, Kukanov & Stoikov (2014)** — "The Price Impact of Order Book Events": Order flow imbalance tiene poder predictivo independiente sobre returns a corto plazo. El imbalance es la señal; no requiere validación adicional de la posición del precio respecto a una media.
- **Bouchaud et al. (2009)** — "How Markets Slowly Digest Changes in Supply and Demand": El impacto del flujo es persistente y predecible. La absorción (flujo sin movimiento de precio) indica participación institucional pasiva.
- **Kyle (1985)** — Modelo de informed trading: Los participantes informados operan contra el flujo visible. La absorción es evidencia de este comportamiento.

### 6.3 Resumen de la divergencia

| Aspecto | Methodology Estándar | Casino-V3 Actual |
|---|---|---|
| **Señal** | Absorción + nivel = ENTRY | Absorción + nivel + Z_vwap > 2.0 + Z_cvd < 2.5 |
| **Target** | POC (centro del Value Area) | VWAP (media temporal diferente) |
| **Stop** | Detrás del nivel (estructural) | 3.5σ del VWAP (estadístico) |
| **VWAP** | Contexto / scoring | Hard gate (kill switch) |
| **Resultado** | Múltiples trades por sesión | 1 trade en 24h |

---

## 7. Propuesta de Corrección

### 7.1 Cambios Estructurales

| Componente | Estado Actual | Propuesta | Justificación |
|---|---|---|---|
| `Statistical Location Guardian` | Hard gate (Z > 2.0) | Soft scoring (confidence multiplier) | Absorción es LEADING; VWAP Z es contexto, no gate |
| `Delta Divergence Guardian` | Hard gate (Z > 2.5) | Eliminar | Redundante con AbsorptionDetector |
| `Micro Gate` | Hard gate (Z > 2.0) | Eliminar | Idéntico a Delta Divergence |
| `TP target` | VWAP | POC | Coherente con tesis de Market Profile |
| `SL target` | 3.5σ del VWAP | Detrás de VAL/VAH + buffer | Tesis invalidada = nivel roto, no estadística |
| `VWAP Z-score` | Bloquea entrada | Multiplica sizing (±30%) | Más extremo = más confianza, pero nunca bloquea |

### 7.2 Pipeline Propuesto

```
SEÑAL:    AbsorptionDetector (Z_delta > 1.5)         ← EL EDGE (no tocar)
GATE 1:   Proximity (price near VAH/VAL < 0.35%)     ← Contexto estructural
GATE 2:   Regime Guardian (no counter-trend fuerte)   ← Protección macro
GATE 3:   VA Integrity (Value Area es válido)         ← Calidad de datos
SCORING:  VWAP Z-score → confidence multiplier        ← Contexto, no gate
ENTRY:    Si pasa Gates 1-3 → ENTER con size × confidence
TARGET:   POC                                         ← Market Profile
STOP:     Detrás de VAL/VAH + buffer                  ← Estructural
```

### 7.3 Impacto Esperado

Con esta corrección, el funnel pasaría de:

```
Actual:    1,416 → 286 → 98 → 5 → 2 señales (0.14% conversion)
Estimado:  1,416 → 286 → 98 → ~60-80 señales (~5-7% conversion)
```

El incremento viene de eliminar STATISTICAL_LOCATION como hard gate (588 rejects → 0 rejects, pero las señales reciben scoring variable).

---

## 8. Riesgos de la Corrección

| Riesgo | Mitigación |
|---|---|
| Más trades = más fee drag | Activar Limit Sniper (maker fees 0.01% vs taker 0.035%) |
| Señales de baja calidad pasan | El scoring de VWAP reduce el sizing, no bloquea |
| Overfitting al dataset SOL 24h | Validar con `/long-range-edge-audit` (LTC × 3 regímenes × 3 días) |
| Más trades perdedores | El Ratio MFE/MAE de 4.42 sugiere que el edge es real cuando la señal pasa |

---

## 9. Preguntas Abiertas para Discusión

1. **¿El Z_delta > 1.5 del AbsorptionDetector es suficiente como señal, o necesita un segundo confirmador?** La academia sugiere que sí, pero nuestra muestra (n=2) es insuficiente para afirmarlo estadísticamente.

2. **¿Debemos mover el VWAP de hard gate a soft scoring, o eliminarlo completamente del pipeline de entrada?** Trader Dale no lo usa; los fondos cuantitativos sí pero como feature, no como gate.

3. **¿El POC rolling (sesión actual) es mejor target que el POC de la sesión previa?** La mayoría de los practitioners usan el POC de la sesión previa como referencia más estable.

4. **¿El threshold de proximidad (0.35% a VAH/VAL) es correcto, o debería ajustarse por volatilidad del activo?** SOL (alta vol) podría necesitar 0.50%; LTC (baja vol) podría funcionar con 0.25%.

5. **Si relajamos los guardians, ¿tenemos suficiente protección en el Exit Engine (ESCALADOR) para manejar el aumento de trades?** El SCE scale-out + breakeven debería proteger, pero necesita validación con mayor muestra.

---

*Documento generado a partir de code review + backtest instrumentado. Todos los números provienen de ejecuciones reproducibles sobre `tests/validation/cross_section/SOL_USDT_USDT_24h.csv`.*
