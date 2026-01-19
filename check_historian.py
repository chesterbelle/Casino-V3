import logging

from core.observability.historian import TradeHistorian

logging.basicConfig(level=logging.INFO)


def check():
    h = TradeHistorian()

    print("\n=== GLOBAL STATS ===")
    stats = h.get_session_stats()
    for k, v in stats.items():
        print(f"{k}: {v}")

    print("\n=== ERROR BREAKDOWN ===")
    errors = h.get_error_breakdown()
    for reason, count in errors.items():
        print(f"{reason}: {count}")

    print("\n=== RECENT SESSION STATS (SCALABILITY_TEST_20260119) ===")
    session_stats = h.get_session_stats(session_id="SCALABILITY_TEST_20260119")
    for k, v in session_stats.items():
        print(f"{k}: {v}")

    session_errors = h.get_error_breakdown(session_id="SCALABILITY_TEST_20260119")
    print("\n=== SESSION ERROR BREAKDOWN ===")
    for reason, count in session_errors.items():
        print(f"{reason}: {count}")


if __name__ == "__main__":
    check()
