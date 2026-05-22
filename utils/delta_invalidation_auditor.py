#!/usr/bin/env python3
"""
Delta Invalidation Auditor — offline analysis on audit historian.db.

Correlates micro_z trajectories with price MFE to calibrate SlimExit Pilar 4:
when would delta_z invalidation fire vs first +1% touch and giveback.
"""

import argparse
import json
import sqlite3
import statistics
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

DEFAULT_THRESHOLDS = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
DEFAULT_ARM_AFTER = [0.0, 0.5, 0.8, 1.0]
ABSORPTION_SETUPS = {"TacticalAbsorptionV2", "absorption_reversal"}


def load_signals(conn: sqlite3.Connection, setups: Optional[set]) -> list:
    rows = conn.execute(
        "SELECT timestamp, symbol, side, price, setup_type, metadata FROM signals ORDER BY timestamp"
    ).fetchall()
    out = []
    for ts, sym, side, price, setup_type, meta in rows:
        if setups and setup_type not in setups:
            continue
        try:
            meta_d = json.loads(meta) if meta else {}
        except (json.JSONDecodeError, TypeError):
            meta_d = {}
        z_entry = meta_d.get("z_score_entry")
        if z_entry is None:
            continue
        horizon = meta_d.get("max_holding_time") or 14400
        out.append(
            {
                "ts": ts,
                "sym": sym,
                "side": side,
                "price": price,
                "setup": setup_type,
                "z_entry": float(z_entry),
                "horizon": int(horizon),
            }
        )
    return out


def load_samples(
    conn: sqlite3.Connection, sym: str, start: float, end: float
) -> List[Tuple[float, float, Optional[float]]]:
    rows = conn.execute(
        """
        SELECT timestamp, price, micro_z FROM price_samples
        WHERE symbol=? AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
        """,
        (sym, start, end),
    ).fetchall()
    return [(t, p, z) for t, p, z in rows]


def favorable_pct(side: str, entry: float, price: float) -> float:
    m = (price - entry) / entry * 100.0
    return -m if side == "SHORT" else m


def di_triggered(side: str, delta_z: float, thresh: float) -> bool:
    if side == "LONG":
        return delta_z > thresh
    return delta_z < -thresh


def analyze_signal(
    conn: sqlite3.Connection,
    sig: dict,
    thresholds: List[float],
) -> Optional[dict]:
    samples = load_samples(conn, sig["sym"], sig["ts"], sig["ts"] + sig["horizon"])
    if len(samples) < 2:
        return None

    series = []
    for t, p, z in samples:
        if z is None:
            continue
        mfe = favorable_pct(sig["side"], sig["price"], p)
        dz = z - sig["z_entry"]
        series.append((t - sig["ts"], mfe, dz))

    if not series:
        return None

    peak_mfe = max(m for _, m, _ in series)
    t_first_10 = next((e for e, m, _ in series if m >= 1.0), None)
    t_first_08 = next((e for e, m, _ in series if m >= 0.8), None)
    t_peak = next(e for e, m, _ in series if m == peak_mfe)

    t_giveback = None
    post_peak = [(e, m) for e, m, _ in series if e >= t_peak]
    if post_peak:
        peak_val = max(m for _, m in post_peak)
        for e, m in post_peak:
            if m <= peak_val - 0.25:
                t_giveback = e
                break

    di_times = {}
    for th in thresholds:
        hits = [e for e, _, dz in series if di_triggered(sig["side"], dz, th)]
        di_times[th] = hits[0] if hits else None

    return {
        "sym": sig["sym"],
        "side": sig["side"],
        "setup": sig["setup"],
        "peak_mfe": peak_mfe,
        "t_first_08": t_first_08,
        "t_first_10": t_first_10,
        "t_giveback": t_giveback,
        "di_times": di_times,
        "series": series,
    }


def summarize_di(rows: List[dict], thresholds: List[float], arm_after: float) -> dict:
    eligible = []
    for r in rows:
        if arm_after > 0:
            if r["peak_mfe"] < arm_after:
                continue
        eligible.append(r)

    n = len(eligible)
    if n == 0:
        return {"n": 0}

    out = {"n": n, "thresh": {}}
    for th in thresholds:
        before_1 = after_1 = never = 0
        deltas_after = []
        for r in eligible:
            t_di = r["di_times"].get(th)
            t10 = r["t_first_10"]
            if t_di is None:
                never += 1
            elif t10 is None:
                if t_di is not None:
                    after_1 += 1
            elif t_di < t10:
                before_1 += 1
            else:
                after_1 += 1
                deltas_after.append(t_di - t10)

        out["thresh"][th] = {
            "before_1pct": 100.0 * before_1 / n,
            "after_1pct": 100.0 * after_1 / n,
            "never": 100.0 * never / n,
            "med_di_minus_1pct_sec": statistics.median(deltas_after) if deltas_after else None,
        }
    return out


def giveback_concordance(rows: List[dict], thresh: float) -> dict:
    pairs = 0
    within_60 = 0
    for r in rows:
        t_di = r["di_times"].get(thresh)
        t_gb = r["t_giveback"]
        if t_di is None or t_gb is None:
            continue
        pairs += 1
        if abs(t_di - t_gb) <= 60:
            within_60 += 1
    return {
        "pairs": pairs,
        "within_60s_pct": 100.0 * within_60 / pairs if pairs else 0.0,
    }


def print_report(rows: List[dict], thresholds: List[float], arm_levels: List[float], certified: set):
    print("=" * 72)
    print("  DELTA INVALIDATION AUDITOR")
    print("=" * 72)
    print(f"Signals analyzed (with z_entry + micro_z): {len(rows)}")
    print()

    print("[1] DI ALWAYS ARMED (from entry) — % of signals")
    print(f"{'thresh':>8}  {'before +1%':>12}  {'after +1%':>12}  {'never DI':>10}  {'med lag s':>10}")
    print("-" * 60)
    s0 = summarize_di(rows, thresholds, arm_after=0.0)
    for th in thresholds:
        t = s0["thresh"][th]
        med = t["med_di_minus_1pct_sec"]
        med_s = f"{med:.0f}" if med is not None else "n/a"
        print(
            f"{th:>8.1f}  {t['before_1pct']:>11.1f}%  {t['after_1pct']:>11.1f}%  " f"{t['never']:>9.1f}%  {med_s:>10}"
        )
    print()

    print("[2] DI ARMED ONLY AFTER MFE >= arm_after%")
    for arm in arm_levels:
        if arm == 0:
            continue
        print(f"\n  --- arm_after MFE >= {arm}% ---")
        print(f"{'thresh':>8}  {'before +1%':>12}  {'after +1%':>12}  {'never DI':>10}")
        sa = summarize_di(rows, thresholds, arm_after=arm)
        print(f"  (n={sa['n']})")
        for th in thresholds:
            t = sa["thresh"][th]
            print(f"{th:>8.1f}  {t['before_1pct']:>11.1f}%  {t['after_1pct']:>11.1f}%  {t['never']:>9.1f}%")
    print()

    print("[3] DI vs price giveback (0.25% from peak) — thresh=5.0")
    gc = giveback_concordance(rows, 5.0)
    print(f"  Pairs with both DI and giveback: {gc['pairs']}")
    print(f"  DI within 60s of giveback:       {gc['within_60s_pct']:.1f}%")
    print()

    if certified:
        print("[4] Certified symbols only:", ", ".join(sorted(certified)))
        sub = [r for r in rows if r["sym"] in certified]
        s0 = summarize_di(sub, thresholds, arm_after=0.0)
        print(f"  n={s0['n']}")
        for th in [4.5, 5.0, 5.5]:
            if th in s0["thresh"]:
                t = s0["thresh"][th]
                print(f"    thresh {th}: before+1%={t['before_1pct']:.1f}%  after+1%={t['after_1pct']:.1f}%")
    print()
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="Delta invalidation trajectory audit")
    parser.add_argument("--db", default="data/historian.db")
    parser.add_argument("--window", type=int, default=None, help="Override horizon seconds")
    parser.add_argument("--thresholds", default=",".join(str(x) for x in DEFAULT_THRESHOLDS))
    parser.add_argument("--arm-after", default=",".join(str(x) for x in DEFAULT_ARM_AFTER))
    parser.add_argument("--all-setups", action="store_true", help="Include non-absorption setups")
    parser.add_argument(
        "--certified",
        default="BNBUSDT,SOLUSDT,SUIUSDT,AVAXUSDT",
        help="Comma-separated symbols for section 4",
    )
    args = parser.parse_args()

    thresholds = [float(x) for x in args.thresholds.split(",")]
    arm_levels = [float(x) for x in args.arm_after.split(",")]
    certified = {s.strip() for s in args.certified.split(",") if s.strip()}
    setups = None if args.all_setups else ABSORPTION_SETUPS

    conn = sqlite3.connect(args.db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "price_samples" not in tables:
        print("ERROR: price_samples table missing. Run generalized-edge-audit first.")
        return 1
    has_z = conn.execute("SELECT COUNT(*) FROM price_samples WHERE micro_z IS NOT NULL").fetchone()[0]
    total_ps = conn.execute("SELECT COUNT(*) FROM price_samples").fetchone()[0]
    if total_ps and has_z == 0:
        print("ERROR: price_samples exist but micro_z is empty. Re-run audit with commit 4ffa07b+.")
        return 1

    signals = load_signals(conn, setups)
    if args.window:
        for s in signals:
            s["horizon"] = args.window

    rows = []
    for sig in signals:
        r = analyze_signal(conn, sig, thresholds)
        if r:
            rows.append(r)

    print_report(rows, thresholds, arm_levels, certified)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
