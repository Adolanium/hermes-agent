import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'

import { cases } from './fixtures.mjs'

const [baselinePath, outputPath] = process.argv.slice(2)
assert(baselinePath && outputPath, 'Provide baseline module path and output JSON path')
const { window } = new JSDOM('', { url: 'http://localhost' })
Object.assign(globalThis, { window, document: window.document, localStorage: window.localStorage })
const baseline = await import(pathToFileURL(resolve(baselinePath)).href)
const candidate = await import(pathToFileURL(resolve('apps/desktop/src/lib/markdown-preprocess.ts')).href)
const fragments = [
  'Normal prose. ',
  '\r\n',
  '\n\n',
  '日本語の説明',
  '**bold**',
  '`$5`',
  '$500',
  'R$ 12.345',
  '$4\\in A$',
  '$x + \\$5$',
  '$$a\nb$$',
  '\\(x + 1\\)',
  '\\\\(y\\\\)',
  '\\[\nx = 2\n\\]',
  '[/inline]y[/inline]',
  '[/math]\nz = 2\n[/math]',
  '$変数（説明）$',
  '\\$escaped',
  '```python\nprint("$5")\n```',
  '~~~text\n\\(literal\\)\n~~~',
  '[Guide](https://example.com)',
  '<think>hidden</think>',
  '<custom>visible</custom>',
  '[/unknown]',
  '[/in',
  '\\',
  '$',
  '[/math]'
]
const inputs = cases.map(fixture => fixture.text)
for (const fragment of fragments) {
  // Streaming prefixes include incomplete delimiters, escapes, fences, and UTF-16 boundaries.
  for (let i = 0; i <= fragment.length; i++) inputs.push(`Before.\n\n${fragment.slice(0, i)}`)
}
let seed = 0x5eeda11
for (let i = 0; i < 4000; i++) {
  let text = ''
  for (let j = 0; j < 8; j++) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
    text += fragments[seed % fragments.length]
  }
  inputs.push(text)
}
const digest = createHash('sha256')
for (const name of ['preprocessMarkdown', 'normalizeFilePreviewMath']) {
  for (const [i, input] of inputs.entries()) {
    const expected = baseline[name](input)
    assert.equal(candidate[name](input), expected, `${name}, input ${i}: ${JSON.stringify(input)}`)
    digest.update(JSON.stringify([name, input, expected]))
  }
}
const report = {
  seed: '0x5eeda11',
  inputs: inputs.length,
  comparisons: inputs.length * 2,
  sha256: digest.digest('hex')
}
writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`)
console.log(report)
window.close()
