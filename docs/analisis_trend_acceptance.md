# Análisis y Diagnóstico: El Problema de `trend_acceptance`

## 1. El Diagnóstico (Root Cause)

Tras el éxito rotundo del fix en `liquidity_exhaustion` (que pasó de -0.08% a +0.48% Net Taker), el audit mensual LTC expuso de manera evidente al verdadero culpable del mal rendimiento general: **`trend_acceptance` (TA)**.

**Métricas del desastre (Mensual LTC):**
*   **Señales:** 146 (66% del total de señales post-fix).
*   **Win Rate:** 14.4% (Pésimo).
*   **MFE/MAE Ratio:** 0.01 (El precio va en nuestra contra el 92.5% del tiempo).
*   **Net Taker:** -0.7105%.

**¿Por qué TA destruye el edge en mensual pero "funcionaba" en 24h?**
1.  **Overfitting temporal:** En un dataset de 24h con tendencia clara, casi cualquier rompimiento funciona. En un mes completo, el mercado pasa el 70-80% del tiempo en consolidación/rango (chop).
2.  **Fakeouts (Falsos Rompimientos):** La lógica actual de TA busca que el precio salga del VA con CVD, avance un poco, y retroceda al borde para entrar. En un mercado de rango, el precio hace exactamente esto (sale, limpia stops, retrocede) e inmediatamente **reingresa al VA**, tocando nuestro Stop Loss. Un *fakeout* es indistinguible de un *breakout* en sus primeros minutos si no se tiene el contexto de régimen.
3.  **Falta de Filtro de Régimen Restrictivo:** Según `memory.md`, el `VA_GATE` bloquea mean-reversion en tendencia, pero aparentemente **no está bloqueando `trend_acceptance` en rango**. TA se está ejecutando libremente en mercados picados, siendo aniquilado sistemáticamente.

---

## 2. Plan de Acción (Opciones)

Para rescatar el Net Taker global, necesitamos neutralizar el daño de TA. Propongo 3 opciones de abordaje, ordenadas de menor a mayor complejidad:

### Opción 1: Cuarentena de TA (Aislamiento y Baseline) - *Recomendada para corto plazo*
Desactivar temporalmente `trend_acceptance` (o ponerle un threshold imposible) para correr un audit mensual solo con los setups que funcionan (`liquidity_exhaustion`, `tactical_absorption`, `failed_breakout`).
*   **Pro:** Nos daría inmediatamente una baseline mensual ganadora y validaría que el núcleo del bot sirve. Nos da confianza para seguir trabajando.
*   **Contra:** Perdemos los trades de tendencia por ahora.

### Opción 2: Endurecimiento Táctico (Parámetros)
El código muestra que pedimos `min_breakout_distance_bps = 20.0` y un `cvd_confirmation_threshold` bajo. Podríamos:
*   Aumentar drásticamente la distancia mínima del rompimiento (ej. 50-80 bps) antes de considerar el pullback. Que demuestre que realmente rompió.
*   Exigir un flujo (CVD) masivo para el breakout.
*   **Pro:** Mantiene TA activo.
*   **Contra:** Puede que simplemente filtremos todo y lleguemos a 0 señales, sin arreglar el problema subyacente.

### Opción 3: Arreglo Estructural (VA_GATE para Rango)
Modificar el `ScenarioManager` (o donde viva la lógica de `VA_GATE`) para asegurar que si el régimen es de "RANGO" (ej. overlapping value areas, integrity alta), `trend_acceptance` quede estrictamente **BLOQUEADO**.
*   **Pro:** Es la solución conceptualmente correcta en Auction Market Theory.
*   **Contra:** Toma más tiempo de desarrollo y pruebas.

---

## 3. Próximo Paso Sugerido

Recomiendo fuertemente aplicar la **Opción 1 primero**: hagamos una prueba mensual rápida con TA apagado. Si el bot es rentable sin TA, entonces hemos salvado el proyecto y podemos enfocarnos en arreglar TA (Opción 3) sin la presión de un sistema perdedor.

> [!IMPORTANT]
> **Pregunta para el usuario:** ¿Procedemos con la Opción 1 (apagar TA temporalmente y correr audit mensual para confirmar baseline positiva) o prefieres ir directamente a la Opción 3 (arreglar el filtro de régimen)?
