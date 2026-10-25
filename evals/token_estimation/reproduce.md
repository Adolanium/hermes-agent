# Reproduce the token-estimation measurements

Use a disposable checkout at
`29c3c2edf16eee907786437dfcd004a35da71f68`, with both measured commits available in
its Git history. Prepare a test interpreter through PM as described in
[CONTRIBUTING.md](../../CONTRIBUTING.md#manual-development-and-test-environment).
Use that same interpreter for all four runs. The recorded run used CPython 3.14.9.

The code below temporarily replaces `agent/model_metadata.py`. Run it only in
the disposable checkout. It restores the file in `finally`, including when a
benchmark exits unsuccessfully. Stop other test and lint commands before starting.

From the disposable checkout's root, run this Python code with the prepared
interpreter. It uses the benchmark from the optimized commit for both versions.
It writes new receipts under the ignored `.cache/token-estimation-rerun`
directory and leaves the archived results untouched.

```python
import json
from pathlib import Path
import statistics
import subprocess
import sys

baseline_ref = "4ea8d23cc9f527332ccb1d55359b27741b6ea51b"
optimized_ref = "29c3c2edf16eee907786437dfcd004a35da71f68"
source = Path("agent/model_metadata.py")
benchmark = Path("evals/benchmark_token_estimation.py")
original = source.read_bytes()
versions = {
	label: subprocess.check_output(["git", "show", f"{ref}:{source.as_posix()}"])
	for label, ref in (("before", baseline_ref), ("after", optimized_ref))
}
expected_benchmark = subprocess.check_output(
	["git", "show", f"{optimized_ref}:{benchmark.as_posix()}"]
)
assert benchmark.read_text(encoding="utf-8") == expected_benchmark.decode("utf-8")
output = Path(".cache/token-estimation-rerun")
output.mkdir(parents=True, exist_ok=False)
receipts = {"before": [], "after": []}

try:
	for label, run in (("before", 1), ("after", 1), ("after", 2), ("before", 2)):
		source.write_bytes(versions[label])
		path = output / f"token-{label}-{run}.json"
		with path.open("wb") as stream:
			subprocess.run(
				[sys.executable, str(benchmark), "--repeat", "7"],
				stdout=stream, check=True, timeout=120,
			)
		receipts[label].append(json.loads(path.read_text(encoding="utf-8")))
finally:
	source.write_bytes(original)

comparison = {}
for name in receipts["before"][0]["results"]:
	rows = [receipt["results"][name] for runs in receipts.values() for receipt in runs]
	assert len({row["tokens"] for row in rows}) == 1, name
	medians = {
		label: statistics.median([
			sample
			for receipt in runs
			for sample in receipt["results"][name]["samples_ms"]
		])
		for label, runs in receipts.items()
	}
	comparison[name] = {
		"tokens": rows[0]["tokens"],
		"before_ms": medians["before"],
		"after_ms": medians["after"],
		"speedup": medians["before"] / medians["after"],
	}
(output / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
print(json.dumps(comparison, indent=2))
```

Compare token totals as well as timing medians. Inspect all samples for host noise.
Keep every sample, and report results from both versions even when a case gets
slower. Do not treat sub-percent changes as established improvements or regressions
from this sample size.

## Verify the archived aggregates

Run this code from a checkout containing this report. It reads the original
receipts, checks their sample counts and token totals, and recalculates every
aggregate in `token-comparison.json`. It does not rerun the benchmark.

```python
import json
from pathlib import Path
import statistics

folder = Path("evals/token_estimation/results")
aggregate = json.loads((folder / "token-comparison.json").read_text(encoding="utf-8"))
runs = {
	side: [
		json.loads((folder / f"token-{side}-{run}.json").read_text(encoding="utf-8"))
		for run in (1, 2)
	]
	for side in ("before", "after")
}
for name, expected in aggregate["results"].items():
	for side, receipts in runs.items():
		rows = [receipt["results"][name] for receipt in receipts]
		assert all(len(row["samples_ms"]) == 7 for row in rows)
		assert all(row["tokens"] == expected["tokens"] for row in rows)
		assert all(statistics.median(row["samples_ms"]) == row["median_ms"] for row in rows)
		samples = [sample for row in rows for sample in row["samples_ms"]]
		assert statistics.median(samples) == expected[f"{side}_ms"]
	assert expected["speedup"] == expected["before_ms"] / expected["after_ms"]
print("All archived medians, ratios, sample counts, and token totals match.")
```

## Run the targeted tests

Set `HERMES_PYTHON` to the absolute path of the prepared test interpreter. Use
Git Bash on Windows. Run the canonical runner from the repository root:

```bash
scripts/run_tests.sh \
	tests/agent/test_cjk_token_estimation.py \
	tests/agent/test_token_estimation_runs.py \
	tests/agent/test_token_estimator_shared.py \
	tests/agent/test_replay_budget_accounting.py \
	tests/agent/test_compressor_image_tokens.py \
	tests/agent/test_model_metadata.py \
	tests/agent/test_context_compressor.py -q
```

At the optimized commit, this ran 451 test cases: six new cases and 445 existing
cases. Run the repository checks with the same interpreter:

```bash
"$HERMES_PYTHON" scripts/check
```
