# Empty timeline page performance

`get_session_timeline()` used to rebuild every eligible prompt when a cursor
returned no entries. Its first query computed previews to find the page. With
no result row to carry the total, a second query repeated the same preview work
to obtain the count.

The change left-joins the bounded page to its total within one query. An empty
page still produces a count row, whose null message id is removed before building
the response. Both reads remain in the existing snapshot. Preview rules, logical
ordering, cursor semantics, profile ownership, and the response shape stay unchanged.

## Sources and environment

- Baseline: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`.
- Implementation, benchmark, and tests: `26e258b04c784170798593f92aa71fa614674c2c`.
- Independent branch from local `main`, without the earlier performance changes.
- Host: Windows amd64, Intel Core i7-10700K, CPython 3.14.9, SQLite 3.53.1.
- Collection date: 2026-10-25 UTC.
- Environment: PM-managed `.venv` with development and test dependency groups.

## Baseline and diagnosis

The existing [session-history benchmark](../../tests/hermes_cli/benchmark_session_timeline.py)
measured about 59 ms for two timeline requests covering 600 prompts and 6,000
message rows. Profiling identified prompt projection as a substantial cost.
A focused benchmark then found 1,200 preview evaluations for an exhausted cursor,
versus 600 for a page with entries. The second count query caused the duplication.

The first separate-process comparison measured gains for empty pages but also
slower populated pages. Those results were insufficient to accept the change.
An alternating comparison against the same database reproduced the empty-page
gain while the populated-page slowdown disappeared. The final measurement uses
that paired design to reduce variation between processes. The initial
[baseline](exploration/baseline.json), [optimized run](exploration/optimized.json),
and [benchmark source](exploration/benchmark.py.txt) remain available.

## Measurement method

[benchmark.py](benchmark.py) creates synthetic data in a temporary `HERMES_HOME`
and `HERMES_RUNTIME_DIR`. It uses real `SessionDB` instances and the real HTTP
router through FastAPI's `TestClient`. It runs no tools, providers, or external
services, and never opens a live user database.

Indexed and legacy sessions each contain 600 user prompts and 5,400 assistant
and tool rows. Tool calls carry 4,096-character arguments and tool results carry
800 repeated output lines. Legacy rows have null display identity and order metadata
to exercise the read-only fallback. Other cases have 600 synthetic notifications
or no messages. All message timestamps are fixed.

Each process loads the baseline module from Git and uses the current module for
the optimized function. Both versions share the same database and unchanged
dependencies. The direct cases reuse one read-only handle; HTTP requests open
their usual per-request handle. The selected function is changed outside the
timer and restored after each case.

Two untimed calls check repeatability and count preview evaluations. Counting
instrumentation is removed before timing. `timeit.autorange()` calibrates each
version independently to at least 200 ms per batch. Seven rounds alternate
baseline/optimized and optimized/baseline order. Each sample is elapsed batch
time divided by the recorded call count, in milliseconds. `timeit` disables
garbage collection during the timed batch. Imports, fixture setup, hashing,
calibration, and instrumentation are excluded from the saved timing samples.

Two fresh processes repeat all nine cases. No test or lint jobs overlap those
runs. Each version contributes 14 batch means per case. Results below use their
pooled median and `baseline / optimized` for speedup. Ratios below 1 mean a
measured slowdown. Each process's ratio and all raw samples are retained.

## Results

| Case | Baseline ms | Optimized ms | Speedup | Process 1 / process 2 |
| --- | ---: | ---: | ---: | ---: |
| `db_indexed_after_0` | 20.78745 | 20.99365 | 0.990x | 0.999x / 0.961x |
| `db_indexed_after_5000` | 22.14031 | 21.65749 | 1.022x | 1.019x / 1.305x |
| `db_indexed_after_6000` | 42.56051 | 21.13772 | 2.013x | 1.861x / 1.963x |
| `db_legacy_after_0` | 30.45943 | 31.43793 | 0.969x | 0.990x / 1.014x |
| `db_legacy_after_12000` | 63.65149 | 34.01707 | 1.871x | 1.923x / 1.864x |
| `db_synthetic_after_0` | 13.88904 | 6.92494 | 2.006x | 2.039x / 1.921x |
| `db_empty_after_0` | 0.37979 | 0.28482 | 1.333x | 1.323x / 1.398x |
| `http_indexed_after_0` | 39.68904 | 38.69233 | 1.026x | 1.033x / 1.033x |
| `http_indexed_after_6000` | 46.11599 | 30.53248 | 1.510x | 1.591x / 1.465x |

The targeted empty-page gains repeat in both processes. The indexed exhausted
cursor improves by 1.86x and 1.96x; the legacy exhausted cursor improves by 1.92x
and 1.86x. The real HTTP endpoint improves by 1.59x and 1.47x. Its pooled time
falls from 46.116 ms to 30.532 ms, about 34% less time.

Normal-page controls are mixed. Their pooled first-page times are 1.0% higher
for the indexed direct read and 3.2% higher for the legacy direct read, while
the HTTP first-page time is 2.5% lower. The legacy per-process direction reverses.
These small differences sit within much wider sample variation, so no normal-page
speedup is claimed and smaller regressions cannot be ruled out by these runs.

[analyze.py](analyze.py) also resamples paired baseline/optimized batch means
within each process, with replacement, 5,000 times. Each case uses seed 20261025.
Each replicate computes the ratio of pooled medians; the saved interval contains
the 2.5th and 97.5th percentiles. Every normal-page interval includes 1. The
targeted indexed and legacy exhausted-cursor intervals are 1.78-2.20x and
1.76-2.00x, and the HTTP exhausted-cursor interval is 1.46-1.60x.
These are diagnostics of the stored batch means. Time correlation and only two
processes limit inference; the intervals do not establish equivalence.

All nine output hashes match across versions and processes. Empty populated
timelines reduce preview evaluations from 1,200 to 600. Pages with entries stay
at 600 evaluations, and an empty store performs none. The new query removes work
without caching data between requests.

These are warm local reads on one host. The HTTP measurements include the real
route and database opening, but exclude browser rendering and network latency.
No CPU affinity or frequency controls were imposed. The samples are batch means,
not a distribution of individual request latencies. Other hosts, SQLite builds,
and transcript sizes can produce different timings.

## Behavior checks

The canonical runner passed **32 tests with no failures** against both source
versions. Thirty cases already existed; two new parameterized cases check indexed
and legacy stores. They verify that empty pages retain the correct total, omit
the SQL count placeholder, and show newly appended prompts on a subsequent read.
Existing coverage checks compaction, cursor stability, visibility, profile
ownership, bounded transcript jumps, and read-only SQL access.

`python scripts/check` passed all 12 checks. The full repository suite and other
operating systems were not tested.

## Artifacts

- [Reproduction commands](REPRODUCE.md).
- [Paired process 1](results/paired-1.json).
- [Paired process 2](results/paired-2.json).
- [Derived medians, ranges, and process ratios](results/comparison.json).

Raw receipts include Python, SQLite, host information, timestamps, source and
benchmark SHA-256 hashes, call counts, preview counts, output hashes, and every
sample. Source hashes describe working-tree bytes; checkout line endings can
change those hashes on another machine.
