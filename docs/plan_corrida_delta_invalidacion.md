# Plan de corrida — Generalized Edge Audit + datos para Pilar Delta Invalidation

**Rama:** `v8.1-unified-decision-dna`
**Objetivo inicial:** Recopilar evidencia empírica para **rehacer el Pilar 4 (delta invalidation)** del SlimExitEngine en demo/live.
**Protocolo base:** `.agent/workflows/generalized-edge-audit.md`
**Análisis previo:** `docs/analisis_academicoexits.md` (§2.3, §2.4)

---

## 1. Qué vamos a demostrar (entregables)

Al terminar esta corrida + análisis offline, debemos poder responder:

| Pregunta | Dato requerido |
|----------|----------------|
| ¿DI cerraría **antes** del +1 % (falso positivo)? | `micro_z(t)` vs `z_score_entry`, umbral SlimExit |
| ¿DI coincide con el **fin del impulso** (~1 %)? | Tiempo `t_delta_trigger` vs `t_first_1pct` vs giveback precio |
| ¿Qué umbral `delta_z` minimiza FP y no pierde captura? | Barrido 3.0–6.0 en `delta_z` |
| ¿Cuándo **armar** DI (no desde entry)? | MFE% en el que DI empieza a tener sentido (ej. 0.5 / 0.8 / 1.0 %) |
| ¿Giveback precio solo basta o delta aporta señal extra? | Concordancia DI vs giveback ≥0,25 % post-pico |

**Salida final:** Tabla de recomendación para `config/trading.py` + cambio en `slim_exit_engine._check_delta_invalidation` (fase 2, tras este plan).

---

## 2. Pre-requisitos (antes de correr)

```bash
cd /home/chesterbelle/Casino-V3

# Datasets L2 (10 monedas)
ls data/datasets/backtest_ready/2024-01-01_{ADA,AVAX,BNB,DOGE,ETH,LINK,LTC,SOL,SUI,XRP}USDT.db

# Código commitado con micro_z en audit (commit 4ffa07b+)
grep -q micro_z core/observability/historian.py && echo "OK micro_z"

# max_holding_time = 14400 en metadata (ABSORPTION_MAX_HOLDING_SEC)
grep ABSORPTION_MAX_HOLDING_SEC config/trading.py
```

**No correr** si falta algún `.db` en `backtest_ready/`.

**RAM:** Usar **lotes de 2–3** (no 10 paralelos). Script: `logs/edge_audit_20260521/run_batches.sh` (copiar a carpeta con fecha nueva si querés conservar la corrida anterior).

---

## 3. Fase A — Corrida del protocolo (recolección)

### A0 — Reset nuclear

```bash
.venv/bin/python utils/reset_data.py
# Debe imprimir: ✨ Sistema limpio.
```

### A1 — Backtests en lotes (≈2–3 h total)

```bash
# Opción recomendada: reutilizar script probado
RUN_DIR="logs/edge_audit_$(date +%Y%m%d)"
mkdir -p "$RUN_DIR"
cp logs/edge_audit_20260521/run_batches.sh "$RUN_DIR/run_batches.sh"
# Editar LOG_DIR dentro del script → "$RUN_DIR" si hace falta

nohup "$RUN_DIR/run_batches.sh" > "$RUN_DIR/master.log" 2>&1 &
tail -f "$RUN_DIR/master.log"
```

**Orden de lotes (ya en script):**

| Lote | Monedas | Paralelo |
|------|---------|----------|
| 1-light | LTC, XRP, DOGE | ×3 |
| 2-mid | LINK, ADA, SUI | ×3 |
| 3-mid2 | BNB, AVAX | ×2 |
| 4-solo | ETH | ×1 |
| 5-solo | SOL | ×1 |

Al final el script ejecuta `merge_historian.py` → **`data/historian.db`**.

### A2 — Verificar recolección (mínimos)

```bash
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('data/historian.db')
s = c.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
p = c.execute('SELECT COUNT(*) FROM price_samples').fetchone()[0]
z = c.execute('SELECT COUNT(*) FROM price_samples WHERE micro_z IS NOT NULL').fetchone()[0]
t = c.execute('SELECT COUNT(*) FROM decision_traces').fetchone()[0]
print(f'signals={s}  price_samples={p}  micro_z={z}  traces={t}')
for sym, n in c.execute('SELECT symbol, COUNT(*) FROM signals GROUP BY symbol ORDER BY n DESC'):
    flag = 'OK' if n >= 10 else 'LOW_N'
    print(f'  {flag} {sym}: {n}')
"
```

| Métrica | Objetivo | Si falla |
|---------|----------|----------|
| Señales totales | ≥ 300 | Repetir o relajar guardians (solo tras discutir) |
| `micro_z` not null | = `price_samples` | Revisar commit / backtest `--audit` |
| Por moneda certificada (BNB,SOL,SUI,AVAX) | n ≥ 10 | Incluir en análisis delta solo monedas con n≥10 |

### A3 — Auditoría estándar (contexto, no sustituye delta)

```bash
.venv/bin/python utils/setup_edge_auditor.py --window 14400 2>&1 | tee logs/edge_audit_$(date +%Y%m%d)/edge_auditor.txt
.venv/bin/python scratch_matrix.py 2>&1 | tee logs/edge_audit_$(date +%Y%m%d)/matrix.txt
.venv/bin/python utils/l2_depth_auditor.py 2>&1 | tee logs/edge_audit_$(date +%Y%m%d)/l2_audit.txt
```

Guardar los tres `.txt` en la misma carpeta `RUN_DIR`.

---

## 4. Fase B — Análisis delta invalidation (objetivo central)

Ejecutar **después** de A2, sobre `data/historian.db` limpio de esta corrida.

### B1 — Script de trayectoria delta (a implementar si no existe)

**Ruta propuesta:** `utils/delta_invalidation_auditor.py`

Por cada fila en `signals` (solo `TacticalAbsorptionV2` + `absorption_reversal` si querés foco):

1. Leer `z_entry` = `metadata.z_score_entry`.
2. Cargar `price_samples` en `[ts, ts + max_holding_time]` (14 400 s) con `price` y `micro_z`.
3. Construir trayectoria favorable % y `delta_z(t) = micro_z(t) - z_entry`.
4. Registrar eventos:

| Evento | Definición |
|--------|------------|
| `t_first_08` | primer sample con MFE ≥ 0,8 % |
| `t_first_10` | primer sample con MFE ≥ 1,0 % |
| `t_peak` | máximo MFE en ventana |
| `t_giveback_025` | primer sample post-pico con MFE ≤ peak − 0,25 % |
| `t_di_L` / `t_di_S` | primer sample con `delta_z > thresh` (LONG) o `< -thresh` (SHORT) |

5. Barrer `thresh ∈ {3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0}` (perfiles SlimExit usan 4.5–5.5).

### B2 — Tablas que debe imprimir el auditor

**Tabla 1 — DI siempre armado (simula SlimExit actual sin estados)**

| thresh | % señales con DI **antes** de +1 % | % DI **después** de +1 % | Mediana `t_di - t_first_10` |
|--------|-----------------------------------|--------------------------|----------------------------|

**Tabla 2 — DI armado solo tras MFE ≥ X%**

| arm_after | thresh | % FP evitados | % capturas perdidas (DI nunca tras +1 %) |
|---------|--------|---------------|----------------------------------------|

**Tabla 3 — Concordancia DI vs giveback precio**

| Condición | n | % DI dentro de 60 s del giveback_025 |
|-----------|---|--------------------------------------|

**Tabla 4 — Por moneda certificada** (BNB, SOL, SUI, AVAX): mismas métricas, n≥10.

### B3 — Criterios de decisión para el pilar

| Resultado | Acción en SlimExit |
|-----------|-------------------|
| DI antes de +1 % > 15 % con thresh=5.0 | **Desarmar** hasta `arm_after_mfe >= 0.8%` |
| DI después de +1 % alineado con giveback en >60 % | Mantener DI + añadir giveback como confirmación OR |
| thresh óptimo 4.5 vs 5.5 estable entre monedas | Unificar en `ASSET_EXIT_PROFILES` |
| DI no aporta vs giveback solo | Simplificar pilar a precio; delta como filtro secundario |

### B4 — Comando (cuando exista el script)

```bash
.venv/bin/python utils/delta_invalidation_auditor.py \
  --db data/historian.db \
  --window 14400 \
  --thresholds 3.0,3.5,4.0,4.5,5.0,5.5,6.0 \
  --arm-after 0.0,0.5,0.8,1.0 \
  2>&1 | tee logs/edge_audit_$(date +%Y%m%d)/delta_invalidation.txt
```

---

## 5. Fase C — Síntesis para diseño del pilar (documento)

Actualizar `docs/analisis_academicoexits.md` §2.3 con:

- Números reales de esta corrida (no la de n=98).
- Umbral recomendado y regla `arm_after_mfe`.
- Diagrama de estados PATIENCE → IMPULSE → CAPTURE validado.

Opcional: sección en `.agent/memory.md` solo con **veredicto** + enlace al RUN_DIR.

---

## 6. Qué NO hacer en esta corrida

| Evitar | Por qué |
|--------|---------|
| Activar SlimExit en `--audit` | Contamina trayectorias (cero interferencia) |
| 10 backtests paralelos | Tilda el PC |
| Limpiar `historian.db` entre análisis B y A sin copia | Pérdida de datos |
| Concluir umbral solo con n &lt; 300 | Marcar resultados como **preliminares** |

---

## 7. Cronograma estimado

| Fase | Duración |
|------|----------|
| A0–A1 (lotes) | ~2–3 h |
| A2–A3 | ~15 min |
| B1 implementar script (si falta) | ~1–2 h |
| B2–B4 análisis | ~10 min CPU |
| C documentar | ~30 min |

---

## 8. Checklist rápido

```
[x] A0 reset_data.py
[x] A1 run_batches.sh → historian.db merge (2026-05-22, logs/edge_audit_delta_20260522)
[x] A2 signals=96, micro_z=27834 (INSUFICIENTE n≥300)
[x] A3 edge_auditor + matrix → RUN_DIR
[x] B1 delta_invalidation_auditor.py
[x] B4 delta_invalidation.txt generado
[ ] C analisis_academicoexits.md actualizado
[ ] Decisión: umbral + arm_after + ¿giveback OR?
```

### Resultados preliminares (corrida 2026-05-22)

Ver `logs/edge_audit_delta_20260522/delta_invalidation.txt`. Hallazgos clave (n=91 absorption, thresh=5.0):

- **DI siempre armado:** 27,5 % dispara **antes** del +1 %; 57 % después.
- **DI armado tras MFE≥1,0 %:** 73,5 % aún dispara **antes** del +1 % (solo 34 señales con pico≥1 %).
- **DI armado tras MFE≥0,8 %:** 58 % antes del +1 %.
- **Concordancia DI vs giveback 0,25 %:** 0 % dentro de 60 s (delta y precio desacoplados en tiempo).
- **Recomendación provisional:** Desarmar DI hasta MFE≥1 % **no basta**; evaluar combinar giveback precio como gatillo principal y delta como confirmación, o subir `arm_after` y bajar sensibilidad.

---

## 9. Siguiente paso inmediato

1. **Vos o el agente:** lanzar Fase A (corrida en lotes).
2. **Agente (cuando A2 pase):** implementar `utils/delta_invalidation_auditor.py` y ejecutar Fase B.
3. **Revisión conjunta:** tabla B2 → parámetros del pilar en código.

---

## Referencias

- `.agent/workflows/generalized-edge-audit.md`
- `croupier/components/slim_exit_engine.py` — `_check_delta_invalidation`
- `config/trading.py` — `ABSORPTION_MAX_HOLDING_SEC`, `AUDIT_SAMPLING_FREQ`
- Commits: `4ffa07b` (micro_z), `1dcafb6` (scripts auxiliares)
