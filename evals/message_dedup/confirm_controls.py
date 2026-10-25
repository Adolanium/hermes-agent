"""Longer batches with an unchanged-copy control for the two uncertain workloads."""

import argparse
from datetime import UTC, datetime
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import timeit
from types import ModuleType

import benchmark


def collect(procedure, variants, number, repeat):
    timers, results = {}, {}
    for label, module in variants.items():
        call = partial(procedure, module)
        output = call()
        assert call() == output
        timers[label] = timeit.Timer(call)
        results[label] = {"output_sha256": benchmark.digest(output), "calls_per_sample": number, "samples_ms": []}
        timers[label].timeit(number=number)
    assert len({value["output_sha256"] for value in results.values()}) == 1
    orders = (
        ("baseline", "baseline_copy", "optimized"),
        ("baseline_copy", "optimized", "baseline"),
        ("optimized", "baseline", "baseline_copy"),
    )
    for i in range(repeat):
        for label in orders[i % len(orders)]:
            results[label]["samples_ms"].append(timers[label].timeit(number=number) * 1000 / number)
    for result in results.values():
        result["median_ms"] = statistics.median(result["samples_ms"])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=9)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-dedup-controls-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(Path(directory) / "runtime")
        from gateway.platforms import helpers
        from hermes_platform.host.facts import cpu_model, native_arch, os_family

        ref = "4ea8d23cc9f527332ccb1d55359b27741b6ea51b"
        source = subprocess.check_output(["git", "show", f"{ref}:gateway/platforms/helpers.py"], cwd=benchmark.ROOT, timeout=30)
        variants = {}
        for label in ("baseline", "baseline_copy"):
            module = ModuleType(label)
            exec(compile(source, f"<{label}>", "exec"), module.__dict__)
            variants[label] = module
        variants["optimized"] = helpers
        metadata = {
            "started_utc": datetime.now(UTC).isoformat(), "python": sys.version,
            "cpu": cpu_model(), "os": os_family(), "architecture": native_arch(), "repeat": args.repeat,
            "baseline_ref": ref, "baseline_source_sha256": hashlib.sha256(source).hexdigest(),
            "optimized_source_sha256": hashlib.sha256((benchmark.ROOT / "gateway/platforms/helpers.py").read_bytes()).hexdigest(),
            "benchmark_sha256": hashlib.sha256(Path(benchmark.__file__).read_bytes()).hexdigest(),
            "confirmation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        workloads = benchmark.cases()
        results = {name: collect(workloads[name], variants, number, args.repeat)
                   for name, number in (("below_capacity_100", 40000), ("handoff_4000_cap2000", 500))}
    print(json.dumps({**metadata, "results": results}, indent=2))


if __name__ == "__main__":
    main()
