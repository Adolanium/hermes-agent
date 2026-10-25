# Desktop file-preview math normalization — performance series 6

Skip math normalization for file previews whose text contains none of the supported delimiter
starters: `$`, `\`, or `[/`. Such a document needs neither math rewrites nor code-span shielding.
The change adds one conservative early return to `normalizeFilePreviewMath` (six lines).
Chat preprocessing and all shared math-normalization helpers remain unchanged.

Base: `4ea8d23cc9f527332ccb1d55359b27741b6ea51b` (`main`).
Branch: `perf/desktop-file-preview-math`. Earlier performance-series changes are not included.

## Results and scope

These are **normalization times**, not total file-open, Markdown-render, or application speedups.
Each result pools 27 batches: nine alternating AB/BA pairs in each of three fresh Node processes.
Lower milliseconds are better. The time reduction is `100 * (1 - after / before)`.

| File-preview input                     | Before, ms/call | After, ms/call | Less time |
| -------------------------------------- | --------------: | -------------: | --------: |
| 1 KiB prose                            |        0.012095 |       0.000196 |     98.4% |
| 16 KiB prose                           |        0.165880 |       0.001253 |     99.2% |
| 64 KiB prose                           |        0.663875 |       0.005095 |     99.2% |
| 512 KiB prose                          |        5.505218 |       0.048810 |     99.1% |
| 16 KiB Markdown, links and inline code |        0.338310 |       0.002333 |     99.3% |
| Unicode prose, 16,384 UTF-16 units     |        0.227036 |       0.002504 |     98.9% |

The guard intentionally falls through for currency, math, escaped dollars, and ordinary backslashes.
A dollar inside a code fence also takes the original path. The optimization does not attempt to
parse whether those characters are active delimiters.

The 512 KiB fixture approximates this base version's automatic text-preview ceiling. It was measured
separately with the same nine-pair protocol in three fresh processes; `final-large-*.json` retains
those samples. Its baseline was the same saved, unchanged module.

[summary.json](results/summary.json) includes every case and each process's ratio. The
`final-{1,2,3}.json` files retain all samples and source/input/output hashes. Controls fluctuate
around parity, including small negative results: pooled file-preview code-fence time increased
1.1%, math 0.6%, and escaped dollars 1.0%. These are not claimed wins. The unchanged chat entry point
and the identical-source A/A runs also show variation. See `aa-control.json` and
`aa-extra-controls.json`; a baseline/after ratio below 1 means that measurement was slower.

## Selection and discarded experiments

The existing production-renderer probe first measured transcript mounting and streaming in an
isolated Electron instance. A warmed 1,000-turn transcript mounted in about 136–146 ms. Cost did
not grow proportionally with history because Desktop already bounds the displayed window. CPU
profiles implicated state subscriptions, Markdown processing, and layout.

A narrower benchmark then established a baseline before any production edit. Its profile put
`normalizeDisplayMathForMarkdown`, `splitHuggingDisplayMath`,
`escapeCurrencyDollarsPreservingMath`, and `escapeCjkProseDollars` among this module's largest
self-time contributors. Ordinary text paid those costs even when no rewrite was possible.
[screening.json](results/screening.json) retains the initial Electron samples and profile self-time
aggregates. [baseline-unprofiled.json](results/baseline-unprofiled.json) is the separate pre-edit
baseline without profiling overhead.

The earlier experiments are retained, not part of the shipped code:

- V1 skipped math processing inside the shared helper. Prose improved, but math/currency controls
  repeatedly slowed slightly.
- V2 added native dollar searches. Currency improved, but the math-preview control still slowed.
- V3 also skipped the CJK rewrite for text without CJK characters. Additional CJK-heavy controls
  exposed a small slowdown.
- V4 kept two early returns and restored the original dollar loops. Function measurements improved,
  but the full renderer did not provide convincing confirmation for changing chat preprocessing.
- Final/V5 places the early return only at the file-preview entry point. It skips the whole
  normalization pass for eligible documents and leaves the chat path unchanged.

`rejected-v*.patch` files reproduce the discarded versions against the base with
`git apply --unidiff-zero <patch>`. Their raw timings,
including unfavorable samples, remain in `results/`. The CJK-control batch grew from 60 to 600 calls
for V4, V5, and A/A measurements; both sides of each comparison always used the same count.

For V4, six fresh Electron launches ran A/B/B/A/B/A, with three samples per scenario per launch.
All passed full-content and renderer-error checks, and screenshots were inspected. The complete
67,584-character stream elapsed-time median was 2,935.1 → 2,930.9 ms, essentially unchanged.
Renderer task-time medians were 899.2 → 935.7 ms (**4.1% higher**); launch medians were
899/861/910 versus 963/853/936 ms. Individual ranges overlapped (840–977 and 851–975 ms), but this
was insufficient evidence to retain the broader chat optimization. These results are explicitly
labeled `rejected-v4-electron-*`; they are not measurements of V5.

## Reproduce the function measurements

Use the project's supported dependency setup; no new dependency is required. Run from the
repository root. Keep a copy of the base module inside this checkout so its unchanged `@/` imports
resolve through the same Desktop TypeScript configuration:

```powershell
New-Item -ItemType Directory -Force .cache/desktop-markdown | Out-Null
git show 4ea8d23cc9f527332ccb1d55359b27741b6ea51b:apps/desktop/src/lib/markdown-preprocess.ts |
  Set-Content -Encoding utf8 .cache/desktop-markdown/baseline.ts
$env:TSX_TSCONFIG_PATH = 'apps/desktop/tsconfig.json'
node --import tsx evals/desktop_markdown/bench.mjs `
  --baseline .cache/desktop-markdown/baseline.ts `
  --output .cache/desktop-markdown/paired.json
node --import tsx evals/desktop_markdown/verify.mjs `
  .cache/desktop-markdown/baseline.ts .cache/desktop-markdown/verification.json
```

Repeat in three fresh processes with distinct output paths. Omit `--baseline` to measure a single
checked-out version. `--cases` accepts comma-separated fixture names; `--samples` controls repetitions.
For A/A, pass `--baseline` and `--candidate` pointing to separate copies of the base module.
Line-ending conversion can change source-byte hashes; fixture and output hashes are unaffected.

The benchmark imports the actual public functions. JSDOM supplies browser globals needed by their
renderer-store imports; no DOM work is timed. Each function warms 30 times and its output is checked
before a fixed-count timed batch. A checksum consumes every return value. Fixture construction,
imports, equality checks, and JSON output are untimed. There is no forced garbage collection,
adaptive iteration count, sample trimming, or CI timing gate. Profiling was separate from the
reported paired measurements.

`verify.mjs` compares both entry points against the base on deterministic fixtures, every prefix
of delimiter/fence/Unicode examples, and 4,000 seeded fragment combinations. Its JSON records the
input count, comparison count, seed, and digest. The new unit tests use literal expected output;
the differential check provides additional coverage, not a replacement for those assertions.

## Reproduce the discarded Electron experiment

`desktop.spec.mjs` preserves the full-renderer feedback loop used to reject V4. It uses the existing
production performance probe, real stores, and a localhost mock provider. To reproduce V4, apply
its archived patch to the base before building. The Electron main bundle uses `--dev` to avoid a
packaged-install stamp; the renderer itself is production:

```powershell
$env:VITE_PERF_PROBE = '1'
Push-Location apps/desktop
& ../../node_modules/.bin/vite.cmd build
Pop-Location
node apps/desktop/scripts/bundle-electron-main.mjs --dev
$env:HERMES_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
$env:DESKTOP_BENCH_OUTPUT = '.cache/desktop-markdown/electron'
node node_modules/@playwright/test/cli.js test `
  --config evals/desktop_markdown/playwright.config.mts
```

The spec strips inherited credentials and creates isolated Hermes, runtime, and Electron profiles.
It does not copy real user state or use paid model calls. It attaches through Playwright's existing
CDP session, then closes Electron and runs `gateway stop` for that isolated home, never `--all`.
Temporary profiles remain for diagnosis; `sandbox.json` records their paths.

After warm-up it repeats the existing 200- and 1,000-turn transcript scenarios. Its streaming check
waits for all 128 chunks (67,584 characters), checks 128 inline-code elements and 1,024 sentence
occurrences, and rejects renderer errors. A fixed delay alone could stop a slow run before it had
done the same work. Elapsed time includes driver pacing and polling. Task duration includes all
renderer tasks during the window, not just preprocessing.

Setup failures produced no completed comparison sample: an initial Windows profile lacked AppData,
a launch lacked the native main bundle after Vite cleared `dist`, and an initial DOM assertion
expected `<strong>` although this app represents bold text differently. The successful assertion
checks rendered text and inline-code counts instead.

## Verification and environment

The focused checks run from `apps/desktop`:

```powershell
& ../../node_modules/.bin/vitest.cmd run --project ui --maxWorkers 2 `
  src/lib/markdown src/lib/file-preview-math src/lib/reasoning-blocks src/lib/session-refs `
  src/components/assistant-ui/markdown-text src/app/chat/right-rail/preview-file.test.tsx
& ../../node_modules/.bin/tsc.cmd -p . --noEmit
& ../../node_modules/.bin/eslint.cmd src/lib/markdown-preprocess.ts `
  src/lib/markdown-preprocess.file-preview-prose.test.ts
```

The two added behavior tests also passed on the base: this is an output-preserving optimization,
so the timing benchmark supplies the performance evidence. Existing `MarkdownPreview` tests
exercise the actual preview component with Streamdown, KaTeX, links, code, and other content.
Repository-wide checks use `python scripts/check` with an isolated Hermes home/runtime.

Final verification: **271 tests passed** (269 existing and two added), **8,682 differential output
comparisons passed**, and renderer TypeScript checking and targeted ESLint passed.

Environment: Windows 11 (`10.0.26200`), Intel Core i7-10700K, Node 24.22.1, Electron 40.10.2,
`@assistant-ui/react-streamdown` 0.3.5, Vitest 4.1.11. Existing dependencies were reused through
worktree-local links. Vite was 8.2.0, while this checkout declares 8.2.4; both renderer variants used
the same installed dependencies. Declared `@simple-git/argv-parser` 2.0.1 was supplied in a temporary
install for the Electron build. No manifest, lockfile, or root-checkout installation changed.

These local synthetic measurements support the focused normalization change. They do not establish
universal file-open speedups or cross-platform rendering performance.
