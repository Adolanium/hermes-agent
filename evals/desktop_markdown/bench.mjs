// Run from the repository root with TSX_TSCONFIG_PATH=apps/desktop/tsconfig.json
// and `node --import tsx evals/desktop_markdown/bench.mjs --output result.json`.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'
import { JSDOM } from 'jsdom'

import { cases } from './fixtures.mjs'

const { values } = parseArgs({
  options: {
    baseline: { type: 'string' },
    candidate: { type: 'string' },
    output: { type: 'string' },
    cases: { type: 'string' },
    samples: { type: 'string', default: '9' }
  }
})
const sampleCount = Number(values.samples)
assert(Number.isInteger(sampleCount) && sampleCount > 0)
assert(values.output, '--output is required')

// The production module imports renderer stores. No rendered UI or DOM work is timed.
const { window } = new JSDOM('', { url: 'http://localhost' })
Object.assign(globalThis, { window, document: window.document, localStorage: window.localStorage })
const source = resolve(values.candidate || 'apps/desktop/src/lib/markdown-preprocess.ts')
const paths = values.baseline ? { baseline: resolve(values.baseline), candidate: source } : { baseline: source }
const modules = {}
for (const [label, path] of Object.entries(paths)) modules[label] = await import(pathToFileURL(path).href)
const hash = text => createHash('sha256').update(text).digest('hex')
const report = {
  node: process.version,
  platform: `${process.platform} ${os.release()} ${os.arch()}`,
  cpu: os.cpus()[0].model,
  samples: sampleCount,
  warmupCalls: 30,
  sources: Object.fromEntries(Object.entries(paths).map(([label, path]) => [label, hash(readFileSync(path))])),
  results: []
}
const selected = values.cases ? cases.filter(fixture => values.cases.split(',').includes(fixture.name)) : cases
assert(selected.length > 0, 'No matching cases')
let checksum = 0
for (const functionName of ['preprocessMarkdown', 'normalizeFilePreviewMath']) {
  for (const fixture of selected) {
    const functions = Object.entries(modules).map(([label, module]) => [label, module[functionName]])
    const expected = functions[0][1](fixture.text)
    const samples = Object.fromEntries(functions.map(([label]) => [label, []]))
    for (const [, fn] of functions) {
      assert.equal(fn(fixture.text), expected, `${functionName}: ${fixture.name}`)
      for (let i = 0; i < report.warmupCalls; i++) checksum += fn(fixture.text).length
    }
    for (let sample = 0; sample < sampleCount; sample++) {
      // AB/BA pairs counterbalance order within each process; every batch has fixed work.
      const ordered = sample % 2 ? [...functions].reverse() : functions
      for (const [label, fn] of ordered) {
        const start = performance.now()
        for (let i = 0; i < fixture.iterations; i++) checksum += fn(fixture.text).length
        samples[label].push((performance.now() - start) / fixture.iterations)
      }
    }
    const result = {
      function: functionName,
      case: fixture.name,
      chars: fixture.text.length,
      inputSha256: hash(fixture.text),
      outputSha256: hash(expected),
      iterations: fixture.iterations,
      millisecondsPerCall: samples
    }
    report.results.push(result)
    console.log(JSON.stringify(result))
  }
}
report.checksum = checksum
writeFileSync(values.output, `${JSON.stringify(report, null, 2)}\n`)
window.close()
