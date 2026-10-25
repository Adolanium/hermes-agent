# Reproduce the output-cleanup measurements

Use a clean checkout of this branch and a PM-managed development/test environment
as described in [CONTRIBUTING.md](../../CONTRIBUTING.md). The saved run used
`.venv/Scripts/python.exe` on Windows. Use `.venv/bin/python` on POSIX.

## Collect four runs

Run the following Python code from the repository root with that interpreter.
It temporarily replaces only `tools/ansi_strip.py` and restores its original bytes
in `finally`. Keep other tests and benchmarks stopped during collection.

```python
import json
from pathlib import Path
import subprocess
import sys

source = Path("tools/ansi_strip.py")
optimized = source.read_bytes()
baseline = subprocess.check_output([
	"git", "show", "4ea8d23cc9f527332ccb1d55359b27741b6ea51b:tools/ansi_strip.py",
], timeout=30)
destination = Path(".cache/output-cleanup-reproduction")
destination.mkdir(parents=True, exist_ok=True)
try:
	for name, content in [
		("baseline-1", baseline), ("optimized-1", optimized),
		("optimized-2", optimized), ("baseline-2", baseline),
	]:
		source.write_bytes(content)
		run = subprocess.run([
			sys.executable, "evals/benchmark_output_cleanup.py", "--repeat", "7",
		], capture_output=True, check=True, timeout=180)
		assert len(json.loads(run.stdout)["results"]) == 17
		(destination / (name + ".json")).write_bytes(run.stdout)
finally:
	source.write_bytes(optimized)
```

Compare matching cases in all four JSON files. Verify equal `benchmark_sha256`,
`input_sha256`, and `output_sha256` values before comparing timings.
Pool the 14 `samples_ms` values for each version, take their median, and divide
the baseline median by the optimized median. A ratio below 1 means slower.
Also compare each process pair separately to check repeatability.

## Check the controls within each process

The independent-process runs showed variation on dense ANSI text and Unicode-tag
controls. Run the supplemental probe four times to alternate both source versions
within each process, using the same four fixtures:

```python
from pathlib import Path
import subprocess
import sys

destination = Path(".cache/output-cleanup-reproduction")
destination.mkdir(parents=True, exist_ok=True)
for i in range(1, 5):
	run = subprocess.run([
		sys.executable, "evals/output_cleanup/verify_controls.py",
	], capture_output=True, check=True, timeout=180)
	(destination / f"controls-{i}.json").write_bytes(run.stdout)
```

Compare the input and output hashes with the primary benchmark. Each probe saves
ten calibrated batch means per version and case, in the recorded batch order.
Report each process separately as well as the medians pooled across all processes.
The archive includes two runs before and two after adding the Git timeout, as
described in the report. Their timed code and fixtures are identical.

## Run the behavior checks

Use Git Bash on Windows. The system `bash.exe` can point to WSL.
The exact PowerShell invocation used for both source versions was:

```powershell
$env:HERMES_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
& 'C:/Program Files/Git/bin/bash.exe' scripts/run_tests.sh `
	tests/tools/test_ansi_strip.py `
	tests/tools/test_unicode_tag_strip.py `
	tests/tools/test_output_cleanup_ascii.py `
	tests/tools/test_mcp_resource_content.py `
	tests/tools/test_code_execution.py `
	tests/tools/test_code_kernel.py `
	tests/tools/test_read_extract.py `
	tests/tools/test_approval.py -q
```

Run `python scripts/check` with the same PM-managed interpreter and isolated
`HERMES_HOME` and `HERMES_RUNTIME_DIR` paths.
