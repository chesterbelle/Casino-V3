# Auditoría de Condiciones de Entrada vs. Teoría de Subasta (AMT)

**Foco:** ¿La lógica que dispara trades es teóricamente coherente con los principios de Market Auction Theory?
**Objeto:** Los 4 detectores (`tactical_absorption`, `liquidity_exhaustion`, `failed_breakout`, `trend_acceptance`) y sus condiciones de entrada.
**Preguntas que responde este documento:**
1. ¿Qué debería ser cada setup según AMT/Dalton?
2. ¿Qué está midiendo el código hoy?
3. ¿Dónde se rompe la teoría? ¿Qué variable proxy es incorrecta?
4. ¿Cómo debería escribirse la condición correcta?

> No se discute aquí TP/SL, sizing, brackets, calidad ni VA_GATE. Esos son problemas ortogonales. Esto es exclusivamente sobre **la decisión de entrada**.

---

## Marco teórico primero (el estándar contra el que auditar)

Toda la lógica de AMT parte de tres principios de Dalton que deben respetarse literales:

1. **Initiative (Initiator)**: la mano que crea el delta. Si CVD sube, el initiative es comprador (agresivo). Si CVD cae, el initiative es vendedor. **El initiative define la dirección del riesgo atacado.**

2. **Response**: el profesional en el otro lado del book que **no se mueve por precio, sino por el excesivo initiative del atacante**. Compra en 낮 el VAL cuando los vendedores atacan y se quedan sin munición (Initiative exhausted).

3. **Auction failures**: cuando el initiative ataca un borde de valor (VAH/VAL) y el Delta NO confirma — el que está cargando el riesgo pierde convicción. La subasta "falla" y el precio regresa al rango.

Las tres formas válidas de tomar posición en subasta:

| Patrón AMT                              | Condición de entrada correcta                                                 | Dirección del trade                                  |
|-----------------------------------------|-------------------------------------------------------------------------------|------------------------------------------------------|
| **Initiative exhaustion (RESPONSIVE)**  | Ataques repetidos al mismo borde con Delta cada vez más débil + Response del lado contrario | Contraria al initiative que falla                    |
| **Failed auction**                      | Excedencia del borde con NO confirmación de Delta + regreso al rango          | Contraria a la falsa ruptura                         |
| **Acceptance breakout (INITIATIVE)**    | Excedencia del borde CON confirmación de Delta + extensión + pullback al borde | A favor de la iniciativa que sí confirma              |

Cada setup tiene **un lado** (LONG o SHORT) que no es negociable: lo dicta la mano atacante y su respuesta. Lo que se acepta es la **dirección del initiative** o su **contraria**.

Ahora sí, auditoría setup por setup.

---

## 1. `tactical_absorption` — Lo más roto del bot

### Qué dice AMT que debe ser
Tactical absorption es el caso puro de RESPONSE: el bot detecta que el **initiative vendedor atacó fuerte** (volumen grande, delta vendedor) y que **el bid absorbió toda esa venta sin que el precio cayera al siguiente nivel**. Es la firma profesional de que alguien defiende un nivel. La entrada es a favor del RESPONSE — **LONG cuando el initiative vendedor se agota en el VAL**, SHORT cuando el initiative comprador se agota en el VAH.

### Qué mide el código
`decision/scenarios/instant/tactical_absorption.py:112`:
```python
side = "LONG" if state.cvd_session_delta < 0 else "SHORT"
```
La dirección **se decide por el signo del CVD de sesión acumulada, sin importar el borde donde está parado el precio**. No hay test de qué lado del book está absorbiendo (bid vs ask). No hay mapeo a VAL/POC/VAH. No hay identificación de qué lado del orderbook anuló el ataque.

### La falla teórica concreta
1. **Inversión lógica de Response**: AMA lo largo de "los compradores defendieron la presión vendedora", el código dispara LONG porque el CVD es negativo. Pero un CVD negativo *per se* puede significar que **los vendedores están ganando iniciativa**, no que se agotaron. La condición correcta no es el signo, es la **convergencia**: el delta de los últimos *k* ventanas*t decreciendo en magnitud mientras el volumen permanece alto. Eso es exhaustion.

2. **Bidireccionalidad ausente**: AMT dice que la absorción en el **bid** (defendiendo el lado bajo) PROTECTORIAL y entra LONG; absorción en el **ask** (defendiendo el lado alto) PROTECTORIAL y entra SHORT. El código actual dispara LONG o SHORT cerca del POC, VAH o VAL **sin chequear qué lado del book hizo el trabajo**.

3. **Sesión-reset artefact**: `cvd_session_delta` se resetea cada 4 h. Cerca del reset, el CVD cae a ~0 y los criterios de signo se vuelven ruidosos o simplemente dejan de disparar.

### Conclusión de auditoría
`tactical_absorption` está midiendo el síntoma equivocado. **No hay forma de que la dirección sea teóricamente correcta como está codificada hoy.** Cualquier mejora de TP/SL, sizing o calidad es ruido mientras esta condición sea así. *Esta es la única falla bloqueante del bot en términos puramente teóricos.*

### Cómo debería escribirse la condición (sketch AMT-puro)
- Detectar "ventana agotada" por reducción de `|cvd_velocity|` sostenido (z-score decay, no signo).
- Detectar **qué lado del book defendió**: comparar bid_imbalance vs ask_imbalance en la banda del borde relevante. Si has absorbido en el bid cerca del VAL → LONG. Si ask absorbió cerca del VAH → SHORT. **Si no hay evidencia del lado del book, NO disparar.**
- Anclar al **borde que se está defendiendo**, no al POC ni a una "zona genérica cerca del valor". En AMT la diferencia entre POC y VAL importa porque el POC no es un borde — es donde se concentra el precio a través del tiempo. Combatir absorption en POC es una lectura que no existe en AMT; el POC no es una defensa, es un imán.

---

## 2. `liquidity_exhaustion` — Conceptualmente correcto pero implementado con proxy mala

### Qué dice AMT que debe ser
La respuesta básica de un profesional: el seller/vendor ha atacado el mismo nivel múltiples veces, cada vez con menos agresión (delta declining), y al final el comprador aparece para defender. La entrada es la **respuesta profesional a la initiative exhaustion**: en sentido contrario al initiative que falla.

### Qué mide el código
`decision/scenarios/confirmation/liquidity_exhaustion.py:107-108`:
```python
raw_cvd_velocity = getattr(state, "cvd_velocity", 0.0)
current_delta = abs(raw_cvd_velocity)
```
El "delta" del test es `|cvd_velocity|`, que es un **z-score**, no una magnitud absoluta de aggressive. Luego líneas 150-152:
```python
is_declining = all(
    recent[i]["delta"] < recent[i - 1]["delta"] * declining_threshold for i in range(1, len(recent))
)
```
Busca que cada z sea estrictamente decreciente.

### La falla teórica
- **El "delta declining" mide el z-score, no la aggression**. Un z decrece porque la ventana rodante se **ensancha** (más variabilidad) tanto como porque la aggression decrece. En AMT no mides initialization exhaustion con z; mides con magnitud de flujo dividido entre volumen realizado. Esto convierte el "delta declining" en un indicador de **reducción de la concentración del flujo**, no de reducción del flujo.

- **Fragmentación de identidad del nivel**: línea 131:
  ```python
  level_key = f"{level_name}_{level_price:.2f}"
  ```
  El historial de tests se keya por precio exacto a 2 decimales. En mercados líquidos, VAH/VAL pueden moverse 0.05% entre tests consecutivos sin que sea "otro nivel" desde el punto de vista AMT. Pero el código cuenta cada test como parte de un *nivel diferente* con level_key diferente, porque el precio exacto cambió. **No acumula tests.** Es como llevar un diario de "cuántas veces defendí 54.32" en vez de "cuántas veces defendí el VAH".

- La condición de defensa (líneas 156-159) está bien: requiere que `cvd_velocity` sea positivo para defender VAL (compradores retornando). Aquí sí respetan AMT.

### Conclusión de auditoría
La idea está alineada con AMT (multiple test + declining aggression + response). La **implementación se equivoca en dos lugares**: el delta debería ser magnitud bruta de flow, no z-score relativizado a la std rolling, y los tests deberían agruparse por **borde lógico (VAL, VAH, POC)** no por precio decimal exacto. Con esos dos cambios, la condición se vuelve coherente.

### Mejoras concretas
1. `current_delta = |net_delta_volume|` (acumulado de la ventana relacionado al mismo lado del book que ataca), **NO** `|z|`.
2. `level_key = f"{symbol}_{level_name}"` (solo el nombre del borde, ignorando el precio exacto para identificar un test de VAL vs otro distinto VAL).
3. Cuando la `declining_threshold` sea 0.5-0.7 (config actual), validar que **no se acepten declines negativos del lado equivocado** (i.e., que el decline en magnitud venga por exhaustion, no por el lado equivocado del book).

---

## 3. `failed_breakout` — El más cercano a AMT, pero con un agujero

### Qué dice AMT que debe ser
Una failed auction clásica: el initiative ataca un borde (sale del VAL o VAH), el Delta **no acompaña** (no confirma), y el precio regresa dentro del rango. La entrada está en el momento del regreso al rango, en sentido contrario al initiative atacante.

### Qué mide el código
`decision/scenarios/confirmation/failed_breakout.py:96-114`:
- **Fase 1**: detecta break con un buffer (`min_break_distance_pct` default 0.0003 = 3 bps), guarda timestamp + CVD al momento del break.
- **Fase 2**: espera que el precio regrese dentro del rango dentro de `max_break_age` (60s default).
- **Fase 3**: valida divergencia. Dos criterios:
  - `exhaustion_z = 2.0`: si el CVD acompañó la ruptura con `avg_velocity_z > 2.0`, lo trata como trend acceptance y descarta.
  - `divergence_z = 0.5`: requiere que `|avg_velocity_z| < 0.5` o que el CVD haya ido **opuesto** a la ruptura.

### La falla teórica
1. **No discrimina "fail" por exhaustion vs "fail" por response**. AMT distingue dos modos:
   - **Initiative exhausts**: el vendedor intentó, no pudo, se queda sinconvenientes. La entrada es LODGING porque el comprador va a defender.
   - **Initiative recognized**: el vendedor intenta, **alguien del lado contrario lo convence de que está mal** (se ve bid cargado). La entrada también es LONG, pero por una dynamically más robusta: hay respuesta visible.
   El código actual ignora este matiz. Solo valida que la CVD no haya acompañado fuerte (proxy de "no hay initiative"). Lo trata todo igual.

2. **La ventana de 60 segundos es muy estrecha**. Una false break en AMT a menudo toma minutos en completar (el precio revisa el borde, retrocede un poco, lo re-ataca, falla). Exigir re-entrada en menos de 60s descarta muchas failed auctions reales que se desarrollan en escalas de minutos.

3. **Acumulación de un solo pending_breaks por símbolo** (line 96: `self.pending_breaks.get(symbol)`). Si el primer break es justo y el segundo llega antes de cumplirse el primero, el segundo se IGNORA. En AMT no puedes ignorar breaks porque el mercado emite la información — capturarla toda es parte del surveillance.

### Conclusión de auditoría
Fallaría muchas aulas reales pero capturaría muchas aulas falsas. La estructura conceptual respeta AMT. Los defectos son calibración, no conceptuales.

### Mejoras concretas
1. Mantener múltiples pending breaks simultáneamente (lista), no uno por símbolo.
2. Aumentar `max_break_age` por defecto a esperar más tiempo en regímenes donde el rango es ancho.
3. Cuando hay divergencia, NO confiar solo en `cvd_velocity`. Añadir un check de **volumen seco en el book durante el break** (spikes de absorption en el lado contrario en footprint): eso *demuestra* que hubo response, no solo "no hubo initiative".

---

## 4. `trend_acceptance` — El único que respeta AMT y aun así tiene sus issue

### Qué dice AMT que debe ser
Initiative breakout: el precio sale de la VA con CVD concentrado en la dirección del breakout, extiende un poco (prueba que los contrarios no defienden), y vuelve a probar el borde roto ("pullback to the broken level"). El borde roto (ahora support/resistance) es donde AL initiative ganadora hace la pausa, y allí se entra Ahorra.

### Qué mide el código
`trend_acceptance.py:107-128`: requiere `price > vah` con `cvd_velocity > 4.0`, o simétrico para short. Threshold 4.0 (z-score 4-sigma). Confirma si `max_price` extienda más allá de `min_breakout_distance_bps` antes de tocar el "pullback level".

### La falla teórica
1. **`cvd_confirmation_threshold = 4.0` es muy alto**. Un z-score de 4-sigma ocurre **rara vez** (en distribución normal, ~una vez cada ~16k eventos). Combinado con la necesidad de `price > vah` simultáneo, esto se vuelve un setup que "solo dispara en movimientos parabólicos". El resultado es que **el setup casi nunca se ejecuta**, y cuando lo hace es tarde. En AMT un breakout aceptable confirma con z entre 1.5 y 3.0, no 4, porque el modelo mide initiative relativa, no intensidad absoluta.

2. **El janela del pullback es muy estrecha** (12 bps por defecto). `breakout_distance >= 20 bps` para validar que la ruptura extendió. Un pullback de 12 bps en una ruptura que extiende 20 requiere que el precio se dé vuelta muy rápido. Si se da vuelta lenta (más realista en AMT), el precio cae por debajo del pullback_level antes de que `breakout_distance_bps` se acumule. La condición se cancela cuando `price <= vah` (line 170) — literalmente se pierde la entrada.

3. **`max_pullback_penetration_pct` está siendo mal bridgeppado** como `min_breakout_distance_bps` (lines 78-79). Esto confunde dos cosas: distancia de ruptura mínima vs máxima profundidad de pullback permitida. Es un defecto de naming, no de concepto.

4. **Los cooldowns de 240–600 segundos** son muy altos para un breakout trend. AMT dice que el último breakout es el más relevante; cooldowns largos simplemente **mutilan la estadística del setup**.

### Conclusión de auditoría
Conceptualmente es el setup más AMT-aligned. Pero el Threshold 4-sigma lo deja inerte, la ventana de pullback es estrecha, y los cooldowns son excesivos. **El setup funciona bien en teoría, fatalmente calibrado en práctica.**

### Mejoras concretas
1. `cvd_confirmation_threshold: 1.5–2.5` (z-score 1.5-2.5).
2. Aumentar `pullback_bps` a 25-50 para recoger pullbacks más lentos y naturales.
3. Eliminar `max_breakout_distance_bps` como filtro; permitir que CUALQUIER pullback al nivel roto sea una entrada válida, siempre y cuando la CVD del breakout fue positivo. La distancia de extensión es informativa, no filter.
4. Bajar cooldown a 60-120s. Breakouts válidos pueden parecer consecutivos.

---

## Síntesis: lo que está bien y lo que no

| Setup | Conceptual AMT | Implementación actual | Diagnóstico |
|-------|----------------|------------------------|------------|
| `tactical_absorption` | Response a initiative exhaustion | Dirección por signo del CVD sin importar el book side | **Teóricamente incorrecto** — es la falla bloqueante |
| `liquidity_exhaustion` | Multiple test + declining attack + response reciente | Mide delta con z-score en vez de flujo; fragmenta nivel por decimal | Estructura correcta, proxies mal elegidas |
| `failed_breakout` | Break + no confirmación de delta + regreso al rango | Solo 1 break pendiente, ventana muy corta, sin discriminar response real | Estructura correcta, escala mal calibrada |
| `trend_acceptance` | Breakout + delta confirmation + extensión + pullback al borde | Threshold z=4 imposible, ventana pullback estrecha, cooldown enorme | Conceptualmente bien pero firewall de thresholds lo inutiliza |

## ¿Dónde está el "edge" teórico real?

De los 4 setups, **solo `liquidity_exhaustion` y `trend_acceptance` miden el patrón AMT correcto**. Pero ambos están calibrados para disparar **casi nunca**, lo que significa que el bot está operando primariamente `tactical_absorption` (donde la condición está conceptualmente mal) y siendo ahogado en falsas entradas o en `failed_breakout` (donde solo se ejecuta una pequeña fracción).

**El edge AMT — si existe — está enterrado bajo:**
1. Una condición de entrada conceptualmente rota (`tactical_absorption`).
2. Dos condiciones correctas pero inertes por exceso de threshold (`liquidity_exhaustion` y `trend_acceptance`).
3. Una que no logra capturar el patrón natural de la failed auction por ventana (`failed_breakout`).

## Trabajo derivado de este análisis (no implementación)

1. Reescribir `tactical_absorption.on_tick` para que **mapée location→direction coherentemente**: bid absorbiendo en/cerca del VAL → LONG; ask absorbiendo en/cerca del VAH → SHORT; sin absorción clara en book → descartar.
2. Cambiar el delta de `liquidity_exhaustion`: de `|z(cvd_velocity)|` a `|net_volume_flow|` y arreglar la identidad del nivel a solo el nombre del borde.
3. En `failed_breakout`: soportar múltiples pending breaks; ajustar `max_break_age` por régimen; añadir check de absorption-side en el book durante el break para distinguir response.
4. Bajar los thresholds en `trend_acceptance` para que el setup pueda disparar con normalidad (z 1.5-2.0, pullback 25-50 bps, cooldown 60-120s).
