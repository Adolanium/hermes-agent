# Reproduce the YAML discovery measurements

Use this branch and a PM-managed development/test environment prepared according
to [CONTRIBUTING.md](../../CONTRIBUTING.md). Run commands from the repository root.
The saved runs use `.venv/Scripts/python.exe` on Windows. Use `.venv/bin/python`
on POSIX.

## Collect paired samples

Run this Python code with that interpreter. Each process loads the baseline
module from Git and alternates it with the current module. It does not replace
working-tree files. Stop tests and other benchmarks during collection.

```python
from pathlib import Path
import subprocess
import sys

folder = Path(".cache/yaml-reproduction")
folder.mkdir(parents=True, exist_ok=True)
for i in (1, 2):
    run = subprocess.run([
        sys.executable, "evals/yaml_discovery/benchmark.py", "--repeat", "7",
    ], capture_output=True, check=True, timeout=300)
    (folder / f"paired-{i}.json").write_bytes(run.stdout)
```

The default baseline is `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`. Use
`--baseline-ref REF` to compare another revision. That Git object must exist
locally. Both versions use the current checkout's unchanged dependencies and
skill-index callers. Each process creates and removes its own synthetic fixtures.

Verify that source and benchmark hashes match across processes and that each
case's output hash matches across versions and processes. Pool the fourteen
`samples_ms` values per version and case, take each median, and calculate
`baseline / optimized`. Also compare each process separately. Ratios below 1
mean a measured slowdown.

To regenerate the comparison and paired bootstrap diagnostics, run:

```powershell
& ./.venv/Scripts/python.exe evals/yaml_discovery/analyze.py .cache/yaml-reproduction
```

Without a directory argument, the analyzer reads the committed samples. It prints
JSON and preserves pairing within each process when resampling. Its 5,000
replicates use seed 20261025 separately for each case.

## Run the behavior checks

On Windows, use Git Bash explicitly. The system `bash.exe` can point to WSL.
This is the PowerShell invocation used against both source versions:

```powershell
$env:HERMES_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
& 'C:/Program Files/Git/bin/bash.exe' scripts/run_tests.sh `
    tests/test_hermes_yaml.py `
    tests/test_hermes_yaml_extensions.py `
    tests/test_load_yaml_file_readonly.py `
    tests/test_utils_atomic_roundtrip_yaml_save.py `
    tests/test_yaml_indent_consistency.py `
    tests/hermes_cli/test_config_yaml_comment_preservation.py `
    tests/agent/test_skill_utils.py `
    tests/hermes_cli/test_atomic_yaml_write.py -q
```

To verify the baseline separately, use an isolated checkout at the baseline
commit and copy the new `test_hermes_yaml_extensions.py` into it. Use the same
PM-managed interpreter and test selection. The baseline result includes the
same existing Windows path-separator failure described in the [report](README.md).

Run the repository checks with isolated state:

```powershell
$env:HERMES_HOME = Join-Path $env:TEMP 'hermes-perf-yaml-home'
$env:HERMES_RUNTIME_DIR = Join-Path $env:TEMP 'hermes-perf-yaml-runtime'
& ./.venv/Scripts/python.exe scripts/check
```
