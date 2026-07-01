# Auditoría Cuantitativa — Capa Lógica de Trading (AMT + Order Flow)

**Auditor:** Senior Quant / Hedge Fund Risk Desk
**Objeto:** Evaluación holística del *edge* de mercado del bot Casino-V3
**Evidencia base:** 3 backtests mensuales LTC (Mar/Abr/May 2026) + lectura directa de la capa de decisión
**Veredicto de una línea:** *No hay edge estructural. Hay un generador de señales sin coherencia entre ubicación y dirección, brackets rotos, y un gate de régimen que no gatea. Lo que se midió como "edge" es ruido con varianza de un solo mes favorable.*

---

## 0. Evidencia forense (los números no mienten)

| Mes | PnL | Trades | Win Rate | Profit Factor | Ratio SL:TP (conteo) |
|-----|-----|--------|----------|---------------|----------------------|
| Marzo 2026 | +$1.48 (+0.01%) | 209 | 33.5% | 1.23 | 2.0 : 1 |
| Abril 2026 | **-$14.14 (-0.14%)** | 60 | **6.7%** | **0.27** | **10.8 : 1** |
| Mayo 2026 | +$17.49 (+0.17%) | 149 | 40.3% | 1.81 | 2.2 : 1 |
| **Agregado** | **+$4.83 (+0.05%)** | 418 | ~30% | ~1.0 | ~2.5 : 1 |

**Lectura de trader:** Un PF agregado de ~1.0 sobre 3 meses no es un edge, es breakeven antes de costos de oportunidad. La varianza inter-mensual (de 0.27 a 1.81 PF) es enorme para el mismo activo y los mismos parámetros. **Eso es la firma de un sistema que depende del régimen de mercado que le toque, no de una ventaja estadística.** Abril (mercado que no le convino) reveló la asimetría negativa real: cuando el mercado no coopera, el sistema sangra con 6.7% de aciertos.

---

## 1. Puntos ciegos de la subasta (dónde falla catastróficamente)

### 1.1 CRÍTICO — Los brackets TP/SL están numéricamente rotos
Perfil activo `LTC_NOISY_UNCERTAIN_1` (`config/coin_profiles_LTC_NOISY_UNCERTAIN_1_optimized.py:275-280`):
```python
"failed_breakout":     {"sl_pct": 1.2, "tp_pct": 1.2}    # 120%
"liquidity_exhaustion":{"sl_pct": 2.5, "tp_pct": 2.5}    # 250%
"tactical_absorption": {"sl_pct": 2.0, "tp_pct": 1.0}    # 200% SL / 100% TP
"trend_acceptance":    {"sl_pct": 2.5, "tp_pct": 2.5}    # 250%
```
El código (`decision/engine/targets.py:70-75`) hace `price * (1 ± pct)`. Con `sl_pct=2.5` en un LONG, el SL cae en `price*(1-2.5)` = **precio negativo**. Los brackets nunca funcionan como stops estructurales: son marcadores absurdos que el motor de salida temporal (`SlimExitEngine V11`) ignora o llena de inmediato. **Toda la gestión de riesgo por precio está deshabilitada de facto.** El sistema sale por tiempo/compresión, no por invalidación estructural del setup. Esto es inaceptable en producción.

### 1.2 CRÍTICO — `tactical_absorption` fadea contra la subasta sin coherencia ubicación↔dirección
`decision/scenarios/instant/tactical_absorption.py:112`:
```python
side = "LONG" if state.cvd_session_delta < 0 else "SHORT"
```
La dirección se decide **solo por el signo del CVD de sesión**, no por dónde está el precio respecto al nodo. El bot puede abrir un LONG pegado al VAH (resistencia) simplemente porque el CVD de sesión es negativo. Peor: `cvd_session_delta` se resetea cada 4h (`order_flow/engine.py`), así que cerca de un reset la dirección **se voltea arbitrariamente**. En AMT esto es herejía: comprar absorción en el extremo alto de la subasta es pararse frente a la iniciativa vendedora. Y este setup **evade el VA_GATE por completo** (ver §1.4).

**Escenario de falla catastrófica:** Tendencia bajista sostenida (como parte de Abril). El precio testea el VAL/POC repetidamente en su camino a abajo. `cvd_session_delta` negativo → el bot dispara LONGs de absorción una y otra vez contra la tendencia. Cada rebote muere. Resultado: 6.7% win rate, 10.8:1 SL:TP. **Eso es exactamente lo que muestra Abril.**

### 1.3 ALTO — `va_integrity` es una métrica sin normalizar contra un umbral arbitrario
`core/market_profile.py:210-235`:
```python
concentration = poc_vol / total_volume
magnetism     = 1.0 / (va_range_pct * 100)
score         = concentration * magnetism
```
`magnetism` no está acotado. Con un VA estrecho, `va_range_pct → 0` y `magnetism → ∞`, disparando `va_integrity` muy por encima de 1.0, lo que hace que **casi siempre supere el umbral de 0.15 y el gate deje pasar todo**. En un dataset mensual, `total_volume` acumula el mes entero → `concentration` colapsa → el gate se comporta de forma impredecible. La métrica que decide "¿estamos en subasta balanceada o en tendencia?" es dimensionalmente inconsistente. **El regime filter no filtra régimen; filtra ruido.**

### 1.4 ALTO — El gate de régimen no gatea al setup más peligroso
`va_gate.block_in_trending` lista `tactical_absorption`, pero ese setup viaja por el *Fast-Lane* (`decision/engine/core.py:227`) y **nunca pasa por `SignalArbitrator._apply_va_gate`**. Es decir: el único setup contra-tendencia de alto riesgo está *nominalmente* bloqueado en tendencia pero *realmente* exento del bloqueo. Es un cinturón de seguridad pintado en la puerta.

### 1.5 MEDIO — Los detectores de confirmación casi nunca disparan por buenas razones (y cuando disparan, es por fragmentación)
- `liquidity_exhaustion` keyea el historial de tests por `f"{level}_{price:.2f}"` (`liquidity_exhaustion.py:131`). VAH/VAL driftan tick a tick → cada test cae en una key distinta → **los tests nunca se acumulan a `min_tests`**. Cuando sí acumula, es por coincidencia de redondeo, no por estructura.
- `trend_acceptance` exige `cvd_velocity > 4.0` donde `cvd_velocity` es un **z-score** (4 sigma). La ventana de entrada es `(vah, vah*1.0012]` — 12 bps. Un pullback rápido salta la ventana en un tick → cancela en vez de entrar.
- El "delta declinante" de exhaustion compara z-scores, no agresión absoluta. Un z cae porque la std rodante se ensancha, no porque haya menos agresión. **La narrativa AMT está rota a nivel de señal.**

### 1.6 MEDIO — HVN/LVN calculados pero nunca usados
`core/footprint_registry.py:157-171` (`get_volume_profile`) existe "para TP dinámico por nodos de volumen" — pero `targets.py` nunca lo llama. Los TP/SL son porcentajes planos. **El corazón de AMT (operar los nodos de volumen) es código muerto.** El bot dice hacer AMT pero opera porcentajes fijos.

---

## 2. Crítica de trader: "esto se mejora así y así"

El objetivo no es "hacer que funcione en esos 3 datasets" (eso es curve-fitting). El objetivo es **construir coherencia estructural** para que el edge sea robusto a cualquier régimen. En orden de impacto:

### FIX 1 — Reparar los brackets (bloqueante, trivial, mayor impacto)
Los targets deben ser fracciones reales. `tp_pct: 2.5` debe ser `0.025` (2.5%). Corregir `config/coin_profiles_LTC_NOISY_UNCERTAIN_1_optimized.py:275-280`:
```python
"failed_breakout":     {"sl_pct": 0.012, "tp_pct": 0.012}
"liquidity_exhaustion":{"sl_pct": 0.025, "tp_pct": 0.025}   # o mejor, RR positivo
"tactical_absorption": {"sl_pct": 0.010, "tp_pct": 0.020}   # invertir a RR 2:1
"trend_acceptance":    {"sl_pct": 0.025, "tp_pct": 0.025}
```
Y añadir validación de rango en `param_validation` que rechace cualquier `pct >= 1.0`. **Sin esto, ninguna otra mejora es medible** porque el riesgo por precio no existe.

### FIX 2 — Acoplar dirección a la ubicación en la subasta (arreglar la incoherencia AMT)
En `tactical_absorption.py:112`, la dirección NO debe salir del signo del CVD de sesión. Debe salir de **dónde está el precio y qué está absorbiendo el book**:
- Cerca del VAL con bid absorbiendo venta agresiva → LONG (comprador defendiendo el borde bajo del valor).
- Cerca del VAH con ask absorbiendo compra agresiva → SHORT.
- Cerca del POC sin confirmación de borde → **no operar** (el POC es imán, no borde).

Regla: *nunca fadear en el extremo equivocado del valor.* Un LONG solo es válido en la mitad inferior del VA; un SHORT solo en la mitad superior. Esto elimina el modo de falla de Abril de raíz.

### FIX 3 — Meter `tactical_absorption` bajo el VA_GATE (cerrar el bypass)
Rutear el Fast-Lane a través de `_apply_va_gate` antes de emitir, o replicar el chequeo de régimen en `sensor_manager`. En tendencia fuerte, la absorción contra-tendencia debe estar **prohibida de verdad**, no en el papel.

### FIX 4 — Normalizar `va_integrity` a [0,1] con significado
`magnetism` debe acotarse. Propuesta:
```python
va_range_pct = max(va_range_pct, epsilon)
magnetism = min(1.0, target_range / va_range_pct)   # relativo a un rango típico del activo
integrity = concentration * magnetism   # ahora en [0,1] interpretable
```
Y calibrar el umbral por activo con datos, no un 0.15 mágico global. Un gate que no distingue régimen es peor que no tener gate porque da falsa confianza.

### FIX 5 — Estabilizar la identidad de niveles (arreglar fragmentación de tests)
En vez de keyear por `price:.2f`, keyear por **banda de nivel** (VAL/VAH como zonas de ±tolerancia, no como precios exactos). Un test cuenta si el precio entra en la banda del nivel *lógico* (VAL), sin importar el decimal exacto. Esto hace que `liquidity_exhaustion` acumule tests como debe.

### FIX 6 — Normalizar el riesgo por trade (no por nocional)
`players/adaptive.py:66` dimensiona por % de nocional fijo (A=1%, B=0.5%) ignorando la distancia al SL. Un trade con SL de 5% arriesga 5x más capital que uno con SL de 1% para el mismo "grade". Cambiar a **sizing por riesgo constante**:
```python
risk_per_trade = equity * risk_pct        # ej. 0.5% del equity en riesgo
qty = risk_per_trade / (sl_distance_abs)  # nocional derivado del stop
```
Esto normaliza la asimetría y hace que grades y RR sean comparables entre setups.

### FIX 7 — Conectar los TP a nodos de volumen reales (activar el AMT prometido)
Usar `get_volume_profile` (código muerto hoy) para poner TP en el siguiente LVN (el precio viaja rápido por los vacíos de volumen) y SL detrás del HVN/borde de valor invalidante. Esto convierte los targets de porcentajes arbitrarios en niveles estructurales — que es *todo el punto* de operar subasta.

---

## 3. Diagnóstico de por qué "pasó el audit" pero pierde en trade real

El *audit mode* mide expectancy de señales sobre muestreo de precios (sin ejecución, sin brackets, sin SlimExitEngine). Con brackets rotos y salida temporal, **el audit y el trade miden cosas distintas**. El "+0.1144% Net Taker" del audit nunca fue una promesa de PnL ejecutable — fue una estadística de señal desconectada de la ejecución real. Los 3 meses de trade lo confirman: el edge de señal no sobrevive al contacto con la ejecución.

---

## 4. Prioridad de trabajo (ruta a un edge real)

1. **FIX 1** (brackets) — bloqueante. Re-correr los 3 meses. Sin esto no se puede medir nada.
2. **FIX 2 + FIX 3** (coherencia direccional + gate real) — matan la asimetría negativa de Abril.
3. **FIX 6** (riesgo normalizado) — hace comparables los resultados entre setups.
4. **FIX 4 + FIX 5** (integrity + niveles) — recuperan la fidelidad de las señales.
5. **FIX 7** (TP por nodos) — activa el AMT que el sistema dice hacer.
6. Re-auditar mes a mes buscando PF > 1.3 **consistente** (no un mes bueno y dos malos). Validar en régimen adverso (tendencia fuerte) como test de estrés, no solo en meses balanceados.

**Métrica de éxito honesta:** No busques el mes que gana. Busca que el peor mes no destruya. Un sistema con PF 1.2 estable en 6 meses vale infinitamente más que uno con 1.81 en mayo y 0.27 en abril.
