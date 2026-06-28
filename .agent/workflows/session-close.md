---
description: Protocolo de Cierre de Sesión (Actualiza memory.md y changelog.md)
---

# Protocolo de Cierre de Sesión (/session-close)

## 🎯 Objetivo
Asegurar que el conocimiento técnico, las decisiones estratégicas y las métricas de rendimiento queden preservadas de forma estructurada antes de finalizar la interacción.

## 📋 Pasos del Protocolo

### Paso 1: Actualizar el Historial (`changelog.md`)
*   **Nueva Entrada**: Crear un bloque con la fecha actual y la descripción de la sesión.
*   **Detalle Técnico**: Listar archivos modificados y por qué (justificación).
*   **Hallazgos y Errores**: Registrar bugs encontrados, lecciones aprendidas y por qué fallaron ciertos experimentos.
*   **Métricas Crudas**: Volcar tablas de resultados de backtests o auditorías realizadas en la sesión.

### Paso 2: Actualizar la Brújula (`memory.md`)
*   **Capa de Certificación**: Si se alcanzó un hito (ej. paridad lograda), actualizar el estado de la Capa (Hierro, Cristal o Acero).
*   **Tabla Comparativa**: Si hay un nuevo "Baseline" certificado, actualizar la tabla de estrategias.
*   **Manual Técnico & Gotchas**: Si se descubrió una regla nueva o un comportamiento extraño del exchange/bot, añadirlo a la sección correspondiente.
*   **Objetivo de Sesión**: Actualizar la meta para la siguiente sesión basándose en lo concluido hoy.
*   **Roadmap**: Si se completó una refactorización grande (ej. OrderFlowEngine, instant/confirmation), agregar en el roadmap la **verificación pre-merge** para la próxima sesión (ver Paso 4).

### Paso 3: Verificación de Integridad
*   **Regla del Minuto**: El `memory.md` debe seguir siendo legible y útil en menos de 1 minuto. Si se está volviendo demasiado largo, mover detalles al `changelog.md`.
*   **Estado de Git**: Confirmar si se realizó `commit` o `tag` y reflejarlo en el Memory.

### Paso 4: Roadmap de Verificación Pre-Merge (Si hubo refactorización)
*   **Validación con Orchestrator**: En la próxima sesión, correr `scripts/orchestrator.py` con todos los protocolos relevantes (`single-coin-audit`, `cluster_*`, `probe`) para validar que la refactorización no rompió el flujo de backtests.
*   **Validación con Cluster Optimizer**: Correr `scripts/cluster_optimizer.py --validate-only` para confirmar que la optimización de parámetros funciona con los nuevos paths.
*   **Validate-All Pipeline**: Ejecutar `.agent/workflows/validate-all.md` (Layers 0-3) para verificación completa antes del merge a `dev`.

## 🚀 Ejecución
Este protocolo debe ejecutarse **SIEMPRE** antes de despedirse, o cuando se cambie radicalmente de tarea dentro de la misma sesión.
