# CJK token-estimation measurements

The run-based estimator reduces the cost of counting contiguous CJK text while
preserving the existing token totals. On the recorded workloads, Chinese and
Japanese estimation became about 28 times faster, and the compression budget
walk became about 22 times faster. These are local CPU timings, not measurements
of overall agent response latency.

## Source and environment

- Measurement date: 2026-10-25.
- Baseline: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`.
- Optimized implementation and benchmark: `29c3c2edf16eee907786437dfcd004a35da71f68`.
- Host: Windows, x86-64.
- Interpreter: `3.14.9 (main, Oct 21 2026, 17:48:58) [MSC v.1944 64 bit (AMD64)]`.
- Environment: a fresh PM environment built with
  `python -m pm.build_env --source . --out .venv --group dev --group test`.
- Benchmark: [`evals/benchmark_token_estimation.py`](../benchmark_token_estimation.py).
- Benchmark SHA-256 at the optimized commit:
  `57361109a035aa7073a0c11a133afc37d8c1c636c863fd9585675c4733d80f68`.
- `uv.lock` SHA-256 at that commit:
  `bad16d76da35fa9433181ac77089b8638f1390c36054336cf4a8bf04a2f4983b`.

Both versions used the same interpreter, dependencies, benchmark, and checkout.
The original runner replaced only `agent/model_metadata.py` between runs and
restored the optimized file afterward. A source comment was added before the
optimized commit; the executable code measured here is the code in that commit.

The CPU model, power settings, and exact Windows build were not recorded. The
experiment did not pin CPU affinity or frequency. The final benchmark runs were
sequential, with no test or lint run launched alongside them. Other host activity
was not controlled.

## Workloads

The benchmark constructs all inputs locally. It does not call a provider or read
user conversations. Each process gets a temporary `HERMES_HOME` and
`HERMES_RUNTIME_DIR`.

The nine large-text cases repeat a fixed string and truncate it to **262,144
Unicode characters**, not bytes. The strings are defined in the benchmark source.
The cases cover ASCII, Chinese, Japanese, Korean with spaces, mixed English and
CJK, Arabic, accented Latin, sparse CJK, and alternating `字a`.

The short case is exactly `Hello 世界!`. The compression case builds 64 tool
messages. Message `i` contains `Output {i}: ` followed by 256 copies of the Chinese
fixture sentence. It calls the real
`agent.context_compressor._estimate_msg_budget_tokens` for each message and sums
the results. This measures the budget walk, not summary generation or an entire
compression operation.

## Timing and aggregation

Each invocation starts a fresh Python process. Within that process, cases run in
the benchmark's fixed order. Imports and fixture construction finish before the
timer starts. Each case gets one untimed warmup call and an untimed check after
measurement that its token total has not changed.

`timeit.repeat` records seven batches per case. The batch size is fixed per
workload, identically for baseline and optimized code. Each stored `samples_ms`
value is `batch_elapsed_seconds * 1000 / calls_per_sample`. It is an average time
per invocation within that batch, not a single-call latency sample. `timeit` uses
its default timer and disables cyclic garbage collection during each batch.

Four processes ran in this order:

1. [Baseline, first run](results/token-before-1.json).
2. [Optimized, first run](results/token-after-1.json).
3. [Optimized, second run](results/token-after-2.json).
4. [Baseline, second run](results/token-before-2.json).

This order reduces sensitivity to gradual host drift. There are 14 samples per
version per workload, or 308 samples in total. No samples were discarded.
The reported time is the median of the 14 pooled samples, not the median of the
two run medians. Speedup is `baseline_median / optimized_median`.

The four receipts retain every sample, per-run median, batch size, token total,
and interpreter version. Their JSON values and sample order are unchanged;
text line endings are normalized to LF. The original
[aggregate comparison](results/token-comparison.json) is also preserved. Its
medians were recomputed from the raw receipts before this report was committed.
Token totals match across all four runs for all 11 workloads.

## Results

Times are milliseconds per invocation. Each compression invocation covers all
64 messages. Values in this table are rounded; the JSON retains full precision.

| Workload | Calls per batch | Before, ms | After, ms | Speedup |
| --- | ---: | ---: | ---: | ---: |
| ASCII | 1,000,000 | 0.000144834 | 0.000146199 | 0.991x |
| Chinese | 10 | 25.751440 | 0.905565 | 28.44x |
| Japanese | 10 | 25.446980 | 0.907330 | 28.05x |
| Korean | 10 | 21.664725 | 8.469820 | 2.56x |
| English and CJK | 100 | 3.731398 | 1.897261 | 1.97x |
| Arabic | 100 | 1.282718 | 1.291520 | 0.993x |
| Accented Latin | 100 | 1.212313 | 1.217715 | 0.996x |
| Sparse CJK | 100 | 1.273471 | 1.275445 | 0.998x |
| Alternating CJK and ASCII | 10 | 17.474215 | 16.185105 | 1.08x |
| Short mixed text | 100,000 | 0.000740053 | 0.000643341 | 1.15x |
| Compression budget, 64 messages | 10 | 24.483295 | 1.105130 | 22.15x |

ASCII, Arabic, accented Latin, and sparse CJK medians increased by less than 1%.
Their sample ranges overlap between versions. These results show no clear
regression in those controls, but they do not establish a statistical equivalence
bound. The largest gains apply to long dense runs. Short or alternating text has
smaller gains.

## Bottleneck and rejected alternatives

An initial profiler run attributed almost all of the dense-CJK estimation cost
to regex substitution. The baseline removes one dense character per match. The
optimized code matches whole runs, then joins the remaining text. The character
class, ASCII fast path, sparse UTF-8 byte accounting, and rounding are unchanged.

Two exploratory alternatives were rejected before the final measurement series:

- A character class followed by `+` sped up dense CJK but slowed non-CJK scans.
  The retained pattern starts with an unquantified character class so regex
  search can skip directly to candidate characters.
- Run-based substitution slowed alternating CJK and ASCII. Splitting and joining
  avoids the empty replacement fragments and removed that slowdown in the final
  measurements.

These exploratory probes guided the change. Their complete raw timings were not
archived in this result set, so they are not part of the reported comparison.

## Behavior verification

The original targeted run passed 451 tests across seven files. Six cases were
added in [`test_token_estimation_runs.py`](../../tests/agent/test_token_estimation_runs.py),
across two test functions. The other 445 tests already existed. This was not the
full repository test suite.

The new cases cover long dense runs, mixed Unicode including an emoji and a lone
surrogate, alternating characters, sparse CJK, ASCII, and character-class range
boundaries. They also passed on the baseline because they protect existing output
semantics. The benchmark supplies the performance comparison.

The canonical `python scripts/check` command passed all 12 checks. Commands for
repeating the measurements, recomputing the aggregates, and running the targeted
tests are in [Reproduce the measurements](reproduce.md).

## Scope of the evidence

These results describe repeated synthetic inputs on one Windows host and one
CPython version. They do not measure cold imports, provider latency, memory use,
multi-session throughput, or Linux and macOS performance. The benchmark does not
prove that the token estimates match a model's tokenizer; it verifies that this
optimization preserves the existing estimator's results for the measured inputs.
