import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: 'benchmark.spec.mjs',
  timeout: 300_000,
  workers: 1,
  reporter: 'list',
  outputDir: '../../.cache/desktop-startup/playwright'
})
