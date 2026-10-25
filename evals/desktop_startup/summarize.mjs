import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const directory = process.argv[2] || new URL('./results/', import.meta.url)
const samples = ['baseline-a', 'candidate-a', 'candidate-b', 'baseline-b', 'candidate-c', 'baseline-c'].flatMap(label => {
  const file = directory instanceof URL ? new URL(`${label}.json`, directory) : join(directory, `${label}.json`)
  return JSON.parse(readFileSync(file, 'utf8')).results
    .filter(row => !row.warmup)
    .map(row => ({ ...row, variant: label.split('-')[0] }))
})

function stats(variant, mode) {
  const values = samples.filter(row => row.variant === variant && row.mode === mode)
    .map(row => row.interactiveMs).sort((a, b) => a - b)
  const middle = Math.floor(values.length / 2)
  return {
    n: values.length,
    medianMs: values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2,
    minMs: values[0], maxMs: values.at(-1)
  }
}

console.log(JSON.stringify(['cold-gateway', 'warm-gateway'].map(mode => {
  const before = stats('baseline', mode)
  const after = stats('candidate', mode)
  return { mode, before, after, savedMs: before.medianMs - after.medianMs,
    reductionPercent: 100 * (1 - after.medianMs / before.medianMs) }
}), null, 2))
