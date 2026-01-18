---
description: [Descripción corta: ej. "Protocolo para discutir antes de actuar"]
---

# Título del Flujo de Trabajo

## 1. Fase de Análisis (Solo Lectura)
En esta fase, el agente debe **leer y analizar**, no ejecutar cambios.
- [ ] Leer archivos relevantes.
- [ ] Explicar el problema al usuario.
- [ ] **PAUSA**: Esperar confirmación del usuario antes de pasar a la siguiente fase.

## 2. Fase de Propuesta (Planificación)
- [ ] Crear/Actualizar `implementation_plan.md`.
- [ ] Detallar los cambios exactos.
- [ ] **PAUSA**: El usuario debe escribir "Aprobado" para continuar.

## 3. Fase de Ejecución (Acción)
/* turbo */ (Esta etiqueta permite al agente ejecutar comandos seguidos sin preguntar en cada línea, pero SOLO en esta fase)
- [ ] Aplicar cambios de código.
- [ ] Ejecutar tests unitarios.

## 4. Fase de Verificación
- [ ] Confirmar que el fix funciona.
- [ ] Actualizar `history.md`.
