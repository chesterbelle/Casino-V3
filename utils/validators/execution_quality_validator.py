import argparse
import re
import sys
from collections import Counter
from pathlib import Path


def validate_execution_quality(log_path: str):
    path = Path(log_path)
    if not path.exists():
        print(f"❌ Error: File not found {log_path}")
        return False

    content = path.read_text()

    print(f"\n🔬 Auditing Execution Quality: {log_path}")
    print("-" * 50)

    # 1. Execution Counts
    positions_opened = len(re.findall(r"Position opened:", content)) + len(
        re.findall(r"Order Executed: CASINO_ENTRY", content)
    )
    positions_closed = len(re.findall(r"Position.*closed", content, re.IGNORECASE)) + len(
        re.findall(r"Force-closed", content)
    )

    # 2. Axia Exits vs Hard Exits
    trapped_traders = len(re.findall(r"Trapped Traders", content)) + len(re.findall(r"Trapped_Traders", content))
    fade_extreme = len(re.findall(r"Fade Extreme", content)) + len(re.findall(r"Fade_Extreme", content))
    delta_divergence = len(re.findall(r"Delta Divergence", content)) + len(re.findall(r"Delta_Divergence", content))
    tp_sl_hits = len(re.findall(r"Stop Order Executed", content))

    # 3. Execution Errors (Stalls, Overlap, Asynchio leaks)
    tracebacks = len(re.findall(r"Traceback", content))
    cancelled_errors = len(re.findall(r"CancelledError", content))
    unhandled_exceptions = len(re.findall(r"Exception in", content))
    timeouts = len(re.findall(r"TimeoutError", content))
    stalls = len(re.findall(r"Task Stalled", content))

    print(f"🚀 Execution Pipeline Metrics:")
    print(f"   • Positions Opened: {positions_opened // 2 if positions_opened // 2 > 0 else positions_opened}")
    print(f"   • Positions Closed: {positions_closed // 2 if positions_closed // 2 > 0 else positions_closed}")
    print(f"   • Total TP/SL Placements: {tp_sl_hits}")

    print(f"\n🧠 Smart Exits (Axia/Regime):")
    print(f"   • Trapped Traders triggers: {trapped_traders}")
    print(f"   • Fade Extreme triggers: {fade_extreme}")
    print(f"   • Delta Divergence triggers: {delta_divergence}")

    print(f"\n⚠️ Infrastructure Errors:")
    print(f"   • Tracebacks: {tracebacks}")
    print(f"   • Asyncio Cancelled/Unhandled: {cancelled_errors + unhandled_exceptions}")
    print(f"   • Event/Task Stalls/Timeouts: {stalls + timeouts}")

    print("-" * 50)
    failures = []

    if tracebacks > 0:
        failures.append(f"Tracebacks detectados en el log: {tracebacks}")
    if cancelled_errors + unhandled_exceptions > 0:
        failures.append(f"Fugas de Asyncio/Excepciones no manejadas: {cancelled_errors + unhandled_exceptions}")
    if stalls + timeouts > 0:
        failures.append(f"Stalls o Timeouts de tareas: {stalls + timeouts}")

    if failures:
        print("❌ VERDICT: FAIL - La capa de ejecución tiene inestabilidades.")
        for f in failures:
            print(f"   ↳ {f}")
        return False

    actual_positions = positions_opened // 2 if positions_opened // 2 > 0 else positions_opened
    if actual_positions == 0:
        print("❌ VERDICT: FAIL - No se detectó ninguna actividad real (0 trades ejecutados). Test nulo.")
        return False

    print("✅ VERDICT: PASS - Ejecución Limpia y Determinística.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditor de Calidad de Ejecución (Execution Funnel)")
    parser.add_argument("log_file", help="Path to the execution log to audit")
    args = parser.parse_args()

    success = validate_execution_quality(args.log_file)
    sys.exit(0 if success else 1)
