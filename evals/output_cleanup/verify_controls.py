"""Compare cleanup controls within one process to check process-to-process noise."""

from datetime import UTC, datetime
from functools import partial
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import timeit
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BASELINE = "4ea8d23cc9f527332ccb1d55359b27741b6ea51b"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main():
    from tools import ansi_strip as optimized

    baseline_source = subprocess.check_output(["git", "show", f"{BASELINE}:tools/ansi_strip.py"], timeout=30)
    baseline = ModuleType("baseline_ansi_strip")
    exec(compile(baseline_source, "<baseline_ansi_strip>", "exec"), baseline.__dict__)

    def resized(unit, size):
        return (unit * (size // len(unit) + 1))[:size]

    plain = resized("Generated build output line 0123456789\n", 16384)
    flag = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    cases = [
        ("ansi_colored_1048576", "strip_ansi", resized("\x1b[32mGenerated output\x1b[0m\n", 1048576)),
        ("tags_orphan_16384", "strip_unicode_tags", plain + "\U000e0041\U000e0042"),
        ("tags_flag_16384", "strip_unicode_tags", plain + flag),
        ("display_ascii_16384", "sanitize_display_text", plain),
    ]
    results = {}
    for name, function, text in cases:
        procedures = {label: partial(getattr(module, function), text)
                      for label, module in (("baseline", baseline), ("optimized", optimized))}
        output = procedures["baseline"]()
        assert procedures["optimized"]() == output
        timers = {label: timeit.Timer(procedure) for label, procedure in procedures.items()}
        counts = {label: timer.autorange()[0] for label, timer in timers.items()}
        samples = {"baseline": [], "optimized": []}
        for _ in range(5):
            for label in ("baseline", "optimized", "optimized", "baseline"):
                samples[label].append(timers[label].timeit(number=counts[label]) * 1000 / counts[label])
        results[name] = {
            "input_sha256": digest(text), "output_sha256": digest(output),
            "calls_per_sample": counts, "samples_ms": samples,
            "medians_ms": {label: statistics.median(values) for label, values in samples.items()},
        }
    print(json.dumps({
        "python": sys.version, "finished_utc": datetime.now(UTC).isoformat(),
        "baseline_commit": BASELINE,
        "baseline_source_sha256": hashlib.sha256(baseline_source).hexdigest(),
        "optimized_source_sha256": hashlib.sha256(Path(optimized.__file__).read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "batch_order": ["baseline", "optimized", "optimized", "baseline"] * 5,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
