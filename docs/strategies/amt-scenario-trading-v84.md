# AMT Scenario Trading v8.4 — Crystal Reforge

**Clasificación**: Scalping de Microestructura basado en Auction Market Theory
**Mercado**: Futuros de Criptomonedas (24/7, Binance)
**Horizonte**: Scalping Intradía (5s–30min)
**Versión**: v8.4 — Quality Pipeline + Exhaustion Core

---

## 1. Tesis Central

Los mercados de futuros cripto son subastas continuas. La estrategia opera **narrativas de mercado** completas donde la causa, la confirmación y la consecuencia están alineadas.

El edge no viene de la señal. **Viene de saber qué narrativa de mercado está activa** y operar exactamente esa narrativa con targets calibrados.

### Principios Fundamentales

1. **Exhaustion es el core**: No entras contra un flujo creciente. Entras cuando el agresor se está apagando.
2. **Calidad sobre cantidad**: Un trade con quality score 0.8 vale más que 5 trades con score 0.5.
3. **Contexto sobre patrón**: El mismo patrón tiene edge diferente según dónde estés en la subasta.
4. **Graduación sobre bloqueo**: Un factor débil penaliza, no elimina.

---

## 2. Los Cuatro Escenarios

### Escenario ① — Excess Rejection (Rechazo de Exceso)

**Narrativa AMT**: El precio se mueve fuera del Área de Valor. Agresores atacan el extremo — pero la liquidez pasiva los absorbe. El volumen agresivo **se agota** (cada ola es más débil que la anterior). El mercado va a rechazar el exceso y volver al consenso.

**Condiciones de entrada**:
1. Precio fuera del Área de Valor (OUT_OF_VALUE o EXCESS)
2. Absorción detectada: z-score >= 3.0, concentración >= 0.50, ruido <= 0.35
3. **Agotamiento confirmado**: delta_ratio < 0.5 (agresor se apaga)
4. Precio en zona de value (no en POC — eso es ruido)

**Dirección**: Hacia el POC (centro de valor). Si los vendedores se agotaron → LONG. Si los compradores se agotaron → SHORT.

**Target**: POC del Volume Profile.
**Stop**: 1.5× ATR desde entry.

---

### Escenario ② — Failed Breakout (Ruptura Fallida)

**Narrativa AMT**: El precio rompe un nivel estructural (VAH/VAL). Los breakout traders entran agresivamente. **Pero el flujo no confirma** — el CVD no acompaña la ruptura. El precio retorna al Área de Valor. Los breakout traders están **atrapados**.

**Condiciones de entrada**:
1. Precio rompió VAH (para SHORT) o VAL (para LONG) en los últimos 60 segundos
2. CVD divergence: el CVD durante la ruptura NO confirmó la dirección
3. Precio retornó dentro del Área de Valor
4. El retorno fue rápido (< 60 segundos)

**Dirección**: Opuesta a la ruptura. Ruptura al alza fallida → SHORT. Ruptura a la baja fallida → LONG.

**Target**: Opuesto VA edge (VAH para SHORT, VAL para LONG).
**Stop**: 2.0× ATR desde entry.

---

### Escenario ③ — Liquidity Exhaustion (Agotamiento de Liquidez)

**Narrativa AMT**: Un nivel estructural (VAH o VAL) es atacado repetidamente. Cada ataque tiene **menos fuerza** que el anterior. El lado atacante está agotando su liquidez. El nivel va a sostenerse.

**Condiciones de entrada**:
1. El mismo nivel fue testeado **3 o más veces** en los últimos 120 segundos
2. El delta en cada test sucesivo es **declinante**
3. El precio rebotó del nivel (no se está consolidando EN el nivel)

**Dirección**: Opuesta al lado atacante. Tests repetidos de VAL sin romperlo → LONG. Tests repetidos de VAH → SHORT.

**Target**: Opuesto VA edge.
**Stop**: 2.0× ATR desde entry.

---

### Escenario ④ — Trend Acceptance (Aceptación de Tendencia)

**Narrativa AMT**: El precio sale del Área de Valor con **convicción** — el CVD confirma la dirección. El mercado está genuinamente aceptando nuevos precios. La entrada es en el **pullback** al nivel roto.

**Condiciones de entrada**:
1. Precio ha estado fuera del Área de Valor durante **3 o más velas consecutivas**
2. CVD durante la ruptura **confirmó** la dirección
3. Precio hace pullback hacia el nivel roto sin re-entrar completamente

**Dirección**: A favor de la tendencia. Ruptura al alza + pullback a VAH → LONG.

**Target**: 1.5× ATR (extensión de tendencia).
**Stop**: 1.0× ATR desde entry.

---

## 3. Exhaustion: El Core del Sistema

### ¿Qué es el agotamiento?

Cuando un lado del mercado ataca un nivel repetidamente con volumen decreciente, está mostrando **agotamiento**. Cada ola de agresión es más débil porque:

- Los participantes más convictos ya entraron
- Los stops de los atrapados ya fueron ejecutados
- La liquidez pasiva del otro lado sigue intacta

### Métricas

```python
exhaustion = footprint_registry.get_exhaustion(symbol)
delta_ratio = exhaustion["delta_ratio"]    # |delta_short| / |delta_long|
volume_ratio = exhaustion["volume_ratio"]  # vol_short / vol_long
```

### Scoring de Exhaustion

```python
if delta_ratio > 1.5:
    exhaustion_score = 0.0  # Agresor intensificándose → NO ENTRAR
elif delta_ratio < 0.5:
    exhaustion_score = 1.0  # Agotamiento perfecto
else:
    exhaustion_score = 1.0 - delta_ratio  # Gradual
```

### Validación Empírica

| Grupo | Delta Ratio | Resultado |
|---|---|---|
| **Ganadoras** | 0.52 (agotado) | Agresor perdió fuerza |
| **Perdedoras** | 0.56 + 0% vol declinante | Agresor aún activo |
| **Timeouts** | 1.22 (intensificándose) | Sin resolución |

---

## 4. Quality Pipeline (Reemplaza Guardianes)

### El Problema con los Guardianes

Los guardianes son una cadena de kill rígida que mata el 98% de las señales. Un L2 ratio de 1.8 no debería MATAR una señal con exhaustion perfecto y régimen correcto.

### La Solución: Quality Score

Cada factor contribuye un score de 0.0 a 1.0:

```python
quality_score = (
    exhaustion_score * 0.35 +    # El factor más importante
    regime_score * 0.25 +         # Contexto de mercado
    structure_score * 0.20 +      # Geografía correcta
    liquidity_score * 0.15 +      # Profundidad L2
    spread_score * 0.05           # Costo de transacción
)
```

### Grade Mapping

```python
if quality_score >= 0.7:
    grade = "A"  # Full size (1%)
elif quality_score >= 0.4:
    grade = "B"  # Half size (0.5%)
else:
    grade = None  # No trade
```

### Risk Check (Solo Blocks Reales)

Solo 2 hard blocks:
1. **Spread > 3x average** (costo excesivo)
2. **Sistema no warm** (datos insuficientes)

---

## 5. Targets Simplificados

### Reversiones (Escenarios 1, 2, 3)

```
TP = POC (centro de valor)
SL = entry × (1 ± atr_pct × 1.5)
```

### Continuaciones (Escenario 4)

```
TP = entry × (1 ± atr_pct × 1.5)
SL = entry × (1 ∓ atr_pct × 1.0)
```

### Rationale

- **Reversiones van al POC**: El POC es el centro de consenso. ReversionesBuscan el consenso.
- **Continuaciones extienden**: En tendencia, el momentum continúa.

---

## 6. Régimen de Mercado

| Condición | Escenarios Activos | Escenarios Bloqueados |
|---|---|---|
| **Balance** (in VA) | ① Rechazo, ③ Agotamiento | ④ Aceptación |
| **Balance** (out of VA) | ① Rechazo, ② Ruptura Fallida | — |
| **Tendencia confirmada** | ④ Aceptación, ③ Agotamiento | ① Rechazo |

---

## 7. Gestión de Riesgo

### Sizing

- Grade A (quality >= 0.7): 1% del balance
- Grade B (quality >= 0.4): 0.5% del balance

### Exit Engine

- **Scale Out**: A 2.5 ATR, cerrar 30% de la posición
- **Micro-Z Reversal**: Si |current_z - entry_z| > 4.0, cerrar toda la posición

### Max Holding Time

- Reversiones: 14400s (4 horas)
- Continuaciones: 3600s (1 hora)

---

## 8. Por Qué Este Edge Existe

1. **Información asimétrica**: La absorción y agotamiento solo son visibles en L2 tick-by-tick.
2. **Comportamiento mecánico**: Los atrapados generan flujo predecible al salir.
3. **Calidad sobre cantidad**: El quality scoring filtra el ruido y mantiene solo trades con edge.

---

## 9. Evolución

| Versión | Cambio | Edge |
|---|---|---|
| V10 (original) | Escenarios narrativos + Exhaustion confirmation | +0.13% bruto |
| **v8.4 Crystal Reforge** | Quality Pipeline + Exhaustion Core | **+0.68% net (target)** |

---

## 10. Archivos del Sistema

| Archivo | Propósito |
|---|---|
| `decision/engine/quality_scorer.py` | Quality scoring engine |
| `sensors/absorption/absorption_detector.py` | Escenario 1 + exhaustion gate |
| `decision/scenarios/failed_breakout.py` | Escenario 2 |
| `decision/scenarios/liquidity_exhaustion.py` | Escenario 3 |
| `decision/scenarios/trend_acceptance.py` | Escenario 4 |
| `decision/engine/targets.py` | Cálculo de targets |
| `config/absorption.py` | Parámetros de absorción |
| `config/trading.py` | Parámetros de trading |
