# Repo Sanitization Analysis

## Objetivo
Identificar, archivar o eliminar componentes obsoletos, scripts legacy o archivos huérfanos para reducir la deuda técnica y mejorar la mantenibilidad del repositorio.

## Análisis Preliminar (Áreas de interés)
*   **`scripts/`**: Tras la creación del orquestador, ¿`run_batches.sh` sigue siendo necesario?
*   **`archive/`**: ¿Qué contenido hay dentro? ¿Es necesario?
*   **`scratch/`**: ¿Existen experimentos abandonados que no aportan valor?
*   **`tests/validation/`**: Verificar si hay archivos de datos/logs que ya no se usan.
*   **`docs/`**: ¿Hay documentación desactualizada?

## Instrucciones para la Reunión
Antes de realizar cualquier acción destructiva, revisaremos esta lista para asegurar que nada crítico sea borrado.

---
**Lista de propuestas para revisión:**
*(A rellenar durante nuestra reunión)*
