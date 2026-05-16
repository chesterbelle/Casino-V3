import re
from collections import Counter

counts = Counter()
errors = Counter()
try:
    with open("test.log", "r") as f:
        for line in f:
            if "Signal Detected:" in line:
                match = re.search(r"Signal Detected: ([^@]+)", line)
                if match:
                    counts[match.group(1)] += 1
            elif "Error" in line and ("Worker" in line or "sensor" in line.lower()):
                errors[line] += 1

    print("--- SENSOR SIGNAL COUNTS ---")
    if not counts:
        print("No signals found.")
    for sensor, count in counts.most_common():
        print(f"{sensor}: {count}")

    print("\n--- SENSOR ERRORS ---")
    if not errors:
        print("No errors detected.")
    else:
        for err, count in errors.most_common(5):
            print(f"{count}x: {err.strip()}")

except Exception as e:
    print(e)
