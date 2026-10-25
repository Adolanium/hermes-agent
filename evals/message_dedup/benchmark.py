"""Offline paired timings and differential traces for gateway message deduplication."""

import argparse
from contextlib import contextmanager, ExitStack
from datetime import UTC, datetime
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import timeit
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@contextmanager
def controlled_clock(module, now):
    previous = module.time
    module.time = SimpleNamespace(time=lambda: now[0])
    try:
        yield
    finally:
        module.time = previous


def fingerprint(cache, duplicate_count, ids):
    return {"duplicates": duplicate_count,
            "retained": [cache.contains(ids[i]) for i in (0, len(ids) // 2, -1)]}


def burst(module, ids, cap, *, timestamps=None, ttl=300):
    cache = module.MessageDeduplicator(max_size=cap, ttl_seconds=ttl)
    if timestamps is None:
        duplicates = sum(cache.is_duplicate(key) for key in ids)
        return fingerprint(cache, duplicates, ids)
    now = [0.0]
    with controlled_clock(module, now):
        duplicates = 0
        for key, timestamp in zip(ids, timestamps):
            now[0] = timestamp
            duplicates += cache.is_duplicate(key)
        return fingerprint(cache, duplicates, ids)


def handoff(module, ids):
    with controlled_clock(module, [100.0]):
        predecessor = module.MessageDeduplicator(max_size=len(ids))
        for key in ids:
            assert predecessor.is_duplicate(key) is False
        replacement = module.MessageDeduplicator(max_size=2000)
        replacement.absorb(predecessor)
        assert replacement.is_duplicate("handoff-new") is False
        return fingerprint(replacement, 0, ids)


def cases():
    ids = [f"generated-{i:04d}" for i in range(4000)]
    return {
        "below_capacity_100": partial(burst, ids=ids[:100], cap=2000),
        "duplicate_hits_2000": partial(burst, ids=ids[:2000] * 2, cap=2000),
        "fresh_2000_cap1000": partial(burst, ids=ids[:2000], cap=1000),
        "fresh_4000_cap2000": partial(burst, ids=ids, cap=2000),
        "fresh_200_cap10": partial(burst, ids=ids[:200], cap=10),
        "tied_4000_cap2000": partial(burst, ids=ids, cap=2000, timestamps=[100.0] * 4000),
        "rollback_4000_cap2000": partial(
            burst, ids=ids, cap=2000,
            timestamps=[100.0 + i // 32 - (20 if i % 64 == 0 else 0) for i in range(4000)]),
        "expiry_4000_cap2000": partial(burst, ids=ids, cap=2000, timestamps=list(range(4000)), ttl=1000),
        "handoff_4000_cap2000": partial(handoff, ids=ids),
    }


def verify_traces(variants):
    """Compare public results after replay, expiry, rollback, release, clear, and handoff."""
    rng = random.Random(20261025)
    ids = [f"trace-{i}" for i in range(30)]
    steps = 0
    for cap in (-1, 0, 1, 3, 20):
        for ttl in (0, 5, float("inf")):
            now = [100.0]
            with ExitStack() as stack:
                caches = {}
                for label, module in variants.items():
                    stack.enter_context(controlled_clock(module, now))
                    caches[label] = [module.MessageDeduplicator(max_size=cap, ttl_seconds=ttl) for _ in range(2)]
                for _ in range(300):
                    now[0] += rng.choice((-2, 0, 0, 1, 5))
                    action = rng.choice(("is_duplicate",) * 6 + ("contains", "discard", "clear", "absorb"))
                    index, key = rng.randrange(2), rng.choice(ids)
                    results = []
                    for pair in caches.values():
                        cache = pair[index]
                        if action == "absorb":
                            result = cache.absorb(pair[1 - index])
                        elif action == "clear":
                            result = cache.clear()
                        else:
                            result = getattr(cache, action)(key)
                        results.append((result, [[item.contains(key) for key in ids] for item in pair]))
                    assert results[0] == results[1], (cap, ttl, steps, action, key)
                    steps += 1
    return {"seed": 20261025, "traces": 15, "steps": steps, "public_results_equal": True}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def measure(procedure, variants, repeat):
    results, timers = {}, {}
    for label, module in variants.items():
        call = partial(procedure, module)
        output = call()
        assert call() == output
        timers[label] = timeit.Timer(call)
        number, _ = timers[label].autorange()
        results[label] = {"output_sha256": digest(output), "calls_per_sample": number, "samples_ms": []}
    assert results["baseline"]["output_sha256"] == results["optimized"]["output_sha256"]
    for round_number in range(repeat):
        order = ("baseline", "optimized") if round_number % 2 == 0 else ("optimized", "baseline")
        for label in order:
            number = results[label]["calls_per_sample"]
            results[label]["samples_ms"].append(timers[label].timeit(number=number) * 1000 / number)
    for label, result in results.items():
        assert digest(procedure(variants[label])) == result["output_sha256"]
        result["median_ms"] = statistics.median(result["samples_ms"])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--baseline-ref", default="4ea8d23cc9f527332ccb1d55359b27741b6ea51b")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-dedup-bench-") as directory:
        os.environ["HERMES_HOME"] = directory
        os.environ["HERMES_RUNTIME_DIR"] = str(Path(directory) / "runtime")
        from gateway.platforms import helpers
        from hermes_platform.host.facts import cpu_model, native_arch, os_family

        source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:gateway/platforms/helpers.py"], cwd=ROOT, timeout=30)
        baseline = ModuleType("baseline_helpers")
        exec(compile(source, "<baseline_helpers>", "exec"), baseline.__dict__)
        variants = {"baseline": baseline, "optimized": helpers}
        metadata = {
            "started_utc": datetime.now(UTC).isoformat(), "python": sys.version,
            "cpu": cpu_model(), "os": os_family(), "architecture": native_arch(), "repeat": args.repeat,
            "baseline_ref": args.baseline_ref,
            "baseline_source_sha256": hashlib.sha256(source).hexdigest(),
            "optimized_source_sha256": hashlib.sha256((ROOT / "gateway/platforms/helpers.py").read_bytes()).hexdigest(),
            "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "differential_verification": verify_traces(variants),
        }
        results = {name: measure(procedure, variants, args.repeat) for name, procedure in cases().items()}
    print(json.dumps({**metadata, "results": results}, indent=2))


if __name__ == "__main__":
    main()
