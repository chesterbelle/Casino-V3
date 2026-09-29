---
description: Protocolo estandarizado de re-certificación de perfiles de activos (PARAM_OPTIMIZER_DAILY -> OOS_MONTHLY -> LIVE_READY).
---

# 🔄 Protocolo Oficial de Re-Certificación de Activos (`recertify-coin`)

Este protocolo establece el procedimiento obligatorio para certificar cualquier moneda desde cero o actualizar perfiles antiguos (`PARAM_OPTIMIZER_DAILY`), garantizando rigor metodológico y completitud de datos out-of-sample (OOS).

---

## 📋 Flujo General de 3 Etapas

```
[PARAM_OPTIMIZER_DAILY]
        │
        ▼  (Etapa 1: Verificación / Descarga de Datasets Mensuales)
[monthly_backtest_ready/{SYM}_monthly_2026_*.db]
        │
        ▼  (Etapa 2: Auditoría MFE Expandido TP 3.0%-7.0%)
[OOS_MONTHLY]
        │
        ▼  (Etapa 3: Prueba Demo Trajectory 2h)
[LIVE_READY]
```

## 🛡️ PASO 0: Saneamiento y Recuperación Post-Crash (Post-Power Loss)

En caso de que el sistema o la PC hayan sufrido un apagón, reinicio abrupto o interrupción forzada:
```bash
python3 utils/heal_historian.py --db data/historian.db --fix
```
*(Garantiza la eliminación de filas corruptas producidas por la recuperación de disco de SQLite antes de generar o auditar telemetría).*

---

## 📡 ETAPA 1: Verificación y Descarga de Datasets Mensuales

### 1.1 Verificación de Existencia
Comprobar si existen los datasets mensuales en `data/datasets/monthly_backtest_ready/`:
```bash
ls -lh data/datasets/monthly_backtest_ready/<SYM>_monthly_*.db
```

### 1.2 Descarga de Datos Raw (Si no existen)
Si la moneda no cuenta con datasets mensuales completos (ej. 6 meses de 2026):
```bash
nice -n 19 ionice -c3 .venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol <SYMBOL> --start 2026-01-01 --end 2026-06-30
```
*(Para monedas pesadas como BTCUSDT o ETHUSDT, agregar la bandera `--sequential` para evitar OOM).*

### 1.3 Procesamiento e Inyección L2
Convertir los archivos raw `.csv.gz` a bases de datos SQLite `.db` en `monthly_backtest_ready/`:
```bash
nice -n 19 ionice -c3 .venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYMBOL>
```
Mover/asegurar los archivos `.db` procesados a `data/datasets/monthly_backtest_ready/<SYM>_monthly_YYYY_MM.db`.

---

## 📊 ETAPA 2: Auditoría MFE Expandido & Recalibración (`OOS_MONTHLY`)

### 2.1 Generación de Señales Out-of-Sample
Ejecutar el backtest de auditoría sobre los datasets mensuales para popular `data/historian.db`:
```bash
nice -n 19 ionice -c3 .venv/bin/python backtest.py --depth-db-path data/datasets/monthly_backtest_ready/<SYM>_monthly_2026_01.db --symbol <SYMBOL> --run-type audit
```

### 2.2 Auditoría de Grilla de Targets Expandida (TP 3.0% – 7.0%)
Correr el evaluador de trayectoria de MFE/MAE:
```bash
python utils/setup_edge_auditor.py --db data/historian.db --coin <SYMBOL> --window 864000
```

### 2.3 Actualización de Perfil
Actualizar la matriz de targets en `config/coin_profiles.py` con los valores óptimos y establecer:
```python
"optimization_status": {
    "certification_status": "OOS_MONTHLY",
    "date": "<YYYY-MM-DD>",
    "is_certified": True,
    "method": "edge_auditor_oos_monthly",
    "notes": "Re-calibración de TP/SL tras auditoría mensual OOS de MFE."
}
```

---

## 🟢 ETAPA 3: Certificación Live Demo (`LIVE_READY`)

### 3.1 Ejecución de Simulación Live con Registro de Trajectoria
Correr el bot en modo Demo para el activo certificado durante una sesión continua de **al menos 2 horas (120 minutos)**:
```bash
.venv/bin/python main.py \
  --run-type trade \
  --symbol <SYMBOL> \
  --mode demo \
  --bet-size 0.01 \
  --record-trajectory \
  --timeout 120 \
  2>&1 | tee logs/demo_certification_<SYMBOL>_$(date +%Y%m%d_%H%M%S).log
```

### 3.2 Verificación de Trajectoria y Cero Errores
1. Validar que la retención de MFE en vivo coincida con el comportamiento proyectado en backtest.
2. Confirmar `0` errores de ejecución o latencia en el log.

### 3.3 Promoción Final a `LIVE_READY`
Actualizar `config/coin_profiles.py`:
```python
"optimization_status": {
    "certification_status": "LIVE_READY",
    "date": "<YYYY-MM-DD>",
    "is_certified": True,
    "method": "live_demo_trajectory_audited",
    "notes": "Certificación en vivo en Demo (2h) con --record-trajectory completada con éxito."
}
```
y registrar la promoción en `docs/ROADMAP_PRODUCCION.md`.
