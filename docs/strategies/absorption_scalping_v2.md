ABSORPTION SCALPING V2: Agotamiento Confirmado

Filosofía Central

El mercado es una guerra entre agresores y defensores. Cuando un bando ataca con todo su volumen y no logra mover el precio, queda expuesto: se quedó sin munición. El otro bando lo devora y el precio gira.

Pero aquí está el problema que destruye a la mayoría de traders de absorción: no todo volumen agresivo es agotamiento. A veces el atacante solo está recargando. A veces el defensor no está absorbiendo — está retrocediendo lentamente. A veces el volumen extremo es el inicio de un impulso legítimo que arrasará todo a su paso.

La diferencia entre absorción real y falso agotamiento no se ve en el momento del ataque. Se ve en lo que pasa después.

Esta estrategia no entra cuando detecta el ataque. Entra cuando verifica la rendición.

El mercado no debe nada a tu señal de absorción. Hasta que el precio confirme el giro, es solo una hipótesis.


1. El Principio de Esfuerzo sin Resultado — y Su Trampa

1.1 El Concepto

Imagina dos ejércitos en el campo de batalla. El ejército rojo (vendedores) lanza una ofensiva masiva. El volumen se dispara. El delta se desploma. Los vendedores están empujando con todo.

Pero la línea del frente no se mueve.

El ejército verde (compradores pasivos) está absorbiendo cada ataque sin retroceder. Los rojos gastan su munición. Cuando se quedan sin balas, los verdes avanzan. El precio sube.

Esto es Absorción: volumen agresivo sin desplazamiento de precio.

1.2 La Trampa

El concepto es seductoramente simple. Tan simple que la mayoría de traders de order flow entran en el momento exacto en que ven volumen extremo sin movimiento de precio. Y la mitad de las veces, pierden.

¿Por qué? Porque delta extremo sin desplazamiento puede significar tres cosas muy distintas:

Absorción real: Un defensor grande está absorbiendo pasivamente. El agresor se agotará y el precio girará.

Impulso en pausa: El agresor está recargando, no rendido. El volumen extremo es el inicio de un movimiento direccional fuerte. Entrar contra él es suicidio.

Batalla indecisa: Ambos bandos atacan con fuerza. No hay absorción — hay guerra. La dirección es incierta.

La única forma de distinguir entre estas tres posibilidades es esperar. Observar qué pasa después del evento de volumen extremo. Si el agresor se rindió, aparecerán señales de giro en los ticks posteriores. Si no se rindió, el precio continuará en la dirección del ataque.

1.3 La Solución: Dos Fases Estrictamente Separadas

FASE 1 — DETECCIÓN: Identificar candidato a absorción (delta extremo + precio estancado)
FASE 2 — CONFIRMACIÓN: Verificar que el agresor se rindió (giro de delta + precio rompe nivel)

No se entra en la Fase 1. Se entra solo cuando la Fase 2 confirma.


2. Fuente de Verdad: El Footprint en Tiempo Real

2.1 El Principio

Toda la estrategia opera sobre el Footprint Chart calculado en tiempo real desde el stream de trades. Cada nivel de precio acumula:

- Volumen Ask: Compras agresivas (traders que cruzan el spread para comprar)
- Volumen Bid: Ventas agresivas (traders que cruzan el spread para vender)
- Delta: Volumen Ask menos Volumen Bid en ese nivel
- Delta Acumulado (CVD): Suma corrida del Delta desde el inicio de la sesión

No se utilizan perfiles de sesión predefinidos, Value Areas, POCs históricos ni zonas de soporte/resistencia dibujadas a mano. La absorción puede aparecer en cualquier nivel y es igualmente válida. El Footprint no miente. Las zonas sí.

2.2 Absorción vs. Agotamiento

Estos dos conceptos se confunden frecuentemente pero son mecánicamente distintos:

Absorción: Un defensor pasivo (órdenes límite grandes) recibe todo el ataque del agresor y el precio no se mueve. El agresor tiene munición pero no puede avanzar porque hay un muro. Ejemplo: vendedores golpean el bid con volumen extremo, pero compradores pasivos absorben cada contrato y el precio no baja.

Agotamiento: El agresor se queda sin munición por sí solo. No hay defensor activo — simplemente nadie más quiere atacar. El volumen se desvanece en los extremos. Ejemplo: compradores empujaban el precio al alza, pero el volumen de compra disminuye progresivamente hasta desaparecer.

Absorción detiene el precio desde afuera (un muro lo frena). Agotamiento detiene el precio desde adentro (el motor se apaga). Ambos llevan al mismo resultado — giro de precio — pero la absorción es más potente porque el defensor activo puede contraatacar una vez que el agresor se rinde.

V2 detecta específicamente absorción (delta extremo + precio estancado), no agotamiento genérico (volumen decreciente). La distinción importa porque la absorción implica un participante grande defendiendo un nivel, lo cual genera un giro más violento cuando el agresor se rinde — los traders atrapados en la dirección del ataque generan una cascada de salidas que acelera el movimiento a favor.


3. El Setup de Entrada: Dos Fases Separadas

3.1 FASE 1 — Detección de Candidato a Absorción

Un nivel de precio es candidato a absorción cuando cumple tres condiciones simultáneas:

Condición 1: Volumen agresivo extremo
El delta absoluto en un nivel de precio específico supera significativamente el delta promedio de los niveles circundantes. Esto se mide como z-score cross-sectional: cuántas desviaciones estándar por encima de la media se encuentra el delta de este nivel comparado con todos los niveles activos del footprint actual.

Un z-score de 2.5 o superior indica que el volumen en este nivel es estadísticamente anómalo — no es ruido normal, es un evento.

Condición 2: Precio estancado
A pesar del delta extremo, el precio no se desplaza significativamente en la dirección del ataque. Permanece en el mismo nivel o se mueve menos de 0.05% en la dirección del agresor durante la ventana de acumulación.

Esta es la condición que muchos traders de absorción omiten. Delta extremo donde el precio SÍ se movió no es absorción — es impulso legítimo. Un atacante que logra avanzar no está siendo absorbido; está ganando. Entrar contra él es suicidio.

Condición 3: Ausencia de ruido contrario
Durante la ventana de absorción, menos del 20% del volumen del nivel es delta en dirección contraria. Si hay volumen agresivo en ambos lados, no es absorción — es una batalla indecisa. La absorción real es limpia: un bando ataca, el otro absorbe sin contraatacar.

3.2 FASE 2 — Confirmación de Rendición

La Fase 1 identifica un candidato. Pero el candidato puede ser falso — el agresor puede estar recargando, no rendido. La Fase 2 espera evidencia de que el giro efectivamente ocurrió.

Se requiere que AL MENOS DOS de las siguientes tres confirmaciones ocurran dentro de una ventana de tiempo corta (típicamente 1-3 velas posteriores a la detección):

Confirmación A: Delta opuesto aparece
Tras el agotamiento del agresor, aparecen ticks con delta en dirección contraria al ataque original. Si el ataque era de venta (delta negativo extremo), ahora aparece delta positivo. Esto indica que el defensor dejó de absorber pasivamente y empezó a contraatacar agresivamente.

Confirmación B: Precio rompe el nivel de absorción
El precio se mueve en la dirección opuesta al ataque original, atravesando el nivel donde ocurrió la absorción. Si la absorción fue de venta en el nivel 100.50, el precio sube por encima de 100.50. Esto confirma que el defensor tomó el control y el agresor ya no puede mantener el nivel.

Confirmación C: CVD cambia de dirección
El delta acumulado (CVD) muestra una inflexión visible — la pendiente se aplana y luego gira en dirección opuesta al ataque original. Esto confirma que el flujo de ordenes cambió de bando, no fue solo una pausa.

¿Por qué se requieren solo 2 de 3 y no las 3?
Porque esperar las tres confirmaciones reduce demasiado la cantidad de señales. En la práctica, el delta opuesto y la ruptura de precio suelen ocurrir casi simultáneamente, mientras que el CVD es un indicador más lento que puede no girar hasta que el movimiento ya está en curso. Requerir 2 de 3 balancea rigor con oportunidad.

3.3 Dirección de la Entrada

- Absorción de venta (delta negativo extremo, precio no baja) + confirmación de giro → Entrada LARGA
- Absorción de compra (delta positivo extremo, precio no sube) + confirmación de giro → Entrada CORTA

3.4 La Ventana de Confirmación

La confirmación debe ocurrir dentro de una ventana temporal limitada. Si pasan más de 3 velas (típicamente 3-5 minutos en timeframe de 1 minuto) sin que aparezcan las confirmaciones, el candidato expira. La absorción que no genera giro rápido no era absorción real — era acumulación lenta o batalla en curso.

4. Los Filtros de Calidad (Fase 1)

Cada candidato a absorción debe pasar por 3 filtros antes de pasar a la Fase 2. Si cualquiera falla, el candidato se descarta.

Filtro 1: Magnitud del Agotamiento
El delta del nivel de absorción debe ser genuinamente extremo, no una fluctuación normal del mercado.

El delta absoluto del nivel debe superar 2.5 desviaciones estándar del delta promedio de todos los niveles activos del footprint actual (z-score cross-sectional).

Si el delta es grande pero está dentro de lo normal para ese activo en ese momento, no hay agotamiento real — es volumen normal disfrazado de señal.

Filtro 2: Concentración del Ataque
La absorción debe ocurrir en un nivel específico, no dispersarse por múltiples niveles. Si el delta extremo está repartido entre 5 niveles, no hay un punto de defensa claro — es flujo distribuido.

Al menos el 60% del delta extremo debe concentrarse en un solo nivel de precio. Absorción dispersa = señal débil. Se descarta.

Filtro 3: Ausencia de Ruido Contrario
Durante la fase de absorción, no debe haber ticks significativos en dirección contraria. Si aparecen compras agresivas durante una absorción de venta, el bando defensor no está absorbiendo limpiamente — está contraatacando. Eso no es agotamiento, es batalla confusa.

Menos del 20% del volumen del nivel debe ser delta contrario durante la ventana de absorción. Si hay ruido, se descarta.

5. Los Guardianes de Confirmación (Fase 2)

Los guardianes son los evaluadores de la Fase 2. No detectan hechos — evalúan confluencia. Un guardián toma las observaciones de los sensores tácticos y decide si la evidencia es suficiente para entrar.

5.1 Arquitectura: Sensores y Guardianes

Esta estrategia utiliza una separación estricta entre dos tipos de componentes:

SENSORES TÁCTICOS — Detectan hechos observables del mercado. No opinan. No deciden. Solo reportan lo que ven:

- AbsorptionDetector: "Delta extremo en nivel X, dirección SELL, z-score 3.2, concentración 75%"
- DeltaReversalSensor: "Delta acaba de cambiar de negativo a positivo en los últimos 2 ticks"
- PriceBreakSensor: "Precio rompió por encima del nivel de absorción X"
- CVDFlipSensor: "CVD cambió de pendiente negativa a positiva"

GUARDIANES — Evalúan la confluencia de múltiples sensores. No detectan nada por sí mismos. Solo deciden si la evidencia es suficiente:

- AbsorptionReversalGuardian: Requiere AbsorptionDetector como gatillo. Confirma con ≥2 de {DeltaReversal, PriceBreak, CVDFlip} en ventana de confirmación.
- CounterAbsorptionGuardian: Durante posición abierta, si aparece nueva absorción en dirección contraria, cierra inmediatamente.

5.2 El Guardián de Entrada: AbsorptionReversalGuardian

Este guardián es el cerebro de la Fase 2. Su lógica es:

1. Recibe señal del AbsorptionDetector (candidato a absorción)
2. Inicia ventana de confirmación (3 velas)
3. Monitorea los 3 sensores de confirmación
4. Si ≥2 de 3 se activan → genera señal de entrada
5. Si la ventana expira sin confirmación → descarta el candidato

Esta separación es crítica porque evita el error más común en trading de absorción: entrar en el momento de detección. El guardián obliga a esperar. No importa cuán fuerte parezca la absorción — sin confirmación, no hay entrada.

5.3 El Guardián de Salida: CounterAbsorptionGuardian

Si durante un trade abierto aparece una nueva absorción en dirección contraria, la tesis original murió. El mercado encontró un nuevo defensor que está absorbiendo TU dirección. La posición se cierra inmediatamente sin esperar al stop loss.

- Largo abierto + nueva absorción de compra en nivel superior → cierre inmediato (compradores absorbidos arriba, vendedores tomarán control)
- Corto abierto + nueva absorción de venta en nivel inferior → cierre inmediato (vendedores absorbidos abajo, compradores tomarán control)

El mercado te está diciendo: "El otro bando acaba de recargar." No esperes a que te dispare.

6. El Filtro de Régimen

6.1 El Problema

La absorción en contra de una tendencia fuerte es la trampa más cara del order flow. Cuando el mercado tiene momentum direccional claro, un evento de volumen extremo contra la tendencia suele ser una pausa del agresor, no una rendición. El atacante solo está recargando. Entrar contra la tendencia basándose en absorción es apostar contra un ejército que aún tiene munición.

6.2 La Solución

V2 no elimina señales en tendencia. Reduce el tamaño de posición y endurece los requisitos de confirmación:

- RANGO: Confirmación estándar (2 de 3). Tamaño completo.
- TENDENCIA A FAVOR: Confirmación estándar (2 de 3). Tamaño completo. La absorción a favor de tendencia es la más potente — el agresor contra-tendencia se agota y la tendencia continúa.
- TENDENCIA EN CONTRA: Confirmación estricta (3 de 3 obligatorias). Tamaño reducido al 50%. Solo se entra si TODAS las confirmaciones están presentes, indicando un giro genuino y no una pausa.

7. Gestión de Entrada y Salida

7.1 Entrada
Entrada a mercado tan pronto como el AbsorptionReversalGuardian genera la señal de entrada. No se usan órdenes límite esperando retrocesos. La confirmación es el gatillo.

7.2 Stop Loss
El stop loss se coloca en el extremo del nivel de absorción:

- Para largos: SL por debajo del mínimo del nivel donde ocurrió la absorción, con un buffer del 0.15% del precio.
- Para cortos: SL por encima del máximo del nivel donde ocurrió la absorción, con un buffer del 0.15% del precio.

Si el precio vuelve a ese nivel, la absorción falló. El agresor no se agotó realmente. La tesis está muerta.

7.3 Take Profit
El take profit es dinámico y se basa en la estructura del Footprint posterior a la entrada:

- Primer objetivo (50% de la posición): Primer nivel de bajo volumen (LVN) en dirección del trade. Estos niveles de "aire" ofrecen poca resistencia y el precio los atraviesa rápido.
- Segundo objetivo (50% restante): Primer nodo de alto volumen en dirección contraria. Ahí hay un nuevo defensor. Se toma ganancia antes de que absorba el movimiento.

7.4 Invalidación por Nueva Absorción Contraria
Sección 5.3 — CounterAbsorptionGuardian. Cierre inmediato sin esperar al SL.

8. Señales Tácticas Reconocidas

La estrategia reconoce una sola familia de señales: agotamiento del agresor confirmado por giro de delta. Las manifestaciones específicas incluyen:

Absorción Simple — Un nivel muestra delta extremo sin desplazamiento. El precio gira. Confirmación de giro aparece. Entrada.

Absorción con Divergencia de CVD — El CVD muestra una divergencia: el precio intenta seguir la dirección del ataque pero el CVD no acompaña. El agresor perdió el respaldo del flujo. Confirmación de giro aparece. Entrada.

Absorción tras Ruptura Falsa — El precio rompe un nivel, el Footprint muestra que la ruptura tuvo bajo delta (sin convicción), y aparece absorción en dirección contraria justo después. Confirmación de giro aparece. Entrada contra la falsa ruptura.

Absorción a Favor de Tendencia — En un retroceso dentro de una tendencia establecida, aparece absorción del bando contra-tendencia. El retroceso se agota y la tendencia continúa. Esta es la señal de mayor probabilidad porque combina el principio de absorción con el momentum direccional.

Todas son variaciones del mismo principio. Un detector de absorción bien calibrado las captura todas. Los sensores de confirmación las filtran.

9. Resumen Ejecutivo

Absorption Scalping V2 detecta el momento en que un bando del mercado ataca con todo y fracasa, y ENTONCES ESPERA a que el mercado confirme que el giro es real antes de entrar.

Detecta el ataque. Verifica la rendición. Entra solo cuando ambas fases coinciden.

Arquitectura:

FASE 1 — DETECCIÓN (Sensor Táctico: AbsorptionDetector)
   └── Delta extremo + Precio estancado + Sin ruido contrario
   └── 3 filtros de calidad: Magnitud, Concentración, Ruido
   └── Resultado: Candidato a absorción (NO es entrada)

FASE 2 — CONFIRMACIÓN (Guardián: AbsorptionReversalGuardian)
   └── 3 sensores de confirmación: DeltaReversal, PriceBreak, CVDFlip
   └── Requiere ≥2 de 3 en ventana de 3 velas
   └── En tendencia en contra: requiere 3 de 3 + tamaño reducido
   └── Resultado: Señal de entrada

SALIDA
   └── SL: Extremo del nivel de absorción + buffer
   └── TP: LVN (50%) + HVN contrario (50%)
   └── Invalidación: CounterAbsorptionGuardian (nueva absorción contraria → cierre)

Sin Value Areas. Sin POCs históricos. Sin perfiles de sesión. Sin zonas predefinidas. Solo el Footprint, el delta, y la confirmación del giro.

Funciona en cualquier condición de mercado porque mide lo único que importa: oferta y demanda en tiempo real, y el momento en que uno de los dos bandos se rinde. Pero a diferencia del approach ingenuo, esperamos a que la rendición sea verificada antes de apostar por ella.

El mercado no debe nada a tu señal. La confirmación es todo.
