#!/usr/bin/env python3
"""
Unified CLI entry point for operational utilities.

Examples:
    python3 -m utils.cli download-training-data
    python3 -m utils.cli train-memory
    python3 -m utils.cli analyze-memory
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

from .analysis import analyze_memory, check_sensors

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _stream_subprocess(
    command: List[str],
    *,
    cwd: Path = ROOT,
    env: Optional[dict] = None,
    log_path: Optional[Path] = None,
) -> int:
    """
    Execute a subprocess while streaming its output to stdout and an optional log.

    Returns:
        Process return code.
    """
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    log_handle = log_path.open("w", encoding="utf-8") if log_path else None
    try:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            if log_handle:
                log_handle.write(line)
        process.wait()
    finally:
        if log_handle:
            log_handle.close()
    return process.returncode


def run_download_training_data(
    symbols: Iterable[str],
    interval: str,
    days: int,
    tag: str,
) -> bool:
    symbols = list(symbols) or ["BTCUSDT", "ETHUSDT", "LTCUSDT", "BNBUSDT", "SOLUSDT"]
    output_dir = ROOT / "tables" / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("==================================")
    logger.info("📥 DESCARGA DE DATOS PARA ENTRENAMIENTO")
    logger.info("==================================\n")
    logger.info("📋 Configuración:")
    logger.info(f"  Símbolos: {' '.join(symbols)}")
    logger.info(f"  Intervalo: {interval}")
    logger.info(f"  Días: {days}")
    logger.info(f"  Tag: {tag}")
    logger.info("")

    script_path = ROOT / "utils" / "data" / "download_kline_dataset.py"
    if not script_path.exists():
        logger.error("❌ Error: utils/download_kline_dataset.py no encontrado")
        logger.info("   Asegúrate de correr desde la raíz del proyecto.")
        return False

    total = len(symbols)
    failed = 0

    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{total}] Descargando {symbol}...")
        command = [
            PYTHON,
            str(script_path),
            "--symbol",
            symbol,
            "--interval",
            interval,
            "--days",
            str(days),
            "--tag",
            tag,
        ]
        return_code = _stream_subprocess(command)
        if return_code == 0:
            logger.info(f"  ✅ {symbol} descargado exitosamente\n")
        else:
            logger.error(f"  ❌ Error descargando {symbol}\n")
            failed += 1

    logger.info("==================================")
    logger.info("📊 RESUMEN DE DESCARGAS")
    logger.info("==================================")
    logger.info(f"  Total símbolos: {total}")
    logger.info(f"  Exitosos: {total - failed}")
    logger.info(f"  Fallidos: {failed}\n")

    if failed == 0:
        logger.info("✅ ¡Todas las descargas completadas!\n")
        generated = sorted(output_dir.glob(f"*_{interval}_{tag}.csv"))
        if generated:
            logger.info("📁 Archivos generados:")
            for path in generated:
                logger.info(f"   - {path.relative_to(ROOT)}")
        else:
            logger.info(f"📁 No se encontraron archivos con tag '{tag}'.")
        logger.info("\n🎯 Próximo paso:")
        logger.info("   python3 -m utils.cli train-memory")
    else:
        logger.warning("⚠️  Algunas descargas fallaron, revisa los mensajes anteriores.")

    logger.info("==================================")
    return failed == 0


TRAINING_CONFIG_TEMPLATE = """\
# Configuración temporal para ENTRENAMIENTO DE MEMORIA
# Generado automáticamente por utils.cli

from config import *  # noqa: F401,F403

MODE = "backtest"
FORCE_GHOST_ALL = True

ACTIVE_SENSORS = {
    "RSIReversion": True,
    "BollingerTouch": True,
    "KeltnerReversion": True,
    "StochasticReversion": True,
    "BollingerSqueeze": True,
    "WilliamsRReversion": True,
    "CCIReversion": True,
    "ZScoreReversion": True,
    "EMACrossover": True,
    "MACDCrossover": True,
    "Supertrend": True,
    "ADXFilter": True,
    "ParabolicSAR": True,
    "OBVBreakout": True,
    "VWAPDeviation": True,
    "MFIReversion": True,
    "AccumulationDistribution": True,
}

MIN_SUPPORT = 500
MEMORY_WINDOW = 500
AUTOSAVE_INTERVAL = 50
BAYES_CREDIBILITY_THRESHOLD = 0.7

print("=" * 60)
print("⚙️  CONFIGURACIÓN: MODO ENTRENAMIENTO (GHOST)")
print("=" * 60)
print(f"  FORCE_GHOST_ALL: {FORCE_GHOST_ALL}")
print(f"  MIN_SUPPORT: {MIN_SUPPORT}")
print(f"  SENSORES ACTIVOS: {len(ACTIVE_SENSORS)}")
print("=" * 60)
"""


def run_train_memory(pattern: str) -> bool:
    data_dir = ROOT / "tables" / "data" / "raw"
    datasets = sorted(data_dir.glob(pattern))
    if not datasets:
        print(f"❌ No se encontraron datasets con patrón: {pattern}")
        print(f"   Directorio: {data_dir.relative_to(ROOT)}")
        print("\n💡 Ejecuta primero:\n   python3 -m utils.cli download-training-data")
        return False

    logger.info("==================================")
    logger.info("🧠 ENTRENAMIENTO DE MEMORIA (GHOST MODE)")
    logger.info("==================================\n")

    logger.info(f"📊 Datasets encontrados: {len(datasets)}")
    for ds in datasets:
        try:
            label = ds.relative_to(ROOT)
        except ValueError:
            label = ds
        logger.info(f"  - {label}")
    logger.info("")

    config_training_path = ROOT / "config_training.py"
    config_training_path.write_text(TRAINING_CONFIG_TEMPLATE, encoding="utf-8")
    logger.info("⚙️  Configuración temporal creada en config_training.py\n")

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) if not python_path else f"{str(ROOT)}{os.pathsep}{python_path}"

    total = len(datasets)
    failed = 0

    try:
        for idx, dataset in enumerate(datasets, 1):
            try:
                dataset_str = dataset.relative_to(ROOT).as_posix()
            except ValueError:
                dataset_str = str(dataset)

            log_path = logs_dir / f"training_{dataset.stem}.log"

            logger.info(f"[{idx}/{total}] Entrenando con: {dataset_str}")
            command = [
                PYTHON,
                "-c",
                textwrap.dedent(
                    f"""
import asyncio
import sys
sys.path.insert(0, '.')
# Import config_training to override system settings
import config_training
from players import paroli_player
import main

# Run the backtest for training
asyncio.run(main.run_backtest(
    player_module=paroli_player,
    data_file='{dataset_str}',
    max_candles=None,
    initial_balance=10000.0
))
"""
                ),
            ]
            return_code = _stream_subprocess(command, env=env, log_path=log_path)
            if return_code == 0:
                logger.info("  ✅ Entrenamiento completado\n")
            else:
                logger.error("  ❌ Error en entrenamiento\n")
                failed += 1
    finally:
        if config_training_path.exists():
            config_training_path.unlink()

    logger.info("==================================")
    logger.info("📊 RESUMEN DE ENTRENAMIENTO")
    logger.info("==================================")
    logger.info(f"  Datasets procesados: {total}")
    logger.info(f"  Exitosos: {total - failed}")
    logger.info(f"  Fallidos: {failed}\n")

    if failed == 0:
        logger.info("✅ ¡Entrenamiento completado!\n")
        logger.info("📁 Memoria guardada en:")
        logger.info("   gemini/data/memory_log.csv")
        logger.info("   gemini/data/memory_state.json\n")
        logger.info("📊 Revisar estadísticas:")
        logger.info("   python3 -m utils.cli analyze-memory\n")
        logger.info("🎯 Próximo paso:")
        logger.info("   python3 -m utils.cli validate-strategies")
    else:
        logger.warning("⚠️  Algunos entrenamientos fallaron")
        logger.info("   Revisa los logs en: logs/")
    logger.info("==================================")
    return failed == 0


def run_validate_strategies(pattern: str, limit: int, starting_balance: float) -> bool:
    data_dir = ROOT / "tables" / "data" / "raw"
    datasets = sorted(data_dir.glob(pattern))[:limit]
    if not datasets:
        logger.error(f"❌ No se encontraron datasets con patrón: {pattern}")
        return False

    memory_path = analyze_memory.DEFAULT_MEMORY_PATH
    if not memory_path.exists():
        logger.error("❌ No se encontró memoria entrenada")
        logger.info("   Ejecuta primero: python3 -m utils.cli train-memory")
        return False

    logger.info("==================================")
    logger.info("✅ VALIDACIÓN DE ESTRATEGIAS")
    logger.info("==================================\n")

    logger.info("📊 Datasets de validación:")
    for ds in datasets:
        try:
            label = ds.relative_to(ROOT)
        except ValueError:
            label = ds
        logger.info(f"  - {label}")
    print("")

    state = analyze_memory.load_memory(memory_path)
    if state:
        strategies = state.get("strategies", {})
        approved = [name for name, data in strategies.items() if data.get("wins", 0) + data.get("losses", 0) >= 500]
        logger.info("🧠 Memoria encontrada:")
        logger.info(f"  Total estrategias: {len(strategies)}")
        logger.info(f"  Estrategias aprobadas (>=500 trades): {len(approved)}\n")

        sorted_strats = sorted(
            [(name, strategies[name].get("winrate", 0)) for name in approved],
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        if sorted_strats:
            logger.info("  Top 5 por winrate:")
            for name, winrate in sorted_strats:
                logger.info(f"    - {name[:50]:50s}: {winrate:.2%}")
            print("")

    results_dir = ROOT / "results" / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) if not python_path else f"{str(ROOT)}{os.pathsep}{python_path}"

    total = len(datasets)
    failed = 0

    for idx, dataset in enumerate(datasets, 1):
        try:
            dataset_str = dataset.relative_to(ROOT).as_posix()
        except ValueError:
            dataset_str = str(dataset)

        out_file = results_dir / f"validation_{dataset.stem}.txt"
        logger.info(f"[{idx}/{total}] Validando con: {dataset_str}")

        command = [
            PYTHON,
            "-c",
            textwrap.dedent(
                f"""
import sys
sys.path.insert(0, '.')
import config
config.MODE = "backtest"
config.DATASET_PATH = {dataset_str!r}
config.STARTING_BALANCE = {starting_balance}
import main  # noqa: F401
"""
            ),
        ]

        return_code = _stream_subprocess(command, env=env, log_path=out_file)
        if return_code == 0:
            logger.info("  ✅ Validación completada\n")
        else:
            logger.error("  ❌ Error en validación\n")
            failed += 1

    logger.info("==================================")
    logger.info("📊 VALIDACIÓN COMPLETADA")
    logger.info("==================================\n")
    logger.info("📁 Resultados guardados en:")
    logger.info(f"   {results_dir.relative_to(ROOT)}\n")
    logger.info("🎯 Analizar resultados:")
    logger.info("   python3 -m utils.cli analyze-memory")
    logger.info("   tail -n 40 %s", results_dir.relative_to(ROOT) / "*.txt")
    logger.info("==================================")
    return failed == 0


def run_full_pipeline(args) -> bool:
    start_time = datetime.now()

    logger.info("")
    logger.info("╔════════════════════════════════════════════════════════════════╗")
    logger.info("║                                                                ║")
    logger.info("║     🎰 CASINO V2 - PIPELINE COMPLETO DE ENTRENAMIENTO         ║")
    logger.info("║                                                                ║")
    logger.info("╚════════════════════════════════════════════════════════════════╝")
    logger.info("")
    logger.info(f"⏰ Inicio: {start_time:%Y-%m-%d %H:%M:%S}\n")

    ok = run_download_training_data(
        symbols=args.symbols or [],
        interval=args.interval,
        days=args.days,
        tag=args.tag,
    )
    if not ok:
        logger.error("❌ Error en Fase 1 (download-training-data)")
        return False

    if not args.non_interactive:
        input("⏸️  Presiona ENTER para continuar con Fase 2...")
        logger.info("")

    ok = run_train_memory(pattern=args.pattern)
    if not ok:
        logger.error("❌ Error en Fase 2 (train-memory)")
        return False

    if not args.non_interactive:
        input("⏸️  Presiona ENTER para continuar con Fase 3...")
        logger.info("")

    analyze_memory.main()

    if not args.non_interactive:
        input("⏸️  Presiona ENTER para continuar con Fase 4...")
        logger.info("")

    ok = run_validate_strategies(
        pattern=args.validation_pattern,
        limit=args.limit,
        starting_balance=args.starting_balance,
    )
    if not ok:
        logger.error("❌ Error en Fase 4 (validate-strategies)")
        return False

    end_time = datetime.now()
    duration = end_time - start_time
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)

    logger.info("")
    logger.info("╔════════════════════════════════════════════════════════════════╗")
    logger.info("║                                                                ║")
    logger.info("║     ✅ PIPELINE COMPLETADO EXITOSAMENTE                        ║")
    logger.info("║                                                                ║")
    logger.info("╚════════════════════════════════════════════════════════════════╝")
    logger.info("")
    logger.info(f"⏱️  Tiempo total: {int(hours)}h {int(minutes)}m {int(seconds)}s\n")
    logger.info("📁 Archivos generados:")
    logger.info("   - Memoria: gemini/data/memory_state.json")
    logger.info("   - Logs: logs/")
    logger.info("   - Resultados: results/\n")
    logger.info("🎯 Próximos pasos:")
    logger.info("   1. Revisar análisis de memoria")
    logger.info("   2. Revisar resultados de validación")
    logger.info("   3. Configurar live/paper trading si todo está correcto\n")

    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Casino V2 consolidated utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_cmd = subparsers.add_parser("download-training-data", help="Descarga datasets históricos.")
    download_cmd.add_argument("--symbols", nargs="*", default=None, help="Símbolos a descargar (ej. BTCUSDT ETHUSDT).")
    download_cmd.add_argument("--interval", default="1m", help="Intervalo de velas (default: 1m).")
    download_cmd.add_argument("--days", type=int, default=1000, help="Días hacia atrás a descargar (default: 1000).")
    download_cmd.add_argument(
        "--tag", default="training", help="Etiqueta para los archivos generados (default: training)."
    )

    train_cmd = subparsers.add_parser("train-memory", help="Ejecuta el entrenamiento GHOST de la memoria.")
    train_cmd.add_argument(
        "--pattern", default="*_training.csv", help="Patrón de datasets a usar (default: *_training.csv)."
    )

    validate_cmd = subparsers.add_parser("validate-strategies", help="Valida estrategias entrenadas.")
    validate_cmd.add_argument("--pattern", default="*_15m_*.csv", help="Patrón de búsqueda de datasets.")
    validate_cmd.add_argument("--limit", type=int, default=3, help="Número máximo de datasets a validar (default: 3).")
    validate_cmd.add_argument(
        "--starting-balance", type=float, default=10000.0, help="Balance inicial para la validación."
    )

    subparsers.add_parser("analyze-memory", help="Analiza el estado de la memoria Gemini.")
    subparsers.add_parser("check-sensors", help="Verifica sensores registrados y activos.")

    pipeline_cmd = subparsers.add_parser(
        "full-pipeline", help="Ejecuta todo el pipeline de datos → entrenamiento → validación."
    )
    pipeline_cmd.add_argument(
        "--symbols", nargs="*", default=None, help="Sobrescribe la lista de símbolos para la descarga."
    )
    pipeline_cmd.add_argument("--interval", default="1m", help="Intervalo de velas (default: 1m).")
    pipeline_cmd.add_argument("--days", type=int, default=1000, help="Días hacia atrás a descargar (default: 1000).")
    pipeline_cmd.add_argument(
        "--tag", default="training", help="Etiqueta para los archivos generados (default: training)."
    )
    pipeline_cmd.add_argument("--pattern", default="*_training.csv", help="Patrón de datasets para entrenamiento.")
    pipeline_cmd.add_argument("--validation-pattern", default="*_15m_*.csv", help="Patrón de datasets para validación.")
    pipeline_cmd.add_argument("--limit", type=int, default=3, help="Número máximo de datasets de validación.")
    pipeline_cmd.add_argument(
        "--starting-balance", type=float, default=10000.0, help="Balance inicial usado en validación."
    )
    pipeline_cmd.add_argument(
        "--non-interactive", action="store_true", help="Desactiva las pausas interactivas entre fases."
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "download-training-data":
        ok = run_download_training_data(
            symbols=args.symbols or [],
            interval=args.interval,
            days=args.days,
            tag=args.tag,
        )
        return 0 if ok else 1

    if args.command == "train-memory":
        ok = run_train_memory(pattern=args.pattern)
        return 0 if ok else 1

    if args.command == "validate-strategies":
        ok = run_validate_strategies(
            pattern=args.pattern,
            limit=args.limit,
            starting_balance=args.starting_balance,
        )
        return 0 if ok else 1

    if args.command == "analyze-memory":
        return analyze_memory.main()

    if args.command == "check-sensors":
        return check_sensors.main()

    if args.command == "full-pipeline":
        ok = run_full_pipeline(args)
        return 0 if ok else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
