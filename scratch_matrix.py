import collections
import sqlite3

conn = sqlite3.connect("data/historian.db")
signals = conn.execute("SELECT timestamp, symbol, side, price, setup_type FROM signals ORDER BY timestamp").fetchall()

windows = [3600, 7200, 14400]
targets = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]

# setup_signals[window][setup_type][sym] = [traj, traj...]
setup_signals = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))

for window in windows:
    for ts, sym, side, price, setup_type in signals:
        ps = conn.execute(
            "SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (sym, ts, ts + window),
        ).fetchall()
        if not ps:
            continue
        trajectory = []
        for (p,) in ps:
            m = (p - price) / price * 100
            if side == "SHORT":
                m = -m
            trajectory.append(m)
        setup_signals[window][setup_type][sym].append(trajectory)

for window in windows:
    print(f'\n{"=" * 90}')
    print(f"  WINDOW: {window}s ({window//3600}h)")
    print(f'{"=" * 90}')

    # Sort setup types
    for setup_type in sorted(setup_signals[window].keys()):
        # skip if total signals for this setup < 5
        total_setup_n = sum(len(trajs) for trajs in setup_signals[window][setup_type].values())
        if total_setup_n < 2:
            continue

        print(f"\n  🔹 SETUP: {setup_type} 🔹")
        for sym in sorted(setup_signals[window][setup_type].keys()):
            n = len(setup_signals[window][setup_type][sym])
            if n < 3:
                continue  # skip extremely low N pairs
            print(f"\n  【 {sym} 】 (n={n})")
            print(f'  {"Target":>8}  {"WR%":>6}  {"W":>3}  {"L":>3}  {"TO":>4}  {"TO%":>5}  {"Net Taker%":>12}')
            print(f'  {"-" * 60}')
            for tgt in targets:
                wins = losses = timeouts = 0
                for traj in setup_signals[window][setup_type][sym]:
                    hit_tp = hit_sl = False
                    for m in traj:
                        if not hit_tp and m >= tgt:
                            hit_tp = True
                        if not hit_sl and m <= -tgt:
                            hit_sl = True
                    if hit_tp and not hit_sl:
                        wins += 1
                    elif hit_sl:
                        losses += 1
                    else:
                        timeouts += 1
                resolved = wins + losses
                wr = wins / resolved * 100 if resolved > 0 else 0
                to_pct = timeouts / n * 100
                gross_exp = ((wins * tgt) - (losses * tgt)) / n if n > 0 else 0
                net_taker = gross_exp - 0.12
                marker = " ✅" if net_taker > 0 else ""
                print(
                    f"  {tgt:>7.1f}%  {wr:>5.1f}%  {wins:>3}  {losses:>3}  {timeouts:>4}  {to_pct:>4.0f}%  {net_taker:>11.4f}%{marker}"
                )
