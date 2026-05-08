# Manifiesto de Estrategia: Absorción Estadística V2.1 (Statistical Absorption Scalping)

**Enfoque**: Scalping de Reversión a la Media (Mean-Reversion) guiado por Order Flow.
**Entorno**: Mercados 24/7 (Criptomonedas).

---

## 1. La Filosofía Base

El mercado no se mueve por líneas diagonales imaginarias ni soportes estáticos. El mercado se mueve por la **búsqueda de liquidez** y el **agotamiento direccional**.

En los mercados tradicionales (como futuros del CME), la estructura del mercado se define por "sesiones" con horarios estrictos (Market Profile). En el ecosistema cripto, que opera ininterrumpidamente, los límites de las sesiones son arbitrarios. Un nivel estático calculado a las 4:00 AM pierde relevancia cuando la volatilidad cambia a las 10:00 AM.

Por lo tanto, el concepto de **Valor Justo (Fair Value)** debe ser dinámico, no estático. Nuestra estrategia busca identificar dislocaciones extremas de ese valor justo y operar la reversión **solamente cuando el flujo de órdenes en tiempo real confirma que el agresor ha sido atrapado**.

---

## 2. Los Dos Pilares de la Estrategia

La estrategia no adivina techos ni suelos. Requiere la coincidencia exacta de dos dimensiones: el "Dónde" (Contexto Estadístico) y el "Cuándo" (Microestructura).

### Pilar A: El Mapa Estadístico (VWAP y Bandas de Desviación)
Utilizamos un **Rolling VWAP** (Precio Promedio Ponderado por Volumen) como nuestra brújula de Valor Justo.

Sobre este VWAP, proyectamos bandas de Desviación Estándar (ej. ±2.0Z a ±2.5Z). Estas bandas actúan como **nuestras zonas de interés dinámicas**:
*   **Zona de Ruido**: Todo lo que ocurre cerca de la media (VWAP). Aquí el mercado está en equilibrio. Operar aquí es un juego de azar.
*   **Zona de Trampa (Los Extremos)**: Cuando el precio toca o supera las bandas externas, sabemos matemáticamente que el activo está experimentando una dislocación estadística (euforia o pánico). Aquí es donde prestamos atención.

### Pilar B: El Gatillo Táctico (Absorción en el Footprint)
El precio en un extremo estadístico no es motivo suficiente para entrar al mercado (evitamos intentar atrapar "cuchillos cayendo"). Necesitamos ver quién gana la batalla en la trinchera.

Utilizamos el análisis de **Footprint (Order Flow)** para buscar **Absorción Institucional**.
La absorción ocurre cuando vemos un volumen agresivo masivo (compras o ventas a mercado) estrellándose contra un muro de liquidez pasiva (órdenes limitadas) **sin lograr desplazar el precio**. El agresor gasta toda su munición, el precio se estanca y quedan "atrapados" en un nivel extremo.

---

## 3. El Setup de Ejecución

Una operación solo se ejecuta cuando ocurre la siguiente secuencia:

1. **Contexto Extremo**: El mercado sufre un impulso direccional agresivo que lo empuja fuera de las bandas de desviación (ej. > +2.0Z del VWAP).
2. **Agotamiento Detectado**: En el nivel más alto del impulso, el Footprint detecta un *Delta* extremo de compra, pero la vela cierra sin avance direccional. Las compras a mercado fueron absorbidas por liquidez pasiva.
3. **Disparo**: La combinación de desequilibrio estadístico + agresores atrapados genera una entrada inmediata en contra del movimiento (Short), apostando a que los agresores tendrán que liquidar sus posiciones, acelerando la reversión.

---

## 4. Gestión de Salida (Take Profit y Stop Loss)

Nuestra gestión de la salida es estrictamente matemática y estructural, eliminando la emocionalidad del trader.

*   **Take Profit (El Imán Matemático)**: Nuestro objetivo no es adivinar hasta dónde llegará el mercado. Nuestro único objetivo es el **VWAP actual**. Cuando el mercado expulsa a los participantes atrapados, el precio tiende a regresar a su punto de equilibrio natural (la media). Operar de los extremos hacia la media ofrece una tasa de acierto muy superior a buscar expansiones.
*   **Stop Loss (Invalidación de Tesis)**: El Stop Loss se coloca de forma rígida detrás del nivel de absorción. Si entramos porque un muro pasivo estaba absorbiendo compras, y ese muro es derribado (el precio rompe con volumen), nuestra tesis queda inmediatamente invalidada. Asumimos la pérdida pequeña y salimos.

---

## 5. Por Qué Funciona en Entornos Modernos

1. **Agnóstica a Horarios**: Al basarse en un Rolling VWAP, la estrategia no sufre el "reinicio" artificial del Market Profile. Las bandas se expanden automáticamente en momentos de alta volatilidad y se contraen en consolidaciones.
2. **Alta Fidelidad**: Evita las entradas prematuras de los sistemas puramente estadísticos (que operan solo porque el precio está lejos) al exigir la confirmación táctica del Footprint.
3. **Riesgo Asimétrico**: Operar reversiones desde extremos estadísticos con confirmación de flujo permite utilizar Stops muy ajustados, logrando un Ratio Riesgo/Beneficio altamente eficiente para el scalping agresivo.
