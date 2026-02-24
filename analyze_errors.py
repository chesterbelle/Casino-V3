import collections
import re

tracebacks = collections.defaultdict(int)
errors = collections.defaultdict(int)

in_traceback = False
current_traceback = []

with open("bot.log", "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if "Traceback (most recent call last):" in line:
            in_traceback = True
            current_traceback = [line]
            continue

        if in_traceback:
            current_traceback.append(line)
            if not line.startswith(" ") and ":" in line and not line.startswith("File"):
                # End of traceback (usually the Exception name)
                tb_str = "\n".join(current_traceback)
                # Keep only the last few lines of the traceback for uniqueness
                sig = "\n".join(current_traceback[-3:])
                tracebacks[sig] += 1
                in_traceback = False
                current_traceback = []
        elif " ERROR " in line or " CRITICAL " in line or "Exception" in line:
            # Extract the actual error message after the log level
            parts = re.split(r" (ERROR|CRITICAL) \| ", line, maxsplit=1)
            if len(parts) > 1:
                msg = parts[-1].strip()
                # Remove dynamic parts like IDs or timestamps if possible, just keep it simple for now
                msg = re.sub(r"\d+", "X", msg)
                errors[msg] += 1

with open("error_analysis_report.txt", "w") as out:
    out.write("==== UNIQUE TRACEBACKS ====\n")
    for tb, count in sorted(tracebacks.items(), key=lambda x: x[1], reverse=True):
        out.write(f"Count: {count}\n{tb}\n{'-'*40}\n")

    out.write("\n==== TOP 50 UNIQUE ERRORS ====\n")
    for err, count in sorted(errors.items(), key=lambda x: x[1], reverse=True)[:50]:
        out.write(f"Count: {count} | {err}\n")
