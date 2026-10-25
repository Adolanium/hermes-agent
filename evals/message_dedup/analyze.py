"""Print pooled timing comparisons and paired bootstrap diagnostics for two runs."""

import argparse
import json
from pathlib import Path
import random
import statistics


def bootstrap_interval(pairs):
    rng = random.Random(20261025)
    ratios = []
    for _ in range(5000):
        baseline, optimized = [], []
        for before, after in pairs:
            indices = rng.choices(range(len(before)), k=len(before))
            baseline.extend(before[i] for i in indices)
            optimized.extend(after[i] for i in indices)
        ratios.append(statistics.median(baseline) / statistics.median(optimized))
    quantiles = statistics.quantiles(ratios, n=40, method="inclusive")
    return [quantiles[0], quantiles[-1]]


def summarize(runs):
    for field in ("benchmark_sha256", "baseline_source_sha256", "optimized_source_sha256",
                  "baseline_ref", "python", "cpu", "os", "differential_verification",
                  "architecture", "repeat"):
        assert runs[0][field] == runs[1][field], field
    results = {}
    for name in runs[0]["results"]:
        cases = [run["results"][name] for run in runs]
        assert len({case[version]["output_sha256"] for case in cases
                    for version in ("baseline", "optimized")}) == 1, name
        samples = {version: [value for case in cases for value in case[version]["samples_ms"]]
                   for version in ("baseline", "optimized")}
        medians = {version: statistics.median(values) for version, values in samples.items()}
        pairs = [(case["baseline"]["samples_ms"], case["optimized"]["samples_ms"]) for case in cases]
        results[name] = {
            "medians_ms": medians,
            "speedup": medians["baseline"] / medians["optimized"],
            "time_change_percent": (medians["optimized"] / medians["baseline"] - 1) * 100,
            "process_speedups": [case["baseline"]["median_ms"] / case["optimized"]["median_ms"] for case in cases],
            "ranges_ms": {version: [min(values), max(values)] for version, values in samples.items()},
            "paired_bootstrap_95_percent": bootstrap_interval(pairs),
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--controls", action="store_true", help="compare longer batches, including the unchanged copy")
    args = parser.parse_args()
    prefix = "controls" if args.controls else "paired"
    files = [f"{prefix}-{i}.json" for i in (1, 2)]
    runs = [json.loads((args.directory / name).read_bytes()) for name in files]
    if args.controls:
        assert runs[0]["confirmation_sha256"] == runs[1]["confirmation_sha256"]
        comparisons = {}
        for version in ("baseline_copy", "optimized"):
            selected = [{"differential_verification": None, **run, "results": {
                name: {"baseline": case["baseline"], "optimized": case[version]}
                for name, case in run["results"].items()}} for run in runs]
            comparisons[version] = summarize(selected)
        print(json.dumps({"runs": files, "comparisons": comparisons}, indent=2))
        return
    print(json.dumps({
        "baseline_ref": runs[0]["baseline_ref"], "runs": files,
        "bootstrap": {"replicates": 5000, "seed_per_case": 20261025,
                      "method": "Resample baseline/optimized batch pairs within each process; ratio of pooled medians."},
        "all_output_hashes_equal": True, "cases": summarize(runs),
    }, indent=2))


if __name__ == "__main__":
    main()
