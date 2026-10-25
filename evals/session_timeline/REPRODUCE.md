# Reproduce the timeline measurements

Use this branch and a PM-managed development/test environment prepared according
to [CONTRIBUTING.md](../../CONTRIBUTING.md). Run commands from the repository root.
The saved runs use `.venv/Scripts/python.exe` on Windows. Use `.venv/bin/python`
on POSIX.

## Collect paired samples

Run this Python code with that interpreter. Each process loads the baseline
module from Git and alternates its timeline function with the current function.
It does not replace working-tree files. Keep tests and other benchmarks stopped
during collection.

```python
from pathlib import Path
import subprocess
import sys

folder = Path(".cache/timeline-reproduction")
folder.mkdir(parents=True, exist_ok=True)
for i in (1, 2):
	run = subprocess.run([
		sys.executable, "evals/session_timeline/benchmark.py", "--repeat", "7",
	], capture_output=True, check=True, timeout=240)
	(folder / f"paired-{i}.json").write_bytes(run.stdout)
```

The default baseline is `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`. Use
`--baseline-ref REF` to compare another revision. The benchmark needs that Git
object and uses the current checkout's unchanged dependencies for both versions.

Verify that source hashes and benchmark hashes match across processes, and that
each case has the same output hash across both versions and processes. Pool the
14 `samples_ms` values per version and case, take each median, and calculate
`baseline / optimized`. Also compare each process separately. Ratios below 1
mean a measured slowdown.

To regenerate the comparison and paired bootstrap diagnostics, run:

```powershell
& ./.venv/Scripts/python.exe evals/session_timeline/analyze.py .cache/timeline-reproduction
```

The analyzer prints JSON and preserves pairing within each process when it
resamples. Its 5,000 replicates use seed 20261025 separately for each case.

## Run the behavior checks

On Windows, use Git Bash explicitly. The system `bash.exe` can point to WSL.
This is the PowerShell invocation used against both source versions:

```powershell
$env:HERMES_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
& 'C:/Program Files/Git/bin/bash.exe' scripts/run_tests.sh `
	tests/hermes_cli/test_session_timeline.py `
	tests/hermes_state/test_timeline_empty_page.py `
	tests/hermes_state/test_get_messages_around.py `
	tests/hermes_state/test_display_projection_parity.py `
	tests/hermes_state/test_display_read_removed_rows.py `
	tests/hermes_state/test_display_split_heal.py -q
```

Run `python scripts/check` with the same interpreter and isolated `HERMES_HOME`
and `HERMES_RUNTIME_DIR` paths.
