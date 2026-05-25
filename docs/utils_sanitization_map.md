# Utils Sanitization Map

## Estado: Auditoría de `utils/`

Hemos centralizado la orquestación en `scripts/orchestrator.py`. Ahora estamos revisando `utils/` para identificar qué archivos son:
1.  **[ACTIVO]**: Necesarios para el funcionamiento (orquestador, estrategias, validadores activos).
2.  **[LEGACY]**: Obsoletos (v4/v5, lógica vieja), listos para `archive/`.
3.  **[DUDA]**: Requieren revisión conjunta.

---

### Análisis preliminar:

| Archivo | Estado | Razón |
| :--- | :--- | :--- |
| `utils/amt_researcher.py` | **LEGACY** | Parte de los experimentos de AMT v1. Ya se incorporó en `setup_edge_auditor`. |
| `utils/analyze_performance.py`| **LEGACY** | Función cubierta por `exit_edge_auditor.py`. |
| `utils/audit_logs.py` | **ACTIVO** | Usado en Layer 4.4 de `validate-all.md`. |
| `utils/check_docs_sync.py` | **DUDA** | ¿Lo usas frecuentemente para sincronizar documentación? |
| `utils/check_structure.py` | **DUDA** | ¿Validación interna necesaria? |
| `utils/compare_metrics.py` | **LEGACY** | Scripts antiguos de comparación de backtests (v4). |
| `utils/compare_results.py` | **LEGACY** | Reliquia de comparativas de estrategias. |
| `utils/compare_strategies.py`| **LEGACY** | Reliquia de comparativas de estrategias. |
| `utils/consolidate_params.py` | **LEGACY** | Parámetros ya integrados en `config/trading.py`. |
| `utils/generate_test_ticks.py`| **LEGACY** | Utilizado para pruebas de estrés antiguas. |
| `utils/l2_harvester.py` | **ACTIVO** | Necesario para recolectar datos L2. |
| `utils/reset_data.py` | **ACTIVO** | Paso 0 de todos los workflows. |
| `utils/run_strategy_comparison.py`| **LEGACY** | Obsoleto. |
| `utils/sensor_analysis.py` | **DUDA** | Parece una herramienta de debug antigua. |
| `utils/symbol_norm.py` | **ACTIVO** | Utilizado por `players/adaptive.py`. |
| `utils/test_connection.py` | **ACTIVO** | Útil para verificar conexiones de red. |
| `utils/trace_bullet.py` | **ACTIVO** | Integrado en `TraceBulletValidator`. |
| `utils/verify_exchanges.py` | **ACTIVO** | Herramienta de mantenimiento de exchange. |

---
**¿Qué hacemos?**
1. Revisa los archivos marcados como **[LEGACY]**. ¿Estás de acuerdo con moverlos a `archive/`?
2. ¿Alguna duda sobre los marcados como **[DUDA]**?
