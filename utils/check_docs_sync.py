#!/usr/bin/env python3
"""
====================================================
🔍 CHECK DOCS SYNC - Casino V2
====================================================

Verifica que los 4 archivos pilares estén sincronizados:
1. README.md
2. DEVELOPER.md
3. docs/workflow.md
4. docs/development/PENDIENTES.md

Uso:
    python scripts/check_docs_sync.py

Salida:
    ✅ Si todos están sincronizados
    ❌ Si hay inconsistencias (exit code 1)
====================================================
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Importar versión desde core
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.version import __release_date__, __version__, __version_name__

# =====================================================
# 🎯 CONFIGURACIÓN
# =====================================================
PILLAR_FILES = [
    "README.md",
    "DEVELOPER.md",
    "docs/workflow.md",
    "docs/development/PENDIENTES.md",
]

# Patrones de búsqueda para versión
VERSION_PATTERNS = [
    r"[Vv]ersión[:\s]+v?(\d+\.\d+(?:\.\d+)?)",
    r"[Vv]ersion[:\s]+v?(\d+\.\d+(?:\.\d+)?)",
    r"\*\*[Vv]ersión[:\s]*\*\*[:\s]*v?(\d+\.\d+(?:\.\d+)?)",
    r"v(\d+\.\d+(?:\.\d+)?)\s*-",
    r"Badge.*[Vv]ersión.*v?(\d+\.\d+(?:\.\d+)?)",
]


# =====================================================
# 🔍 FUNCIONES DE EXTRACCIÓN
# =====================================================
def extract_version_from_file(file_path: str) -> Optional[str]:
    """
    Extrae la versión de un archivo de documentación.

    Args:
        file_path: Ruta al archivo

    Returns:
        Versión encontrada o None
    """
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Intentar con cada patrón
    for pattern in VERSION_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            # Retornar la primera versión encontrada
            return matches[0]

    return None


def check_version_mentions(file_path: str, expected_version: str) -> List[str]:
    """
    Verifica todas las menciones de versión en un archivo.

    Args:
        file_path: Ruta al archivo
        expected_version: Versión esperada

    Returns:
        Lista de problemas encontrados
    """
    problems = []

    if not os.path.exists(file_path):
        problems.append(f"Archivo no existe: {file_path}")
        return problems

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        for pattern in VERSION_PATTERNS:
            matches = re.findall(pattern, line)
            for match in matches:
                if match != expected_version:
                    problems.append(f"  Línea {i}: Encontrado v{match}, esperado v{expected_version}")

    return problems


# =====================================================
# 📊 FUNCIÓN PRINCIPAL
# =====================================================
def main():
    """Función principal de verificación."""
    logger.info("=" * 60)
    logger.info("🔍 VERIFICACIÓN DE SINCRONIZACIÓN DE DOCUMENTACIÓN")
    logger.info("=" * 60)
    logger.info(f"\n📌 Versión esperada: v{__version__}")
    logger.info(f"📝 Nombre: {__version_name__}")
    logger.info(f"📅 Fecha: {__release_date__}\n")

    # Verificar que estamos en el directorio correcto
    if not os.path.exists("core/version.py"):
        logger.error("❌ ERROR: Ejecutar desde el directorio raíz del proyecto")
        sys.exit(1)

    # Extraer versiones de cada archivo
    logger.info("📂 Verificando archivos pilares...\n")
    versions: Dict[str, Optional[str]] = {}
    all_problems: Dict[str, List[str]] = {}

    for file_path in PILLAR_FILES:
        version = extract_version_from_file(file_path)
        versions[file_path] = version

        if version:
            status = "✅" if version == __version__ else "❌"
            logger.info(f"{status} {file_path}: v{version}")

            # Verificar todas las menciones
            if version != __version__:
                problems = check_version_mentions(file_path, __version__)
                if problems:
                    all_problems[file_path] = problems
        else:
            logger.warning(f"⚠️  {file_path}: No se encontró versión")
            versions[file_path] = "NOT_FOUND"

    # Análisis de resultados
    logger.info("\n" + "=" * 60)
    logger.info("📊 RESULTADOS")
    logger.info("=" * 60)

    unique_versions = set(v for v in versions.values() if v and v != "NOT_FOUND")

    if len(unique_versions) == 1 and __version__ in unique_versions:
        logger.info(f"\n✅ ÉXITO: Todos los documentos están en v{__version__}")
        logger.info("\n🎉 Documentación sincronizada correctamente!")
        return 0

    # Hay problemas
    logger.error("\n❌ PROBLEMAS DETECTADOS:\n")

    # Mostrar versiones inconsistentes
    if len(unique_versions) > 1:
        logger.warning("🔴 Versiones inconsistentes encontradas:")
        for file_path, version in versions.items():
            if version != __version__:
                logger.warning(f"  • {file_path}: v{version} (esperado v{__version__})")
        print()

    # Mostrar archivos sin versión
    missing = [f for f, v in versions.items() if v == "NOT_FOUND"]
    if missing:
        logger.warning("⚠️  Archivos sin versión detectada:")
        for file_path in missing:
            logger.warning(f"  • {file_path}")
        print()

    # Mostrar problemas detallados
    if all_problems:
        logger.info("📝 Detalles de inconsistencias:")
        for file_path, problems in all_problems.items():
            logger.info(f"\n  {file_path}:")
            for problem in problems[:5]:  # Limitar a 5 problemas por archivo
                logger.info(f"    {problem}")
            if len(problems) > 5:
                logger.info(f"    ... y {len(problems) - 5} más")

    # Instrucciones de corrección
    logger.info("\n" + "=" * 60)
    logger.info("🔧 CÓMO CORREGIR")
    logger.info("=" * 60)
    logger.info(
        f"""
1. Actualizar manualmente cada archivo con v{__version__}
2. Buscar y reemplazar versiones antiguas
3. Ejecutar este script nuevamente para verificar

Comando útil:
  grep -n "v1\\." README.md DEVELOPER.md docs/workflow.md docs/development/PENDIENTES.md
"""
    )

    return 1


# =====================================================
# 🚀 ENTRY POINT
# =====================================================
if __name__ == "__main__":
    sys.exit(main())
