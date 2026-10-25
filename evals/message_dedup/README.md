# Message deduplication eviction performance

`MessageDeduplicator.is_duplicate()` enforces a capacity bound after removing
expired IDs. When the cache remains full, the original implementation sorts
every retained entry and builds another dictionary to remove the oldest entry.
This happens on each new ID during a burst above capacity.

The change uses `min()` when exactly one entry must be evicted. It selects the
oldest timestamp and preserves the existing first-in tie behavior. Larger
overflows after reconnect handoff still use the original sort. TTL checks,
duplicate handling, expiry pruning, and the public methods remain unchanged.
Overflow maintenance lives in `_prune()` to keep the common insertion path small.
The optimization adds no cache or persistent state. The remaining expiry scan
means an insertion into a saturated cache still takes linear work.

## Sources and environment

- Baseline: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`.
- Final implementation: `635e00822cec3def2c431869365869cb542fd670`.
- Benchmark and tests: `fbe0eccafa3684c31348c6dc2afaacb0acc14e59`.
- Independent branch from local `main`, without the earlier performance changes.
- Host: Windows amd64, Intel Core i7-10700K, CPython 3.14.9.
- Collection date: 2026-10-25 UTC.
- Environment: PM-managed Python with development and test groups and the `sms`
  extra, which supplies pinned `aiohttp` for Mattermost tests.

## Baseline and diagnosis

Initial [screening](exploration/screen-baseline.json) measured 690 ms for 4,000
unique IDs at the default capacity of 2,000. The five samples ranged from 649 ms
to 741 ms. A separate [profile](exploration/baseline-profile.txt)
recorded 2,000 sorts, 4,002,000 Python key-function calls, and 945 ms inside sorting
out of 1,457 ms under instrumentation. Clock calls accounted for about 2 ms.

This pointed to selection of the oldest entry as the first useful change.
The prototype replaced only single-entry sorting, leaving expiry pruning intact.
The first paired comparison reproduced the eviction gain but measured the bulk
handoff control 2.1% slower overall. Both process medians were slower, so the
candidate needed closer inspection.

On the measured Python build, extending `is_duplicate()` introduced an
`EXTENDED_ARG` instruction on the ordinary insertion path. Moving overflow
maintenance to `_prune()` removes that extra instruction. This was a plausible
source of overhead, not proof that it explained the entire control difference.
The unchanged benchmark then compared the final implementation with the original
baseline in two new processes. The [first comparison](exploration/comparison.json)
and both original receipts remain available in `exploration/`; they are not
pooled with the final implementation's samples.

The capacity bound is intentional. Commit `cebf95854bf5ee577930a7566a1dc07968821d72`
added it because TTL pruning alone lets the cache grow under sustained traffic.
This change preserves that bound and selects the same retained IDs.

## Measurement method

[benchmark.py](benchmark.py) imports the current helper module and loads the
baseline module from Git. Both run in the same process with the same dependencies.
`HERMES_HOME` and `HERMES_RUNTIME_DIR` point to temporary directories. The benchmark
uses synthetic IDs and makes no network calls or adapter connections.

Every timed invocation creates a fresh cache. The below-capacity case inserts
100 IDs into a 2,000-entry cache. The duplicate-hit case inserts 2,000 IDs and
replays them. Fresh-ID bursts insert 2,000 or 4,000 IDs into 1,000- or 2,000-entry
caches, respectively. A small-capacity case inserts 200 IDs into a ten-entry cache.
These cases use the real clock and the default 300-second TTL.

Controlled-clock cases insert 4,000 IDs into a 2,000-entry cache. The tied case
holds time at 100 seconds. The rollback case advances time every 32 IDs and
moves it back 20 seconds on every 64th ID. The expiry control advances one second
per ID with a 1,000-second TTL, allowing expiry pruning to clear space. The handoff
control fills a predecessor with 4,000 IDs at one timestamp, absorbs them into a
2,000-entry replacement, and inserts one more ID. This exercises bulk eviction.

Construction, insertion, replay, simulated-clock updates where applicable, and
three membership probes are included in each timed invocation. Input generation,
imports, hashing, calibration, and differential verification are excluded.

Two untimed calls verify repeatability. `timeit.autorange()` independently
calibrates each version to at least 200 ms per batch. Seven rounds alternate
baseline/optimized and optimized/baseline order. Samples are elapsed batch times
divided by the recorded invocation count, in milliseconds. `timeit` disables
garbage collection during each batch.

Two fresh processes repeat all nine workloads. Tests, checks, and dependency
builds do not overlap collection. Each version contributes fourteen batch means
per workload. Results use the median of the pooled samples. Speedup is
`baseline / optimized`; values below 1 mean a measured slowdown. Per-process
ratios use each process's own medians.

## Results

| Workload | Baseline ms | Optimized ms | Speedup | Process 1 / process 2 |
| --- | ---: | ---: | ---: | ---: |
| `below_capacity_100` | 0.0277 | 0.0288 | 0.961x | 0.975x / 0.949x |
| `duplicate_hits_2000` | 1.0450 | 1.0231 | 1.021x | 1.033x / 0.985x |
| `fresh_2000_cap1000` | 183.8187 | 100.3474 | 1.832x | 1.930x / 1.740x |
| `fresh_4000_cap2000` | 713.6077 | 391.0927 | 1.825x | 1.668x / 1.839x |
| `fresh_200_cap10` | 0.6233 | 0.4149 | 1.502x | 1.663x / 1.634x |
| `tied_4000_cap2000` | 697.3613 | 381.0861 | 1.830x | 1.965x / 1.757x |
| `rollback_4000_cap2000` | 700.4277 | 366.6757 | 1.910x | 1.925x / 1.889x |
| `expiry_4000_cap2000` | 1.3016 | 1.2737 | 1.022x | 0.985x / 1.007x |
| `handoff_4000_cap2000` | 2.0189 | 2.0548 | 0.983x | 0.914x / 1.021x |

The targeted eviction gains repeat in both processes. The default-capacity
4,000-ID burst takes 45.2% less time in the pooled samples. The 1,000-entry
case takes 45.4% less time, and tied and backward timestamps preserve the gain.

Below-capacity insertions and bulk handoff have pooled times 4.0% and 1.8%
higher. Those are measured slowdowns, not wins. Duplicate hits and expiry
are about 2.1% faster, but their per-process directions reverse. All four
control intervals include 1; no improvement is claimed for those paths.

[analyze.py](analyze.py) resamples paired batch means within each process
5,000 times, with replacement and seed 20261025 per workload. Each replicate
takes the ratio of pooled medians. The saved interval uses the 2.5th and
97.5th percentiles. The default-capacity burst interval is 1.65-2.00x.
Time correlation and only two processes limit inference; these diagnostics
do not establish equivalence. Pooled ratios need not fall between the
per-process ratios because medians do not combine linearly.

All nine output hashes match across both versions and both processes.

### Longer control confirmation

The small control differences warranted a separate check before keeping the
change. [confirm_controls.py](confirm_controls.py) reuses the same workload
functions, adds a second unchanged baseline module, and uses longer batches.
The three versions rotate through all execution positions over nine rounds.
Two fresh processes provide eighteen samples per version and workload.
Batches contain 40,000 below-capacity invocations or 500 handoffs, about one
second each. Every version receives one full untimed batch before collection.

| Workload | Baseline ms | Unchanged copy ms | Optimized ms |
| --- | ---: | ---: | ---: |
| `below_capacity_100` | 0.026466 | 0.026246 | 0.025865 |
| `handoff_4000_cap2000` | 1.869155 | 1.854788 | 1.864423 |

The longer check does not reproduce the slowdowns. Optimized below-capacity
insertions take 2.3% less time overall, with speedup ratios of 1.015x and 1.081x
in the two processes. Handoff takes 0.25% less time overall, with ratios of
0.997x and 1.020x. The handoff interval is 0.97-1.05x and includes parity.

The unchanged copy also differs from its identical baseline: its per-process
ratios range from 0.989x to 1.036x. That variation cautions against treating small
point differences as code effects. These results support retaining the large,
repeatable eviction gain; they do not establish equivalence or rule out small
regressions on other workloads. No control-path improvement is claimed.

## Behavior verification

The same eight-file selection passed **110 tests with no failures** before and
after the change. Two tests are new; 108 already existed. The new tests exercise
capacity eviction with equal timestamps, a backward clock adjustment, duplicate
hits that must not refresh timestamps, and reconnect handoff followed by eviction.
Existing coverage includes expiry, cancellation, platform replay windows,
adapter reconnects, profile isolation, and Discord and Mattermost delivery.

The benchmark also runs fifteen seeded differential traces of 300 operations
each. It compares public return values and membership of both caches after every
step. Operations include insertion, replay, lookup, release, clearing, and
handoff, with forward and backward time changes. Capacities include -1, 0, 1, 3,
and 20 to check that the original edge behavior is preserved. TTLs include zero,
five seconds, and infinity. All 4,500 steps match the baseline.

The initial test environment lacked optional `aiohttp`, causing ten Mattermost
failures. A fresh PM environment with the declared extra resolved all ten before
the production edit. The final test selection passes on both source versions.

`python scripts/check` passed all twelve checks. The full repository suite and
other operating systems were not tested.

## Limits and artifacts

These workloads measure the local synchronous cache helper. The improvement
applies when fresh entries fill the cache beyond capacity. It is not a claim
about model latency, network delivery, or complete gateway throughput. Cache
creation and initial filling are included, so the burst timings are not individual
message latencies. No CPU affinity or frequency controls were imposed.

- [Reproduction commands](REPRODUCE.md).
- [Paired process 1](results/paired-1.json).
- [Paired process 2](results/paired-2.json).
- [Medians, ranges, process ratios, and bootstrap diagnostics](results/comparison.json).
- [Longer control process 1](results/controls-1.json),
  [process 2](results/controls-2.json), and
  [both control comparisons](results/control-comparison.json).
- [First candidate's process 1](exploration/paired-1.json) and
  [process 2](exploration/paired-2.json).
- [Original screening source](exploration/screen_gateway.py.txt), archived as text.

Raw receipts include timestamps, environment information, source and benchmark
SHA-256 hashes, batch sizes, output hashes, differential-verification results, and
every timing sample. Source hashes describe file bytes; checkout line endings
can change them on another machine.
