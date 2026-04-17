# LTA V4: Reversión Estructural + Fade de Cascada

## Filosofía Central

El mercado es una subasta continua. El precio busca el punto de máxima aceptación (POC) y oscila entre los extremos del Área de Valor (VAH/VAL). Cuando el precio se desplaza hacia un extremo sin volumen que lo sostenga, se genera una trampa de liquidez — un desequilibrio temporal que eventualmente se corrige mediante una reversión al centro de gravedad.

La LTA V4 no predice dirección. **Detecta agotamiento en los bordes y capitaliza la corrección gravitacional.**

---

## 1. La Trampa de Liquidez (Liquid Trap)

### 1.1 El Concepto

Imagina un imán (el POC) rodeado por dos paredes (VAH arriba, VAL abajo). El precio es una bola de acero que rebota entre las paredes, pero siempre tiende a regresar al imán.

Cuando la bola golpea una pared con fuerza y no la rompe, eso es una **Failed Auction** — el mercado probó un precio extremo, nadie quiso transaccionar allí, y ahora regresará al imán.

### 1.2 La Ventaja Estadística

La teoría de Market Profile (Dalton, 1990) demuestra que el precio pasa el **70% del tiempo dentro del Área de Valor**. Cada desviación hacia los extremos tiene una probabilidad inherente de corrección. La LTA V4 explota esta asimetría estadística.

Resultado certificado: **Win Rate 59.5%** a 0.3%/0.3% TP/SL con expectancy positiva sobre 112 señales en 3 pares cripto (24h cada uno).

### 1.3 El "Slow Burn" (Maduración de 15 Minutos)

La reversión estructural no es instantánea. Después de que el precio toca el extremo y muestra señales de rechazo, la migración de vuelta al POC toma típicamente entre 5 y 15 minutos. Esto es clave: la estrategia requiere paciencia institucional, no scalping nervioso.

---

## 2. Fuente de Verdad: El Perfil de Sesión

### 2.1 El Principio

Toda la estrategia opera sobre **perfiles de liquidez por ventana**, no sobre un perfil acumulativo global. Cada ventana de liquidez (Asian, London, Overlap, NY, Quiet) produce su propio juego de niveles:

- **POC de sesión** — El punto de máxima aceptación *de esta ventana*.
- **VAH/VAL de sesión** — Los extremos del Área de Valor *de esta ventana*.
- **VA Integrity de sesión** — La concentración del perfil *de esta ventana*.

Cuando la ventana cambia (ej: Asian → London), el perfil se resetea. Esto asegura que los niveles estructurales son siempre frescos y relevantes a la liquidez actual, no contaminados por volumen de horas anteriores.

### 2.2 Por Qué No el Perfil Global

Un perfil que acumula 24 horas de ticks diluye el POC hasta que pierde fuerza gravitacional. El VA se expande artificialmente. La integridad colapsa a valores microscópicos. **Un perfil acumulativo miente sobre la estructura real del mercado.**

La misma lógica aplica para multi-símbolo: cada par tiene su propio perfil de sesión independiente, con niveles que reflejan su liquidez y estructura específica.

---

## 3. Los Dos Playbooks

### 3.1 Playbook Alpha: Reversión Estructural

**Señal:** El precio alcanza el borde del Área de Valor (VAH para shorts, VAL para longs) y un sensor de microestructura detecta agotamiento, absorción o divergencia delta.

**Mecánica:**
1. El precio está dentro del 0.25% de VAH o VAL (de la ventana activa).
2. Un sensor táctico confirma el rechazo (absorción, exhaustión, delta divergence, trampa de traders, etc.).
3. Los 6 Guardianes de Flujo validan la calidad del setup.
4. Se entra en dirección al POC con SL fuera del borde.

**Target:** El POC de la ventana de liquidez activa.

**SL:** Buffer estructural fuera del extremo (VAH + buffer para shorts, VAL - buffer para longs).

---

### 3.2 Playbook Beta: Fade de Cascada de Liquidación

**Señal:** Una cascada de liquidaciones retail (stop-chain) ha ocurrido y se ha agotado.

**Mecánica:**
1. Volumen explota a 5× el promedio de 20 barras.
2. Z-score del delta supera ±4.0 (flujo extremamente unidireccional).
3. El precio se desplaza más de 2× ATR en la dirección de la cascada.
4. La exhaustión se confirma: el volumen cae a menos del 50% del pico y el delta se invierte.

**Concepto:** "Surfear el Tsunami" — no intentamos predecir la ola, esperamos a que se estrelle contra la costa y luego surfeamos el reflujo.

**Target:** POC (el precio gravitará de vuelta al centro después de la dislocación extrema).

**SL:** Igual que Playbook Alpha — fuera del borde estructural.

---

## 4. Los 6 Guardianes del Flujo

Cada señal de entrada debe pasar por 6 gates defensivas antes de ejecutarse. Si cualquiera falla, el trade se descarta.

### Guardián 1: Alineación de Régimen
El mercado tiene un régimen macro (tendencia alcista, bajista o neutral). Una reversión SHORT en VAH durante una tendencia alcista fuerte (OTF Bull) es estadísticamente suicida — el trend puede sobrepasarse. Este guardián bloquea reversiones contra-tendencia.

- **NEUTRAL** → Siempre PASA.
- **UP + LONG** en VAL → PASA (alineado con tendencia).
- **UP + SHORT** en VAH → BLOQUEADO (contra-tendencia peligrosa).
- **DOWN + SHORT** en VAH → PASA.
- **DOWN + LONG** en VAL → BLOQUEADO.

### Guardián 2: Migración del POC
Si el POC está migrando activamente en la dirección opuesta a nuestra entrada, el mercado está en fase de "descubrimiento" — está aceptando precios en una nueva zona. Fading un descubrimiento activo es autodestructivo.

- Bloqueado si la migración excede el 0.5% en contra.

### Guardián 3: Integridad del Área de Valor
Un VA limpio y concentrado (perfil en forma de campana) indica que el POC es un imán poderoso. Un VA expandido o con doble pico indica incertidumbre — el POC no tiene fuerza gravitacional.

La integridad se calcula **del perfil de la ventana activa**, no del perfil acumulativo global. Esto asegura que la medición refleja la liquidez real de la sesión actual.

El umbral es dinámico según la ventana de liquidez:

| Ventana | Umbral | Razón |
|---------|--------|-------|
| Asian | 0.06 | Volumen bajo, perfiles naturalmente dispersos |
| London | 0.10 | Mayor liquidez, perfiles más limpios |
| Overlap | 0.12 | Pico de liquidez, perfiles más definidos |
| NY | 0.10 | Alta liquidez |
| Quiet | 0.05 | Muy baja liquidez, ser permisivo |

### Guardián 4: Confirmación de Subasta Fallida
La vela actual debe mostrar una "mecha de rechazo" — el precio probó más allá del borde pero cerró dentro. Esto confirma que los participantes rechazaron activamente el precio extremo.

- La mecha de rechazo debe ser al menos el 5% del cuerpo de la vela.

### Guardián 5: Divergencia Delta
El flujo de órdenes (delta acumulativo) debe estar neutral o a favor de nuestra dirección. Si el delta está agresivamente contra nosotros, el rechazo no es genuino — hay presión real detrás del movimiento.

### Guardián 6: Sanidad del Spread
El spread bid/ask debe estar dentro de rangos normales. Si el spread es mayor al doble de su promedio de 5 minutos, estamos en un micro-momento de iliquidez donde el slippage se comería la ventaja.

---

## 5. Gestión de Riesgo

### 5.1 TP/SL Estructural
- **TP:** POC de la ventana de liquidez activa.
- **SL:** Fuera del borde estructural con buffer calibrado.
- **RR mínimo:** 1.0 (rechazado si es menor).

### 5.2 Invalidación por Flujo (Botón de Pánico Institucional)
Si durante un trade abierto el Z-score del delta cae por debajo de -3.0 (para longs) o sube por encima de +3.0 (para shorts), la narrativa de la entrada murió. La posición se cierra inmediatamente sin esperar al SL.

Esto es el equivalente a que un trader institucional diga: "La tesis está muerta, salgo ahora."

### 5.3 Stagnation Exit
Si el precio no se resuelve dentro de un timeout adaptativo (ajustado por volatilidad), la posición se cierra por "narrativa estancada."

### 5.4 Catastrophic Stop
Última línea de defensa: si la posición pierde más del 50% de su valor, se cierra inmediatamente independientemente de cualquier otro criterio.

---

## 6. Operación por Ventanas de Liquidez

La estrategia opera 24/7 pero adapta su comportamiento según la ventana de liquidez activa:

| Ventana | Horario UTC | Volatilidad | Adaptación |
|---------|------------|-------------|------------|
| Asian | 00:00 - 08:00 | Baja | VA Integrity relajada (0.06) |
| London | 08:00 - 16:00 | Media-Alta | VA Integrity estricta (0.10) |
| Overlap | 13:00 - 16:00 | Muy Alta | VA Integrity máxima (0.12) |
| NY | 16:00 - 21:00 | Alta | VA Integrity estricta (0.10) |
| Quiet | 21:00 - 00:00 | Muy Baja | VA Integrity mínima (0.05) |

El Initial Balance (IB) se calcula en los primeros 10 minutos de cada ventana (5 minutos en Overlap). El perfil de cada ventana se resetea al inicio de la misma, asegurando niveles frescos.

---

## 7. Señales Tácticas Compatibles

La estrategia acepta múltiples tipos de señales de microestructura como confluencia para la entrada:

1. **Absorción** — Alto volumen en un nivel sin movimiento de precio.
2. **Rejection** — Rechazo visible en footprint (mecha larga con volumen).
3. **Delta Divergence** — Precio hace nuevo extremo pero delta no confirma.
4. **Trapped Traders** — Participantes atrapados en el lado equivocado.
5. **Exhaustión** — Volumen se seca en el extremo (nadie más quiere participar).
6. **Stacked Imbalance** — Desequilibrios apilados que confirman dirección.
7. **POC Shift** — POC migra confirmando la dirección del trade.
8. **Liquidation Cascade** — Cascada de liquidaciones retail que se agota.

---

## 8. Resumen Ejecutivo

> La LTA V4 es una estrategia de reversión al centro de gravedad del mercado, activada por señales de microestructura en los extremos del Área de Valor, protegida por 6 capas defensivas, y complementada por un detector de cascadas de liquidación. Opera sobre perfiles de sesión (no acumulativos), lo que asegura que los niveles estructurales son frescos y la integridad del VA refleja la liquidez real. Es una estrategia de paciencia institucional, no de predicción.
