# Desktop startup: skip an unused update-receipt lookup

This change reduced launch-to-editable-chat time on a Windows source installation.
`_receipt_reports_stale_runtime()` now checks whether a receipt can contain relevant
runtime evidence before refreshing live checkout provenance. An absent receipt or a
completed receipt without a post-restart fleet already returned `False`. It now does
so without spawning git commands first. Receipts with a fleet and unfinished receipts
still use the existing comparison. Independent host restart obligations are unchanged.

## Results

Lower elapsed time is better. Each cell summarizes nine measured launches, excluding
one cold and one warm preparation launch per batch.

| Launch condition | Before median | After median | Time saved | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Gateway stopped, initialized profile | 10,840.44 ms | 10,178.68 ms | 661.76 ms | 6.10% |
| Gateway already running | 4,542.67 ms | 4,321.93 ms | 220.74 ms | 4.86% |

Cold ranges were 10,558.57–11,687.27 ms before and 10,095.40–12,085.41 ms after.
Warm ranges were 4,459.06–5,061.27 ms before and 4,226.09–4,612.19 ms after.
All three batch comparisons improved at the median. Individual launches varied,
including a slower candidate cold-launch outlier. This is a modest median startup
improvement, not a claim that every individual launch becomes faster.

These results apply to an unstamped source backend with no update receipt, an empty
session history, and a configured mock provider. Packaged backends that read a version
stamp avoid most git work already and may save much less. Actual pending-update checks,
model response speed, scrolling, and other Desktop interactions were not optimized.

## Measurement method

- Base: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b`, local `main`.
- Order: baseline A, candidate A, candidate B, baseline B, candidate C, baseline C. Only
  `hermes_cli/update_cmd_fleet.py` changed between variants. Each raw file records its SHA-256.
- One fresh sandbox per batch. A discarded cold/warm pair initializes the home, Desktop
  preferences, and bytecode. Three measured cold/warm pairs then reuse that sandbox.
- Cold means the canonical gateway was stopped between pairs. It does not mean an OS
  reboot, a cleared filesystem cache, or a fresh installation.
- Start: `performance.now()` immediately before Playwright's `_electron.launch()`.
- End: the real composer passes normal click hit-testing, accepts a unique draft, and
  contains that text. This waits through the connecting overlay without forcing clicks.
- The intermediate window and gateway-connected timestamps are diagnostic only. A
  painted window or an open socket alone does not satisfy the endpoint.
- The same production renderer, native bundle, window dimensions, mock provider, and
  launch flags were used throughout. No builds, test suites, profiles, or recordings
  ran concurrently with measured batches. Each launch also asserts no renderer errors.
- Existing `e2e/fixtures.ts` provides credential stripping, separate Electron user data,
  and an isolated Hermes home. Windows user-profile paths and the runtime directory
  are isolated too. The real Python gateway handles startup. No model turn is submitted.
- Closing Desktop disconnects its viewer. The benchmark stops only its own gateway
  with `hermes gateway stop`; it never uses `--all`.
- Summary: pooled medians and observed ranges, no tail-percentile or cross-machine claim.

The first four batches gave cold medians of 10,801.77 and 10,161.76 ms and warm
medians of 4,535.84 and 4,278.47 ms. A final run of the saved benchmark showed wider
variation, so another baseline control was added. Both C batches are retained in the
headline numbers, including the 12,085.41 ms candidate outlier. Their own cold medians
were 11,456.91 ms before and 10,892.55 ms after. Their warm medians were 4,605.84 ms
before and 4,425.75 ms after. The C files retain the original `verification-*` run labels.

The initial exploratory launch included fresh-home setup and took 23 seconds. Subsequent
fresh-home launches took 13–14 seconds. Those observations prompted the initialization
control above and are **not** used as the before number.

The separate [cProfile capture](results/profile-before.txt) of a warm
`python -m cProfile -o ensure.prof -m hermes_cli.main gateway ensure --json` attributed
289 ms to `_receipt_reports_stale_runtime()` and its live checkout refresh.
`get_version_info()` performed two full git provenance resolutions in that invocation.
The optimization removes the redundant receipt-driven resolution in this scenario.
Both the Desktop launcher and a newly started gateway run the CLI startup path.
The profiler's elapsed times are attribution evidence, not benchmark samples.

## Environment

Measured 2026-10-25 on Windows 11 Pro, build 26200, Intel Core i7-10700K,
8 cores / 16 logical processors, approximately 32 GiB RAM.

| Component | Actual version |
| --- | --- |
| PM Python | 3.14.9 |
| Node | 24.22.1 |
| Electron | 40.10.2 |
| Playwright | 1.62.1 |
| Vite | 8.2.0 |

Dependencies were reused without mutation. Vite was 8.2.0 rather than the manifest's
8.2.4. Both variants used those same dependencies. The existing worktree-local
`@simple-git/argv-parser` override was 2.0.1. No lockfile changed.

The renderer was minified with `VITE_PERF_PROBE=1`; Electron used the development
main bundle against the production renderer. This is not a packaged-installer benchmark.
Window size was 1220 × 800 with zoom level zero. Background timer throttling, renderer
backgrounding, occluded-window backgrounding, and native window occlusion were disabled
identically in both variants.

Bundle SHA-256 values:

- `electron-main.mjs`: `c01a1e6cabbf69d63d0ff1cddfeee9a986e7b8a298954ef26a1b5cbe355432bb`
- Renderer entry `index-Dpm4WGwr.js`: `b6f5cc0b8ad19cc5498a4b9127c92ca25321135092b51f1e96515619525107b1`

## Reproduce

Use a dedicated clean worktree of this branch and the repository's PM development
environment. Set `HERMES_PYTHON` to that environment's interpreter. Install JavaScript
dependencies through the normal repository workflow. From the repository root, build
the renderer once and then the native bundle, since Vite clears `dist`:

```powershell
$env:VITE_PERF_PROBE = '1'
Push-Location apps/desktop
& ../../node_modules/.bin/vite.cmd build
Pop-Location
node apps/desktop/scripts/bundle-electron-main.mjs --dev
```

For each batch, set `BENCH_LABEL` and run the same benchmark:

```powershell
$env:BENCH_LABEL = 'baseline-a'
node node_modules/@playwright/test/cli.js test --config evals/desktop_startup/playwright.config.mts
```

In the dedicated worktree, use `git restore --source=4ea8d23cc9f527332ccb1d55359b27741b6ea51b -- hermes_cli/update_cmd_fleet.py`
for baseline batches and `git restore --source=HEAD -- hermes_cli/update_cmd_fleet.py`
for candidate batches. Run labels in the order `baseline-a`, `candidate-a`,
`candidate-b`, `baseline-b`, `candidate-c`, `baseline-c`, then restore the candidate.
Keep the Desktop build fixed.
Do not use these restore commands in a worktree containing other edits to that file.

Outputs default to `.cache/desktop-startup`; `BENCH_OUTPUT` changes that directory.
The benchmark retains its isolated sandbox for log inspection and records the location.
It requires no running Desktop instance or real provider credentials.

```powershell
node evals/desktop_startup/summarize.mjs .cache/desktop-startup
```

Run the summarizer without arguments to regenerate the committed
[summary](results/summary.json) from the six [raw sample files](results/).
The committed benchmark uses the same timed loop as the scratch measurement script;
only its output location, interpreter selection, and final cleanup handling were generalized.

## Verification

The two added test functions produce four parameterized cases. On the base, the two
no-evidence cases failed because they consulted the checkout; the two stale-runtime
cases passed. All four pass after the change.

See [verification.txt](results/verification.txt) for the exact test selection and results,
including existing Windows shell failures reproduced on the unchanged base.
