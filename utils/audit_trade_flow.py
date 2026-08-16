"""
Trade Flow Auditor (Phase 260)
Reads historian.db to determine Execution Hygiene based on the trades table
(source of truth for exit_reason) + lifecycle events (supplementary telemetry).

The trades table records each closed trade with its exit_reason. Any exit that
is NOT a clean exit reason (and not healed) is an execution failure that
contaminates Error Recovery (e.g. EXTERNAL_CLOSE) -> VERDICT FAIL.
"""

import argparse
import os
import sqlite3
import sys

# Mirror of CLEAN_EXIT_REASONS in core/observability/historian.py.
# Trades with an exit_reason NOT in this set (e.g. EXTERNAL_CLOSE) are
# execution failures that contaminate Error Recovery -> VERDICT FAIL.
CLEAN_EXIT_REASONS = {
    "TP",
    "SL",
    "MANUAL",
    "TIMEOUT",
    "TIME_EXIT",
    "TP_SL_HIT",
    "TP (Recon)",
    "SL (Recon)",
    "TP (ACCOUNT_UPDATE)",
    "SL (ACCOUNT_UPDATE)",
    "ORPHAN_RECOVERY",
    "NOT_FILLED",
    "DRAIN_PANIC",
    "DRAIN_AGGRESSIVE",
    "DRAIN_OPTIMISTIC_ESCALATION",
    "DRAIN_DEFENSIVE_ESCALATION",
    "DRAIN_AGGRESSIVE_ESCALATION",
    "DRAIN_PANIC_ESCALATION",
    "AUDIT_GHOST_REMOVAL",
    "AUDIT_RECON_FORCE",
    "LIQUIDATION",
    "SHADOW_SL",
    "BREAKEVEN",
    "TRAILING_STOP",
    "COMMISSION",
    "FUNDING_FEE",
    "INSURANCE_CLEAR",
    "ADJUSTMENT",
}

# Exit reasons that represent pure accounting rows (fees/funding), not trades.
NON_TRADE_EXIT_REASONS = {"COMMISSION", "FUNDING_FEE", "INSURANCE_CLEAR", "ADJUSTMENT"}


def _latest_session(cursor) -> str:
    """Auto-detect the most recent run: the session_id with the newest trade."""
    cursor.execute(
        "SELECT session_id FROM trades WHERE session_id IS NOT NULL "
        "AND session_id != '' ORDER BY timestamp DESC LIMIT 1"
    )
    row = cursor.fetchone()
    return row[0] if row else None


def audit_trade_flow(db_path: str, session: str = None):
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        return False

    print(f"\n🔍 Auditing Trade Flow: {db_path}")
    print("=" * 50)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Determine which run to audit. Default = most recent session.
        if not session:
            session = _latest_session(cursor)
            if session:
                print(f"ℹ️  Auto-detect session: {session}")

        # Fetch lifecycle events (supplementary telemetry per client_order_id)
        cursor.execute(
            "SELECT trade_id, timestamp, event_type, details FROM trade_lifecycle_events ORDER BY timestamp ASC"
        )
        events = cursor.fetchall()

        # Fetch trades for the audited session. Real trades have a parent id.
        if session:
            cursor.execute(
                "SELECT trade_id, parent_trade_id, symbol, exit_reason, healed, net_pnl "
                "FROM trades WHERE session_id = ? AND parent_trade_id IS NOT NULL",
                (session,),
            )
        else:
            cursor.execute(
                "SELECT trade_id, parent_trade_id, symbol, exit_reason, healed, net_pnl "
                "FROM trades WHERE parent_trade_id IS NOT NULL"
            )
        trades = cursor.fetchall()

        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

    total = len(trades)
    if total == 0:
        print("⚠️ No trades found for the audited session.")
        return True

    clean = 0
    healed = 0
    force_closed = 0

    force_closed_ids = []

    for t in trades:
        reason = t["exit_reason"]
        is_healed = bool(t["healed"])

        if reason in NON_TRADE_EXIT_REASONS:
            # Accounting-only rows (fees/funding) are not trades.
            continue
        if is_healed:
            healed += 1
        elif reason in CLEAN_EXIT_REASONS:
            clean += 1
        else:
            # exit_reason NOT in clean set + not healed = poor execution
            # (e.g. EXTERNAL_CLOSE, SAFETY_CLOSE, OCO_ABORT, ERROR, ...)
            force_closed += 1
            force_closed_ids.append(t["trade_id"])

    evaluated = clean + healed + force_closed
    if evaluated == 0:
        print("⚠️ No real trades (only accounting rows) found for the audited session.")
        return True

    print(f"ℹ️  Events registrados: {len(events)}")
    print(f"ℹ️  Session auditada: {session or 'ALL'}")
    print(f"📊 TRADE FLOW HYGIENE AUDIT")
    print(f"Total Trades Evaluados: {evaluated}")
    print("-" * 50)
    print(f"🟢 Clean Executions:   {clean:4d}  ({(clean/evaluated)*100:.1f}%)")
    print(f"🟡 Recon Healed:       {healed:4d}  ({(healed/evaluated)*100:.1f}%)")
    print(f"🔴 Force Closed (Poor Execution): {force_closed:4d}  ({(force_closed/evaluated)*100:.1f}%)")

    print("=" * 50)

    if force_closed > 0:
        print("❌ VERDICT: FAIL")
        print("   ↳ Se detectaron trades con ejecución pobre (exit no limpio):")
        for tid in force_closed_ids[:5]:
            print(f"      - {tid}")
        if len(force_closed_ids) > 5:
            print(f"      - ... y {len(force_closed_ids) - 5} más.")
        return False
    else:
        print("✅ VERDICT: PASS (Ejecución Higiénica 100%)")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audits trade lifecycle events to measure execution hygiene.")
    parser.add_argument("--db", type=str, default="data/historian.db", help="Path to historian.db")
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID a auditar (default: auto-detecta la más reciente)",
    )
    args = parser.parse_args()

    success = audit_trade_flow(args.db, session=args.session)
    sys.exit(0 if success else 1)
