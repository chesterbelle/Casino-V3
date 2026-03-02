#!/usr/bin/env python3
"""
=============================================================
🎯 STRATEGY AUDIT — Phase 650 Edge Validation
=============================================================

Analyses the historian.db to compute:
  - Win Rate (goal: > 55%)
  - Profit Factor (goal: > 1.2)
  - Expectancy (per trade, in USDT)
  - MFE / MAE proxy via exit_reason distribution
  - Signal quality per sensor (if embedded in trade_id/exit_reason)
  - Early exit rate (Shadow SL / Recon exits that could have been TPs)
  - Breakeven churn (trades that barely moved)
  - Latency T0→T4 per symbol

Usage:
    python utils/strategy_audit.py [--db data/historian.db] [--session SESSION_ID] [--last N]

"""
import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# ─── ANSI colours ───────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg):
    return f"{GREEN}✅ {msg}{RESET}"


def fail(msg):
    return f"{RED}❌ {msg}{RESET}"


def warn(msg):
    return f"{YELLOW}⚠️  {msg}{RESET}"


def header(msg):
    line = "=" * 70
    return f"\n{BOLD}{CYAN}{line}\n  {msg}\n{line}{RESET}"


# ─── DB helpers ─────────────────────────────────────────────
def load_trades(db_path: str, session_id: str = None, last_n: int = None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base = """
        SELECT trade_id, symbol, side, entry_price, exit_price,
               qty, fee, gross_pnl, net_pnl, exit_reason,
               timestamp, bars_held, session_id, healed,
               t0_signal_ts, t4_fill_ts, slippage_pct
        FROM trades
        WHERE entry_price > 0
          AND exit_price > 0
    """
    params = []

    if session_id:
        base += " AND session_id = ?"
        params.append(session_id)

    base += " ORDER BY id DESC"

    if last_n:
        base += f" LIMIT {int(last_n)}"

    cur.execute(base, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def reset_db(db_path: str):
    """Wipes all trades from historian.db for a clean slate."""
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
    conn.commit()
    conn.close()
    print(f"{YELLOW}🗑️  DB Reset: {count} trades removed. Starting clean.{RESET}")


# ─── Core Metrics ────────────────────────────────────────────
def compute_edge_metrics(trades):
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    n = len(trades)

    if n == 0:
        return None

    win_rate = len(wins) / n * 100
    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)
    total_pnl = sum(t["net_pnl"] for t in trades)

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "total_pnl": total_pnl,
    }


def compute_exit_breakdown(trades):
    by_reason = defaultdict(list)
    for t in trades:
        by_reason[t["exit_reason"] or "UNKNOWN"].append(t["net_pnl"])
    return {k: {"count": len(v), "pnl": sum(v)} for k, v in by_reason.items()}


def compute_per_symbol(trades):
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t)
    result = {}
    for sym, ts in by_sym.items():
        metrics = compute_edge_metrics(ts)
        if metrics:
            result[sym] = metrics
    return result


def compute_early_exit_rate(trades):
    """
    Early exit = trades closed by SHADOW_SL, AUDIT_RECON_FORCE, Recon variants.
    These *might* have been winners if held longer.
    """
    early_exit_reasons = {"SHADOW_SL", "AUDIT_RECON_FORCE", "SL (Recon)", "TP (Recon)"}
    early = [t for t in trades if t["exit_reason"] in early_exit_reasons]
    potential_rescues = [t for t in early if t["net_pnl"] < 0]

    return {
        "early_exit_count": len(early),
        "early_exit_pct": len(early) / len(trades) * 100 if trades else 0,
        "early_exits_that_lost": len(potential_rescues),
        "early_exit_pnl": sum(t["net_pnl"] for t in early),
    }


def compute_latency_stats(trades):
    latencies = []
    for t in trades:
        t0 = t.get("t0_signal_ts")
        t4 = t.get("t4_fill_ts")
        if t0 and t4 and t4 > t0:
            latencies.append((t4 - t0) * 1000)  # ms
    if not latencies:
        return None
    latencies.sort()
    return {
        "count": len(latencies),
        "avg_ms": sum(latencies) / len(latencies),
        "median_ms": latencies[len(latencies) // 2],
        "p95_ms": latencies[int(len(latencies) * 0.95)],
        "max_ms": latencies[-1],
    }


def compute_side_bias(trades):
    longs = [t for t in trades if t["side"] == "LONG"]
    shorts = [t for t in trades if t["side"] == "SHORT"]
    long_wr = len([t for t in longs if t["net_pnl"] > 0]) / len(longs) * 100 if longs else 0
    short_wr = len([t for t in shorts if t["net_pnl"] > 0]) / len(shorts) * 100 if shorts else 0
    return {
        "long_count": len(longs),
        "short_count": len(shorts),
        "long_win_rate": long_wr,
        "short_win_rate": short_wr,
        "long_pnl": sum(t["net_pnl"] for t in longs),
        "short_pnl": sum(t["net_pnl"] for t in shorts),
    }


# ─── Reporting ───────────────────────────────────────────────
def _pf_color(pf):
    if pf >= 1.2:
        return GREEN
    elif pf >= 1.0:
        return YELLOW
    return RED


def _wr_color(wr):
    if wr >= 55:
        return GREEN
    elif wr >= 45:
        return YELLOW
    return RED


def print_report(trades, session_id=None, last_n=None):
    label = []
    if session_id:
        label.append(f"session={session_id}")
    if last_n:
        label.append(f"last {last_n} trades")
    label_str = " | ".join(label) if label else "ALL TIME"

    print(header(f"STRATEGY AUDIT — Phase 650 ({label_str})"))

    edge = compute_edge_metrics(trades)
    if not edge:
        print(f"\n{RED}No trades found in the database matching filters.{RESET}\n")
        return 1

    # ── 1. Core Edge Metrics ──────────────────────────────
    print(f"\n{BOLD}[1] EDGE METRICS{RESET}  (Phase 650 Goals: WR > 55%, PF > 1.2)")
    wr_c = _wr_color(edge["win_rate"])
    pf_c = _pf_color(edge["profit_factor"])
    wr_pass = edge["win_rate"] >= 55
    pf_pass = edge["profit_factor"] >= 1.2

    print(f"  Total Trades   : {edge['n']}")
    print(f"  Wins / Losses  : {edge['wins']} / {edge['losses']}")
    print(f"  Win Rate       : {wr_c}{edge['win_rate']:.1f}%{RESET}  {'✅' if wr_pass else '❌'}  (goal: ≥55%)")
    print(f"  Profit Factor  : {pf_c}{edge['profit_factor']:.3f}{RESET}  {'✅' if pf_pass else '❌'}  (goal: ≥1.2)")
    print(f"  Avg Win        : ${edge['avg_win']:+.4f}")
    print(f"  Avg Loss       : ${edge['avg_loss']:+.4f}")
    exp_str = f"${edge['expectancy']:+.4f}"
    pnl_str = f"${edge['total_pnl']:+.4f}"
    print(f"  Expectancy     : {exp_str:>12}  per trade")
    print(f"  Total Net PnL  : {pnl_str:>12}")

    # ── 2. Exit Breakdown (MFE/MAE proxy) ─────────────────
    print(f"\n{BOLD}[2] EXIT BREAKDOWN{RESET}  (MFE/MAE Proxy)")
    exits = compute_exit_breakdown(trades)
    total = edge["n"]
    for reason, data in sorted(exits.items(), key=lambda x: -x[1]["count"]):
        pct = data["count"] / total * 100
        pnl = data["pnl"]
        bar = "█" * int(pct / 3)
        color = GREEN if pnl > 0 else RED
        print(f"  {reason:<25} {data['count']:>4}  ({pct:>5.1f}%)  PnL: {color}${pnl:+.4f}{RESET}  {bar}")

    # ── 3. Early Exit Audit ────────────────────────────────
    print(f"\n{BOLD}[3] EARLY EXIT AUDIT{RESET}  (Shadow SL / Recon leakage)")
    early = compute_early_exit_rate(trades)
    color = RED if early["early_exit_pct"] > 20 else YELLOW if early["early_exit_pct"] > 10 else GREEN
    print(f"  Early exits    : {color}{early['early_exit_count']} ({early['early_exit_pct']:.1f}%){RESET}")
    print(f"  Of those lost  : {early['early_exits_that_lost']}")
    print(f"  PnL from early : ${early['early_exit_pnl']:+.4f}")
    if early["early_exit_pct"] > 20:
        print(warn("  Shadow SL / Recon exits are eating >20% of trades. Review exit thresholds."))

    # ── 4. Long vs Short Bias ─────────────────────────────
    print(f"\n{BOLD}[4] DIRECTIONAL BIAS{RESET}")
    bias = compute_side_bias(trades)
    lwr_c = _wr_color(bias["long_win_rate"])
    swr_c = _wr_color(bias["short_win_rate"])
    print(
        f"  LONG  trades   : {bias['long_count']:>4}  WR: {lwr_c}{bias['long_win_rate']:.1f}%{RESET}  PnL: ${bias['long_pnl']:+.4f}"
    )
    print(
        f"  SHORT trades   : {bias['short_count']:>4}  WR: {swr_c}{bias['short_win_rate']:.1f}%{RESET}  PnL: ${bias['short_pnl']:+.4f}"
    )
    if abs(bias["long_win_rate"] - bias["short_win_rate"]) > 15:
        print(warn("  Large asymmetry between LONG/SHORT WR. Consider direction filter."))

    # ── 5. Per-Symbol Breakdown ───────────────────────────
    print(f"\n{BOLD}[5] PER-SYMBOL STATS{RESET}")
    per_sym = compute_per_symbol(trades)
    for sym, m in sorted(per_sym.items(), key=lambda x: -x[1]["total_pnl"]):
        wr_c2 = _wr_color(m["win_rate"])
        pf_c2 = _pf_color(m["profit_factor"])
        print(
            f"  {sym:<12}  n={m['n']:>4}  "
            f"WR: {wr_c2}{m['win_rate']:.1f}%{RESET}  "
            f"PF: {pf_c2}{m['profit_factor']:.2f}{RESET}  "
            f"PnL: ${m['total_pnl']:+.4f}"
        )

    # ── 6. Latency (T0 signal → T4 fill) ─────────────────
    print(f"\n{BOLD}[6] SIGNAL-TO-FILL LATENCY{RESET}")
    lat = compute_latency_stats(trades)
    if lat:
        color = GREEN if lat["avg_ms"] < 500 else YELLOW if lat["avg_ms"] < 1000 else RED
        print(
            f"  Measured (n={lat['count']})  Avg: {color}{lat['avg_ms']:.0f}ms{RESET}  Median: {lat['median_ms']:.0f}ms  P95: {lat['p95_ms']:.0f}ms  Max: {lat['max_ms']:.0f}ms"
        )
    else:
        print("  No T0/T4 timestamps available in this dataset.")

    # ── 7. VERDICT ────────────────────────────────────────
    print(f"\n{BOLD + '=' * 70}{RESET}")
    if wr_pass and pf_pass:
        print(ok(f"STRATEGY HAS POSITIVE EDGE  —  WR {edge['win_rate']:.1f}% / PF {edge['profit_factor']:.3f}"))
        verdict = 0
    else:
        issues = []
        if not wr_pass:
            issues.append(f"WR {edge['win_rate']:.1f}% < 55%")
        if not pf_pass:
            issues.append(f"PF {edge['profit_factor']:.3f} < 1.2")
        print(fail(f"EDGE NOT YET ACHIEVED  —  {' | '.join(issues)}"))
        print(f"  Keep tuning Phase 650 parameters.")
        verdict = 1
    print(f"{'=' * 70}{RESET}\n")

    return verdict


# ─── CLI ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Phase 650 Strategy Audit")
    parser.add_argument("--db", default="data/historian.db", help="Path to historian SQLite database")
    parser.add_argument("--session", default=None, help="Filter by session_id")
    parser.add_argument("--last", type=int, default=None, help="Analyse only the last N trades")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Wipe the historian DB before analysis (use before running the bot for a clean session)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists() and not args.reset_db:
        print(f"{RED}❌ Database not found: {db_path}{RESET}")
        sys.exit(1)

    if args.reset_db:
        if db_path.exists():
            reset_db(str(db_path))
        else:
            print(f"{YELLOW}⚠️  DB does not exist yet — will be created fresh when the bot runs.{RESET}")
        # Exit after reset — the workflow will run the bot next
        sys.exit(0)

    if not db_path.exists():
        print(f"{RED}❌ Database not found: {db_path}{RESET}")
        sys.exit(1)

    trades = load_trades(str(db_path), session_id=args.session, last_n=args.last)
    verdict = print_report(trades, session_id=args.session, last_n=args.last)
    sys.exit(verdict)


if __name__ == "__main__":
    main()
