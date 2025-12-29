"""
Comparación de Resultados de main.py.

Este script compara los resultados finales de main.py ejecutado en
modo testing vs backtesting, parseando la salida estándar.

Usage:
    # Capturar salidas durante ejecución:
    python main.py --mode=testing ... | tee logs/testing_output.txt
    python main.py --mode=backtest ... | tee logs/backtest_output.txt

    # Comparar:
    python tests/validation/compare_main_results.py \
        --testing logs/testing_output.txt \
        --backtest logs/backtest_output.txt
"""

import argparse
import re
from typing import Dict, Optional


def parse_results(output_text: str) -> Optional[Dict]:
    """
    Parsea la salida de main.py para extraer resultados.

    Args:
        output_text: Texto de salida de main.py

    Returns:
        Dict con resultados o None si no se pudo parsear
    """
    results = {}

    # Buscar sección de resultados
    if "BACKTEST RESULTS" in output_text:
        section = "BACKTEST"
    elif "TESTING RESULTS" in output_text:
        section = "TESTING"
    else:
        return None

    results["mode"] = section

    # Parsear métricas usando regex
    patterns = {
        "initial_balance": r"Initial Balance:\s+\$?([\d,]+\.?\d*)",
        "final_balance": r"Final Balance:\s+\$?([\d,]+\.?\d*)",
        "final_equity": r"Final Equity:\s+\$?([\d,]+\.?\d*)",
        "net_pnl": r"Net PnL:\s+\$?([+-]?[\d,]+\.?\d*)",
        "total_fees": r"Total Fees:\s+\$?([\d,]+\.?\d*)",
        "total_trades": r"Total Trades:\s+(\d+)",
        "wins": r"Wins:\s+(\d+)",
        "losses": r"Losses:\s+(\d+)",
        "win_rate": r"Win Rate:\s+([\d.]+)%",
        "avg_win": r"Avg Win:\s+\$?([+-]?[\d,]+\.?\d*)",
        "avg_loss": r"Avg Loss:\s+\$?([+-]?[\d,]+\.?\d*)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, output_text)
        if match:
            value = match.group(1).replace(",", "")
            # Convertir a número
            if key in ["total_trades", "wins", "losses"]:
                results[key] = int(value)
            elif key == "win_rate":
                results[key] = float(value) / 100  # Convertir % a decimal
            else:
                results[key] = float(value)

    return results if results else None


def compare_results(testing_results: Dict, backtest_results: Dict) -> Dict:
    """
    Compara resultados de testing vs backtesting.

    Args:
        testing_results: Resultados del modo testing
        backtest_results: Resultados del modo backtesting

    Returns:
        Dict con comparación y validación
    """
    comparison = {
        "differences": [],
        "validation_passed": True,
        "summary": {},
    }

    # Tolerancias
    BALANCE_TOLERANCE = 0.001  # 0.1%
    METRIC_TOLERANCE = 0.01  # 1%

    # Comparar balance final
    testing_balance = testing_results.get("final_balance", 0)
    backtest_balance = backtest_results.get("final_balance", 0)

    if testing_balance > 0:
        balance_diff_percent = abs(testing_balance - backtest_balance) / testing_balance
        comparison["summary"]["balance_diff_percent"] = balance_diff_percent * 100

        if balance_diff_percent > BALANCE_TOLERANCE:
            comparison["differences"].append(
                {
                    "metric": "Final Balance",
                    "testing": testing_balance,
                    "backtest": backtest_balance,
                    "diff_percent": balance_diff_percent * 100,
                    "tolerance": BALANCE_TOLERANCE * 100,
                    "status": "WARNING",
                }
            )
            comparison["validation_passed"] = False
        else:
            comparison["summary"]["balance_status"] = "PASS"

    # Comparar número de trades
    testing_trades = testing_results.get("total_trades", 0)
    backtest_trades = backtest_results.get("total_trades", 0)

    if testing_trades != backtest_trades:
        comparison["differences"].append(
            {
                "metric": "Total Trades",
                "testing": testing_trades,
                "backtest": backtest_trades,
                "diff": backtest_trades - testing_trades,
                "status": "FAIL",
            }
        )
        comparison["validation_passed"] = False
    else:
        comparison["summary"]["trades_status"] = "PASS"

    # Comparar win rate
    testing_wr = testing_results.get("win_rate", 0)
    backtest_wr = backtest_results.get("win_rate", 0)

    if testing_wr != backtest_wr:
        comparison["differences"].append(
            {
                "metric": "Win Rate",
                "testing": testing_wr * 100,
                "backtest": backtest_wr * 100,
                "diff": (backtest_wr - testing_wr) * 100,
                "status": "WARNING",
            }
        )

    # Comparar PnL
    testing_pnl = testing_results.get("net_pnl", 0)
    backtest_pnl = backtest_results.get("net_pnl", 0)

    if testing_pnl != 0:
        pnl_diff_percent = abs(testing_pnl - backtest_pnl) / abs(testing_pnl)
        comparison["summary"]["pnl_diff_percent"] = pnl_diff_percent * 100

        if pnl_diff_percent > METRIC_TOLERANCE:
            comparison["differences"].append(
                {
                    "metric": "Net PnL",
                    "testing": testing_pnl,
                    "backtest": backtest_pnl,
                    "diff_percent": pnl_diff_percent * 100,
                    "tolerance": METRIC_TOLERANCE * 100,
                    "status": "WARNING",
                }
            )

    return comparison


def print_comparison_report(testing_results: Dict, backtest_results: Dict, comparison: Dict):
    """Imprime reporte de comparación."""
    print("\n" + "=" * 80)
    print("📊 COMPARACIÓN: Testing vs Backtesting")
    print("=" * 80)

    # Resultados individuales
    print("\n🔵 TESTING (Live Testnet):")
    print(f"  Initial Balance: ${testing_results.get('initial_balance', 0):,.2f}")
    print(f"  Final Balance:   ${testing_results.get('final_balance', 0):,.2f}")
    print(f"  Net PnL:         ${testing_results.get('net_pnl', 0):+,.2f}")
    print(f"  Total Trades:    {testing_results.get('total_trades', 0)}")
    print(f"  Win Rate:        {testing_results.get('win_rate', 0)*100:.1f}%")

    print("\n🟢 BACKTESTING (Historical Data):")
    print(f"  Initial Balance: ${backtest_results.get('initial_balance', 0):,.2f}")
    print(f"  Final Balance:   ${backtest_results.get('final_balance', 0):,.2f}")
    print(f"  Net PnL:         ${backtest_results.get('net_pnl', 0):+,.2f}")
    print(f"  Total Trades:    {backtest_results.get('total_trades', 0)}")
    print(f"  Win Rate:        {backtest_results.get('win_rate', 0)*100:.1f}%")

    # Diferencias
    if comparison["differences"]:
        print("\n⚠️  DIFERENCIAS ENCONTRADAS:")
        print("-" * 80)
        for diff in comparison["differences"]:
            print(f"\n  {diff['metric']}:")
            print(f"    Testing:    {diff.get('testing', 'N/A')}")
            print(f"    Backtesting: {diff.get('backtest', 'N/A')}")
            if "diff_percent" in diff:
                print(f"    Diferencia: {diff['diff_percent']:.3f}%")
                print(f"    Tolerancia: {diff['tolerance']:.3f}%")
            elif "diff" in diff:
                print(f"    Diferencia: {diff['diff']}")
            print(f"    Status:     {diff['status']}")
    else:
        print("\n✅ No se encontraron diferencias significativas")

    # Resultado final
    print("\n" + "=" * 80)
    if comparison["validation_passed"]:
        print("✅ VALIDACIÓN EXITOSA")
        print("Backtesting produce los mismos resultados que testing en vivo")
    else:
        print("❌ VALIDACIÓN FALLIDA")
        print("Se encontraron diferencias significativas entre testing y backtesting")

    print("=" * 80 + "\n")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Compara resultados de main.py (testing vs backtesting)")
    parser.add_argument("--testing", type=str, required=True, help="Path a salida de testing")
    parser.add_argument("--backtest", type=str, required=True, help="Path a salida de backtesting")

    args = parser.parse_args()

    # Leer archivos
    with open(args.testing, "r") as f:
        testing_output = f.read()

    with open(args.backtest, "r") as f:
        backtest_output = f.read()

    # Parsear resultados
    testing_results = parse_results(testing_output)
    backtest_results = parse_results(backtest_output)

    if not testing_results:
        print("❌ Error: No se pudieron parsear resultados de testing")
        return

    if not backtest_results:
        print("❌ Error: No se pudieron parsear resultados de backtesting")
        return

    # Comparar
    comparison = compare_results(testing_results, backtest_results)

    # Imprimir reporte
    print_comparison_report(testing_results, backtest_results, comparison)


if __name__ == "__main__":
    main()
