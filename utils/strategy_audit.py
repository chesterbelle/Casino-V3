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
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

# ─── ANSI colours ───────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ─── Exit Reason Categories ───────────────────────────────────
DRAIN_EXIT_REASONS = {"DRAIN_DEFENSIVE_ESCALATION", "DRAIN_PANIC", "DRAIN_AGGRESSIVE_ESCALATION"}
ACTIVE_EXIT_REASONS = {"SHADOW_SL", "TP_SL_HIT", "TRADE_CONFIRMED", "SL_HIT", "TP_HIT"}


def ok(msg):
    return f"{GREEN}✅ {msg}{RESET}"


def fail(msg):
    return f"{RED}❌ {msg}{RESET}"


def warn(msg):
    return f"{YELLOW}⚠️  {msg}{RESET}"


def header(msg):
    line = "=" * 70
    return f"\n{BOLD}{CYAN}{line}\n  {msg}\n{line}{RESET}"


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _iter_log_files(log_glob: str) -> list[Path]:
    matches = sorted(Path(".").glob(log_glob))
    return [p for p in matches if p.is_file()]


def audit_strategy_logs(log_glob: str) -> int:
    """Option 2: Audit by parsing logs (no DB schema dependency).

    This is intentionally conservative and only relies on stable log signatures.
    """

    log_files = _iter_log_files(log_glob)
    if not log_files:
        print(f"{RED}❌ No log files match: {log_glob}{RESET}")
        return 1

    print(header(f"STRATEGY LOG AUDIT — Setup Segmentation (glob={log_glob})"))

    rx_fast_track = re.compile(
        r"✅ Fast-track confirmed: .*?\(setup_type=(?P<setup>[^,\)]+), "
        r"level_ok=(?P<level_ok>True|False), micro_ok=(?P<micro_ok>True|False), "
        r"level_ref=(?P<level_ref>[^\)]+)\)"
    )

    regressions = {
        "missing_price_metadata": 0,
        "traceback": 0,
        "critical": 0,
        "error": 0,
        "exception": 0,
    }

    by_setup = defaultdict(
        lambda: {"count": 0, "level_ok": 0, "micro_ok": 0, "both_ok": 0, "level_ref": defaultdict(int)}
    )

    for fp in log_files:
        try:
            content = fp.read_text(errors="replace")
        except Exception as e:
            print(f"{RED}❌ Failed to read {fp}: {e}{RESET}")
            return 1

        regressions["missing_price_metadata"] += content.count("missing price metadata for level confirmation")
        regressions["traceback"] += content.count("Traceback (most recent call last)")
        regressions["critical"] += len(re.findall(r"\bCRITICAL\b", content))
        regressions["error"] += len(re.findall(r"\bERROR\b", content))
        regressions["exception"] += len(re.findall(r"\bException\b", content))

        for m in rx_fast_track.finditer(content):
            setup = (m.group("setup") or "unknown").strip()
            level_ok = m.group("level_ok") == "True"
            micro_ok = m.group("micro_ok") == "True"
            level_ref = (m.group("level_ref") or "None").strip()

            rec = by_setup[setup]
            rec["count"] += 1
            if level_ok:
                rec["level_ok"] += 1
            if micro_ok:
                rec["micro_ok"] += 1
            if level_ok and micro_ok:
                rec["both_ok"] += 1
            rec["level_ref"][level_ref] += 1

    total_fast_track = sum(v["count"] for v in by_setup.values())
    print(f"\n{BOLD}[A] FAST-TRACK SETUP BREAKDOWN (from logs){RESET}")
    print(f"  Log files scanned : {len(log_files)}")
    print(f"  Fast-track confirms: {total_fast_track}")

    if total_fast_track == 0:
        print(
            warn(
                "No '✅ Fast-track confirmed' lines found. Ensure the bot run produced signals and logs include fast-track confirmations."
            )
        )
    else:
        for setup, rec in sorted(by_setup.items(), key=lambda x: -x[1]["count"]):
            n = rec["count"]
            lvl = rec["level_ok"]
            mic = rec["micro_ok"]
            both = rec["both_ok"]
            print(f"\n  setup_type={setup}")
            print(f"    n={n}")
            print(f"    confirm_level : {lvl} ({(lvl / n * 100):.1f}%)")
            print(f"    confirm_micro : {mic} ({(mic / n * 100):.1f}%)")
            print(f"    both          : {both} ({(both / n * 100):.1f}%)")

            lr = rec["level_ref"]
            if lr:
                top = sorted(lr.items(), key=lambda kv: -kv[1])[:8]
                top_str = ", ".join([f"{k}:{v}" for k, v in top])
                print(f"    level_ref(top): {top_str}")

    print(f"\n{BOLD}[B] REGRESSION SCAN (execution + telemetry){RESET}")
    print(f"  missing price metadata: {regressions['missing_price_metadata']}")
    print(f"  tracebacks            : {regressions['traceback']}")
    print(f"  CRITICAL lines        : {regressions['critical']}")
    print(f"  ERROR lines           : {regressions['error']}")
    print(f"  Exception tokens      : {regressions['exception']}")

    if regressions["missing_price_metadata"] > 0:
        print(fail("Regression detected: missing price metadata for level confirmation"))
        return 1
    if regressions["traceback"] > 0:
        print(fail("Regression detected: Python traceback"))
        return 1

    print(ok("Log audit PASS (no critical regressions detected by signature scan)"))
    return 0


# ─── DB helpers ─────────────────────────────────────────────
def get_latest_session(db_path: str) -> Optional[str]:
    """Phase 750: Detect the most recent session in the database."""
    if not Path(db_path).exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        res = conn.execute("SELECT session_id FROM trades ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None


def load_trades(db_path: str, session_id: str = None, last_n: int = None, all_time: bool = False):
    """
    Loads trades from historian.db.

    Phase 750: Defaults to the latest session if session_id and all_time are both None.
    """
    if not session_id and not all_time and not last_n:
        session_id = get_latest_session(db_path)
        if session_id:
            print(f"{CYAN}ℹ️  Latest session detected: {BOLD}{session_id}{RESET} (use --all-time to see everything)")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base = """
        SELECT trade_id, symbol, side, entry_price, exit_price,
               qty, fee, gross_pnl, net_pnl, exit_reason,
               timestamp, bars_held, session_id, healed,
               t0_signal_ts, t4_fill_ts, slippage_pct,
               setup_type, level_ref, level_price
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


def categorize_trades(trades: list) -> tuple[list, list]:
    """Separate active strategy trades from drain phase trades.

    Drain phase trades are forced exits due to timeout/shutdown and don't
    represent the strategy's true performance.

    Returns: (active_trades, drain_trades)
    """
    active = [t for t in trades if t["exit_reason"] not in DRAIN_EXIT_REASONS]
    drain = [t for t in trades if t["exit_reason"] in DRAIN_EXIT_REASONS]
    return active, drain


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


def parse_setup_type_from_logs(log_glob: str) -> tuple[dict, dict]:
    """Parse logs to extract setup_type per trade decision.

    Returns dict mapping approximate timestamp -> setup_type
    """
    log_files = _iter_log_files(log_glob)
    if not log_files:
        return {}, {}

    # Pattern: 🎯 Decision: ... | Setup: reversion | TP: ...
    rx_decision = re.compile(r"🎯 Decision: (LONG|SHORT).*?Setup: (\w+).*?TP: ([\d.]+)")

    setup_by_side = defaultdict(lambda: defaultdict(int))
    setups = defaultdict(list)

    for fp in log_files:
        try:
            content = fp.read_text(errors="replace")
        except Exception:
            continue

        for m in rx_decision.finditer(content):
            side = m.group(1)
            setup_type = m.group(2)
            setup_by_side[side][setup_type] += 1
            # Store for later correlation
            setups[setup_type].append({"side": side})

    return setups, setup_by_side


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

    # Separate active strategy trades from drain phase trades
    active_trades, drain_trades = categorize_trades(trades)

    # ── 0. Trade Classification Summary ─────────────────────
    print(f"\n{BOLD}[0] TRADE CLASSIFICATION{RESET}")
    print(f"  Total Trades       : {len(trades)}")
    print(f"  Active Strategy    : {len(active_trades)} trades")
    print(f"  Drain Phase        : {len(drain_trades)} trades (excluded from edge metrics)")

    if drain_trades:
        drain_pnl = sum(t["net_pnl"] for t in drain_trades)
        drain_wins = len([t for t in drain_trades if t["net_pnl"] > 0])
        drain_color = GREEN if drain_pnl >= 0 else RED
        print(
            f"  Drain Phase PnL    : {drain_color}${drain_pnl:+.4f}{RESET} (WR: {drain_wins}/{len(drain_trades)} = {drain_wins/len(drain_trades)*100:.1f}%)"
        )

    # Use active trades for all strategy metrics
    edge = compute_edge_metrics(active_trades)
    if not edge:
        print(f"\n{RED}No active strategy trades found in the database matching filters.{RESET}\n")
        return 1

    # ── 1. Core Edge Metrics (Active Strategy Only) ──────────────────────────────
    print(f"\n{BOLD}[1] EDGE METRICS{RESET}  (Active Strategy Only | Phase 650 Goals: WR > 55%, PF > 1.2)")

    # NEW: Segmented Metrics by setup_type
    by_setup = defaultdict(list)
    for t in active_trades:
        by_setup[t.get("setup_type", "unknown")].append(t)

    for stype, st_trades in sorted(by_setup.items()):
        st_edge = compute_edge_metrics(st_trades)
        if not st_edge:
            continue

        # Per-setup goals
        if stype == "reversion":
            g_wr, g_pf = 55, 1.2
        elif stype == "continuation":
            g_wr, g_pf = 52, 1.1
        else:
            g_wr, g_pf = 55, 1.2

        wr_c = _wr_color(st_edge["win_rate"])
        pf_c = _pf_color(st_edge["profit_factor"])
        wr_pass = st_edge["win_rate"] >= g_wr
        pf_pass = st_edge["profit_factor"] >= g_pf

        print(f"\n  {BOLD}setup_type={stype}{RESET} (n={st_edge['n']})")
        print(
            f"    Win Rate       : {wr_c}{st_edge['win_rate']:.1f}%{RESET}  {'✅' if wr_pass else '❌'}  (goal: ≥{g_wr}%)"
        )
        print(
            f"    Profit Factor  : {pf_c}{st_edge['profit_factor']:.3f}{RESET}  {'✅' if pf_pass else '❌'}  (goal: ≥{g_pf})"
        )
        print(f"    PnL            : ${st_edge['total_pnl']:+.4f}")

    print(f"\n  {BOLD}OVERALL METRICS{RESET}")
    wr_c = _wr_color(edge["win_rate"])
    pf_c = _pf_color(edge["profit_factor"])
    wr_pass = edge["win_rate"] >= 55
    pf_pass = edge["profit_factor"] >= 1.2

    print(f"  Active Trades  : {edge['n']}")
    print(f"  Wins / Losses  : {edge['wins']} / {edge['losses']}")
    print(f"  Win Rate       : {wr_c}{edge['win_rate']:.1f}%{RESET}  {'✅' if wr_pass else '❌'}  (goal: ≥55%)")
    print(f"  Profit Factor  : {pf_c}{edge['profit_factor']:.3f}{RESET}  {'✅' if pf_pass else '❌'}  (goal: ≥1.2)")
    print(f"  Avg Win        : ${edge['avg_win']:+.4f}")
    print(f"  Avg Loss       : ${edge['avg_loss']:+.4f}")
    exp_str = f"${edge['expectancy']:+.4f}"
    pnl_str = f"${edge['total_pnl']:+.4f}"
    print(f"  Expectancy     : {exp_str:>12}  per trade")
    print(f"  Active PnL     : {pnl_str:>12}")

    # Show total including drain
    if drain_trades:
        total_pnl = edge["total_pnl"] + sum(t["net_pnl"] for t in drain_trades)
        print(f"  Total PnL (all): ${total_pnl:+.4f} (includes drain phase)")

    # ── 2. Exit Breakdown (MFE/MAE proxy) ─────────────────
    print(f"\n{BOLD}[2] EXIT BREAKDOWN{RESET}  (Active Strategy | MFE/MAE Proxy)")
    exits = compute_exit_breakdown(active_trades)
    total = edge["n"]
    for reason, data in sorted(exits.items(), key=lambda x: -x[1]["count"]):
        pct = data["count"] / total * 100
        pnl = data["pnl"]
        bar = "█" * int(pct / 3)
        color = GREEN if pnl > 0 else RED
        print(f"  {reason:<25} {data['count']:>4}  ({pct:>5.1f}%)  PnL: {color}${pnl:+.4f}{RESET}  {bar}")

    # ── 3. Early Exit Audit ────────────────────────────────
    print(f"\n{BOLD}[3] EARLY EXIT AUDIT{RESET}  (Shadow SL / Recon leakage)")
    early = compute_early_exit_rate(active_trades)
    color = RED if early["early_exit_pct"] > 20 else YELLOW if early["early_exit_pct"] > 10 else GREEN
    print(f"  Early exits    : {color}{early['early_exit_count']} ({early['early_exit_pct']:.1f}%){RESET}")
    print(f"  Of those lost  : {early['early_exits_that_lost']}")
    print(f"  PnL from early : ${early['early_exit_pnl']:+.4f}")
    if early["early_exit_pct"] > 20:
        print(warn("  Shadow SL / Recon exits are eating >20% of trades. Review exit thresholds."))

    # ── 4. Long vs Short Bias ─────────────────────────────
    print(f"\n{BOLD}[4] DIRECTIONAL BIAS{RESET}")
    bias = compute_side_bias(active_trades)
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
    print(f"\n{BOLD}[5] PER-SYMBOL STATS{RESET}  (Active Strategy)")
    per_sym = compute_per_symbol(active_trades)
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
    lat = compute_latency_stats(active_trades)
    if lat:
        color = GREEN if lat["avg_ms"] < 500 else YELLOW if lat["avg_ms"] < 1000 else RED
        print(
            f"  Measured (n={lat['count']})  Avg: {color}{lat['avg_ms']:.0f}ms{RESET}  Median: {lat['median_ms']:.0f}ms  P95: {lat['p95_ms']:.0f}ms  Max: {lat['max_ms']:.0f}ms"
        )
    else:
        print("  No T0/T4 timestamps available in this dataset.")

    # ── 7. Setup Type Segmentation (from logs) ────────────
    print(f"\n{BOLD}[7] SETUP TYPE SEGMENTATION{RESET}  (from logs)")

    # Try to find the most recent audit log
    log_glob = "logs/strategy_audit_*.log"
    setups, setup_by_side = parse_setup_type_from_logs(log_glob)

    if not setups:
        print("  No setup_type data found in logs.")
        print("  Run with --log flag for detailed setup analysis.")
    else:
        total_decisions = sum(len(v) for v in setups.values())
        print(f"  Total decisions found: {total_decisions}")

        for setup_type, decisions in sorted(setups.items(), key=lambda x: -len(x[1])):
            n = len(decisions)
            pct = n / total_decisions * 100 if total_decisions > 0 else 0

            # Count by side
            longs = sum(1 for d in decisions if d["side"] == "LONG")
            shorts = sum(1 for d in decisions if d["side"] == "SHORT")

            # Goals per setup_type
            if setup_type == "reversion":
                goal_wr = 55
                goal_pf = 1.2
            elif setup_type == "continuation":
                goal_wr = 52
                goal_pf = 1.1
            else:
                goal_wr = 55
                goal_pf = 1.2

            print(f"\n  setup_type={setup_type}")
            print(f"    Decisions: {n} ({pct:.1f}%)")
            print(f"    LONG: {longs} | SHORT: {shorts}")
            print(f"    Goals: WR ≥{goal_wr}% | PF ≥{goal_pf}")

            # Note: We can't correlate exact PnL without DB column
            # This is a limitation - need setup_type in trades table
            if n < 20:
                print(f"    {YELLOW}⚠️  INSUFFICIENT DATA (n<20){RESET}")

    # ── 8. VERDICT ────────────────────────────────────────
    print(f"\n{BOLD + '=' * 70}{RESET}")

    # Check setup-specific goals if we have data
    setup_pass = True
    if active_trades:
        by_setup = defaultdict(list)
        for t in active_trades:
            by_setup[t.get("setup_type", "unknown")].append(t)

        for setup_type, st_trades in sorted(by_setup.items()):
            if len(st_trades) >= 20:
                st_edge = compute_edge_metrics(st_trades)
                if not st_edge:
                    continue

                if setup_type == "reversion":
                    g_wr, g_pf = 55, 1.2
                elif setup_type == "continuation":
                    g_wr, g_pf = 52, 1.1
                else:
                    g_wr, g_pf = 55, 1.2

                wr_pass = st_edge["win_rate"] >= g_wr
                pf_pass = st_edge["profit_factor"] >= g_pf

                status = ok("PASS") if (wr_pass and pf_pass) else fail("FAIL")
                print(
                    f"  setup_type={setup_type}: {status} (WR: {st_edge['win_rate']:.1f}% vs {g_wr}%, PF: {st_edge['profit_factor']:.3f} vs {g_pf})"
                )
                if not (wr_pass and pf_pass):
                    setup_pass = False

    if wr_pass and pf_pass and setup_pass:
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
    parser.add_argument(
        "--all-time", action="store_true", help="Analyze all trades in the DB (default: latest session)"
    )
    parser.add_argument("--last", type=int, default=None, help="Analyse only the last N trades")
    parser.add_argument(
        "--log",
        default=None,
        help=(
            "Option 2: parse logs for setup segmentation + regression scan. "
            "Example: --log 'logs/strategy_audit_*.log' or --log 'bot.log'"
        ),
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Wipe the historian DB before analysis (use before running the bot for a clean session)",
    )
    args = parser.parse_args()

    if args.log:
        sys.exit(audit_strategy_logs(args.log))

    db_path = Path(args.db)
    if not db_path.exists() and not args.reset_db:
        print(f"{RED}❌ Database not found: {db_path}{RESET}")
        sys.exit(1)

    if args.reset_db:
        if db_path.exists():
            reset_db(str(db_path))
        else:
            print(f"{YELLOW}⚠️  DB does not exist yet — will be created fresh when the bot runs.{RESET}")

        # Also truncate audit_trail.jsonl and human.log for a truly clean session
        audit_trail = Path("logs/audit_trail.jsonl")
        human_log = Path("human.log")
        for logfile in [audit_trail, human_log]:
            if logfile.exists():
                logfile.write_text("")
                print(f"🗑️ Truncated {logfile}")

        # Exit after reset — the workflow will run the bot next
        sys.exit(0)

    if not db_path.exists():
        print(f"{RED}❌ Database not found: {db_path}{RESET}")
        sys.exit(1)

    trades = load_trades(str(db_path), session_id=args.session, last_n=args.last, all_time=args.all_time)
    verdict = print_report(
        trades, session_id=args.session or (None if args.all_time else "auto:latest"), last_n=args.last
    )
    sys.exit(verdict)


if __name__ == "__main__":
    main()
