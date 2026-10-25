# ASCII output-cleanup performance

This change removes redundant regex searches from `strip_ansi()` and
`strip_unicode_tags()` in [tools/ansi_strip.py](../../tools/ansi_strip.py).
ASCII text cannot contain C1 controls or Unicode plane-14 tags. ANSI cleanup
therefore needs only an ESC search for ASCII input, and tag cleanup can return
ASCII input immediately. The substitution patterns and Unicode fallback stay
the same.

The baseline showed that candidate-detection regex searches consumed milliseconds
on large clean strings. The two helpers serve tool output, including subprocess
results and MCP resources. This change targets that local processing cost.

## Source and environment

- Baseline: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`.
- Optimized code, benchmark, and two behavior tests:
  `e4023d744cbdde3245a3668a7f36b4d42a804ab1`.
- Independent branch from local `main`; no token-estimation changes included.
- Host: Windows amd64, Intel Core i7-10700K, CPython 3.14.9.
- Collection date: 2026-10-25 UTC.
- Environment: PM-managed `.venv` with development and test dependency groups.

## Method

[benchmark_output_cleanup.py](../benchmark_output_cleanup.py) runs offline with
synthetic text. Each process uses a temporary `HERMES_HOME` and
`HERMES_RUNTIME_DIR`, with secret redaction explicitly enabled for the code-output
case. It makes no provider calls, executes no commands, and starts no MCP server.

Each case has one untimed warmup call. `timeit.autorange()` chooses a batch size
whose calibration takes at least 200 ms. The benchmark then measures seven batches
of that size. Each stored sample is elapsed batch time divided by its call count,
in milliseconds. Garbage collection is disabled during each timed batch by
`timeit`. Imports, input construction, and SHA-256 hashing are outside the timer.

Four fresh processes run sequentially in baseline, optimized, optimized,
baseline order. Only `tools/ansi_strip.py` changes between versions. The benchmark,
fixtures, interpreter, and parameters stay fixed. No test or lint jobs run during
collection. Each version contributes 14 batch means per case. The table uses the
median of those 14 means and reports `baseline / optimized` as the speedup.
A ratio below 1 means the optimized measurement was slower.

The ASCII fixtures contain repeated build-output lines. Other cases cover mixed
Unicode, dense ANSI sequences, an escape after a long clean prefix, C1 controls,
orphan tags, and a valid regional-flag emoji. Name suffixes give the fixture size
or prefix size; exact input lengths are in the JSON. `display_ascii_16384` is an
unchanged `sanitize_display_text()` control.

The caller cases use the real `_render_mcp_resource_block()` function with an
embedded text resource and `_clean_output()` with 16 KiB of stdout. The stdout
fixture stays below the 50,000-byte spill threshold. These measure local cleanup,
excluding process execution, RPC transport, JSON parsing, and model latency.

## Results

These are the complete independent-process results. The slower control cases
prompted the interleaved checks below; none of the original samples were removed.

| Case | Baseline ms | Optimized ms | Speedup | Pair 1 / pair 2 |
| --- | ---: | ---: | ---: | ---: |
| `ansi_ascii_80` | 0.00056655 | 0.00010898 | 5.199x | 5.197x / 5.197x |
| `ansi_ascii_16384` | 0.06810339 | 0.00052428 | 129.898x | 130.331x / 127.278x |
| `ansi_ascii_1048576` | 4.39800100 | 0.03205080 | 137.220x | 133.075x / 137.621x |
| `ansi_unicode_16384` | 0.09831128 | 0.09718170 | 1.012x | 1.004x / 0.999x |
| `tags_ascii_80` | 0.00049046 | 0.00008485 | 5.780x | 5.629x / 6.101x |
| `tags_ascii_16384` | 0.05435957 | 0.00008386 | 648.254x | 619.693x / 651.115x |
| `tags_ascii_1048576` | 3.44849600 | 0.00008450 | 40809.155x | 40679.374x / 41877.664x |
| `tags_unicode_16384` | 0.05507355 | 0.05462682 | 1.008x | 1.003x / 1.021x |
| `ansi_colored_1048576` | 21.95584000 | 30.74321000 | 0.714x | 0.922x / 0.619x |
| `ansi_late_escape_1048576` | 16.11912500 | 11.48594500 | 1.403x | 1.399x / 1.403x |
| `ansi_c1_16384` | 0.24960225 | 0.24088380 | 1.036x | 1.040x / 1.018x |
| `tags_orphan_16384` | 0.30109660 | 0.30412685 | 0.990x | 0.994x / 0.930x |
| `tags_flag_16384` | 0.31414605 | 0.32454610 | 0.968x | 0.906x / 1.016x |
| `display_ascii_16384` | 0.05404008 | 0.05503998 | 0.982x | 0.919x / 1.002x |
| `mcp_resource_ascii_16384` | 0.05417218 | 0.00032960 | 164.356x | 164.690x / 164.106x |
| `mcp_resource_ascii_1048576` | 3.54211250 | 0.00032850 | 10782.568x | 10838.094x / 10297.636x |
| `code_output_ascii_16384` | 0.22622305 | 0.15704210 | 1.441x | 1.418x / 1.449x |

All 17 input and output hashes match across all four processes. Each raw file
records every sample, calibrated call count, source and benchmark byte hashes,
timestamp, and host metadata. The source hash describes working-tree bytes, so
checkout line endings can change that hash on another machine.

The results support faster cleanup of clean ASCII output on this host. The large
tag-filter ratios reflect returning the existing string without scanning it.
They do not measure an equivalent improvement in whole-agent latency.

## Control follow-up

The independent-process median for densely colored ANSI text was 40% slower.
One optimized process took about 38 ms per call, versus about 21-24 ms in the
other processes. Some Unicode-tag and unchanged display controls also moved.
Those measurements alone were insufficient to accept the optimization.

[verify_controls.py](verify_controls.py) loads both source versions into one
process and alternates baseline, optimized, optimized, baseline batches five
times for each of the four affected controls. It calibrates each timer to at
least 200 ms, uses the identical fixtures, and checks output equality. Four fresh
processes yield 40 batch means per version and case. This experiment holds
process conditions shared while comparing the changed functions.

The first two processes used the archived initial probe. A repository check then
required a timeout on its untimed `git show` command. The final two processes use
the checked-in probe with that timeout. No timed code or fixture changed, and
both versions of the probe and all four receipts are retained.

| Control | Baseline ms | Optimized ms | Speedup | Four process ratios |
| --- | ---: | ---: | ---: | --- |
| `ansi_colored_1048576` | 22.01306500 | 21.76001000 | 1.012x | 0.993x, 1.010x, 1.004x, 1.014x |
| `tags_orphan_16384` | 0.30332005 | 0.30373905 | 0.999x | 1.003x, 0.997x, 0.996x, 0.999x |
| `tags_flag_16384` | 0.30852145 | 0.30927415 | 0.998x | 1.001x, 1.009x, 0.993x, 0.989x |
| `display_ascii_16384` | 0.05446795 | 0.05436300 | 1.002x | 1.001x, 0.996x, 1.002x, 1.020x |

The large ANSI slowdown did not reproduce in any interleaved process. Each
control's difference changed direction across the four processes. Every
per-process control ratio was within 2.1% of parity. The pooled orphan-tag result
is still 0.14% slower, and valid flag tags are 0.24% slower. These measurements
do not establish an improvement for those controls.

The retained change has repeatable gains on the intended ASCII cases, identical
outputs, and no repeatable control slowdown distinguishable from the variation
in these checks. The independent-process adverse samples remain part of the
report. Sub-percent neutrality and results on other hosts remain unestablished.

## Verification

The canonical runner tested eight files against both source versions. Each run
reported **314 passed, 2 failed, and 15 skipped**. Two of the passes are new tests;
312 are existing tests. The new tests preserve long ASCII prefixes, remove late
ANSI and C1 controls, and preserve valid emoji tags while removing orphan tags
through the MCP resource renderer.

Both failures reproduce unchanged on the baseline on this Windows host:

- `test_code_execution.py::TestRpcTokenAuthorization::test_missing_token_rejected`
  fails because this Python build has no `socket.AF_UNIX`.
- `test_approval.py::TestDetectDangerousRm::test_symlinked_temp_dir_only_exempts_canonical_target`
  fails its expected dangerous-command classification for a symlinked temporary path.

`python scripts/check` passed all 12 checks. The full repository test suite and
other operating systems were not tested. Timing runs use one host without CPU
affinity or frequency controls; the saved ranges and process pairs expose that
variation rather than establishing a formal confidence interval.

## Artifacts

- [Reproduction instructions](REPRODUCE.md).
- [Baseline process 1](results/baseline-1.json).
- [Optimized process 1](results/optimized-1.json).
- [Optimized process 2](results/optimized-2.json).
- [Baseline process 2](results/baseline-2.json).
- [Derived comparison, ranges, and process-pair ratios](results/comparison.json).
- [Interleaved controls, process 1](results/controls-1.json).
- [Interleaved controls, process 2](results/controls-2.json).
- [Initial interleaved controls, process 1](results/controls-initial-1.json).
- [Initial interleaved controls, process 2](results/controls-initial-2.json).
- [Initial probe source](results/controls-initial.py.txt).
- [Derived control comparison](results/controls-comparison.json).
