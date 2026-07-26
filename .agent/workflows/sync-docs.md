---
description: Sincroniza documentación (Actualiza memory.md, changelog.md y purga task.md)
---

# Protocolo de Sincronización de Documentación (/sync-docs)

## 🎯 Objetivo
Asegurar que el conocimiento técnico, las decisiones estratégicas y las métricas de rendimiento queden preservadas de forma estructurada según la **Metodología de Ingeniería Confiable**, antes de finalizar la interacción.

## 📋 Pasos del Protocolo

### Paso 1: Purga y Consolidación de Tareas (`task.md`)
*   Si existe un archivo `task.md` (El "Durante") en la sesión actual y sus tareas fueron completadas, extraer el resultado final.
*   El archivo temporal `task.md` **NO** debe usarse para almacenar conocimiento permanente. Su único propósito es guiar la ejecución de la sesión actual.

### Paso 2: Actualizar el Historial (`changelog.md`)
*   **Nueva Entrada (El "Después")**: Crear un bloque con la fecha actual y la descripción de la sesión. Aquí se mueve todo el "Timeline" o registro diario.
*   **Detalle Técnico**: Listar archivos modificados y por qué (justificación).
*   **Hallazgos y Errores**: Registrar bugs encontrados, lecciones aprendidas y resultados de los `task.md` completados.
*   **Métricas Crudas**: Volcar tablas de resultados de backtests o auditorías realizadas en la sesión.

### Paso 3: Actualizar la Brújula (`memory.md`)
*   **Regla de Oro (El "Por qué")**: `memory.md` NO debe contener ruido diario ni tareas a corto plazo. Es la Biblia Arquitectónica.
*   **Capa de Certificación**: Si se alcanzó un hito de las fases del Roadmap, actualizar el estado.
*   **Tabla Comparativa**: Si hay un nuevo "Baseline" certificado, actualizar la tabla de estrategias.
*   **Manual Técnico & Gotchas**: Si se descubrió una regla nueva o un comportamiento extraño del exchange/bot/infraestructura, añadirlo a la sección correspondiente.
*   **Roadmap Vivo**: El roadmap vivo está ÚNICAMENTE en `memory.md` (sección "📍 Ruta Actual"). Refleja lo que sigue AHORA. Mover items completados al historial del `changelog.md`.

### Paso 4: Verificación de Integridad
*   **Regla del Minuto**: El `memory.md` debe seguir siendo legible y útil en menos de 1 minuto. Si hay reportes densos de un día en específico, muévelos al `changelog.md`.
*   **Branch Cleanup**: Correr `git branch --merged main | grep -v "\*" | xargs git branch -D` para eliminar feat branches locales ya mergeadas (mantener limpia la casa).
*   **Estado de Git**: Confirmar si se realizó `commit` o `tag` y reflejarlo en el Memory.

## 🚀 Ejecución
Este protocolo debe ejecutarse **SIEMPRE** antes de despedirse, o cuando se cambie radicalmente de tarea dentro de la misma sesión, para garantizar que la transición entre el *Durante*, el *Después* y el *Por qué* sea perfecta.
