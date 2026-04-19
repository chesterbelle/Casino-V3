Quick Scalping Strategy: DOM Flow & Microstructure

Documento de Estrategia Completa
Independiente de implementación técnica
Índice

    Filosofía Fundamental

    Conceptos Base

    Setups de Trading

    Gestión de Riesgo

    Ejecución HFT

    Síntesis y Recomendaciones

1. Filosofía Fundamental
1.1 El Principio Central

"Observa, no supongas" - El mercado no sigue tus ideas. El mercado te muestra lo que está haciendo. La estrategia se basa en el razonamiento inductivo: primero observar el flujo de órdenes en tiempo real, generar una hipótesis sobre la intención institucional, y solo entonces ejecutar. No se entra con una idea preconcebida (deducción), sino que se deja que el mercado "hable" a través del DOM y el footprint.
1.2 Por qué el Order Flow funciona para Scalping
Característica	Ventaja para Scalping
DOM en tiempo real	Ves la guerra de órdenes límite antes de que el precio se mueva
Vacíos de liquidez	Identificas zonas donde el precio se movió sin oposición
Icebergs detectables	Las grandes órdenes ocultas dejan huella en el flujo
Agotamiento medible	El volumen y delta te muestran cuándo se acaba la fuerza
1.3 El Principio de Selección Adversa

Concepto crítico:

    Si una orden es fácil de conseguir, probablemente no la quieras. Si es difícil, es la que buscas.

    Orden pasiva (limit) : La pones y esperas. Si se llena rápido, es porque el mercado se mueve en tu contra. Si se llena con esfuerzo, es buena.

    Orden agresiva (market) : Si entras con market y te dan el precio inmediatamente, es mala señal. Si tienes que "pelear" por el precio, es buena.

    Regla: No entres donde todos entran. Busca la liquidez oculta.

2. Conceptos Base
2.1 Low Volume Node (LVN)

Definición: Nivel o zona de precio donde se ha ejecutado un volumen significativamente menor que el promedio circundante.

Por qué importa:

    El precio cruzó esta zona rápidamente porque no había órdenes límite.

    Es un "vacío de liquidez" que actúa como imán: cuando el precio regresa a un LVN, tiende a reaccionar.

    Los LVNs dentro de un movimiento direccional son zonas ideales para pullbacks.

Identificación:
text

Perfil de volumen en una ventana de 30-60 minutos:
100.0: 450 vols (Alto)
100.1: 12 vols  ← LVN (Vacío)
100.2: 8 vols   ← LVN
100.3: 380 vols (Alto)

2.2 Jump Flow

Definición: Un "salto" en el DOM donde el precio se mueve varios ticks sin encontrar oposición, dejando un vacío claro en el footprint.

Mecánica:

    Aparece un desequilibrio masivo en un lado del libro.

    El otro lado (contrapartida) desaparece o es insignificante.

    El precio se mueve rápidamente, sin colas largas en las velas.

Interpretación:

    Indica que el mercado se ha quedado sin contrapartida en esa dirección.

    Es una señal de continuación agresiva, no de reversión.

2.3 Iceberg Order (Orden Oculta)

Definición: Una orden límite grande que se muestra en el DOM en fragmentos pequeños para ocultar su verdadero tamaño.

Detección:

    Mismo nivel de precio aparece repetidamente en el DOM con cantidades similares.

    El nivel se "recarga" una y otra vez después de ser consumido.

    El precio no logra atravesar el nivel a pesar de múltiples intentos.

Interpretación:

    Si el iceberg está en el bid (compra pasiva), alguien grande quiere comprar y está defendiendo ese nivel.

    Si el iceberg es consumido (absorbido), es una señal de que la presión ha vencido a la orden oculta.

2.4 Poor High / Poor Low

Definición: Un máximo o mínimo de sesión (o de ventana) que tiene muy poco volumen en su extremo y ninguna cola (wick) significativa.

Interpretación:

    Es un nivel "débil" que el mercado probablemente querrá "reparar".

    El precio suele volver a testear estos niveles para buscar liquidez.

    No son buenos niveles para poner stops, sino para anticipar barridos de liquidez.

2.5 4TPO Ledge (Repisa de 4 Perfiles)

Definición: En el perfil de mercado, una zona donde el precio ha estado rotando (4 o más perfiles TPO) sin expandirse.

Interpretación:

    Es una zona de balance o "acumulación".

    Una ruptura de esta zona suele ser falsa inicialmente.

    El mercado busca liquidez más allá de la repisa antes de moverse realmente.

3. Setups de Trading
3.1 Setup #1: Jump Flow Continuation

Tipo: Continuación agresiva

Condiciones:

    Detección de un Jump Flow en el DOM (precio se mueve rápido, dejando vacíos).

    El precio no encuentra oposición inmediata en el siguiente nivel.

    El delta muestra aceleración en la dirección del movimiento.

Entrada:
text

CONTINUACIÓN ALCISTA:
- Jump Flow detectado hacia arriba
- Esperar un micro-pullback (1-2 ticks)
- ENTRAR LONG en el pullback

CONTINUACIÓN BAJISTA:
- Jump Flow detectado hacia abajo
- Esperar un micro-pullback
- ENTRAR SHORT en el pullback

Stop Loss: 2-3 ticks por detrás del nivel donde se originó el Jump Flow.

Take Profit: Próximo LVN o zona de alta densidad de volumen.

Win Rate estimado: 65-70%
3.2 Setup #2: LVN Pullback

Tipo: Continuación tras retroceso

Condiciones:

    Identificar un LVN (Low Volume Node) dentro de un movimiento direccional.

    El precio retrocede hacia la zona del LVN.

    En el LVN, aparece confirmación de order flow (absorción ligera o big order).

Entrada:
text

LVN ALCISTA (para LONG):
- Movimiento alcista previo
- LVN identificado en el camino
- Precio retrocede al LVN
- Confirmación en bid (compradores pasivos)
- ENTRAR LONG

LVN BAJISTA (para SHORT):
- Movimiento bajista previo
- LVN identificado
- Precio retrocede al LVN
- Confirmación en ask (vendedores pasivos)
- ENTRAR SHORT

Stop Loss: Al otro lado del LVN (1-2 ticks).

Take Profit: Continuación hasta el siguiente LVN o extremo del movimiento.

Win Rate estimado: 65-70%
3.3 Setup #3: False Break Reversal

Tipo: Reversión por ruptura falsa

Condiciones:

    El precio rompe un nivel clave (soporte/resistencia, high/low de sesión, etc.).

    La ruptura no tiene follow-through (el precio no sigue en esa dirección).

    El precio vuelve a entrar en el rango previo rápidamente.

    En el momento del reingreso, hay confirmación de order flow en contra de la ruptura.

Entrada:
text

FALSO RUPTURA ALCISTA (para SHORT):
- Precio rompe resistencia
- No sigue subiendo
- Reingresa al rango
- Aparece absorción en el ask o big sell order
- ENTRAR SHORT

FALSO RUPTURA BAJISTA (para LONG):
- Precio rompe soporte
- No sigue bajando
- Reingresa al rango
- Aparece absorción en el bid o big buy order
- ENTRAR LONG

Stop Loss: 1-2 ticks más allá del extremo de la ruptura falsa.

Take Profit: Punto medio del rango previo o próximo nivel de volumen.

Win Rate estimado: 70-75%
3.4 Setup #4: Absorption Reversal

Tipo: Reversión por absorción institucional

Condiciones:

    El precio llega a un nivel clave (soporte/resistencia, LVN, VAH/VAL).

    Aparece volumen pesado en ambos lados del footprint en ese nivel.

    El precio NO avanza a pesar del volumen agresivo.

    Se detecta posible iceberg (el nivel se recarga).

Entrada:
text

ABSORCIÓN EN RESISTENCIA (para SHORT):
- Precio toca resistencia
- Volumen alto en ask (vendedores pasivos) y bid (compradores agresivos)
- Precio no sube
- ENTRAR SHORT cuando precio comienza a bajar

ABSORCIÓN EN SOPORTE (para LONG):
- Precio toca soporte
- Volumen alto en bid (compradores pasivos) y ask (vendedores agresivos)
- Precio no baja
- ENTRAR LONG cuando precio comienza a subir

Stop Loss: 2-3 ticks al otro lado del nivel de absorción.

Take Profit: Nivel opuesto del rango o siguiente LVN.

Win Rate estimado: 65-70%
3.5 Setup #5: Exhaustion Reversal

Tipo: Reversión por agotamiento

Condiciones:

    El precio ha tenido un movimiento direccional fuerte.

    El volumen comienza a disminuir (exhaustión).

    El delta empieza a divergir (precio sigue haciendo extremos, pero delta se aplan o gira).

    Se detecta una "impresión de agotamiento" en el footprint (pico de volumen en el extremo).

Entrada:
text

AGOTAMIENTO ALCISTA (para SHORT):
- Precio hace nuevo máximo
- Volumen en el máximo es bajo o decreciente
- Delta plano o negativo
- ENTRAR SHORT

AGOTAMIENTO BAJISTA (para LONG):
- Precio hace nuevo mínimo
- Volumen en el mínimo es bajo o decreciente
- Delta plano o positivo
- ENTRAR LONG

Stop Loss: 2-3 ticks más allá del extremo.

Take Profit: Retroceso hasta el nivel de inicio del movimiento o siguiente LVN.

Win Rate estimado: 70-75%
3.6 Setup #6: Iceberg Confirmation

Tipo: Confirmación de nivel (para entrada o salida)

Condiciones:

    Se detecta un iceberg en el DOM (mismo nivel recargándose).

    El precio está cerca de ese nivel.

    Se identifica si el iceberg está siendo defendido o consumido.

Entrada:
text

ICEBERG EN SOPORTE (para LONG):
- Iceberg detectado en el bid
- El nivel se recarga una y otra vez
- El precio no logra atravesarlo a la baja
- ENTRAR LONG cuando el precio rebota

ICEBERG EN RESISTENCIA (para SHORT):
- Iceberg detectado en el ask
- El nivel se recarga
- El precio no logra atravesarlo al alza
- ENTRAR SHORT cuando el precio rebota

ICEBERG CONSUMIDO (para salida o contraposición):
- El iceberg es finalmente absorbido por agresión en contra
- Señal de que la defensa ha fallado
- Salir si se está en la dirección del iceberg, o entrar en contra si se busca la ruptura

Stop Loss: 1-2 ticks detrás del nivel del iceberg.

Take Profit: Próximo nivel de volumen o iceberg.

Win Rate estimado: 65-70%
3.7 Setup #7: Poor High/Low Reversal

Tipo: Reversión anticipada

Condiciones:

    Se identifica un Poor High o Poor Low en la sesión actual (extremo con poco volumen).

    El precio se acerca a ese nivel.

    Se espera un barrido de liquidez (el precio supera brevemente el nivel).

    Inmediatamente después del barrido, aparece confirmación de order flow en contra.

Entrada:
text

POOR HIGH (para SHORT):
- Máximo de sesión con poco volumen
- Precio lo supera (barrido)
- El precio vuelve a entrar por debajo del máximo
- Aparece absorción o big sell order
- ENTRAR SHORT

POOR LOW (para LONG):
- Mínimo de sesión con poco volumen
- Precio lo supera a la baja (barrido)
- El precio vuelve a entrar por encima del mínimo
- Aparece absorción o big buy order
- ENTRAR LONG

Stop Loss: 2-3 ticks más allá del extremo barrido.

Take Profit: Punto medio del rango o nivel opuesto.

Win Rate estimado: 70-75%
4. Gestión de Riesgo
4.1 Tamaño de Posición

Regla base: 0.25% - 0.5% del capital por operación.

Para scalping HFT:

    Usar 0.25% debido a la alta frecuencia.

    Escalar la posición: entrar con el 50% del tamaño, añadir el resto si la operación confirma.

4.2 Principio de Escalado (Clipping)

No esperar a que el TP se alcance para cerrar todo.
Nivel de beneficio	Acción
1x riesgo	Cerrar 25% de la posición
1.5x riesgo	Cerrar otro 25%
2x riesgo	Cerrar otro 25%
Resto	Dejar correr con trailing stop

Razón: El mercado raramente llega al TP en línea recta. Escalar asegura beneficios parciales y reduce el dolor si el mercado revierte.
4.3 Stop Loss Dinámico (Nunca mantener toda la posición en contra)
Regla	Acción
Si la posición se mueve 0.5x riesgo en contra	Reducir tamaño un 50%
Si la posición toca el SL estructural	Cerrar todo
Si aparece señal de agotamiento en contra	Cerrar todo inmediatamente

Principio: Es mejor salir con una pérdida pequeña que mantener una posición que podría ser catastrófica.
4.4 Selección Adversa en la Entrada

    Si tu orden limit se llena inmediatamente → reconsidera, probablemente es mala.

    Si tu orden market se ejecuta al precio que pediste sin deslizamiento → probablemente llegaste tarde.

    Si tienes que "pelear" por el precio (deslizamiento de 1-2 ticks) → buena señal.

5. Ejecución HFT
5.1 Requerimientos Técnicos
Componente	Necesario
DOM (Level 2)	Sí (para detectar icebergs y jump flow)
Footprint en tiempo real	Sí
Latencia	< 100ms (ideal < 50ms)
Datos tick-by-tick	Sí
5.2 Timeframes y Herramientas
Herramienta	Uso
DOM (Depth of Market)	Detectar icebergs, jump flow, desequilibrios
Footprint (1-min o tick)	Confirmar absorción, agotamiento, LVNs
Perfil de volumen (15-30 min)	Identificar LVNs y poor high/low
5.3 Horarios Óptimos

    Apertura de NY (13:00-14:00 UTC): Mayor liquidez, más icebergs y jump flow.

    Overlap Londres-NY (13:00-16:00 UTC): Máxima actividad institucional.

    Apertura de Londres (8:00-9:00 UTC): Segundo mejor momento.

    Evitar: Horario asiático (00:00-8:00 UTC) y quiet hours (21:00-00:00 UTC).

5.4 Facilidad de Automatización
Setup	Facilidad	Razón
Jump Flow	Media	Requiere detección de vacíos en DOM
LVN Pullback	Alta	Basado en perfil de volumen estático
False Break	Alta	Basado en niveles y reingreso
Absorption	Alta	Volumen en ambos lados + precio estático
Exhaustion	Alta	Divergencia precio-delta-volumen
Iceberg	Baja	Difícil de detectar automáticamente (patrones de recarga)
Poor High/Low	Media	Basado en volumen en extremos
6. Síntesis y Recomendaciones
6.1 Jerarquía de Setups por Confianza y Frecuencia
Nivel	Setup	Win Rate	Frecuencia	Dificultad automatización
1	Exhaustion Reversal	70-75%	Media	Alta
2	False Break Reversal	70-75%	Media	Alta
3	Absorption Reversal	65-70%	Media-Alta	Alta
4	LVN Pullback	65-70%	Media	Alta
5	Jump Flow	65-70%	Baja-Media	Media
6	Iceberg Confirmation	65-70%	Baja	Baja
7	Poor High/Low	70-75%	Baja	Media
6.2 Combinación de Setups (Confirmación Múltiple)

Ejemplo de operación ideal:
text

1. Se identifica un Poor High en la sesión (contexto estructural).
2. El precio barre el Poor High (barrido de liquidez).
3. En el momento del barrido, aparece un iceberg en el ask (resistencia).
4. El precio reingresa por debajo del Poor High (false break).
5. Aparece absorción en el ask (vendedores pasivos).
6. ENTRAR SHORT.

5 confirmaciones → Alta probabilidad de éxito.

6.3 Lo que NO funciona en este modelo

    Operar sin DOM: Los setups de Jump Flow e Iceberg son imposibles sin Level 2.

    Esperar la confirmación perfecta: Si pides 5 señales, te quedarás sin operar. 2-3 son suficientes.

    Mantener toda la posición hasta el TP: Escalar es clave. El que no escala, regala beneficios.

    Ignorar la selección adversa: Si te dan la orden fácil, desconfía.

6.4 Visión del Modelo

Este enfoque no es un "sistema" cerrado, sino un conjunto de herramientas tácticas para leer la intención institucional en tiempo real. La ventaja no está en un setup mágico, sino en la capacidad de observar, generar una hipótesis y ejecutar con disciplina.

El trader exitoso no es el que mejor predice el mercado, sino el que mejor reacciona a lo que el mercado le muestra en el DOM y el footprint.
Apéndice A: Glosario
Término	Definición
DOM (Depth of Market)	Libro de órdenes que muestra bids y asks con sus cantidades
LVN (Low Volume Node)	Nivel de precio con volumen significativamente menor al promedio
Jump Flow	Movimiento rápido del precio sin oposición, dejando vacíos en el footprint
Iceberg	Orden límite grande mostrada en fragmentos para ocultar su tamaño real
Poor High/Low	Extremo de sesión con poco volumen, propenso a ser barrido
Clipping	Escalado de posición cerrando parcialmente a diferentes niveles de beneficio
Selección Adversa	Principio por el cual las órdenes "fáciles" son malas y las "difíciles" son buenas
4TPO Ledge	Zona de balance en el perfil de mercado donde el precio ha rotado sin expandirse
Apéndice B: Referencias

Conceptos fundamentales (sin fuentes explícitas):

    Auction Market Theory

    Market Profile (Dalton)

    Order Flow (Footprint, DOM)

    Principio de Selección Adversa

    Gestión de riesgo con escalado

Documento creado para evaluación independiente. Independiente de implementación técnica específica.
