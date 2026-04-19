# Propuesta Técnica: Refactorización de Setups Tácticos LTA V5

## Filosofía de Diseño

**Principio rector:** Un setup táctico debe detectar **un fenómeno microestructural específico y no superponible** con otros setups. La redundancia genera señales correlacionadas que aumentan la varianza sin aumentar el edge.

---

## Playbook Alpha: Reversión Estructural

### Setups Mantenidos (Core)

#### 1. TacticalAbsorption (NÚCLEO)
**Fenómeno:** Defensa pasiva de un nivel mediante acumulación de órdenes limitadas que absorben agresión sin permitir movimiento de precio.

**Condiciones técnicas:**
- Volumen superior al 150% del promedio de 20 velas en el nivel
- Delta acumulado en la vela cercano a cero (equilibrio entre compra/venta)
- Rango de vela comprimido (body < 30% del rango total) a pesar del volumen

**Por qué se mantiene:** Es la señal de rechazo más limpia en microestructura. Representa la "absorción institucional" que detiene movimientos en los bordes del VA.

---

#### 2. TacticalDeltaDivergence (CONFIRMADOR)
**Fenómeno:** Agotamiento de momentum donde el precio alcanza un nuevo extremo pero el flujo neto de órdenes (CVD) no confirma la dirección.

**Condiciones técnicas:**
- Precio en nuevo máximo/mínimo relativo (últimas 20 velas)
- CVD en vela actual con signo opuesto al movimiento (ej: precio sube, CVD negativo)
- Divergencia visible en al menos 2 velas consecutivas

**Por qué se mantiene:** Captura el "último empujón" antes de la reversión. Es el agotamiento de participantes direccionales.

---

#### 3. TacticalTrappedTraders (CONFIRMADOR)
**Fenómeno:** Participantes atrapados en el lado equivocado del movimiento, forzados a liquidar cuando el precio revierte.

**Condiciones técnicas:**
- Imbalance fuerte inicial (>2 desviaciones estándar) en dirección del movimiento
- Reversión del precio que supera el 50% del rango de la vela de imbalance
- Volumen de cierre en dirección contraria al imbalance inicial

**Por qué se mantiene:** Estructura de "trap" clásica. Los traders que empujaron el movimiento inicial se ven forzados a salir, alimentando la reversión.

---

### Setup ELIMINADO

#### ~~TacticalRejection~~
**Razón de eliminación:** Redundante con TacticalAbsorption.

**Análisis técnico:**
- Absorption mide el fenómeno microestructural (defensa del nivel)
- Rejection mide el resultado visual (mecha larga)
- ** correlación esperada >0.85** — son la misma señal expresada diferente

**Impacto:** Eliminar reduce ruido sin pérdida de cobertura. Un solo sensor bien calibrado (Absorption) captura ambos fenómenos.

---

#### ~~TacticalStackedImbalance~~
**Razón de eliminación:** Filosofía contradictoria.

**Análisis técnico:**
- Stacked Imbalance predice **continuación** de movimiento (des equilibrios apilados a favor de la dirección)
- Playbook Alpha es **reversión al centro** (mean-reversion)
- **Contradicción lógica:** Usar un predictor de continuación para entrar en reversión genera señales falsas en tendencias fuertes

**Impacto:** Eliminar evita que la estrategia entre contra-tendencia cuando el flujo es unidireccional fuerte.

---

#### ~~TacticalImbalance~~
**Razón de eliminación:** Menos específico que alternativas.

**Análisis técnico:**
- Imbalance simple (1 vela) tiene alta tasa de falsos positivos
- StackedImbalance es más confiable pero ya se eliminó (continuación)
- **Sin alternativa de reversión:** No hay versión "imbalance que falla" que no sea ya TrappedTraders

**Impacto:** El fenómeno ya está mejor capturado por TrappedTraders (imbalance + fallo confirmado).

---

### Setups NUEVOS

#### 4. TacticalPoorExtreme (NUEVO - Adaptado de DOM)
**Fenómeno:** Extremo de sesión (high/low) formado con volumen anormalmente bajo, indicando falta de participación institucional en ese nivel.

**Condiciones técnicas:**
- Nuevo máximo/mínimo de sesión
- Volumen en la vela del extremo < 50% del volumen promedio de los últimos 5 highs/lows de sesión
- Formación del extremo en < 3 velas (movimiento abrupto, no construcción gradual)

**Por qué se añade:**
- Un VAH/VAL que coincide con un Poor High/Low es **doble confirmación de debilidad estructural**
- DOM demuestra que estos extremos tienen 70-75% de probabilidad de reversión tras barrido de liquidez
- **Ortogonal a Absorption:** Mide calidad del nivel, no actividad en el nivel

**Integración:** Sensor independiente que puede confluir con Absorption o actuar como trigger primario si el contexto estructural es favorable.

---

#### 5. TacticalVelocityReversion (NUEVO - Adaptado de DOM False Break)
**Fenómeno:** Ruptura falsa de un nivel clave donde el precio revierte rápidamente al rango previo, indicando rechazo institucional del nuevo precio.

**Condiciones técnicas:**
- Precio rompe el borde del VA (VAH/VAL) por >0.1%
- Reingreso al VA en < 60 segundos (velocidad de rechazo)
- Al cierre de la vela de ruptura, precio dentro del VA
- Volumen de ruptura no superior a 200% del promedio (no es cascada, es probe suave)

**Por qué se añade:**
- Reemplaza la lógica compleja de "Failed Auction" (wick check con backfill) con un criterio objetivo y medible: **tiempo de reingreso**
- **Ortogonal a Absorption:** Mide velocidad de rechazo, no defensa del nivel
- DOM demuestra 70-75% win rate en este setup específico

**Diferencia con TrappedTraders:**
- TrappedTraders requiere imbalance inicial fuerte
- VelocityReversion requiere ruptura + reingreso rápido (puede ocurrir sin imbalance previo fuerte)

---

## Playbook Beta: Fade de Cascada (Sin cambios)

### TacticalLiquidationCascade (MANTENER)

**Fenómeno:** Cascada de liquidaciones retail que se agota, permitiendo un fade hacia el centro de gravedad.

**Condiciones técnicas (existentes):**
- Volumen > 5× promedio de 20 velas
- Z-score del delta > ±4.0 (flujo extremadamente unidireccional)
- Movimiento de precio > 2× ATR en dirección de la cascada
- Post-pico: volumen cae a <50% del máximo y delta se invierte

**Por qué no se modifica:** Es un playbook independiente con lógica propia. No es reversión estructural, es **fade de dislocación extrema**. Modificarlo sería crear una estrategia diferente.

---

## Matriz de Confluencia Propuesta

| Setup | Rol | Puede ser trigger primario | Requiere confirmador |
|-------|-----|---------------------------|---------------------|
| TacticalAbsorption | Núcleo | Sí | No (opcional) |
| TacticalDeltaDivergence | Confirmador | No | Ya es confirmador |
| TacticalTrappedTraders | Confirmador | Sí (si es extremo fuerte) | No (opcional) |
| TacticalPoorExtreme | Núcleo/Contexto | Sí | Recomendado: Absorption |
| TacticalVelocityReversion | Núcleo | Sí | Recomendado: Divergence |
| TacticalLiquidationCascade | Playbook Beta | Sí (standalone) | No (lógica interna) |

---

## TACTICAL_WHITELIST LTA V5 Propuesto

```python
TACTICAL_WHITELIST = (
    # Playbook Alpha: Reversión Estructural (5 setups)
    "TacticalAbsorption",           # Núcleo: defensa del borde
    "TacticalDeltaDivergence",      # Confirmador: agotamiento de momentum
    "TacticalTrappedTraders",       # Confirmador: participantes atrapados
    "TacticalPoorExtreme",          # NUEVO: borde débil de sesión
    "TacticalVelocityReversion",    # NUEVO: ruptura falsa rápida

    # Playbook Beta: Fade de Cascada (1 setup)
    "TacticalLiquidationCascade",   # Excepción: dislocación extrema
)


Reducción: De 9 setups a 6 setups.
Eliminación de redundancia: Rejection, StackedImbalance, Imbalance.
Valor añadido: PoorExtreme (calidad del borde), VelocityReversion (velocidad de rechazo).

Justificación Técnica del Cambio
Antes (LTA V4):
9 setups con superposición de señales (Absorption/Rejection)
1 setup contradictorio (StackedImbalance: continuación en playbook de reversión)
2 setups genéricos (Imbalance, PoCShift ya eliminado)
Después (LTA V5):
6 setups ortogonales (cada uno mide fenómeno diferente)
0 setups contradictorios (todos predicen reversión o fade de extremo)
2 setups con edge documentado en DOM (PoorExtreme, VelocityReversion)
Hipótesis: Menor cantidad de señales pero mayor calidad por señal, manteniendo o mejorando el ratio MFE/MAE > 1.2 certificado.





Para la revisión con otros analistas
Preguntas que probablemente te harán:

"¿Por qué eliminar Rejection si es una señal clásica de price action?"
Respuesta: Redundancia con Absorption. Mostrarles correlación esperada >0.85.
"¿StackedImbalance realmente contradice la tesis?"
Respuesta: Sí, es predictor de continuación. En tu doc original ya eliminaste PoCShift por lo mismo.
"¿Los 2 nuevos setups tienen evidencia?"
Respuesta: DOM.md reporta 70-75% WR en PoorExtreme y False Break. Necesitan Edge Audit para confirmar en tu contexto.
