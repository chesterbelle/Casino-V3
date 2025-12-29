#!/usr/bin/env python3
"""
Compare Results - Casino V2

Compara resultados de testing vs backtest para validación.

Uso:
    python tests/validation/compare_results.py \
        --testing logs/testing_20241107_1900.json \
        --backtest logs/backtest_20241107_1910.json \
        --tolerance 0.5

Compara:
    - Balance inicial/final (±tolerance%)
    - Número de trades (±1)
    - PnL total (±1.0%)
    - Win rate (±5%)

Output:
    - Reporte en consola
    - Archivo comparison_report.txt
    - Exit code 0 si pasa, 1 si falla
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

logger = logging.getLogger("CompareResults")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Compare testing vs backtest results for validation")

    parser.add_argument("--testing", type=str, required=True, help="Testing results JSON file")

    parser.add_argument("--backtest", type=str, required=True, help="Backtest results JSON file")

    parser.add_argument("--tolerance", type=float, default=0.5, help="Balance tolerance percentage (default: 0.5%%)")

    parser.add_argument(
        "--output", type=str, default=None, help="Output report file (default: logs/comparison_TIMESTAMP.txt)"
    )

    return parser.parse_args()


def load_results(filepath: str) -> Dict:
    """
    Load results from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        Results dictionary
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")


def compare_metric(
    name: str, testing_value: float, backtest_value: float, tolerance: float, is_percentage: bool = False
) -> Tuple[bool, float, str]:
    """
    Compare a metric between testing and backtest.

    Args:
        name: Metric name
        testing_value: Value from testing
        backtest_value: Value from backtest
        tolerance: Tolerance percentage
        is_percentage: If True, values are already percentages

    Returns:
        Tuple of (passed, difference, status_emoji)
    """
    if testing_value == 0 and backtest_value == 0:
        return True, 0.0, "✅"

    if testing_value == 0:
        # Avoid division by zero
        diff_pct = 100.0 if backtest_value != 0 else 0.0
    else:
        if is_percentage:
            # For percentages, compare absolute difference
            diff_pct = abs(backtest_value - testing_value)
        else:
            # For values, compare percentage difference
            diff_pct = abs((backtest_value - testing_value) / testing_value * 100)

    passed = diff_pct <= tolerance
    emoji = "✅" if passed else "❌"

    return passed, diff_pct, emoji


def format_value(value: float, is_currency: bool = False, is_percentage: bool = False) -> str:
    """
    Format value for display.

    Args:
        value: Value to format
        is_currency: If True, format as currency
        is_percentage: If True, format as percentage

    Returns:
        Formatted string
    """
    if is_currency:
        return f"${value:,.2f}"
    elif is_percentage:
        return f"{value:.2f}%"
    else:
        return f"{value:.0f}"


def print_comparison(testing: Dict, backtest: Dict, tolerance: float) -> bool:
    """
    Print comparison report.

    Args:
        testing: Testing results
        backtest: Backtest results
        tolerance: Tolerance percentage

    Returns:
        True if all checks passed, False otherwise
    """
    all_passed = True

    # Header
    logger.info("=" * 80)
    logger.info("COMPARACIÓN: Testing vs Backtesting")
    logger.info("=" * 80)

    # General info
    logger.info("\n📊 DATOS GENERALES:")
    logger.info(f"\n  Testing:")
    logger.info(f"    - Mode: {testing.get('mode', 'N/A')}")
    logger.info(f"    - Player: {testing.get('player', 'N/A')}")
    logger.info(f"    - Symbol: {testing.get('symbol', 'N/A')}")
    logger.info(f"    - Timeframe: {testing.get('timeframe', 'N/A')}")
    logger.info(f"    - Timestamp: {testing.get('timestamp', 'N/A')}")

    logger.info(f"\n  Backtesting:")
    logger.info(f"    - Mode: {backtest.get('mode', 'N/A')}")
    logger.info(f"    - Player: {backtest.get('player', 'N/A')}")
    logger.info(f"    - Symbol: {backtest.get('symbol', 'N/A')}")
    logger.info(f"    - Timeframe: {backtest.get('timeframe', 'N/A')}")
    logger.info(f"    - Timestamp: {backtest.get('timestamp', 'N/A')}")

    # Balance comparison
    logger.info("\n💰 BALANCE:")

    # Initial balance
    testing_initial = testing.get("initial_balance", 0)
    backtest_initial = backtest.get("initial_balance", 0)

    logger.info(f"\n  Initial Balance:")
    logger.info(f"    Testing:    {format_value(testing_initial, is_currency=True)}")
    logger.info(f"    Backtesting: {format_value(backtest_initial, is_currency=True)}")

    if testing_initial != backtest_initial:
        logger.warning(f"    ⚠️  WARNING: Initial balances don't match!")
        logger.warning(f"    This will affect comparison accuracy.")
    else:
        logger.info(f"    ✅ Initial balances match")

    # Final balance
    testing_final = testing.get("final_balance", 0)
    backtest_final = backtest.get("final_balance", 0)

    passed, diff_pct, emoji = compare_metric("Final Balance", testing_final, backtest_final, tolerance)
    all_passed = all_passed and passed

    logger.info(f"\n  Final Balance:")
    logger.info(f"    Testing:    {format_value(testing_final, is_currency=True)}")
    logger.info(f"    Backtesting: {format_value(backtest_final, is_currency=True)}")
    logger.info(f"    Difference: {diff_pct:.2f}% {emoji}")
    logger.info(f"    Tolerance:  ±{tolerance}%")

    # PnL comparison
    logger.info("\n📈 PnL:")

    testing_pnl = testing.get("total_pnl", 0)
    backtest_pnl = backtest.get("total_pnl", 0)

    passed, diff_pct, emoji = compare_metric("Total PnL", testing_pnl, backtest_pnl, 1.0)  # 1% tolerance for PnL
    all_passed = all_passed and passed

    logger.info(f"  Testing:    {format_value(testing_pnl, is_currency=True)}")
    logger.info(f"  Backtesting: {format_value(backtest_pnl, is_currency=True)}")
    logger.info(f"  Difference: {diff_pct:.2f}% {emoji}")
    logger.info(f"  Tolerance:  ±1.0%")

    # Trades comparison
    logger.info("\n🔄 TRADES:")

    testing_trades = testing.get("total_trades", 0)
    backtest_trades = backtest.get("total_trades", 0)

    trades_diff = abs(testing_trades - backtest_trades)
    trades_passed = trades_diff <= 1
    trades_emoji = "✅" if trades_passed else "❌"
    all_passed = all_passed and trades_passed

    logger.info(f"  Testing:    {testing_trades}")
    logger.info(f"  Backtesting: {backtest_trades}")
    logger.info(f"  Difference: {trades_diff} {trades_emoji}")
    logger.info(f"  Tolerance:  ±1")

    # Win/Loss comparison
    if testing_trades > 0 or backtest_trades > 0:
        logger.info("\n🎯 WIN/LOSS:")

        testing_wins = testing.get("wins", 0)
        testing_losses = testing.get("losses", 0)
        backtest_wins = backtest.get("wins", 0)
        backtest_losses = backtest.get("losses", 0)

        logger.info(f"  Testing:    {testing_wins}W / {testing_losses}L")
        logger.info(f"  Backtesting: {backtest_wins}W / {backtest_losses}L")

        # Win rate comparison
        testing_wr = testing.get("win_rate", 0) * 100  # Convert to percentage
        backtest_wr = backtest.get("win_rate", 0) * 100

        passed, diff_pct, emoji = compare_metric(
            "Win Rate", testing_wr, backtest_wr, 5.0, is_percentage=True  # 5% tolerance for win rate
        )
        all_passed = all_passed and passed

        logger.info(f"\n  Win Rate:")
        logger.info(f"    Testing:    {testing_wr:.2f}%")
        logger.info(f"    Backtesting: {backtest_wr:.2f}%")
        logger.info(f"    Difference: {diff_pct:.2f}% {emoji}")
        logger.info(f"    Tolerance:  ±5.0%")

    # Final result
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("🎯 RESULTADO: ✅ VALIDACIÓN EXITOSA")
        logger.info("=" * 80)
        logger.info("\n✅ Todas las métricas están dentro de tolerancia")
        logger.info("✅ El backtesting refleja correctamente el comportamiento de testing")
    else:
        logger.info("🎯 RESULTADO: ❌ VALIDACIÓN FALLIDA")
        logger.info("=" * 80)
        logger.info("\n❌ Algunas métricas están fuera de tolerancia")
        logger.info("⚠️  Revisar diferencias y ajustar backtesting si es necesario")

    return all_passed


def save_report(testing: Dict, backtest: Dict, tolerance: float, output_path: str):
    """
    Save comparison report to file.

    Args:
        testing: Testing results
        backtest: Backtest results
        tolerance: Tolerance percentage
        output_path: Output file path
    """
    # Create directory if needed
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Generate report content
    lines = []
    lines.append("=" * 80)
    lines.append("COMPARISON REPORT: Testing vs Backtesting")
    lines.append("=" * 80)
    lines.append(f"\nGenerated: {datetime.now().isoformat()}")
    lines.append(f"\nTesting file: {testing.get('timestamp', 'N/A')}")
    lines.append(f"Backtest file: {backtest.get('timestamp', 'N/A')}")
    lines.append(f"\nTolerance: ±{tolerance}%")
    lines.append("\n" + "=" * 80)
    lines.append("\nMETRICS:")
    lines.append(f"\n  Initial Balance:")
    lines.append(f"    Testing:    ${testing.get('initial_balance', 0):,.2f}")
    lines.append(f"    Backtesting: ${backtest.get('initial_balance', 0):,.2f}")
    lines.append(f"\n  Final Balance:")
    lines.append(f"    Testing:    ${testing.get('final_balance', 0):,.2f}")
    lines.append(f"    Backtesting: ${backtest.get('final_balance', 0):,.2f}")
    lines.append(f"\n  Total PnL:")
    lines.append(f"    Testing:    ${testing.get('total_pnl', 0):,.2f}")
    lines.append(f"    Backtesting: ${backtest.get('total_pnl', 0):,.2f}")
    lines.append(f"\n  Total Trades:")
    lines.append(f"    Testing:    {testing.get('total_trades', 0)}")
    lines.append(f"    Backtesting: {backtest.get('total_trades', 0)}")
    lines.append(f"\n  Win Rate:")
    lines.append(f"    Testing:    {testing.get('win_rate', 0)*100:.2f}%")
    lines.append(f"    Backtesting: {backtest.get('win_rate', 0)*100:.2f}%")
    lines.append("\n" + "=" * 80)

    # Save to file
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"\n📝 Report saved to: {output_file}")


def main():
    """Main function."""
    args = parse_args()

    try:
        # Load results
        logger.info("📥 Loading results...")
        testing = load_results(args.testing)
        backtest = load_results(args.backtest)
        logger.info(f"  Testing: {args.testing}")
        logger.info(f"  Backtest: {args.backtest}\n")

        # Compare results
        all_passed = print_comparison(testing, backtest, args.tolerance)

        # Generate output path if not provided
        if not args.output:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            args.output = f"logs/comparison_{timestamp}.txt"

        # Save report
        save_report(testing, backtest, args.tolerance, args.output)

        # Return exit code
        return 0 if all_passed else 1

    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
