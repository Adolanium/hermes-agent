# YAML extension discovery performance

Each fresh ruamel YAML parser scans its package directory for installed YAML
extensions. Rebuilding a 500-skill index creates 500 parsers and repeats that scan
500 times. Caching the discovered extension paths reduces the measured rebuild
from 474.79 ms to 384.57 ms, about 19% less time. Small YAML loads take about 60%
less time on the measured host.

The change keeps an immutable tuple of installed extension paths in
`hermes_yaml._Yaml`. Every operation still creates its own parser or emitter,
and extension initialization still runs for each instance. Discovery returns a
fresh list so callers cannot mutate the stored tuple. YAML policy, the native
parser's pure-Python fallback, and round-trip formatting remain unchanged.

## Sources and environment

- Baseline: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`.
- Implementation, benchmark, and behavior test: `8b7118e30675b18bcf45e123ff594c2bf92a9d7a`.
- Independent branch from local `main`, without the earlier performance changes.
- Host: Windows amd64, Intel Core i7-10700K, CPython 3.14.9.
- Dependency: ruamel.yaml 0.18.16, with its C parser available.
- Collection date: 2026-10-25 UTC.
- Environment: PM-managed `.venv` with development and test dependency groups.

## Baseline and diagnosis

Initial screening measured about 467 ms to rebuild an index of 500 synthetic
skills. Profiling showed that each frontmatter parse created a YAML instance,
which called `official_plug_ins()` and globbed installed package directories.
Passing an empty `plug_ins` list does not skip that discovery in ruamel 0.18.16.

A separate [diagnostic profile](results/profile.txt) compares one warmed
500-skill rebuild per version using the final benchmark's fixtures and callable.
The baseline performs 500 discovery scans, taking 123 ms of 724 ms under the
profiler. The optimized version performs no discovery scans after warmup.
Both versions parse all 500 skill files and return the same prompt. Profiling
adds overhead; these times are excluded from the performance comparison below.

## Measurement method

[benchmark.py](benchmark.py) creates synthetic data in temporary `HERMES_HOME`
and `HERMES_RUNTIME_DIR` directories. It also uses a temporary working directory
to exclude project-local skills, restoring the working directory before cleanup.
It makes no network calls and does not read a live user's configuration.

Small documents contain a name, a boolean, and a two-item sequence. Large
documents contain 1,000 mappings. Separate cases cover byte input, an explicit
pure-Python parser, a document rejected by the C parser but accepted by the pure
parser, invalid input, dumps, and a complete comment-preserving load/edit/dump.

The real `build_skills_system_prompt()` runs against 100 or 500 generated skills
spread across ten categories. Each file has YAML frontmatter and 100 body lines,
about 5 KB total. Rebuilds clear both the in-memory prompt cache and disk snapshot
inside the timed call, under the owning home scope. Filesystem scanning, parsing,
prompt construction, and snapshot writing are included. The warm 500-skill case
retains both caches and measures the existing cached path, including its file
signature checks.

Each process loads the baseline `hermes_yaml.py` from Git and imports the current
version. Both use the same dependencies, fixture files, and unchanged callers.
The skill loader selects each version outside the timer and restores its original
function afterward. Other cases call the selected YAML module directly.

Two untimed calls verify repeatability and warm discovery. `timeit.autorange()`
calibrates each version independently to at least 200 ms per batch. Seven rounds
alternate baseline/optimized and optimized/baseline order. Each saved sample is
elapsed batch time divided by its call count, in milliseconds. `timeit` disables
garbage collection during each batch. Imports, fixture creation, calibration,
hashing, and profiling are excluded from the saved timing samples.

Two fresh processes repeat all twelve cases. Tests and lint jobs do not overlap
collection. Each version contributes fourteen batch means per case. The table
uses the median of those pooled samples and `baseline / optimized` for speedup.
A ratio below 1 means a measured slowdown. Process ratios use each process's own
medians; the pooled ratio need not lie between them.

## Results

| Case | Baseline ms | Optimized ms | Speedup | Process 1 / process 2 |
| --- | ---: | ---: | ---: | ---: |
| `load_small` | 0.3689 | 0.1462 | 2.523x | 2.511x / 2.525x |
| `load_small_bytes` | 0.3665 | 0.1470 | 2.493x | 2.534x / 2.477x |
| `load_small_pure` | 0.6166 | 0.3903 | 1.580x | 1.585x / 1.570x |
| `load_large` | 53.6836 | 53.8720 | 0.997x | 0.915x / 1.034x |
| `load_pure_fallback` | 0.6708 | 0.2607 | 2.573x | 2.580x / 2.537x |
| `reject_invalid` | 0.7272 | 0.2990 | 2.432x | 2.451x / 2.380x |
| `dump_small` | 0.5595 | 0.3357 | 1.667x | 1.653x / 1.674x |
| `dump_large` | 200.6253 | 201.2030 | 0.997x | 0.994x / 0.998x |
| `roundtrip_edit` | 1.1913 | 0.9586 | 1.243x | 1.198x / 1.255x |
| `skills_rebuild_100` | 99.8551 | 79.8829 | 1.250x | 1.286x / 1.250x |
| `skills_rebuild_500` | 474.7910 | 384.5679 | 1.235x | 1.276x / 1.323x |
| `skills_warm_500` | 68.2359 | 68.4189 | 0.997x | 0.987x / 0.991x |

The setup-sensitive gains repeat in both processes. Small loads improve by
2.51x and 2.53x, while 500-skill rebuilds improve by 1.28x and 1.32x. A complete
round-trip edit uses about 20% less time in the pooled samples.

The large-load, large-dump, and warm-index controls have pooled times 0.35%,
0.29%, and 0.27% higher, respectively. Those are measured slowdowns, not wins.
The large-load direction reverses between processes. The other two controls
are slightly slower in both processes, but the stored samples cannot distinguish
these small differences from run variation. No speedup is claimed for these
controls, and these measurements cannot rule out small regressions.

[analyze.py](analyze.py) resamples paired baseline/optimized batch means within
each process 5,000 times, with replacement and seed 20261025 for each case.
Each replicate computes the ratio of pooled medians. The saved interval uses
the 2.5th and 97.5th percentiles. Small-load and 500-skill-rebuild intervals are
2.48-2.54x and 1.17-1.29x. All three control intervals include 1. These diagnostics
describe the stored samples; time correlation and only two processes limit
inference. They do not establish equivalence.

All twelve output hashes match across both versions and both processes. The
hashes cover parsed data, exact dump text, round-trip output, rejection details,
and generated prompts.

## Scope and limits

The cache contains installed ruamel extension paths only. User data, Hermes
plugins, skills, parsed documents, and mutable parser state are not cached here.
Extension settings are still applied during each parser's initialization.
Changing the installed ruamel extension set requires restarting the process.
Concurrent initial calls can each discover extensions before the tuple is set.

Warmup performs the first discovery; its cost is not removed or included in the
speedup claim. Skill rebuilds reparse files, but the operating system's file cache
is warm. No CPU affinity or frequency controls were imposed. Samples are batch
means, not individual request latencies. Other hosts, dependency builds, document
sizes, and extension installations can produce different results.

## Behavior checks

The same eight-file selection gives **57 passed, 1 failed, and 2 skipped** on
both versions through `scripts/run_tests.sh`. One passing case is new; 56 passing
cases already existed. The new test loads a tagged value through an installed
extension and then changes its settings. The next load must use the new settings,
which verifies that extension initialization still runs for each fresh parser.

Existing coverage includes YAML 1.1 booleans, byte and stream input, duplicate
keys, merge keys, object-construction rejection, Unicode, comments and quotes,
concurrent operations, and recovery after parse errors. The unchanged failure is
`test_skill_config_home_vars_use_subprocess_home` in `tests/agent/test_skill_utils.py`.
It compares a forward-slash path with a Windows backslash path and also fails
on the baseline.

`python scripts/check` passed all twelve checks. The full repository suite and
other operating systems were not tested.

## Artifacts

- [Reproduction commands](REPRODUCE.md).
- [Paired process 1](results/paired-1.json).
- [Paired process 2](results/paired-2.json).
- [Medians, ranges, process ratios, and bootstrap diagnostics](results/comparison.json).
- [Separate diagnostic profile](results/profile.txt).

Raw receipts include timestamps, environment information, source and benchmark
SHA-256 hashes, batch sizes, output hashes, and every sample. Source hashes
describe file bytes; checkout line endings can change them on another machine.
