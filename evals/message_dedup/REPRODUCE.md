# Reproduce the message deduplication measurements

Run these commands from the repository root on this branch. Prepare the
PM-managed Python 3.14 interpreter described in [CONTRIBUTING.md](../../CONTRIBUTING.md).
Use Git Bash explicitly on Windows; the system `bash.exe` can point to WSL.

## Build the test environment outside the checkout

The selected Mattermost tests need `aiohttp`. The declared `sms` extra supplies
that pinned dependency. Build a disposable environment with PM:

```powershell
$taskDirectory = Join-Path $env:TEMP ('hermes-dedup-' + [guid]::NewGuid().ToString('N'))
$env:HERMES_HOME = Join-Path $taskDirectory 'home'
$env:HERMES_RUNTIME_DIR = Join-Path $taskDirectory 'runtime'
& ./.venv/Scripts/python.exe -m pm.build_env --source . `
    --out (Join-Path $taskDirectory 'venv') --group dev --group test --extra sms
$env:HERMES_PYTHON = Join-Path $taskDirectory 'venv/Scripts/python.exe'
```

On POSIX, use the corresponding `venv/bin/python` paths. Keep dependency builds
outside the checkout because the repository's archive check also scans scratch
directories.

## Collect paired samples

Run this Python code with that interpreter. Stop tests, dependency builds, and
other benchmarks during collection. Each process compares both implementations
without replacing working-tree files.

```python
from pathlib import Path
import subprocess
import sys

folder = Path(".cache/dedup-reproduction")
folder.mkdir(parents=True, exist_ok=True)
for i in (1, 2):
    run = subprocess.run([
        sys.executable, "evals/message_dedup/benchmark.py", "--repeat", "7",
    ], capture_output=True, check=True, timeout=300)
    (folder / f"paired-{i}.json").write_bytes(run.stdout)
```

The default baseline is `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`. That Git object
must exist locally. `--baseline-ref REF` selects another revision. Both versions
use the same dependencies in the current checkout. The benchmark isolates
`HERMES_HOME` and `HERMES_RUNTIME_DIR` in a temporary directory and removes it on
exit. It first compares 4,500 seeded operations through the public cache methods,
then collects timings for all nine workloads.

Regenerate the summary with:

```powershell
& $env:HERMES_PYTHON evals/message_dedup/analyze.py .cache/dedup-reproduction
```

Without a directory argument, the analyzer reads the committed samples. It
checks matching metadata and output hashes, pools fourteen samples per version
and workload, and prints medians, ranges, per-process ratios, and bootstrap
diagnostics. Speedup is `baseline / optimized`; values below 1 mean a measured
slowdown. The bootstrap uses 5,000 replicates and seed 20261025 per workload.

Pass `evals/message_dedup/exploration` to the analyzer to regenerate the first
candidate's comparison. Those receipts use implementation
`fbe0eccafa3684c31348c6dc2afaacb0acc14e59`; the final receipts use
`635e00822cec3def2c431869365869cb542fd670`. Both use the same benchmark source.

The original screening source is archived as `exploration/screen_gateway.py.txt`.
To rerun that exploratory screen, copy it to `.cache/series-5/screen_gateway.py`
in an isolated checkout at the baseline revision and run it with the test
interpreter. It writes the screen's samples and profiles into that scratch
directory. Its instrumented profile times are separate from the paired timings.

## Confirm the uncertain controls

The longer confirmation uses the same workload functions and adds a second
unchanged baseline module. It rotates the three execution positions evenly over
nine rounds. Batches use 40,000 below-capacity invocations or 500 handoffs,
about one second each on the measured host.

Run this Python code with the test interpreter:

```python
from pathlib import Path
import subprocess
import sys

folder = Path(".cache/dedup-reproduction")
folder.mkdir(parents=True, exist_ok=True)
for i in (1, 2):
    run = subprocess.run([
        sys.executable, "evals/message_dedup/confirm_controls.py", "--repeat", "9",
    ], capture_output=True, check=True, timeout=180)
    (folder / f"controls-{i}.json").write_bytes(run.stdout)
```

Regenerate both comparisons with:

```powershell
& $env:HERMES_PYTHON evals/message_dedup/analyze.py --controls .cache/dedup-reproduction
```

## Run the behavior checks

The same eight-file selection was run before and after the change:

```powershell
& 'C:/Program Files/Git/bin/bash.exe' scripts/run_tests.sh `
    tests/gateway/test_message_deduplicator.py `
    tests/gateway/test_message_deduplicator_eviction.py `
    tests/gateway/test_shared_adapter_utils.py `
    tests/gateway/test_slack_dedup_ttl.py `
    tests/gateway/test_platform_reconnect.py `
    tests/gateway/test_multiplex_adapter_registry.py `
    tests/gateway/test_discord_double_dispatch.py `
    tests/gateway/test_mattermost.py -q
```

For the baseline, use an isolated checkout at the baseline commit and copy the
new `test_message_deduplicator_eviction.py` into it. Run the same selection with
the same PM-managed interpreter.

Run the repository checks with the isolated home and runtime paths set above:

```powershell
& $env:HERMES_PYTHON scripts/check
```
