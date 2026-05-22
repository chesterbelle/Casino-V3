# Plan de implementación — Exit Edge Auditor

**Rama:** `v8.1-unified-decision-dna`
**Fecha:** 2026-05-22
**Estado:** Aprobado para implementación
**Reemplaza:** `docs/plan_corrida_delta_invalidacion.md` (obsoleto — enfoque DI manual)

---

## 1. Objetivo

Repetir el playbook que certificó el **Setup** (`--audit` → `setup_edge_auditor.py`) para diseñar el **Exit Engine** desde datos, no desde teoría.

| Capa | Estado | Herramienta |
|------|--------|-------------|
| Señales / Setup | Certificada | `utils/setup_edge_auditor.py` |
| Salidas / Exit | Hipótesis (4 pilares sin validar) | **`utils/exit_edge_auditor.py`** (nuevo) |

**Pregunta que debe responder el sistema (automático, sin etiquetado manual por trade):**

> ¿En qué momento del recorrido post-señal el movimiento dejó de tener upside útil, y qué observables lo anticipan?

La salida es una **regla candidata** (fórmula + umbrales) para implementar después en SlimExit — **no** requiere SlimExit corriendo ni backtest sin `--audit` en esta fase.

---

## 2. Principios (no negociables)

1. **Cero interferencia:** seguir usando `--audit` (sin posiciones, sin SlimExit en el loop).
2. **Reutilizar, no duplicar:** misma DB, misma ventana, misma extracción de trayectoria que `EdgeAuditor`.
3. **Descubrimiento automático:** el script infiere `t_stop` y barre reglas; el humano no etiqueta SL vs TP vs 4 h a mano.
4. **Separar contexto de predicción:**
   - **Contexto** (del setup auditor): MFE/MAE global, `real_outcome`, `setup_type`.
   - **Predicción** (del exit auditor): momento de fin de upside + variables en `t` previo.
5. **Un “no” es válido:** si tras n≥300 señales ninguna regla supera umbral de calidad, documentar y ampliar audit (ver §6).

---

## 3. Arquitectura

```text
┌─────────────────────────────────────────────────────────────┐
│  backtest.py / main.py  --audit                             │
│    → historian: signals + price_samples (price, micro_z)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
┌───────────────────┐               ┌───────────────────────┐
│ setup_edge_auditor│               │ exit_edge_auditor     │
│ (existente)       │               │ (nuevo)               │
│ • MFE/MAE/resumen │──contexto────▶│ • curva MFE(t), z(t)  │
│ • WIN/LOSS/TIMEOUT│               │ • t_stop automático   │
│ • matrices TP/SL  │               │ • barrido de reglas   │
└───────────────────┘               └───────────┬───────────┘
                                                ▼
                                    Regla candidata → config / SlimExit
```

### 3.1 Refactor compartido (mínimo)

**Archivo nuevo:** `utils/trajectory_core.py`

Extraer de `setup_edge_auditor.py`:

- `load_data(db_path)` → signals, prices, traces
- `get_trajectory(sig, prices_by_sym, window_sec)` → DataFrame ordenado por `timestamp` con columnas: `elapsed`, `price`, `mfe_pct`, `mae_pct_so_far`, `micro_z` (si existe)
- `SETUP_WINDOWS` / `DEFAULT_WINDOW` (importar o duplicar constante una sola vez)

`setup_edge_auditor.py` se actualiza para usar `trajectory_core` sin cambiar salidas del informe.

---

## 4. Definición operativa de “movimiento terminado” (`t_stop`)

Automática, por señal, sobre la curva `mfe_pct(t)` dentro de la ventana del setup:

```python
# Parámetros iniciales (calibrables en CLI)
UPSIDE_DEAD_DELTA = 0.15   # % — si el MFE futuro no supera mfe(t) + δ, upside muerto
MIN_SAMPLES_AFTER = 2      # al menos 2 muestras (≈60s) confirmando
```

**Algoritmo:**

1. Para cada muestra `t_i`, calcular `max_future_mfe = max(mfe_pct[t_i:])`.
2. Si `max_future_mfe <= mfe_pct(t_i) + UPSIDE_DEAD_DELTA` durante `MIN_SAMPLES_AFTER` consecutivos → **`t_stop = t_i`** (primera ocurrencia).
3. Si nunca ocurre → `t_stop = fin de ventana` (timeout de trayectoria).

Esto no pide al usuario elegir SL vs 4 h; es la etiqueta para buscar la fórmula.

**Etiquetas auxiliares automáticas** (solo contexto, impresas en reporte):

| Campo | Fuente |
|-------|--------|
| `t_peak` | argmax `mfe_pct` |
| `t_tp` / `t_sl` | primer cruce de `tp_price` / `sl_price` en metadata |
| `real_outcome` | misma lógica que setup auditor |
| `certified_1pct` | bool: algún `mfe_pct >= 1.0` |

---

## 5. `exit_edge_auditor.py` — comportamiento

### 5.1 Entrada

```bash
.venv/bin/python utils/exit_edge_auditor.py \
  --db data/historian.db \
  [--setup-type TacticalAbsorptionV2] \
  [--delta-upside 0.15] \
  [--out logs/exit_edge_report.txt]
```

### 5.2 Por señal

1. Cargar trayectoria vía `trajectory_core`.
2. Calcular `t_stop`, `t_peak`, features en ventana `[t_stop - lookback, t_stop]`:
   - `mfe_pct`, `mae_pct_so_far`, `mfe_velocity` (delta entre muestras)
   - `delta_z = micro_z - z_score_entry` (si `micro_z` y metadata disponibles)
   - distancias a `sl_price`, `tp_price`, `poc_price` (% desde entry)
3. Unir fila resumen del setup auditor (`mfe`, `mae`, `real_outcome`, `setup_type`).

### 5.3 Barrido de reglas (automático)

Probar familia de reglas en cada muestra `t` **antes** de `t_stop` y medir:

| Métrica | Definición |
|---------|------------|
| **Hit** | Regla dispara en `t` y `t_stop - t <= max_lead` (ej. 900 s) |
| **False positive (FP)** | Dispara en señales con `certified_1pct` y disparo ocurre **antes** del primer `mfe >= 1.0` |
| **False negative (FN)** | No dispara antes de `t_stop` en señales con `mfe < 0.5` al stop |

**Familias iniciales a barrer:**

```text
R1  delta_z > thresh                    (flujo)
R2  mfe_pct < mfe_thresh @ elapsed > T  (estancamiento precio)
R3  mae_pct > mae_thresh AND mfe < mfe_cap
R4  dist_sl_pct < 0 (precio cruzó SL)
R5  combinaciones R1∧R2, R2∧R3, etc.
```

Salida: top 10 reglas por `precision` con `FP_rate` bajo en subconjunto `certified_1pct`.

### 5.4 Informe (no filas crudas para lupa)

Secciones:

1. **Cohorte:** n señales, % con `micro_z`, ventana media.
2. **Contexto setup:** tabla MFE/MAE/`real_outcome` por `setup_type` (reuso mental del setup auditor).
3. **`t_stop` vs `t_peak` vs `t_sl`:** medianas por cohorte.
4. **Mejores reglas:** tabla thresh / precisión / FP / recall.
5. **Recomendación:** 1–2 reglas candidatas para pilar “fin de movimiento” + nota si hace falta ampliar audit (§6).

---

## 6. Audit: ¿alcanza sin cambios?

| Variable | ¿En audit hoy? | Acción |
|----------|----------------|--------|
| `price` | Sí | — |
| `micro_z` | Sí (post `4ffa07b`) | — |
| `z_score_entry`, TP/SL/POC en metadata | Sí | — |
| Curva MFE(t) | Derivable | En `trajectory_core` |
| `signal_id` en `price_samples` | No | **Fase 2** si mezcla de señales mismo símbolo confunde |
| CVD / skew por muestra | No | **Fase 2** solo si barrido R1 falla y se necesita espejar guardian |
| Muestreo &lt; 30 s | No | **Fase 2** opcional; no bloquea v1 |

**v1 se implementa sin modificar audit.** Fase 2 según resultado del informe.

---

## 7. Protocolo de corrida (igual que setup)

1. `utils/reset_data.py`
2. Lotes `run_batches.sh` (2–3 monedas paralelo), `--audit`, merge → `data/historian.db`
3. Verificar: `signals >= 300` (objetivo protocolo), `micro_z` 100% en `price_samples`
4. `python utils/setup_edge_auditor.py --window 14400`
5. `python utils/exit_edge_auditor.py --db data/historian.db`
6. Documentar regla ganadora en este plan (§8) y luego en `config/trading.py` / SlimExit

---

## 8. Criterios de éxito (fase diseño)

| Criterio | Umbral orientativo |
|----------|-------------------|
| Regla con FP en certified | &lt; 15 % de señales que llegan a +1 % |
| Recall en “muertas” (`mfe` final &lt; 0.5 %) | &gt; 60 % |
| Lead time mediano | &lt; 30 min antes de `t_stop` |
| n señales | ≥ 300 (preliminar ≥ 80 con etiqueta “PRELIMINAR”) |

Si no se cumple → Fase 2 audit (§6), no implementar pilar en producción.

---

## 9. Implementación — checklist

```
[ ] utils/trajectory_core.py          — extracción compartida
[ ] Refactor setup_edge_auditor.py    — usar trajectory_core (sin cambiar reporte)
[ ] utils/exit_edge_auditor.py        — t_stop + barrido + informe
[ ] CLI + README en docstring
[ ] Corrida historian n≥300
[ ] §8 Resultados → regla candidata documentada
[ ] (Después) Pilar SlimExit según regla — fuera de este plan
```

**Orden de trabajo:** `trajectory_core` → `exit_edge_auditor` → refactor setup → corrida → informe.

---

## 10. Fuera de alcance (explícito)

- Ejecutar o validar SlimExit en vivo / sin audit.
- Calibrar el pilar DI legacy como objetivo principal.
- Etiquetado manual trade-by-trade.
- Cambiar SetupEngine / guardians de entrada.

---

## Referencias

- `.agent/memory.md` — baseline 4 h, activos certificados
- `.agent/workflows/generalized-edge-audit.md` — protocolo de corrida
- `utils/setup_edge_auditor.py` — Phase 800 (modelo a replicar)
- `config/trading.py` — `AUDIT_SAMPLING_FREQ`, `ABSORPTION_MAX_HOLDING_SEC`
- `core/observability/historian.py` — schema `signals`, `price_samples`

---

*Plan único vigente para diseño de salidas vía audit. Actualizar §8 tras cada corrida.*
